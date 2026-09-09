"""JD 结构化解析器 — LLM/VL 替代原正则解析。

原 JDSectionSplitter/JDExtractor 正则解析已废弃（对排版敏感、鲁棒性差），
改为 LLM 直接从原文抽取结构化 JSON：
  - parse_text():  文本 LLM（purpose="jd"，默认 parse 同级模型）
  - parse_image(): 视觉模型（VISION_*，如 Qwen3.5-Omni-Flash）直读截图

输出统一为 JDParsedResult（字段与前端 / matcher 消费保持一致）。
"""

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class JDParsedResult:
    """JD 解析结果（字段兼容前端展示与 matcher 消费）"""
    # 核心字段
    job_title: str = ""               # 岗位名称
    location: str = ""                # 工作地点
    salary: str = ""                  # 薪资范围
    responsibilities: List[str] = field(default_factory=list)  # 岗位职责
    requirements: List[str] = field(default_factory=list)      # 任职要求

    # 扩展字段
    company_name: str = ""            # 公司名称
    experience: str = ""              # 经验要求
    education: str = ""               # 学历要求
    benefits: List[str] = field(default_factory=list)          # 福利待遇
    other_info: str = ""              # 其他补充信息

    # 元数据
    raw_text_preview: str = ""        # 原始文本预览
    cleaned_text: str = ""            # 清洗后的完整文本
    parse_confidence: float = 0.0     # 解析置信度


# ---------------------------------------------------------------------------
# LLM 结构化抽取 Prompt（字段 schema 由业务确认，勿随意改字段名/增减）
# ---------------------------------------------------------------------------

JD_TEXT_STRUCTURE_PROMPT = """# JD岗位文本结构化解析任务
输入：原始JD纯文本，文本格式混乱，存在换行错乱、多余空格、符号杂乱。
任务：严格从输入原文提取信息，**禁止脑补，原文没有则填null，不要编造内容**。
输出JSON，固定字段，不允许新增、删减字段：
{
  "job_title": "岗位名称，字符串，没有填null",
  "salary": "薪资范围，原样摘抄原文，无薪资填null",
  "work_location": "工作地点，原样摘抄，无填null",
  "work_experience_require": "经验要求，如3‑5年、不限，原文摘抄，无填null",
  "education_require": "学历要求，本科/硕士等，无填null",
  "benefits": ["数组，福利补贴，一条条拆分，没有为空数组[]"],
  "job_responsibility": ["数组，岗位职责，按原文分句拆分成数组，只摘抄原文，不要改写总结"],
  "job_requirement": ["数组，任职资格/任职要求，原文分句拆分，只摘抄原文，不要改写总结"],
  "other_info": "其他零散信息，原文摘抄，没有填null"
}
硬性约束：
1. 只提取原文真实存在内容，**严禁生成原文不存在的信息，禁止AI脑补补充**；
2. 岗位职责、任职要求必须拆成数组，每一条为数组的一个元素；
3. 不要输出markdown、不要输出解释文字，**只返回纯净JSON字符串，前后不要有任何多余文字**；
4. 遇到乱码、无意义符号直接忽略；
5. 不要合并、润色原文句子，尽量保留原始措辞。"""


JD_IMAGE_STRUCTURE_PROMPT = """# JD岗位图片结构化解析任务
输入：JD岗位截图（图片），可能存在长截图、模糊、倾斜、排版杂乱。
任务：读取图片中的 JD 文字，严格按图中原文提取信息，**禁止脑补，原文没有则填null，不要编造内容**。
输出JSON，固定字段，不允许新增、删减字段：
{
  "job_title": "岗位名称，字符串，没有填null",
  "salary": "薪资范围，原样摘抄图中原文，无薪资填null",
  "work_location": "工作地点，原样摘抄，无填null",
  "work_experience_require": "经验要求，如3‑5年、不限，原文摘抄，无填null",
  "education_require": "学历要求，本科/硕士等，无填null",
  "benefits": ["数组，福利补贴，一条条拆分，没有为空数组[]"],
  "job_responsibility": ["数组，岗位职责，按原文分句拆分成数组，只摘抄原文，不要改写总结"],
  "job_requirement": ["数组，任职资格/任职要求，原文分句拆分，只摘抄原文，不要改写总结"],
  "other_info": "其他零散信息，原文摘抄，没有填null"
}
硬性约束：
1. 只提取图中真实存在内容，**严禁生成图中不存在的信息，禁止AI脑补补充**；
2. 岗位职责、任职要求必须拆成数组，每一条为数组的一个元素；
3. 不要输出markdown、不要输出解释文字，**只返回纯净JSON字符串，前后不要有任何多余文字**；
4. 遇到乱码、无意义符号直接忽略；
5. 不要合并、润色原文句子，尽量保留原始措辞。"""


# LLM schema 字段 → JDParsedResult 字段映射
_LLM_FIELD_MAP = {
    "job_title": "job_title",
    "salary": "salary",
    "work_location": "location",
    "work_experience_require": "experience",
    "education_require": "education",
    "benefits": "benefits",
    "job_responsibility": "responsibilities",
    "job_requirement": "requirements",
    "other_info": "other_info",
}

_LIST_FIELDS = {"benefits", "job_responsibility", "job_requirement"}


