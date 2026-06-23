import cv2
import time
import requests
import threading
import os
from requests.auth import HTTPDigestAuth

class CameraService:
    def __init__(self):
        self.ultimo_frame = None
        self.lock = threading.Lock()
        user = os.getenv("CAM_USER")
        password = os.getenv("CAM_PASS")
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(user, password)

    def lector_rtsp(self, rtsp_url):
        while True:
            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            while True:
                ret, frame = cap.read()
                if not ret:
                    cap.release()
                    time.sleep(1)
                    break
                with self.lock:
                    self.ultimo_frame = frame.copy()

    def mover_camara(self, ip, pan=0, tilt=0, zoom=0, focus=0, iris=0):
        detener = (pan == 0 and tilt == 0 and zoom == 0 and focus == 0 and iris == 0)
        try:
            if pan != 0 or tilt != 0 or zoom != 0 or detener:
                url = f"http://{ip}/ISAPI/PTZCtrl/channels/1/continuous"
                xml = f"<PTZData><pan>{pan}</pan><tilt>{tilt}</tilt><zoom>{zoom}</zoom></PTZData>"
                self.session.put(url, data=xml, timeout=0.5)

            if focus != 0 or detener:
                url = f"http://{ip}/ISAPI/System/Video/inputs/channels/1/focus"
                xml = f"<FocusData><focus>{focus}</focus></FocusData>"
                self.session.put(url, data=xml, timeout=0.5)
        except: pass

    def configurar_auto_iris(self, ip):
        """Intenta poner el Iris en modo automático"""
        url = f"http://{ip}/ISAPI/Image/channels/1/iris"
        xml = "<Iris><irisMode>auto</irisMode></Iris>"
        try: self.session.put(url, data=xml, timeout=1)
        except: pass