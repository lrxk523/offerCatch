"""JD 解析 Skill - 上传截图/文本 → OCR → 清洗 → 结构化提取"""

import json
import asyncio
from typing import Optional
from dataclasses import asdict

from app.agent.skill import Skill, SkillResult
from app.skills.common.ocr import OCREngine
from .parser import (
    JDTextCleaner,
    JDSectionSplitter,
    JDExtractor,
    JDParsedResult,
)


class JDParseSkill(Skill):
    """JD 解析 Skill"""

    name = "parse_jd"
    description = (
        "解析岗位 JD（职位描述），支持上传截图或直接输入文本。"
        "自动提取岗位名称、岗位职责、任职要求、薪资、工作地点等信息。"
    )
    keywords = [
        "jd", "JD", "职位", "岗位", "招聘", "职位描述", "岗位描述",
        "解析jd", "解析JD", "提取jd", "分析职位", "职位解析",
        "岗位要求", "职位要求", "job description", "招聘信息",
        "jd解析", "岗位解析",
    ]
    triggers = [
        "解析jd", "解析JD", "解析职位", "分析jd",
        "提取职位信息", "帮我解析这个职位", "帮我看看这个jd",
        "解析岗位", "分析这个岗位", "分析jd",
    ]

    def __init__(self):
        self._ocr: Optional[OCREngine] = None
        self._ocr_ready = False

    async def _ensure_ocr(self):
        """延迟初始化 OCR 引擎"""
        if self._ocr_ready:
            return
        self._ocr = OCREngine()
        await self._ocr.initialize()
        self._ocr_ready = True

    async def execute(
        self,
        image_path: str = "",
        image_base64: str = "",
        text: str = "",
        **kwargs,
    ) -> SkillResult:
        """
        执行 JD 解析。

        输入方式 (三选一):
          - image_path: 本地图片路径
          - image_base64: 图片的 base64 编码
          - text: 直接传入 JD 文本
        """
        try:
            raw_text = ""

            # ---- 第1步: 获取原始文本 ----
            if text:
                # 直接使用文本
                raw_text = text

            elif image_path or image_base64:
                # OCR 提取文字
                await self._ensure_ocr()
                image_input = image_base64 if image_base64 else image_path
                raw_text = await self._ocr.extract_text(image_input)
                if not raw_text or len(raw_text.strip()) < 5:
                    return SkillResult(
                        success=False,
                        message=(
                            "OCR 未能识别到有效文字，请检查图片是否清晰或尝试直接粘贴文本。"
                            f"（OCR引擎: {self._ocr.engine_name}）"
                        ),
                        data={"ocr_engine": self._ocr.engine_name},
                    )
            else:
                return SkillResult(
                    success=False,
                    message="请提供 JD 文本 (text) 或图片 (image_path/image_base64)",
                )

            # ---- 第2步: 清洗文本 ----
            cleaned_text = JDTextCleaner.clean(raw_text)

            if not cleaned_text or len(cleaned_text.strip()) < 10:
                return SkillResult(
                    success=False,
                    message="清洗后无有效内容，请确认输入的是完整的 JD 信息",
                    data={"raw_length": len(raw_text), "raw_preview": raw_text[:200]},
                )

            # ---- 第3步: 分段 ----
            sections = JDSectionSplitter.split(cleaned_text)

            # ---- 第4步: 提取结构化信息 ----
            result: JDParsedResult = JDExtractor.extract(cleaned_text, sections)

            # ---- 格式化输出 ----
            formatted = self._format_result(result)

            return SkillResult(
                success=True,
                data={
                    "job_title": result.job_title,
                    "location": result.location,
                    "salary": result.salary,
                    "education": result.education,
                    "responsibilities": result.responsibilities,
                    "requirements": result.requirements,
                    "raw_text": raw_text[:500],
                    "cleaned_text": cleaned_text[:500],
                },
                message=f"# 📋 JD 解析结果\n\n{formatted}",
                metadata={
                    "raw_length": len(raw_text),
                    "cleaned_length": len(cleaned_text),
                    "sections_found": [k for k, v in sections.items() if v],
                    "confidence": result.parse_confidence,
                },
            )

        except Exception as e:
            return SkillResult(success=False, message=f"JD 解析失败: {str(e)}")

    def _format_result(self, result: JDParsedResult) -> str:
        """格式化解析结果为可读文本，只输出用户关心的 6 个字段"""
        lines = []

        if result.job_title:
            lines.append(f"岗位名称：{result.job_title}")

        if result.location:
            lines.append(f"地点：{result.location}")

        if result.salary:
            lines.append(f"薪资：{result.salary}")

        if result.education:
            lines.append(f"学历：{result.education}")

        if result.responsibilities:
            lines.append(f"\n岗位职责：")
            for i, item in enumerate(result.responsibilities, 1):
                lines.append(f"  {i}. {item}")

        if result.requirements:
            lines.append(f"\n岗位要求：")
            for i, item in enumerate(result.requirements, 1):
                lines.append(f"  {i}. {item}")

        return "\n".join(lines)

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "JD 截图的本地文件路径，如 /path/to/jd.png。与 image_base64 二选一",
                        },
                        "image_base64": {
                            "type": "string",
                            "description": "JD 截图的 base64 编码。与 image_path 二选一",
                        },
                        "text": {
                            "type": "string",
                            "description": "直接传入 JD 文本内容（如果用户已经粘贴了文本）。与图片输入二选一",
                        },
                    },
                },
            },
        }
