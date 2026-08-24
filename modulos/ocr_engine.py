"""
Módulo de Reconocimiento Óptico de Caracteres (OCR)

 Instanciación Única y Thread-Safe (Singleton)
   - Carga el motor PaddleOCR en memoria una sola vez para evitar sobrecarga y bloqueos

 Preprocesamiento Avanzado de Imagen
   - Genera múltiples filtros sobre la imagen filtro bilateral para maximizar la legibilidad

 Pipeline de Reconocimiento resiliente con Salida Temprana
   - Intenta primero una lectura directa rápida. Si cumple con un umbral alto de confianza  y longitud, devuelve el resultado al instante para ahorrar cómputo.
   - Si no es concluyente, prueba en cascada todas las variantes preprocesadas y rotaciones, seleccionando el texto con mayor puntuación ponderada

Uso del Scoring queda PaddleOCR:
   - Evalúa y premia la confianza del OCR, la cantidad de caracteres alfanuméricos y el ajuste a patrones típicos de precintos de seguridad
"""

import logging
import re
import threading

import cv2
import numpy as np
from paddleocr import PaddleOCR

logging.getLogger("ppocr").setLevel(logging.ERROR)

_ocr = None
_ocr_lock = threading.Lock()

SCORE_RAPIDO_UMBRAL = 0.88
MIN_CHARS_RAPIDO = 5
PATRON_PRECINTO = re.compile(r"[A-Z0-9][A-Z0-9\-]{3,}")


def get_ocr() -> PaddleOCR:
    """Carga PaddleOCR una sola vez, fuera del hilo de la interfaz."""
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            _ocr = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                show_log=False,
                rec_algorithm="SVTR_LCNet",
            )
        return _ocr


def warmup_ocr() -> None:
    get_ocr()


def score(conf: float, texto: str) -> float:
    if not texto:
        return 0.0

    texto_upper = texto.upper()
    chars_validos = len(re.sub(r"[^A-Z0-9\-]", "", texto_upper))
    if chars_validos == 0:
        return 0.0

    base = (chars_validos ** 0.7) * (conf ** 1.3)
    if PATRON_PRECINTO.search(texto_upper):
        base *= 1.25
    return base


def _limpiar_texto(texto: str) -> str:
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    if len(lineas) <= 3 and all(len(l) <= 20 for l in lineas):
        return " ".join(lineas)
    return "\n".join(lineas)


def preprocesar(img: np.ndarray) -> list[tuple[str, np.ndarray]]:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variantes = [("Original", g)]

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    variantes.append(("CLAHE", clahe.apply(g)))

    kernel_sharp = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    variantes.append(("Sharp", cv2.filter2D(g, -1, kernel_sharp)))

    variantes.append(("Bilateral", cv2.bilateralFilter(g, 9, 75, 75)))

    _, binarizada = cv2.threshold(
        clahe.apply(g), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    variantes.append(("Otsu-CLAHE", binarizada))

    adaptativa = cv2.adaptiveThreshold(
        g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    variantes.append(("AdaptThresh", adaptativa))
    return variantes


def _rotar_90(img: np.ndarray, sentido: str) -> np.ndarray:
    if sentido == "izquierda":
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)


def _ocr_imagen(imagen: np.ndarray) -> tuple[str, float]:
    res = get_ocr().ocr(imagen, cls=True)
    if not res or not res[0]:
        return "", 0.0
    lineas = res[0]
    texto = "\n".join(l[1][0] for l in lineas)
    conf = sum(l[1][1] for l in lineas) / len(lineas)
    return texto, conf


def mejor_ocr(img: np.ndarray) -> tuple[str, float, str, float]:
    mejor_texto = ""
    mejor_score = -1.0
    mejor_metodo = "ninguno"
    mejor_conf = 0.0

    def _evaluar(nombre: str, imagen: np.ndarray) -> bool:
        nonlocal mejor_texto, mejor_score, mejor_metodo, mejor_conf
        texto, conf = _ocr_imagen(imagen)
        if not texto:
            return False
        s = score(conf, texto)
        if s > mejor_score:
            mejor_score = s
            mejor_texto = _limpiar_texto(texto)
            mejor_metodo = nombre
            mejor_conf = conf
        chars_validos = len(re.sub(r"[^A-Z0-9\-]", "", texto.upper()))
        return conf >= SCORE_RAPIDO_UMBRAL and chars_validos >= MIN_CHARS_RAPIDO

    texto_rapido, conf_rapido = _ocr_imagen(img)
    if texto_rapido:
        s = score(conf_rapido, texto_rapido)
        mejor_score = s
        mejor_texto = _limpiar_texto(texto_rapido)
        mejor_metodo = "Directo-BGR"
        mejor_conf = conf_rapido
        chars_validos = len(re.sub(r"[^A-Z0-9\-]", "", texto_rapido.upper()))
        if conf_rapido >= SCORE_RAPIDO_UMBRAL and chars_validos >= MIN_CHARS_RAPIDO:
            return mejor_texto, mejor_score, mejor_metodo + " [early-exit]", mejor_conf

    for nombre, imagen_proc in preprocesar(img):
        if _evaluar(f"Proc:{nombre}", imagen_proc):
            return mejor_texto, mejor_score, mejor_metodo + " [early-exit]", mejor_conf

    for sentido in ("izquierda", "derecha"):
        img_rot = _rotar_90(img, sentido)
        if _evaluar(f"Rot90{sentido.capitalize()}-BGR", img_rot):
            return mejor_texto, mejor_score, mejor_metodo + " [early-exit]", mejor_conf
        for nombre, imagen_proc in preprocesar(img_rot):
            if _evaluar(f"Rot90{sentido.capitalize()}-{nombre}", imagen_proc):
                return mejor_texto, mejor_score, mejor_metodo + " [early-exit]", mejor_conf

    return mejor_texto, mejor_score, mejor_metodo, mejor_conf
