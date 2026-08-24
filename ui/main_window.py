"""
Ventana principal de la aplicación

Responsabilidades:
- Visualización de video en vivo con recorte de retícula para precintos
- Control de cámara PTZ
- Captura fotográfica e inferencia asíncrona mediante OcrWorker
- Gestión de configuración, estados de conexión y ciclo de vida de los hilos de trabajo
"""

import threading
from datetime import date, datetime
from difflib import SequenceMatcher

import cv2
from PySide6.QtCore import QDate, QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import (
    CANAL_RTSP_DEFAULT,
    CANAL_RTSP_MEDIO,
    VEL_FOCO,
    asegurar_carpeta_capturas,
    recorte_reticula,
)
from modulos.camera_service import CameraService
from modulos.excel_manifest import RegistroEsperado, cargar_excel
from modulos.ocr_worker import OcrWorker
from modulos.ptz_worker import PtzWorker
from modulos.settings_store import (
    load_camera_settings,
    save_camera_settings,
    settings_completos,
)
from ui.hold_button import HoldButton
from ui.settings_dialog import SettingsDialog
from ui.styles import APP_STYLESHEET
from ui.video_widget import VideoWidget


class RegistroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar registro")

        self._patente = QLineEdit()
        self._marca = QLineEdit()
        self._fecha = QDateEdit()
        self._fecha.setCalendarPopup(True)
        self._fecha.setDisplayFormat("dd-MM-yyyy")
        self._fecha.setDate(QDate.currentDate())
        self._precinto = QLineEdit()

        form = QFormLayout()
        form.addRow("Patente", self._patente)
        form.addRow("Marca", self._marca)
        form.addRow("Fecha esperada", self._fecha)
        form.addRow("Precinto esperado", self._precinto)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(botones)

    def registro(self) -> RegistroEsperado:
        return RegistroEsperado(
            patente=self._patente.text().strip().upper(),
            marca=self._marca.text().strip(),
            fecha_esperada=self._fecha.date().toPython(),
            precinto_esperado=self._precinto.text().strip().upper(),
            estado="Pendiente",
        )

    def accept(self):
        registro = self.registro()
        if not registro.patente or not registro.fecha_esperada or not registro.precinto_esperado:
            QMessageBox.warning(
                self,
                "Datos incompletos",
                "Patente, fecha esperada y precinto esperado son obligatorios.",
            )
            return
        super().accept()


