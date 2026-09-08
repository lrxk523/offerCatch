import fitz
from PIL import Image
from io import BytesIO
import traceback

pdf_path = r"static\pdf\寇宇坤-实施开发工程师-17709256932(1).pdf"

try:
    print(f"打开: {pdf_path}")
    doc = fitz.open(pdf_path)
    print(f"页数: {len(doc)}")

    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=200)
        img = Image.open(BytesIO(pix.tobytes("png")))
        print(f"  第{i+1}页: {img.size}")
    doc.close()
    print("PDF 渲染 OK")

    # 测试 EasyOCR
    print("\n测试 EasyOCR...")
    reader = __import__("easyocr").Reader(["ch_sim", "en"], gpu=False)
    print("EasyOCR 初始化 OK")

except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
