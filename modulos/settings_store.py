import os
from dataclasses import dataclass

from dotenv import load_dotenv
from PySide6.QtCore import QSettings

load_dotenv()

ORG = "ACCELERA"
APP = "SVTI-Precintos"


@dataclass
class CameraSettings:
    ip: str = ""
    usuario: str = ""
    password: str = ""
    canal: str = "101"


def _qsettings() -> QSettings:
    return QSettings(ORG, APP)


def load_camera_settings() -> CameraSettings:
    s = _qsettings()
    return CameraSettings(
        ip=s.value("camara/ip", os.getenv("CAM_IP", "") or ""),
        usuario=s.value("camara/usuario", os.getenv("CAM_USER", "") or ""),
        password=s.value("camara/password", os.getenv("CAM_PASS", "") or ""),
        canal=s.value("camara/canal", os.getenv("CAM_CHANNEL", "101") or "101"),
    )


def save_camera_settings(cfg: CameraSettings) -> None:
    s = _qsettings()
    s.setValue("camara/ip", cfg.ip.strip())
    s.setValue("camara/usuario", cfg.usuario.strip())
    s.setValue("camara/password", cfg.password)
    s.setValue("camara/canal", (cfg.canal or "101").strip())
    s.sync()


def settings_completos(cfg: CameraSettings) -> bool:
    return bool(cfg.ip and cfg.usuario and cfg.password and cfg.canal)
