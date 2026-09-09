"""JD 解析 Skill - 上传截图/文本 → LLM/VL 结构化提取 → 结果展示"""

import json
from typing import Optional

from app.agent.skill import Skill, SkillResult
from .parser import JDLLMParser, JDParsedResult


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

    async def execute(
        self,
        image_path: str = "",
        image_base64: str = "",
        text: str = "",
        **kwargs,
    ) -> SkillResult:
        """
        执行 JD 结构化解析。

        输入方式 (三选一):
          - image_path: 本地图片路径
          - image_base64: 图片的 base64 编码
          - text: 直接传入 JD 文本
        """
        try:
            raw_text = ""
            result: Optional[JDParsedResult] = None

            # ---- 第1步: 获取结构化结果 ----
            if text:
                # 文本直通 LLM 结构化抽取
                raw_text = text
                result = await JDLLMParser.parse_text(text)

            elif image_path or image_base64:
                # 视觉模型直读截图（无需先 OCR 再正则）
                image_input = image_base64 if image_base64 else image_path
                try:
                    result = await JDLLMParser.parse_image(image_input)
                except Exception as e:
                    return SkillResult(
                        success=False,
                        message=(
                            f"JD 图片解析失败: {e}。"
                            "请确认已配置视觉模型 (VISION_API_KEY/VISION_BASE_URL/VISION_MODEL)，"
                            "或尝试直接粘贴 JD 文本。"
                        ),
                    )
            else:
                return SkillResult(
                    success=False,
                    message="请提供 JD 文本 (text) 或图片 (image_path/image_base64)",
                )

            if result is None:
                return SkillResult(success=False, message="JD 解析未产生结果")

            # ---- 第2步: 格式化展示 ----
            formatted = self._format_result(result)

            return SkillResult(
                success=True,
                data={
                    "job_title": result.job_title,
                    "location": result.location,
                    "salary": result.salary,
                    "education": result.education,
                    "experience": result.experience,
                    "benefits": result.benefits,
                    "responsibilities": result.responsibilities,
                    "requirements": result.requirements,
                    "other_info": result.other_info,
                    "raw_text": raw_text[:500],
                    "cleaned_text": raw_text[:500],
                },
                message=f"# 📋 JD 解析结果\n\n{formatted}",
                metadata={
                    "raw_length": len(raw_text),
                    "parse_mode": "llm_text" if text else "vl_image",
                },
            )

        except Exception as e:
            return SkillResult(success=False, message=f"JD 解析失败: {str(e)}")

    def _format_result(self, result: JDParsedResult) -> str:
        """格式化解析结果为可读文本"""
        lines = []

        if result.job_title:
            lines.append(f"岗位名称：{result.job_title}")

        if result.location:
            lines.append(f"地点：{result.location}")

        if result.salary:
            lines.append(f"薪资：{result.salary}")

        if result.experience:
            lines.append(f"经验：{result.experience}")

        if result.education:
            lines.append(f"学历：{result.education}")

        if result.benefits:
            lines.append(f"福利：{'、'.join(result.benefits)}")

        if result.responsibilities:
            lines.append(f"\n岗位职责：")
            for i, item in enumerate(result.responsibilities, 1):
                lines.append(f"  {i}. {item}")

        if result.requirements:
            lines.append(f"\n岗位要求：")
            for i, item in enumerate(result.requirements, 1):
                lines.append(f"  {i}. {item}")

        if result.other_info:
            lines.append(f"\n其他信息：{result.other_info}")

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
                        "image_base64": {
                            "type": "string",
                            "description": "JD 截图的 base64 编码",
                        },
                        "text": {
                            "type": "string",
                            "description": "直接传入 JD 文本内容（如果用户已经粘贴了文本）。与图片输入二选一",
                        },
                    },
                },
            },
        }
