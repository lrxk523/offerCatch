"""OCR 引擎 - 后向兼容导入包装"""
# 实际实现在 skills/common/ocr.py，此文件仅为向后兼容保留。
# 新代码请直接: from skills.common.ocr import OCREngine
from app.skills.common.ocr import OCREngine

__all__ = ["OCREngine"]
