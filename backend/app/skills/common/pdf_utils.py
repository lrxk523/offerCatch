"""PDF 文本提取工具 — 文字层优先，扫描件才降级 OCR。

文档型 PDF（系统导出、Word 转存）自带文字层，pymupdf 直接抽取，
免费且比 OCR 准确；只有渲染型/扫描 PDF 才需要走 OCR/云转录。
"""

from io import BytesIO
from typing import List, Tuple

# 全篇有效文字少于该阈值视为"无文字层"(扫描件)
MIN_TEXT_CHARS = 50


def pdf_to_text(contents: bytes, min_chars: int = MIN_TEXT_CHARS) -> Tuple[str, str]:
    """
    提取 PDF 文字层。

    Returns:
        (text, "layer"): 文字层提取成功（text 可能为空但类型是 layer 判定）
        (text, "need_ocr"): 文字层缺失/过少，需要渲染 OCR
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "", "need_ocr"

    try:
        doc = fitz.open(stream=contents, filetype="pdf")
    except Exception as e:
        # 损坏/非 PDF 文件：不抛异常，走扫描件 OCR 路径（同样会失败并给出友好错误）
        print(f"[PDF-Utils] 无法打开 PDF({e})，判定为扫描件路径")
        return "", "need_ocr"

    try:
        page_texts = []
        for page in doc:
            t = page.get_text().strip()
            if t:
                page_texts.append(t)
    finally:
        doc.close()

    total = "\n\n".join(page_texts).strip()
    if len(total) >= min_chars:
        return total, "layer"
    return total, "need_ocr"


def render_pdf_pages(contents: bytes, dpi: int = 200) -> Tuple[List, int]:
    """
    将 PDF 每页渲染为 PIL Image（供扫描件 OCR 使用）。

    Returns:
        (images, total_pages)
    """
    import fitz  # PyMuPDF
    from PIL import Image

    doc = fitz.open(stream=contents, filetype="pdf")
    try:
        total_pages = len(doc)
        images = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(BytesIO(pix.tobytes("png")))
            images.append(img)
    finally:
        doc.close()
    return images, total_pages
