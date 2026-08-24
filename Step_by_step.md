Crear entorno virtual con Python 3.10:
- py -3.10 -m venv venv

Activar en entorno virtual:
- .\venv\Scripts\activate

Actualizar herramientas de instalación:
- python -m pip install --upgrade pip setuptools wheel

Instalar PaddlePaddle compatible:
- pip install paddlepaddle==2.6.2

Instalar PaddleOCR compatible:
- pip install paddleocr==2.7.3

Instalar Pillow:
- pip install pillow

Instalar NumPy compatible:
- pip install numpy==1.26.4

Instalar OpenCV:
- pip install opencv-python==4.6.0.66

Instalar dotenv:
- pip install dotenv

Instalar lector de Excel:
- pip install openpyxl

Verificar con:
- pip list | findstr "numpy opencv paddle"

numpy                    1.26.4
opencv-python            4.6.0.66
paddleocr                2.7.3
paddlepaddle             2.6.2
