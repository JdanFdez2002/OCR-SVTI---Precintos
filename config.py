import os
from pathlib import Path

# Debe setearse antes del primer VideoCapture
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

COLOR_RETICULA = (0, 180, 80)
GROSOR_RETICULA = 2
ANCHO_RETICULA_PCT = 0.30
ALTO_RETICULA_PCT = 0.20

RAIZ_PROYECTO = Path(__file__).resolve().parent
CARPETA_CAPTURAS = RAIZ_PROYECTO / "capturas_precintos"

CANAL_RTSP_DEFAULT = "101"
PUERTO_RTSP = 554
VEL_FOCO = 5


def asegurar_carpeta_capturas() -> Path:
    CARPETA_CAPTURAS.mkdir(parents=True, exist_ok=True)
    return CARPETA_CAPTURAS


def recorte_reticula(frame):
    """Recorta la zona central equivalente a la retícula de la UI."""
    alto, ancho = frame.shape[:2]
    rw = max(1, int(ancho * ANCHO_RETICULA_PCT))
    rh = max(1, int(alto * ALTO_RETICULA_PCT))
    x1 = max(0, ancho // 2 - rw // 2)
    y1 = max(0, alto // 2 - rh // 2)
    x2 = min(ancho, x1 + rw)
    y2 = min(alto, y1 + rh)
    return frame[y1:y2, x1:x2].copy()
