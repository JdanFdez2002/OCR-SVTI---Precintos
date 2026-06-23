import cv2
import numpy as np
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_textline_orientation=True, lang="es")

ANGULOS = [("0°", None), ("90°", cv2.ROTATE_90_CLOCKWISE),
           ("180°", cv2.ROTATE_180), ("270°", cv2.ROTATE_90_COUNTERCLOCKWISE)]

def preprocesar(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, otsu = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    clahe_bin = cv2.threshold(clahe.apply(g), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    nitida = cv2.addWeighted(g, 1.5, cv2.GaussianBlur(g, (0, 0), 3), -0.5, 0)

    bases = [("Original", img), ("Otsu", otsu), ("CLAHE", clahe_bin), ("Nítida", nitida)]

    out = []
    for nb, ib in bases:
        for na, r in ANGULOS:
            out.append((f"{nb}-{na}", cv2.rotate(ib, r) if r else ib))
    return out

def run_ocr(img):
    res = ocr.ocr(img)
    lineas = res[0] if res and res[0] else []
    texto = "\n".join(l[1][0] for l in lineas)
    conf  = sum(l[1][1] for l in lineas) / len(lineas) if lineas else 0
    chars = len(texto.replace(" ", "").replace("\n", ""))
    return texto, conf, chars

def score(conf, chars):
    return (chars ** 0.7) * (conf ** 1.3)

def mejor_ocr(img):
    candidatos = preprocesar(img)

    mejor = max(
        candidatos,
        key=lambda x: score(*run_ocr(x[1])[1:])
    )

    texto, conf, chars = run_ocr(mejor[1])
    return texto, score(conf, chars), mejor[0]