class JDLLMParser:
    """JD 结构化解析器 — LLM 抽取（文本 + 图片/VL 双通道）"""

    _client = None
    _model = ""
    _vision_client = None
    _vision_model = ""

    # ---- 客户端懒加载 ----

    @classmethod
    def _get_text_client(cls):
        """文本 LLM 客户端（purpose="jd"）"""
        if cls._client is None:
            from app.core.config import create_openai_client
            cls._client, cls._model = create_openai_client("jd")
        return cls._client, cls._model

    @classmethod
    def _get_vision_client(cls):
        """视觉 VL 客户端（VISION_* 配置）；未配置返回 (None, "")"""
        if cls._vision_client is None:
            from app.core.config import create_vision_client
            cls._vision_client, cls._vision_model = create_vision_client()
        return cls._vision_client, cls._vision_model

    # ---- 对外接口 ----

    @classmethod
    async def parse_text(cls, text: str) -> JDParsedResult:
        """文本 LLM 抽取 JD 结构化信息"""
        text = (text or "").strip()
        client, model = cls._get_text_client()
        if not client:
            raise RuntimeError("未配置 LLM 客户端，请检查 LLM_PROVIDER 及对应 API Key 环境变量")

        result = JDParsedResult(raw_text_preview=text[:500], cleaned_text=text)

        def _call():
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": JD_TEXT_STRUCTURE_PROMPT},
                    {"role": "user", "content": text[:20000]},
                ],
                max_tokens=4096,
                temperature=0.1,
            )
            return (resp.choices[0].message.content or "").strip()

        try:
            import asyncio
            content = await asyncio.to_thread(_call)
            data = cls._extract_json(content)
            mapped = cls._to_result(data)
            mapped.raw_text_preview = text[:500]
            mapped.cleaned_text = text
            mapped.parse_confidence = 1.0
            return mapped
        except Exception as e:
            # 显式失败而非静默返回空结果：空结果会让上层误判"解析成功"（前端展示空卡片）
            raise RuntimeError(f"LLM 调用失败: {e}") from e

    @classmethod
    async def parse_image(cls, image_input: str) -> JDParsedResult:
        """视觉模型直读 JD 截图 → 结构化 JSON"""
        result = JDParsedResult()

        client, model = cls._get_vision_client()
        if not client:
            raise RuntimeError("未配置视觉模型 (VISION_API_KEY/VISION_BASE_URL/VISION_MODEL)")

        data_uri = cls._to_data_uri(image_input)

        def _call():
            resp = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": JD_IMAGE_STRUCTURE_PROMPT},
                    ],
                }],
                max_tokens=4096,
                temperature=0.1,
            )
            return (resp.choices[0].message.content or "").strip()

        try:
            import asyncio
            content = await asyncio.to_thread(_call)
            data = cls._extract_json(content)
            mapped = cls._to_result(data)
            mapped.parse_confidence = 1.0
            return mapped
        except Exception as e:
            raise RuntimeError(f"JD 图片解析失败: {e}")

    # ---- 内部工具 ----

    @staticmethod
    def _extract_json(content: str) -> dict:
        """从 LLM 返回中提取 JSON 对象（容忍 markdown 围栏/前后杂文）"""
        content = (content or "").strip()
        # 去掉 ```json ... ``` 围栏
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if fence:
            content = fence.group(1).strip()
        # 取第一个 { 到最后一个 }
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM 返回中未找到 JSON 对象")
        return json.loads(content[start:end + 1])

    @classmethod
    def _to_result(cls, data: dict) -> JDParsedResult:
        """LLM schema dict → JDParsedResult（含字段映射 + 类型规整）"""
        result = JDParsedResult()
        if not isinstance(data, dict):
            return result

        for llm_field, result_field in _LLM_FIELD_MAP.items():
            raw = data.get(llm_field)
            if raw is None:
                continue

            if llm_field in _LIST_FIELDS:
                # 列表字段：容忍 LLM 返回字符串/非列表
                if isinstance(raw, str):
                    items = [s.strip() for s in re.split(r"[\n;；。]+", raw) if s.strip()]
                elif isinstance(raw, list):
                    items = [str(s).strip() for s in raw if str(s).strip() and str(s).lower() != "null"]
                else:
                    items = []
                setattr(result, result_field, items)
            else:
                val = str(raw).strip() if raw is not None else ""
                if val.lower() == "null":
                    val = ""
                setattr(result, result_field, val)

        return result

    @staticmethod
    def _guess_mime(b64: str) -> str:
        """嗅探 base64 图片的 MIME 类型（前几字节 magic）"""
        try:
            head = base64.b64decode(b64[:32])
        except Exception:
            return "image/jpeg"
        if head.startswith(b"\x89PNG"):
            return "image/png"
        if head.startswith(b"\xff\xd8"):
            return "image/jpeg"
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    @classmethod
    def _to_data_uri(cls, image_input: str) -> str:
        """统一图片输入为 data URI（支持 data:image 前缀 / 裸 base64 / 本地路径）"""
        s = image_input.strip()
        if s.startswith("data:image"):
            return s
        # 本地路径
        if len(s) < 512 and ("/" in s or "\\" in s or "." in s) and __import__("os").path.exists(s):
            with open(s, "rb") as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode("utf-8")
            mime = cls._guess_mime(b64)
            return f"data:{mime};base64,{b64}"
        # 裸 base64（resume.py 上传路径）
        b64 = s if not s.startswith("base64,") else s[len("base64,"):]
        mime = cls._guess_mime(b64)
        return f"data:{mime};base64,{b64}"