class MainWindow(QMainWindow):
    _captura_alta_lista = Signal(object)
    _captura_alta_error = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SeAIScan SVTI — Precintos")
        self.resize(1280, 760)
        self.setStyleSheet(APP_STYLESHEET)

        self._cfg = load_camera_settings()
        self._canal_activo = self._cfg.canal
        self._service: CameraService | None = None
        self._rtsp_thread: threading.Thread | None = None
        self._vel_mov = 50
        self._ocr_listo = False
        self._ocr_ocupado = False
        self._captura_thread: threading.Thread | None = None
        self._manifiesto = []
        self._llenando_tabla = False

        self._ptz = PtzWorker(self)
        self._ptz.error.connect(self._on_ptz_error)
        self._ptz.start()

        self._ocr = OcrWorker(self)
        self._ocr.engine_ready.connect(self._on_ocr_listo)
        self._ocr.engine_failed.connect(self._on_ocr_fallo_motor)
        self._ocr.result.connect(self._on_ocr_resultado)
        self._ocr.failed.connect(self._on_ocr_error)
        self._ocr.start()
        self._ocr.pedir_warmup()
        self._captura_alta_lista.connect(self._procesar_captura_alta)
        self._captura_alta_error.connect(self._on_captura_alta_error)

        self._armar_ui()
        self._atajos()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_video)
        self._timer.start(33)

        QTimer.singleShot(200, self._inicio)

    def _armar_ui(self):
        self._video = VideoWidget()

        self._lbl_titulo = QLabel("SeAIScan SVTI")
        self._lbl_titulo.setObjectName("titulo")
        self._lbl_estado = QLabel("Sin conexión")
        self._lbl_estado.setObjectName("estado")
        self._lbl_canal = QLabel(self._texto_canal())
        self._lbl_ocr_motor = QLabel("Motor OCR: cargando…")

        self._btn_config = QPushButton("Configurar cámara")
        self._btn_config.clicked.connect(self._abrir_config)
        self._btn_conectar = QPushButton("Conectar")
        self._btn_conectar.setObjectName("primario")
        self._btn_conectar.clicked.connect(self._toggle_conexion)
        self._btn_modo_dia = QPushButton("Dia")
        self._btn_modo_dia.clicked.connect(lambda: self._cambiar_modo_dia_noche("dia"))
        self._btn_modo_noche = QPushButton("Noche")
        self._btn_modo_noche.clicked.connect(lambda: self._cambiar_modo_dia_noche("noche"))
        self._btn_modo_auto = QPushButton("Auto")
        self._btn_modo_auto.clicked.connect(lambda: self._cambiar_modo_dia_noche("auto"))

        caja_cam = QGroupBox("Cámara")
        lay_cam = QVBoxLayout(caja_cam)
        lay_cam.addWidget(self._lbl_estado)
        lay_cam.addWidget(self._lbl_canal)
        lay_cam.addWidget(self._btn_config)
        lay_cam.addWidget(self._btn_conectar)
        lay_modo = QHBoxLayout()
        lay_modo.addWidget(self._btn_modo_dia)
        lay_modo.addWidget(self._btn_modo_noche)
        lay_modo.addWidget(self._btn_modo_auto)
        lay_cam.addLayout(lay_modo)

        self._btn_up = HoldButton("▲")
        self._btn_down = HoldButton("▼")
        self._btn_left = HoldButton("◀")
        self._btn_right = HoldButton("▶")
        self._btn_stop = QPushButton("Detener")
        self._btn_stop.setObjectName("peligro")
        self._vincular_ptz(self._btn_up, tilt=lambda: self._vel_mov)
        self._vincular_ptz(self._btn_down, tilt=lambda: -self._vel_mov)
        self._vincular_ptz(self._btn_left, pan=lambda: -self._vel_mov)
        self._vincular_ptz(self._btn_right, pan=lambda: self._vel_mov)
        self._btn_stop.clicked.connect(self._detener_ptz)

        grid = QGridLayout()
        grid.addWidget(self._btn_up, 0, 1)
        grid.addWidget(self._btn_left, 1, 0)
        grid.addWidget(self._btn_stop, 1, 1)
        grid.addWidget(self._btn_right, 1, 2)
        grid.addWidget(self._btn_down, 2, 1)
        caja_ptz = QGroupBox("Movimiento PTZ")
        caja_ptz.setLayout(grid)

        self._btn_zoom_in = HoldButton("Zoom +")
        self._btn_zoom_out = HoldButton("Zoom −")
        self._btn_foco_cerca = HoldButton("Foco cerca")
        self._btn_foco_lejos = HoldButton("Foco lejos")
        self._vincular_ptz(self._btn_zoom_in, zoom=lambda: self._vel_mov)
        self._vincular_ptz(self._btn_zoom_out, zoom=lambda: -self._vel_mov)
        self._vincular_ptz(self._btn_foco_cerca, focus=lambda: VEL_FOCO)
        self._vincular_ptz(self._btn_foco_lejos, focus=lambda: -VEL_FOCO)

        caja_lente = QGroupBox("Zoom y foco")
        lay_lente = QGridLayout(caja_lente)
        lay_lente.addWidget(self._btn_zoom_in, 0, 0)
        lay_lente.addWidget(self._btn_zoom_out, 0, 1)
        lay_lente.addWidget(self._btn_foco_cerca, 1, 0)
        lay_lente.addWidget(self._btn_foco_lejos, 1, 1)

        self._slider_vel = QSlider(Qt.Orientation.Horizontal)
        self._slider_vel.setRange(10, 100)
        self._slider_vel.setValue(self._vel_mov)
        self._slider_vel.valueChanged.connect(self._on_vel)
        self._lbl_vel = QLabel(f"Velocidad: {self._vel_mov}")
        caja_vel = QGroupBox("Velocidad")
        lay_vel = QVBoxLayout(caja_vel)
        lay_vel.addWidget(self._lbl_vel)
        lay_vel.addWidget(self._slider_vel)

        self._btn_capturar = QPushButton("Capturar precinto")
        self._btn_capturar.setObjectName("primario")
        self._btn_capturar.setEnabled(False)
        self._btn_capturar.clicked.connect(self._capturar)

        self._lbl_ocr_estado = QLabel("Esperando captura")
        self._lbl_confianza = QLabel("Confianza OCR: —")
        self._lbl_score = QLabel("Score: —")
        self._lbl_variante = QLabel("Método: —")
        self._txt_ocr = QTextEdit()
        self._txt_ocr.setReadOnly(True)
        self._txt_ocr.setPlaceholderText("El texto del precinto aparecerá aquí.")
        self._txt_ocr.setMinimumHeight(120)

        caja_ocr = QGroupBox("Resultado OCR")
        lay_ocr = QVBoxLayout(caja_ocr)
        lay_ocr.addWidget(self._lbl_ocr_motor)
        lay_ocr.addWidget(self._btn_capturar)
        lay_ocr.addWidget(self._lbl_ocr_estado)
        lay_ocr.addWidget(self._lbl_confianza)
        lay_ocr.addWidget(self._lbl_score)
        lay_ocr.addWidget(self._lbl_variante)
        lay_ocr.addWidget(self._txt_ocr)

        ayuda = QLabel(
            "Atajos: WASD mover · I/K zoom · J/L foco · "
            "Espacio detener · P capturar · Tab cambiar resolución"
        )
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color: #A6ADC8; font-weight: 400;")

        self._btn_cargar_excel = QPushButton("Cargar Excel")
        self._btn_cargar_excel.clicked.connect(self._cargar_excel)
        self._btn_agregar_registro = QPushButton("+")
        self._btn_agregar_registro.setObjectName("primario")
        self._btn_agregar_registro.clicked.connect(self._agregar_registro)
        self._btn_eliminar_registro = QPushButton("Eliminar pendiente")
        self._btn_eliminar_registro.clicked.connect(self._eliminar_registros_pendientes)
        self._lbl_excel_estado = QLabel("Sin Excel cargado")
        self._tabla_excel = QTableWidget(0, 5)
        self._tabla_excel.setHorizontalHeaderLabels(
            ["Patente", "Marca", "Fecha esperada", "Precinto esperado", "Estado"]
        )
        self._tabla_excel.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._tabla_excel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabla_excel.verticalHeader().setVisible(False)
        self._tabla_excel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tabla_excel.setMinimumHeight(180)
        self._tabla_excel.itemChanged.connect(self._on_tabla_item_changed)

        caja_excel = QGroupBox("Manifiesto esperado")
        lay_excel = QVBoxLayout(caja_excel)
        lay_excel_botones = QHBoxLayout()
        lay_excel_botones.addWidget(self._btn_cargar_excel)
        lay_excel_botones.addWidget(self._btn_agregar_registro)
        lay_excel_botones.addWidget(self._btn_eliminar_registro)
        lay_excel.addLayout(lay_excel_botones)
        lay_excel.addWidget(self._lbl_excel_estado)
        lay_excel.addWidget(self._tabla_excel)

        lateral = QWidget()
        lateral.setFixedWidth(340)
        lay_lat = QVBoxLayout(lateral)
        lay_lat.setContentsMargins(8, 8, 12, 8)
        lay_lat.addWidget(self._lbl_titulo)
        lay_lat.addWidget(caja_cam)
        lay_lat.addWidget(caja_ptz)
        lay_lat.addWidget(caja_lente)
        lay_lat.addWidget(caja_vel)
        lay_lat.addWidget(caja_ocr, 1)
        lay_lat.addWidget(ayuda)

        scroll_lateral = QScrollArea()
        scroll_lateral.setWidgetResizable(True)
        scroll_lateral.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_lateral.setWidget(lateral)
        scroll_lateral.setFixedWidth(360)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(8, 8, 0, 8)
        panel_video = QWidget()
        lay_video = QVBoxLayout(panel_video)
        lay_video.setContentsMargins(0, 0, 0, 0)
        lay_video.addWidget(self._video, 3)
        lay_video.addWidget(caja_excel, 1)
        lay.addWidget(panel_video, 1)
        lay.addWidget(scroll_lateral)
        self.setCentralWidget(central)

    def _cargar_excel(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self,
            "Cargar Excel",
            "",
            "Archivos Excel (*.xlsx *.xlsm)",
        )
        if not rutas:
            return
        nuevos = []
        errores = []
        for ruta in rutas:
            try:
                nuevos.extend(cargar_excel(ruta))
            except Exception as exc:
                errores.append(f"{ruta}: {exc}")
        if errores:
            QMessageBox.warning(self, "Excel", "\n".join(errores[:5]))
            if not nuevos:
                return
        agregados, repetidos = self._agregar_registros(nuevos)
        self._llenar_tabla_excel()
        self._actualizar_estado_excel()
        if repetidos:
            detalle = "\n".join(repetidos[:10])
            extra = "" if len(repetidos) <= 10 else f"\n... y {len(repetidos) - 10} mas"
            QMessageBox.information(
                self,
                "Registros repetidos",
                f"Se agregaron {agregados} registros.\n"
                f"Se omitieron {len(repetidos)} repetidos:\n{detalle}{extra}",
            )

    def _agregar_registro(self):
        dlg = RegistroDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        registro = dlg.registro()
        registro.estado = self._estado_inicial(registro.fecha_esperada)
        agregados, repetidos = self._agregar_registros([registro])
        if repetidos:
            QMessageBox.warning(self, "Registro repetido", repetidos[0])
            return
        if agregados:
            self._llenar_tabla_excel()
            self._actualizar_estado_excel()

    def _agregar_registros(self, registros: list[RegistroEsperado]) -> tuple[int, list[str]]:
        existentes = {
            self._clave_registro(registro)
            for registro in self._manifiesto
            if self._clave_registro(registro)
        }
        agregados = 0
        repetidos = []
        for registro in registros:
            registro.patente = registro.patente.strip().upper()
            registro.marca = registro.marca.strip()
            registro.precinto_esperado = registro.precinto_esperado.strip().upper()
            registro.estado = self._estado_inicial(registro.fecha_esperada)
            clave = self._clave_registro(registro)
            if clave in existentes:
                repetidos.append(
                    f"{registro.patente} / {registro.precinto_esperado}"
                )
                continue
            existentes.add(clave)
            self._manifiesto.append(registro)
            agregados += 1
        return agregados, repetidos

    def _llenar_tabla_excel(self):
        self._llenando_tabla = True
        self._tabla_excel.setRowCount(len(self._manifiesto))
        for fila, registro in enumerate(self._manifiesto):
            fecha = (
                registro.fecha_esperada.strftime("%d-%m-%Y")
                if registro.fecha_esperada
                else ""
            )
            valores = [
                registro.patente,
                registro.marca,
                fecha,
                registro.precinto_esperado,
                registro.estado,
            ]
            for columna, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                item.setBackground(self._color_estado(registro.estado))
                item.setForeground(QColor("#1E1E2E"))
                flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                if registro.estado == "Pendiente" and columna != 4:
                    flags |= Qt.ItemFlag.ItemIsEditable
                item.setFlags(flags)
                self._tabla_excel.setItem(fila, columna, item)
        self._llenando_tabla = False

    def _actualizar_estado_excel(self):
        self._lbl_excel_estado.setText(f"{len(self._manifiesto)} registros cargados")

    def _clave_registro(self, registro: RegistroEsperado) -> str:
        return self._normalizar_lectura(registro.precinto_esperado)

    def _estado_inicial(self, fecha_esperada) -> str:
        if fecha_esperada and fecha_esperada < date.today():
            return "Atrasado"
        return "Pendiente"

    def _parse_fecha_tabla(self, texto: str):
        texto = texto.strip()
        for formato in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                pass
        return None

    def _on_tabla_item_changed(self, item: QTableWidgetItem):
        if self._llenando_tabla:
            return
        fila = item.row()
        columna = item.column()
        if fila < 0 or fila >= len(self._manifiesto):
            return

        registro = self._manifiesto[fila]
        if registro.estado != "Pendiente" or columna == 4:
            self._llenar_tabla_excel()
            return

        valor = item.text().strip()
        if columna in (0, 2, 3) and not valor:
            QMessageBox.warning(
                self,
                "Dato obligatorio",
                "Patente, fecha esperada y precinto esperado no pueden quedar vacios.",
            )
            self._llenar_tabla_excel()
            return

        if columna == 0:
            registro.patente = valor.upper()
        elif columna == 1:
            registro.marca = valor
        elif columna == 2:
            fecha = self._parse_fecha_tabla(valor)
            if fecha is None:
                QMessageBox.warning(
                    self,
                    "Fecha invalida",
                    "Usa una fecha como 26-08-2026 o 26/08/2026.",
                )
                self._llenar_tabla_excel()
                return
            registro.fecha_esperada = fecha
            registro.estado = self._estado_inicial(fecha)
        elif columna == 3:
            precinto = valor.upper()
            clave = self._normalizar_lectura(precinto)
            for idx, otro in enumerate(self._manifiesto):
                if idx != fila and self._clave_registro(otro) == clave:
                    QMessageBox.warning(
                        self,
                        "Registro repetido",
                        f"Ya existe un registro con el precinto {precinto}.",
                    )
                    self._llenar_tabla_excel()
                    return
            registro.precinto_esperado = precinto

        self._llenar_tabla_excel()
        self._actualizar_estado_excel()

    def _eliminar_registros_pendientes(self):
        filas = sorted(
            {idx.row() for idx in self._tabla_excel.selectedIndexes()},
            reverse=True,
        )
        if not filas:
            QMessageBox.information(
                self,
                "Eliminar",
                "Selecciona una o mas filas pendientes para eliminar.",
            )
            return
        bloqueadas = [
            fila for fila in filas
            if self._manifiesto[fila].estado != "Pendiente"
        ]
        if bloqueadas:
            QMessageBox.warning(
                self,
                "Eliminar",
                "Solo se pueden eliminar filas en estado Pendiente.",
            )
            return
        for fila in filas:
            del self._manifiesto[fila]
        self._llenar_tabla_excel()
        self._actualizar_estado_excel()

    def _color_estado(self, estado: str) -> QColor:
        colores = {
            "Pendiente": QColor("#FFFFFF"),
            "Atrasado": QColor("#F38BA8"),
            "Dudoso": QColor("#F9E2AF"),
            "Llegado": QColor("#A6E3A1"),
        }
        return colores.get(estado, QColor("#FFFFFF"))

    def _normalizar_lectura(self, texto: str) -> str:
        return "".join(ch for ch in texto.upper() if ch.isalnum())

    def _actualizar_manifiesto_por_ocr(self, texto: str) -> str | None:
        if not self._manifiesto:
            return None

        lectura = self._normalizar_lectura(texto)
        if not lectura:
            return None

        mejor_fila = None
        mejor_ratio = 0.0
        for fila, registro in enumerate(self._manifiesto):
            precinto = self._normalizar_lectura(registro.precinto_esperado)
            if not precinto:
                continue
            if precinto in lectura:
                registro.estado = "Llegado"
                self._llenar_tabla_excel()
                self._tabla_excel.selectRow(fila)
                return f"Coincidencia exacta con precinto {registro.precinto_esperado}"

            ratio = SequenceMatcher(None, precinto, lectura).ratio()
            if ratio > mejor_ratio:
                mejor_ratio = ratio
                mejor_fila = fila

        if mejor_fila is not None and mejor_ratio >= 0.72:
            self._manifiesto[mejor_fila].estado = "Dudoso"
            self._llenar_tabla_excel()
            self._tabla_excel.selectRow(mejor_fila)
            registro = self._manifiesto[mejor_fila]
            return f"Coincidencia dudosa con precinto {registro.precinto_esperado}"

        return None

    def _vincular_ptz(self, boton: HoldButton, pan=None, tilt=None, zoom=None, focus=None):
        def start():
            self._enviar_ptz(
                pan=pan() if callable(pan) else 0,
                tilt=tilt() if callable(tilt) else 0,
                zoom=zoom() if callable(zoom) else 0,
                focus=focus() if callable(focus) else 0,
            )

        boton.motion_start.connect(start)
        boton.motion_stop.connect(self._detener_ptz)

    def _atajos(self):
        QShortcut(QKeySequence("1"), self).activated.connect(lambda: self._slider_vel.setValue(20))
        QShortcut(QKeySequence("2"), self).activated.connect(lambda: self._slider_vel.setValue(50))
        QShortcut(QKeySequence("3"), self).activated.connect(lambda: self._slider_vel.setValue(100))

    def _comando_tecla(self, key: int):
        mapa = {
            Qt.Key.Key_W: lambda: self._enviar_ptz(tilt=self._vel_mov),
            Qt.Key.Key_S: lambda: self._enviar_ptz(tilt=-self._vel_mov),
            Qt.Key.Key_A: lambda: self._enviar_ptz(pan=-self._vel_mov),
            Qt.Key.Key_D: lambda: self._enviar_ptz(pan=self._vel_mov),
            Qt.Key.Key_I: lambda: self._enviar_ptz(zoom=self._vel_mov),
            Qt.Key.Key_K: lambda: self._enviar_ptz(zoom=-self._vel_mov),
            Qt.Key.Key_J: lambda: self._enviar_ptz(focus=VEL_FOCO),
            Qt.Key.Key_L: lambda: self._enviar_ptz(focus=-VEL_FOCO),
        }
        fn = mapa.get(key)
        if fn is None:
            return False
        fn()
        return True

    def _atajos_globales_activos(self) -> bool:
        if QApplication.activeModalWidget() is not None:
            return False
        foco = QApplication.focusWidget()
        return not isinstance(foco, (QLineEdit, QTextEdit, QAbstractSpinBox))

    def eventFilter(self, watched, event):
        if isinstance(event, QKeyEvent) and self._atajos_globales_activos():
            teclas_ptz = (
                Qt.Key.Key_W, Qt.Key.Key_S, Qt.Key.Key_A, Qt.Key.Key_D,
                Qt.Key.Key_I, Qt.Key.Key_K, Qt.Key.Key_J, Qt.Key.Key_L,
            )
            if event.isAutoRepeat() and event.key() in teclas_ptz + (
                Qt.Key.Key_Space, Qt.Key.Key_P, Qt.Key.Key_Tab
            ):
                return True
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Tab:
                    self._alternar_canal()
                    return True
                if event.key() == Qt.Key.Key_Space:
                    self._detener_ptz()
                    return True
                if event.key() == Qt.Key.Key_P:
                    self._capturar()
                    return True
                if self._comando_tecla(event.key()):
                    return True
            elif event.type() == QEvent.Type.KeyRelease and event.key() in teclas_ptz:
                self._detener_ptz()
                return True
        return super().eventFilter(watched, event)

    def _inicio(self):
        if not settings_completos(self._cfg):
            self._video.set_placeholder("Configurá la cámara para comenzar")
            self._abrir_config()
            return
        self._conectar()

    def _abrir_config(self):
        dlg = SettingsDialog(self._cfg, self)
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            return
        nuevo = dlg.valores()
        if not settings_completos(nuevo):
            QMessageBox.warning(self, "Datos incompletos", "Completá IP, usuario, contraseña y canal.")
            return
        save_camera_settings(nuevo)
        self._cfg = nuevo
        self._canal_activo = nuevo.canal
        self._lbl_canal.setText(self._texto_canal())
        if self._service is not None:
            self._conectar()

    def _toggle_conexion(self):
        if self._service is not None:
            self._desconectar()
        else:
            self._conectar()

    def _cambiar_modo_dia_noche(self, modo: str):
        if self._service is None or not settings_completos(self._cfg):
            QMessageBox.information(
                self,
                "Camara",
                "Conecta la camara antes de cambiar el modo dia/noche.",
            )
            return
        ok = self._service.configurar_modo_dia_noche(self._cfg.ip, modo)
        if ok:
            self._set_estado(f"Modo camara: {modo}", "#A6E3A1")
            return
        mensaje = self._service.ultimo_error or "La camara no acepto el cambio de modo."
        self._set_estado(f"Modo camara: error", "#F38BA8")
        QMessageBox.warning(self, "Camara", mensaje)

    def _texto_canal(self) -> str:
        tipo = "media" if self._canal_activo == CANAL_RTSP_MEDIO else "alta"
        return f"Resolución: {tipo} (canal {self._canal_activo})"

    def _alternar_canal(self):
        if not settings_completos(self._cfg):
            return
        canal_principal = self._cfg.canal
        self._canal_activo = (
            canal_principal
            if self._canal_activo == CANAL_RTSP_MEDIO
            else CANAL_RTSP_MEDIO
        )
        self._lbl_canal.setText(self._texto_canal())
        if self._service is not None:
            self._conectar()

    def _conectar(self):
        if not settings_completos(self._cfg):
            self._abrir_config()
            return
        self._desconectar()
        self._service = CameraService(self._cfg.usuario, self._cfg.password)
        self._ptz.configurar(self._service, self._cfg.ip)
        self._service.configurar_auto_iris(self._cfg.ip)
        url = CameraService.url_rtsp(
            self._cfg.usuario, self._cfg.password, self._cfg.ip, self._canal_activo
        )
        self._rtsp_thread = threading.Thread(
            target=self._service.lector_rtsp, args=(url,), daemon=True
        )
        self._rtsp_thread.start()
        self._btn_conectar.setText("Desconectar")
        self._set_estado(f"Conectando al canal {self._canal_activo}…", "#F9E2AF")
        self._video.set_placeholder("Conectando al stream RTSP…")

    def _desconectar(self):
        if self._service is None:
            return
        self._detener_ptz()
        self._service.detener_lectura()
        self._service = None
        self._rtsp_thread = None
        self._video.limpiar()
        self._video.set_placeholder("Cámara desconectada")
        self._btn_conectar.setText("Conectar")
        self._set_estado("Sin conexión", "#A6ADC8")
        self._actualizar_captura()

    def _tick_video(self):
        if self._service is None:
            return
        frame = self._service.copiar_frame()
        if frame is None:
            if self._service.ultimo_error:
                self._video.set_placeholder(self._service.ultimo_error)
                self._set_estado(self._service.ultimo_error, "#F38BA8")
            self._actualizar_captura()
            return
        self._video.mostrar_frame(frame)
        self._set_estado("En vivo", "#A6E3A1")
        self._actualizar_captura()

    def _actualizar_captura(self):
        hay_video = self._video.tiene_imagen()
        self._btn_capturar.setEnabled(bool(hay_video and self._ocr_listo and not self._ocr_ocupado))

    def _on_vel(self, valor: int):
        self._vel_mov = valor
        self._lbl_vel.setText(f"Velocidad: {valor}")

    def _enviar_ptz(self, pan=0, tilt=0, zoom=0, focus=0):
        if self._service is None:
            return
        self._ptz.enviar(pan=pan, tilt=tilt, zoom=zoom, focus=focus)
        self._set_estado("Moviendo", "#89B4FA")

    def _detener_ptz(self):
        if self._service is None:
            return
        self._ptz.enviar(0, 0, 0, 0, 0)

    def _on_ptz_error(self, mensaje: str):
        self._set_estado(f"PTZ: {mensaje}", "#F38BA8")

    def _capturar(self):
        if not self._btn_capturar.isEnabled() or self._service is None:
            return
        self._ocr_ocupado = True
        self._actualizar_captura()
        self._lbl_ocr_estado.setText(
            f"Tomando foto en alta resolucion (canal {CANAL_RTSP_DEFAULT})..."
        )
        self._captura_thread = threading.Thread(
            target=self._capturar_alta_res,
            daemon=True,
        )
        self._captura_thread.start()

    def _capturar_alta_res(self):
        url = CameraService.url_rtsp(
            self._cfg.usuario,
            self._cfg.password,
            self._cfg.ip,
            CANAL_RTSP_DEFAULT,
        )
        frame = CameraService.capturar_frame_rtsp(url)
        if frame is None:
            self._captura_alta_error.emit(
                f"No se pudo capturar desde el canal {CANAL_RTSP_DEFAULT}"
            )
            return
        self._captura_alta_lista.emit(frame)

    def _procesar_captura_alta(self, frame):
        recorte = recorte_reticula(frame)
        if recorte.size == 0:
            recorte = frame
        carpeta = asegurar_carpeta_capturas()
        ruta = carpeta / f"precinto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        cv2.imwrite(str(ruta), recorte)
        self._lbl_ocr_estado.setText("Leyendo precinto...")
        self._ocr.pedir_ocr(recorte)

    def _on_captura_alta_error(self, mensaje: str):
        self._ocr_ocupado = False
        self._actualizar_captura()
        self._lbl_ocr_estado.setText("Error al capturar en alta resolucion")
        QMessageBox.warning(self, "Captura", mensaje)

    def _on_ocr_listo(self):
        self._ocr_listo = True
        self._lbl_ocr_motor.setText("Motor OCR: listo")
        self._actualizar_captura()

    def _on_ocr_fallo_motor(self, mensaje: str):
        self._ocr_listo = False
        self._lbl_ocr_motor.setText("Motor OCR: error")
        QMessageBox.critical(self, "OCR", f"No se pudo cargar el motor OCR:\n{mensaje}")

    def _on_ocr_resultado(self, texto: str, score: float, variante: str, conf: float):
        self._ocr_ocupado = False
        self._actualizar_captura()
        if not texto:
            self._lbl_ocr_estado.setText("Sin texto reconocido")
            self._txt_ocr.setPlainText("")
            self._lbl_confianza.setText("Confianza OCR: —")
            self._lbl_score.setText("Score: —")
            self._lbl_variante.setText(f"Método: {variante}")
            return
        coincidencia = self._actualizar_manifiesto_por_ocr(texto)
        if coincidencia:
            self._lbl_ocr_estado.setText(f"Lectura completada - {coincidencia}")
        else:
            self._lbl_ocr_estado.setText("Lectura completada")
        self._txt_ocr.setPlainText(texto)
        self._lbl_confianza.setText(f"Confianza OCR: {conf * 100:.1f} %")
        self._lbl_score.setText(f"Score: {score:.2f}")
        self._lbl_variante.setText(f"Método: {variante}")

    def _on_ocr_error(self, mensaje: str):
        self._ocr_ocupado = False
        self._actualizar_captura()
        self._lbl_ocr_estado.setText("Error en OCR")
        QMessageBox.warning(self, "OCR", mensaje)

    def _set_estado(self, texto: str, color: str):
        self._lbl_estado.setText(texto)
        self._lbl_estado.setStyleSheet(f"color: {color};")

    def closeEvent(self, event):
        self._timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self._service is not None:
            self._detener_ptz()
            self._service.detener_lectura()
        self._ptz.detener_hilo()
        self._ptz.wait(1500)
        self._ocr.detener()
        self._ocr.wait(1500)
        event.accept()
