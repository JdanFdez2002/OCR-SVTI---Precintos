APP_STYLESHEET = """
QMainWindow, QDialog, QWidget {
    background-color: #1E1E2E;
    color: #CDD6F4;
    font-family: Segoe UI, Helvetica, Arial;
    font-size: 13px;
}
QLabel#titulo {
    font-size: 18px;
    font-weight: 700;
    color: #89B4FA;
}
QLabel#estado {
    font-weight: 600;
}
QLineEdit, QTextEdit, QSpinBox {
    background-color: #313244;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #89B4FA;
}
QPushButton {
    background-color: #313244;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 8px;
    padding: 8px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #45475A;
}
QPushButton:pressed {
    background-color: #585B70;
}
QPushButton:disabled {
    color: #6C7086;
}
QPushButton#primario {
    background-color: #89B4FA;
    color: #1E1E2E;
    border: none;
}
QPushButton#primario:hover {
    background-color: #B4BEFE;
}
QPushButton#peligro {
    background-color: #F38BA8;
    color: #1E1E2E;
    border: none;
}
QGroupBox {
    border: 1px solid #45475A;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #89B4FA;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #45475A;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #89B4FA;
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
"""
