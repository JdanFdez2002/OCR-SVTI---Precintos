import queue

from PySide6.QtCore import QThread, Signal


class OcrWorker(QThread):
    """Un solo hilo: PaddleOCR no es seguro en paralelo."""

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
