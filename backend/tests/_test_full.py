"""完整测试简历上传管线"""
import asyncio
import fitz
from PIL import Image
from io import BytesIO
import traceback

from app.skills.jd_parser.ocr import OCREngine

async def main():
    pdf_path = r"static\pdf\寇宇坤-实施开发工程师-17709256932(1).pdf"
    
    print("1. 打开 PDF...")
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    print(f"   {total_pages} 页")

    print("2. 渲染页面为图片 (200 DPI)...")
    page_images = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.open(BytesIO(pix.tobytes("png")))
        page_images.append(img)
    doc.close()
    print("   OK")

    print("3. 初始化 OCR 引擎...")
    ocr = OCREngine()
    engine_name = await ocr.initialize()
    print(f"   引擎: {engine_name}")

    print("4. 逐页 OCR...")
    page_texts = []
    for i, img in enumerate(page_images):
        try:
            text = await ocr.extract_text(img)
            if text and text.strip():
                page_texts.append(text.strip())
            print(f"   第 {i+1}/{total_pages} 页: {len(text) if text else 0} 字符")
        except Exception as e:
            print(f"   第 {i+1}/{total_pages} 页 ERROR: {e}")
            traceback.print_exc()

    full_text = "\n\n".join(page_texts)
    print(f"\n5. 总文本: {len(full_text)} 字符")
    print("=" * 60)
    print(full_text[:2000])
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
