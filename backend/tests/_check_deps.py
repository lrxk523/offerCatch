import importlib, sys

deps = [
    ("fitz", "PyMuPDF"),
    ("PIL", "Pillow"),
    ("paddleocr", "PaddleOCR"),
    ("easyocr", "EasyOCR"),
    ("cnocr", "CnOCR"),
]

for mod, name in deps:
    try:
        importlib.import_module(mod)
        print(f"  OK  {name}")
    except:
        print(f"MISS  {name}")

# 打印 Python 路径
print(f"\nPython: {sys.executable}")
print(f"version: {sys.version}")
