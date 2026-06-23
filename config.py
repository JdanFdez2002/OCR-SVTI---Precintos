import os
from dotenv import load_dotenv

load_dotenv()

# Credenciales (se cargan de env o se sobreescriben en main.py)
CAM_USER = os.getenv("CAM_USER")
CAM_PASS = os.getenv("CAM_PASS")
CAM_IP = os.getenv("CAM_IP")

# Configuración Visual
COLOR_RETICULA = (0, 100, 0)
GROSOR_RETICULA = 1
ANCHO_RETICULA_PCT = 0.30 
ALTO_RETICULA_PCT = 0.20

# Configuración de Rutas
CARPETA_CAPTURAS = "capturas_precintos"
if not os.path.exists(CARPETA_CAPTURAS):
    os.makedirs(CARPETA_CAPTURAS, exist_ok=True)

# Forzar TCP para RTSP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"