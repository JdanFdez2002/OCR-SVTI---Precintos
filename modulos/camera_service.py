import threading
import time
from urllib.parse import quote

import cv2
import requests
from requests.auth import HTTPDigestAuth


class CameraService:
    def __init__(self, user: str, password: str):
        self.ultimo_frame = None
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self.conectado = False
        self.ultimo_error = None
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(user, password)

    @staticmethod
    def url_rtsp(user: str, password: str, ip: str, canal: str = "101", puerto: int = 554) -> str:
        u = quote(user, safe="")
        p = quote(password, safe="")
        return f"rtsp://{u}:{p}@{ip}:{puerto}/Streaming/Channels/{canal}"

    def detener_lectura(self):
        self._stop.set()

    def lector_rtsp(self, rtsp_url: str):
        self._stop.clear()
        self.conectado = False
        while not self._stop.is_set():
            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                self.conectado = False
                self.ultimo_error = "No se pudo abrir el stream RTSP"
                time.sleep(1)
                continue

            while not self._stop.is_set():
                ret, frame = cap.read()
                if not ret:
                    self.conectado = False
                    self.ultimo_error = "Se perdió la señal de video"
                    cap.release()
                    time.sleep(1)
                    break
                with self.lock:
                    self.ultimo_frame = frame.copy()
                self.conectado = True
                self.ultimo_error = None
            else:
                cap.release()

    def copiar_frame(self):
        with self.lock:
            if self.ultimo_frame is None:
                return None
            return self.ultimo_frame.copy()

    def mover_camara(self, ip, pan=0, tilt=0, zoom=0, focus=0, iris=0) -> bool:
        detener = pan == 0 and tilt == 0 and zoom == 0 and focus == 0 and iris == 0
        try:
            if pan != 0 or tilt != 0 or zoom != 0 or detener:
                url = f"http://{ip}/ISAPI/PTZCtrl/channels/1/continuous"
                xml = f"<PTZData><pan>{pan}</pan><tilt>{tilt}</tilt><zoom>{zoom}</zoom></PTZData>"
                self.session.put(url, data=xml, timeout=0.5)

            if focus != 0 or detener:
                url = f"http://{ip}/ISAPI/System/Video/inputs/channels/1/focus"
                xml = f"<FocusData><focus>{focus}</focus></FocusData>"
                self.session.put(url, data=xml, timeout=0.5)
            return True
        except Exception as exc:
            self.ultimo_error = str(exc)
            return False

    def configurar_auto_iris(self, ip) -> bool:
        url = f"http://{ip}/ISAPI/Image/channels/1/iris"
        xml = "<Iris><irisMode>auto</irisMode></Iris>"
        try:
            self.session.put(url, data=xml, timeout=1)
            return True
        except Exception as exc:
            self.ultimo_error = str(exc)
            return False
