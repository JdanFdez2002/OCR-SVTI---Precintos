from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton


class HoldButton(QPushButton):
    """Botón de mantener pulsado para PTZ continuo."""

    motion_start = Signal()
    motion_stop = Signal()

    def __init__(self, texto: str, parent=None):
        super().__init__(texto, parent)
        self.setAutoRepeat(False)
        self.setMinimumSize(56, 44)
        self.pressed.connect(self.motion_start.emit)
        self.released.connect(self.motion_stop.emit)
