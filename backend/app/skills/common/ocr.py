"""OCR 引擎 - 支持模糊截图、手机长截图等多场景"""
# 本文件是从 skills/jd_parser/ocr.py 迁移到公共层的唯一来源。
# 所有模块应从此处导入 OCREngine，勿再从 jd_parser 导入。

import os
import re
import base64
import asyncio
import logging
from typing import Optional, List, Tuple
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


def _detect_gpu() -> bool:
    """自动检测 GPU 是否可用 (CUDA)"""
    env_gpu = os.getenv("OCR_GPU", "").lower()
    if env_gpu in ("0", "false", "no"):
        return False
    if env_gpu in ("1", "true", "yes"):
        return True

    try:
        import torch
        if torch.cuda.is_available():
            logger.info("[OCR] 检测到 CUDA GPU: %s", torch.cuda.get_device_name(0))
            return True
    except ImportError:
        pass

    try:
        import paddle
        if paddle.is_compiled_with_cuda():
            try:
                count = paddle.device.cuda.device_count()
                if count > 0:
                    logger.info("[OCR] PaddlePaddle 检测到 %d 块 CUDA GPU", count)
                    return True
            except Exception:
                pass
    except ImportError:
        pass

    return False


class OCREngine:
    """
    OCR 引擎封装，内置图像预处理流水线。
    策略优先级: PaddleOCR > EasyOCR > tesseract (自动 fallback)
    """

    def __init__(self):
        self._engine = None
        self._engine_type = ""
        self._use_gpu = False

    async def initialize(self) -> str:
        """按优先级初始化 OCR 引擎，返回实际使用的引擎名称"""
        errors = []
        self._use_gpu = _detect_gpu()
        gpu_tag = "GPU" if self._use_gpu else "CPU"

        # 1. 尝试 PaddleOCR (推荐，中文识别最好)
        try:
            from paddleocr import PaddleOCR
            import paddleocr as _pocr
            _pocr_version = getattr(_pocr, "__version__", "2.0")

            if _pocr_version.startswith("3."):
                self._engine = PaddleOCR(use_textline_orientation=True)
            else:
                self._engine = PaddleOCR(
                    lang="ch",
                    use_angle_cls=True,
                    show_log=False,
                    use_gpu=self._use_gpu,
                )
            self._engine_type = "paddleocr"
            print(f"[OCR] Using PaddleOCR v{_pocr_version} ({gpu_tag})")
            return self._engine_type
        except ImportError as e:
            errors.append(f"PaddleOCR not installed: {e}")
        except Exception as e:
            errors.append(f"PaddleOCR init failed: {e}")
            print(f"[OCR] PaddleOCR 初始化失败({e})，回退到 EasyOCR")

        # 2. 尝试 EasyOCR (备选)
        try:
            import easyocr
            print(f"[OCR] Initializing EasyOCR ({gpu_tag}, downloading models if needed)...")
            self._engine = await asyncio.to_thread(
                easyocr.Reader, ["ch_sim", "en"], gpu=self._use_gpu
            )
            self._engine_type = "easyocr"
            print(f"[OCR] Using EasyOCR ({gpu_tag})")
            return self._engine_type
        except ImportError as e:
            errors.append(f"EasyOCR not installed: {e}")
        except Exception as e:
            errors.append(f"EasyOCR init failed: {e}")

        # 3. 尝试 tesseract (兜底)
        try:
            import pytesseract
            self._engine = pytesseract
            self._engine_type = "tesseract"
            print("[OCR] Using Tesseract")
            return self._engine_type
        except ImportError as e:
            errors.append(f"Tesseract not installed: {e}")
        except Exception as e:
            errors.append(f"Tesseract init failed: {e}")

        raise RuntimeError(
            "未找到可用的 OCR 引擎。请安装: pip install paddleocr 或 pip install easyocr\n"
            + "详细错误:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """图像预处理流水线"""
        if image.mode != "RGB":
            image = image.convert("RGB")

        w, h = image.size

        if w >= 1400:
            return image

        if w < 800:
            scale = 1200 / w
            image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.15)

        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.2)

        image = image.filter(ImageFilter.MedianFilter(1))

        return image

    def _split_long_screenshot(self, image: Image.Image, max_height: int = 2000) -> List[Image.Image]:
        """将超长截图切分为多个片段处理"""
        w, h = image.size
        aspect_ratio = h / w if w > 0 else 1.0

        if h <= max_height or aspect_ratio < 2.0:
            return [image]

        overlap = 100
        slices = []
        y = 0
        while y < h:
            bottom = min(y + max_height, h)
            slice_img = image.crop((0, y, w, bottom))
            slices.append(slice_img)
            y = bottom - overlap
        return slices

    async def extract_text(self, image_input, preprocess: bool = True) -> str:
        """从图片提取文字"""
        image = self._load_image(image_input)

        if preprocess:
            image = self._preprocess_image(image)

        w, h = image.size
        slices = self._split_long_screenshot(image)

        if len(slices) > 1 and self._engine_type == "paddleocr":
            tasks = [self._ocr_slice(s) for s in slices]
            results = await asyncio.gather(*tasks)
            all_texts = [t for t in results if t]
        else:
            all_texts = []
            for slice_img in slices:
                text = await self._ocr_slice(slice_img)
                if text:
                    all_texts.append(text)

        return "\n".join(all_texts)

    async def _ocr_slice(self, image: Image.Image) -> str:
        """对单张图片切片执行 OCR"""
        if self._engine_type == "paddleocr":
            return await self._ocr_paddle(image)
        elif self._engine_type == "easyocr":
            return await self._ocr_easyocr(image)
        elif self._engine_type == "tesseract":
            return await self._ocr_tesseract(image)
        return ""

    async def _ocr_paddle(self, image: Image.Image) -> str:
        """PaddleOCR 识别"""
        import numpy as np
        img_array = np.array(image)
        result = await asyncio.to_thread(self._engine.ocr, img_array, cls=False)

        if not result:
            return ""

        lines_data = result[0] if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list) else result

        if not lines_data:
            return ""

        lines = []
        for line_info in lines_data:
            if isinstance(line_info, (list, tuple)) and len(line_info) >= 2:
                bbox, text_conf = line_info[0], line_info[1]
                if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
                    text, confidence = text_conf[0], text_conf[1]
                else:
                    text, confidence = str(text_conf), 1.0

                if isinstance(bbox, (list, tuple)) and len(bbox) >= 3:
                    y_center = (bbox[0][1] + bbox[2][1]) / 2
                else:
                    y_center = 0
                lines.append((y_center, text, confidence))

        if not lines:
            return ""

        lines.sort(key=lambda x: (round(x[0] / 20), x[0]))
        merged = self._merge_lines(lines)
        return merged

    async def _ocr_easyocr(self, image: Image.Image) -> str:
        """EasyOCR 识别"""
        import numpy as np
        img_array = np.array(image)
        result = await asyncio.to_thread(
            self._engine.readtext, img_array, detail=1, paragraph=False,
            width_ths=0.7, height_ths=0.5,
        )
        if not result:
            return ""

        lines = []
        for bbox, text, confidence in result:
            y_center = (bbox[0][1] + bbox[2][1]) / 2
            x_left = bbox[0][0]
            lines.append((y_center, x_left, text, confidence))

        lines.sort(key=lambda x: (round(x[0] / 15), x[0], x[1]))
        return self._merge_lines_v2(lines)

    async def _ocr_tesseract(self, image: Image.Image) -> str:
        """Tesseract 识别 (兜底)"""
        import pytesseract
        text = await asyncio.to_thread(
            pytesseract.image_to_string, image, lang="chi_sim+eng"
        )
        return text.strip()

    def _merge_lines(self, lines: List[Tuple[float, str, float]]) -> str:
        """将 OCR 识别行按阅读顺序合并"""
        if not lines:
            return ""

        current_line = ""
        current_y = round(lines[0][0] / 20)
        output = []

        for y, text, conf in lines:
            line_group = round(y / 20)
            if line_group == current_y:
                current_line += " " + text if current_line else text
            else:
                if current_line:
                    output.append(current_line)
                current_line = text
                current_y = line_group

        if current_line:
            output.append(current_line)

        return "\n".join(output)

    def _merge_lines_v2(self, lines: List[Tuple[float, float, str, float]]) -> str:
        """将 OCR 识别行按阅读顺序合并（v2，含 x 坐标）"""
        if not lines:
            return ""

        output = []
        current_line_texts = []
        current_y_group = round(lines[0][0] / 15)

        for y, x, text, conf in lines:
            line_group = round(y / 15)
            if line_group == current_y_group:
                current_line_texts.append(text)
            else:
                if current_line_texts:
                    output.append(" ".join(current_line_texts))
                current_line_texts = [text]
                current_y_group = line_group

        if current_line_texts:
            output.append(" ".join(current_line_texts))

        return "\n".join(output)

    def _load_image(self, image_input) -> Image.Image:
        """统一加载图片（支持路径 / PIL / base64）"""
        if isinstance(image_input, Image.Image):
            return image_input
        elif isinstance(image_input, str):
            if image_input.startswith("data:image"):
                header, encoded = image_input.split(",", 1)
                data = base64.b64decode(encoded)
                return Image.open(BytesIO(data))
            elif image_input.startswith(("http://", "https://")):
                import urllib.request
                with urllib.request.urlopen(image_input) as resp:
                    data = resp.read()
                return Image.open(BytesIO(data))
            else:
                path = Path(image_input)
                if path.exists():
                    return Image.open(path)
                try:
                    data = base64.b64decode(image_input)
                    return Image.open(BytesIO(data))
                except Exception:
                    raise FileNotFoundError(f"图片文件不存在: {image_input}")
        elif isinstance(image_input, bytes):
            return Image.open(BytesIO(image_input))
        else:
            raise ValueError(f"不支持的图片输入类型: {type(image_input)}")

    @property
    def engine_name(self) -> str:
        return self._engine_type
