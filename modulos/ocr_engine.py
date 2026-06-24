import cv2
import numpy as np
from paddleocr import PaddleOCR
import logging
import re


logging.getLogger("ppocr").setLevel(logging.ERROR)

ocr = PaddleOCR(
    use_angle_cls=True,
    lang="en",
    show_log=False,
    rec_algorithm='SVTR_LCNet'
)

SCORE_RAPIDO_UMBRAL  = 0.88   # Si la primera lectura supera esto, saltamos todo lo demás
MIN_CHARS_RAPIDO     = 5      # Mínimo de caracteres para considerar un early-exit válido
PATRON_PRECINTO      = re.compile(r'[A-Z0-9][A-Z0-9\-]{3,}')  # Patrón típico de precinto


def score(conf: float, texto: str) -> float:
    """
    Evalúa la calidad del resultado ponderando:
      - Longitud de caracteres alfanuméricos + guiones (patrón de precinto)
      - Confianza del OCR
      - Bonus si el texto calza con el patrón típico de precinto (letras+números+guión)
    """
    if not texto:
        return 0.0

    texto_upper = texto.upper()

    # Contar solo caracteres relevantes para un precinto
    chars_validos = len(re.sub(r'[^A-Z0-9\-]', '', texto_upper))
    if chars_validos == 0:
        return 0.0

    base = (chars_validos ** 0.7) * (conf ** 1.3)

    # Bonus si encontramos al menos un token que parece un precinto
    if PATRON_PRECINTO.search(texto_upper):
        base *= 1.25

    return base


def _limpiar_texto(texto: str) -> str:
    """
    Post-procesamiento liviano del texto reconocido:
      - Une líneas que probablemente son un solo código
      - Elimina espacios dentro de tokens alfanuméricos cortos
      - Preserva guiones
    """
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    # Si hay pocas líneas y son cortas, probablemente todo es un solo precinto
    if len(lineas) <= 3 and all(len(l) <= 20 for l in lineas):
        return " ".join(lineas)
    return "\n".join(lineas)


def preprocesar(img: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """
    Genera variantes de imagen optimizadas para precintos metálicos.
    Orden: de menor a mayor complejidad, para que el early-exit
    corte antes si la imagen ya es buena.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. Original en grises — baseline rápido
    variantes = [("Original", g)]

    # 2. CLAHE — mejora contraste en superficies metálicas con reflejos
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    variantes.append(("CLAHE", clahe.apply(g)))

    # 3. Sharpening — resalta bordes de caracteres grabados o pintados
    kernel_sharp = np.array([[0, -1, 0],
                              [-1, 5, -1],
                              [0, -1, 0]], dtype=np.float32)
    variantes.append(("Sharp", cv2.filter2D(g, -1, kernel_sharp)))

    # 4. Bilateral — elimina ruido manteniendo bordes de dígitos
    variantes.append(("Bilateral", cv2.bilateralFilter(g, 9, 75, 75)))

    # 5. Binarización adaptativa (Otsu sobre CLAHE) — útil en fondos no uniformes
    _, binarizada = cv2.threshold(
        clahe.apply(g), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    variantes.append(("Otsu-CLAHE", binarizada))

    # 6. Binarización adaptativa local — cuando la iluminación varía dentro de la imagen
    adaptativa = cv2.adaptiveThreshold(
        g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, blockSize=31, C=10
    )
    variantes.append(("AdaptThresh", adaptativa))

    return variantes


def _rotar_90(img: np.ndarray, sentido: str) -> np.ndarray:
    """Rota la imagen 90° a la izquierda o derecha."""
    if sentido == "izquierda":
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)


def _ocr_imagen(imagen: np.ndarray) -> tuple[str, float]:
    """Ejecuta PaddleOCR sobre una imagen y retorna (texto, confianza_promedio)."""
    res = ocr.ocr(imagen, cls=True)
    if not res or not res[0]:
        return "", 0.0
    lineas = res[0]
    texto = "\n".join(l[1][0] for l in lineas)
    conf  = sum(l[1][1] for l in lineas) / len(lineas)
    return texto, conf


def mejor_ocr(img: np.ndarray) -> tuple[str, float, str]:
    mejor_texto  = ""
    mejor_score  = -1.0
    mejor_metodo = "ninguno"

    def _evaluar(nombre: str, imagen: np.ndarray) -> bool:
        """
        Evalúa una imagen, actualiza el mejor resultado.
        Retorna True si se cumple la condición de early-exit.
        """
        nonlocal mejor_texto, mejor_score, mejor_metodo

        texto, conf = _ocr_imagen(imagen)
        if not texto:
            return False

        s = score(conf, texto)
        if s > mejor_score:
            mejor_score  = s
            mejor_texto  = _limpiar_texto(texto)
            mejor_metodo = nombre

        # Condición de early-exit: alta confianza + suficientes caracteres válidos
        chars_validos = len(re.sub(r'[^A-Z0-9\-]', '', texto.upper()))
        if conf >= SCORE_RAPIDO_UMBRAL and chars_validos >= MIN_CHARS_RAPIDO:
            return True
        return False

    # ── ETAPA 0: lectura rápida sobre imagen original BGR ────────────────────
    texto_rapido, conf_rapido = _ocr_imagen(img)
    if texto_rapido:
        s = score(conf_rapido, texto_rapido)
        mejor_score  = s
        mejor_texto  = _limpiar_texto(texto_rapido)
        mejor_metodo = "Directo-BGR"

        chars_validos = len(re.sub(r'[^A-Z0-9\-]', '', texto_rapido.upper()))
        if conf_rapido >= SCORE_RAPIDO_UMBRAL and chars_validos >= MIN_CHARS_RAPIDO:
            return mejor_texto, mejor_score, mejor_metodo + " [early-exit]"

    candidatos = preprocesar(img)
    for nombre, imagen_proc in candidatos:
        if _evaluar(f"Proc:{nombre}", imagen_proc):
            return mejor_texto, mejor_score, mejor_metodo + " [early-exit]"

    for sentido in ("izquierda", "derecha"):
        img_rot = _rotar_90(img, sentido)

        # Lectura directa sobre imagen rotada
        if _evaluar(f"Rot90{sentido.capitalize()}-BGR", img_rot):
            return mejor_texto, mejor_score, mejor_metodo + " [early-exit]"

        # Variantes de preprocesamiento sobre imagen rotada
        for nombre, imagen_proc in preprocesar(img_rot):
            if _evaluar(f"Rot90{sentido.capitalize()}-{nombre}", imagen_proc):
                return mejor_texto, mejor_score, mejor_metodo + " [early-exit]"

    return mejor_texto, mejor_score, mejor_metodo