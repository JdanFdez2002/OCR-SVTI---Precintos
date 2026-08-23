import threading

from PySide6.QtCore import QThread, Signal


class PtzWorker(QThread):
    """Ejecuta comandos ISAPI fuera del hilo de la UI."""

    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._evento = threading.Event()
        self._comando = None
        self._activo = True
        self._service = None
        self._ip = None

    def configurar(self, service, ip: str):
        with self._lock:
            self._service = service
            self._ip = ip

    def enviar(self, pan=0, tilt=0, zoom=0, focus=0, iris=0):
        with self._lock:
            self._comando = dict(pan=pan, tilt=tilt, zoom=zoom, focus=focus, iris=iris)
        self._evento.set()

    def detener_hilo(self):
        self._activo = False
        self._evento.set()

    def run(self):
        while self._activo:
            self._evento.wait()
            self._evento.clear()
            if not self._activo:
                break
            with self._lock:
                cmd = self._comando
                service = self._service
                ip = self._ip
                self._comando = None
            if not cmd or service is None or not ip:
                continue
            ok = service.mover_camara(ip, **cmd)
            if not ok and service.ultimo_error:
                self.error.emit(service.ultimo_error)
