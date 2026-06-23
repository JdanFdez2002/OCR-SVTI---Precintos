import cv2
import numpy as np
import os
import threading
from datetime import datetime
from config import *
from modulos.camera_service import CameraService
from modulos.ocr_engine import mejor_ocr

def procesar_ocr_bg(ruta):
    img = cv2.imread(ruta)
    if img is None: return
    texto, score_val, variante = mejor_ocr(img)
    print(f"\n===== OCR RESULTADO =====\nVariante: {variante}\nScore: {score_val:.2f}\nTexto:\n{texto}\n=========================\n")

def ejecutar_vision():
    user = os.getenv("CAM_USER")
    pas = os.getenv("CAM_PASS")
    ip = os.getenv("CAM_IP")
    
    service = CameraService()
    rtsp_url = f"rtsp://{user}:{pas}@{ip}:554/Streaming/Channels/101"
    
    # Intentar poner Iris en Auto al arrancar
    service.configurar_auto_iris(ip)
    
    threading.Thread(target=service.lector_rtsp, args=(rtsp_url,), daemon=True).start()

    vel_mov = 30
    vel_lente = 5
    estado_actual = "CONECTADO (IRIS AUTO)"
    
    WINDOW_NAME = "ACCELERA SVTI - Control PTZ"
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1280, 720)

    while True:
        with service.lock:
            frame = None if service.ultimo_frame is None else service.ultimo_frame.copy()

        if frame is None:
            espera = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(espera, "Conectando...", (400, 360), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.imshow(WINDOW_NAME, espera)
            if cv2.waitKey(1) & 0xFF == 27: break
            continue

        frame_limpio = frame.copy()
        rect = cv2.getWindowImageRect(WINDOW_NAME)
        ancho_v, alto_v = max(800, rect[2]), max(450, rect[3])
        alto_video = alto_v - 110
        frame_achicado = cv2.resize(frame, (ancho_v, alto_video))
        
        # Interfaz Visual
        centro_x, centro_y_s = int(ancho_v/2), int(alto_video/2)
        ancho_r, alto_r = int(ancho_v * ANCHO_RETICULA_PCT), int(alto_video * ALTO_RETICULA_PCT)
        y1, y2 = max(0, centro_y_s - int(alto_r/2)), min(alto_video, centro_y_s + int(alto_r/2))
        x1, x2 = max(0, centro_x - int(ancho_r/2)), min(ancho_v, centro_x + int(ancho_r/2))
        
        frame_mostrar = cv2.copyMakeBorder(frame_achicado, 50, 60, 0, 0, cv2.BORDER_CONSTANT, value=[15, 15, 25])
        cv2.rectangle(frame_mostrar, (x1, y1 + 50), (x2, y2 + 50), COLOR_RETICULA, GROSOR_RETICULA)
        
        cv2.putText(frame_mostrar, f"ESTADO: {estado_actual}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame_mostrar, f"VEL: {vel_mov}", (250, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
        cv2.putText(frame_mostrar, "MOV: [8456] | ZOOM: [WS] | FOCO: [79] | PARAR: [ESPACIO]", (20, frame_mostrar.shape[0]-35), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.putText(frame_mostrar, "SISTEMA: OCR [P] | VEL [1-3] | SALIR [ESC]", (20, frame_mostrar.shape[0]-15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        cv2.imshow(WINDOW_NAME, frame_mostrar)
        tecla = cv2.waitKey(1) & 0xFF

        if tecla == 27: break # ESC

        # DETENER TODO (ESPACIO)
        elif tecla == 32: 
            service.mover_camara(ip, 0, 0, 0, 0, 0)
            estado_actual = "DETENIDO"

        # Velocidades
        elif tecla == ord('1'): vel_mov = 20
        elif tecla == ord('2'): vel_mov = 50
        elif tecla == ord('3'): vel_mov = 100

        # Movimiento Numpad
        elif tecla == ord('8'): 
            service.mover_camara(ip, pan=0, tilt=vel_mov)
            estado_actual = "SUBIENDO"
        elif tecla == ord('5'): 
            service.mover_camara(ip, pan=0, tilt=-vel_mov)
            estado_actual = "BAJANDO"
        elif tecla == ord('4'): 
            service.mover_camara(ip, pan=-vel_mov, tilt=0)
            estado_actual = "IZQUIERDA"
        elif tecla == ord('6'): 
            service.mover_camara(ip, pan=vel_mov, tilt=0)
            estado_actual = "DERECHA"

        # Zoom (W / S)
        elif tecla == ord('w') or tecla == ord('W'): 
            service.mover_camara(ip, zoom=vel_mov)
            estado_actual = "ZOOM IN"
        elif tecla == ord('s') or tecla == ord('S'): 
            service.mover_camara(ip, zoom=-vel_mov)
            estado_actual = "ZOOM OUT"

        # Foco (7 / 9)
        elif tecla == ord('7'): 
            service.mover_camara(ip, focus=vel_lente)
            estado_actual = "FOCO CERCA (+)"
        elif tecla == ord('9'): 
            service.mover_camara(ip, focus=-vel_lente)
            estado_actual = "FOCO LEJOS (-)"

        # OCR
        elif tecla == ord('p') or tecla == ord('P'):
            ruta = os.path.join(CARPETA_CAPTURAS, f"precinto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            cv2.imwrite(ruta, frame_limpio)
            threading.Thread(target=procesar_ocr_bg, args=(ruta,), daemon=True).start()
            estado_actual = "CAPTURANDO OCR..."

    service.mover_camara(ip, 0, 0, 0, 0, 0)
    cv2.destroyAllWindows()