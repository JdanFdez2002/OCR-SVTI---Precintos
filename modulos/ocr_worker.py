"""
Módulo Worker en segundo plano (PySide6/Qt) para ejecución asincrona

 Ejecución asíncrona desacoplada (Worker Thread)
   - Ejecuta las tareas pesadas del motor OCR en un hilo dedicado para no congelar la interfaz gráfica de usuario (Queue Threading)

 Procesamiento secuencial mediante Queue
   - Gestiona las peticiones en orden mediante una cola, garantiza que PaddleOCR se use de forma secuencial

 Comunicación por eventos reactivos:
   - Avisa el ciclo de vida del motor (listo/error en arranque) mediante señalees
   - Emite los resultados del análisis (texto, score, variante usada y confianza) o errores de ejecución a la UI
"""

import queue

from PySide6.QtCore import QThread, Signal


class OcrWorker(QThread):
    """
    Mantener como un solo hilo
    Se hicieron pruebas y PaddleOCR no es seguro en paralelo (Multi-Threading)
     """

    engine_ready = Signal()
    engine_failed = Signal(str)
    result = Signal(str, float, str, float)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cola = queue.Queue()

    def pedir_warmup(self):
        self._cola.put(("warmup", None))

    def pedir_ocr(self, frame_bgr):
        self._cola.put(("ocr", frame_bgr))

    def detener(self):
        self._cola.put(("stop", None))

    def run(self):
        while True:
            cmd, payload = self._cola.get()
            if cmd == "stop":
                break
            if cmd == "warmup":
                try:
                    from modulos.ocr_engine import warmup_ocr

                    warmup_ocr()
                    self.engine_ready.emit()
                except Exception as exc:
                    self.engine_failed.emit(str(exc))
            elif cmd == "ocr":
                try:
                    from modulos.ocr_engine import mejor_ocr

                    texto, score_val, variante, conf = mejor_ocr(payload)
                    self.result.emit(texto or "", float(score_val), variante, float(conf))
                except Exception as exc:
                    self.failed.emit(str(exc))
