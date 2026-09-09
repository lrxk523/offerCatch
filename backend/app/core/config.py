"""LLM 多提供商配置 - 通过 LLM_PROVIDER 环境变量一键切换"""

import os
from typing import Tuple, Optional

# ---- 预设提供商配置 ----
# 每个提供商: base_url, 默认模型, 默认优化模型
PROVIDERS = {
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "Qwen/Qwen2.5-7B-Instruct",
        "resume_model": "Qwen/Qwen2.5-72B-Instruct",
        "parse_model": "Qwen/Qwen2.5-7B-Instruct",
        "api_key_env": "SILICONFLOW_API_KEY",
        "vision_model": "Qwen/Qwen3-VL-8B-Instruct",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-v4-flash",
        # resume/match 等长输出任务调用处带 extra_body reasoning_effort=none 关思考
        # （2026-09-09 实测：v4 系思考超长 12000+ tokens 后 content 空返回，关闭后稳定且快）
        # 2026-09-09 用户拍板：resume 优化统一 v4-flash + max_tokens 20000（flash 17s 快且稳，pro 可经 RESUME_MODEL 覆盖）
        "resume_model": "deepseek-v4-flash",
        "parse_model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
        "vision_model": None,  # DeepSeek API 无视觉能力（视觉统一走 VISION_*）
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
        "resume_model": "glm-4-plus",
        "parse_model": "glm-4-flash",
        "api_key_env": "ZHIPU_API_KEY",
        "vision_model": "glm-4v-flash",
    },
    "moonshot": {
        "name": "Moonshot Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "resume_model": "moonshot-v1-8k",
        "parse_model": "moonshot-v1-8k",
        "api_key_env": "MOONSHOT_API_KEY",
        "vision_model": None,  # moonshot-v1 系列无视觉
    },
    "qwen": {
        "name": "通义千问 DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "resume_model": "qwen-max",
        "parse_model": "qwen-plus",
        "api_key_env": "DASHSCOPE_API_KEY",
        "vision_model": "qwen3.5-omni-flash",
    },
    "doubao": {
        "name": "字节豆包",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-pro-4k",
        "resume_model": "doubao-pro-4k",
        "parse_model": "doubao-lite-4k",
        "api_key_env": "DOUBAO_API_KEY",
        "vision_model": None,  # 豆包视觉需独立 endpoint，暂不配置
    },
}


def get_llm_config(
    purpose: str = "default",
) -> Tuple[str, str, str]:
    """
    获取 LLM 配置 (api_key, base_url, model)。

    优先级：
    1. 各用途独立环境变量 (RESUME_MODEL, RESUME_PARSE_MODEL, MATCH_MODEL 等)
    2. LLM_PROVIDER 预设
    3. OPENAI_BASE_URL / OPENAI_MODEL / OPENAI_API_KEY 传统变量

    Args:
        purpose: 用途，可选 "default" | "resume" | "parse" | "match"

    Returns:
        (api_key, base_url, model) 三元组
    """
    # ---- 1. 确定 base_url 和 api_key ----
    provider_name = os.getenv("LLM_PROVIDER", "").lower().strip()
    provider = PROVIDERS.get(provider_name)

    if provider:
        # 使用预设提供商：base_url 固定为 provider 端点
        # key 优先 provider 专属变量 (DEEPSEEK_API_KEY 等)，回落 OPENAI_API_KEY 兼容旧配置
        # ⚠️ OPENAI_BASE_URL/OPENAI_MODEL 不参与——那是无 LLM_PROVIDER 时的自定义通道，
        #    若残留其他平台的 base_url/model 会造成 key/端点错配
        base_url = provider["base_url"]
        api_key = os.getenv(provider["api_key_env"], "")
        if not api_key or api_key.startswith("your-"):
            api_key = os.getenv("OPENAI_API_KEY", "")
    else:
        # 使用传统环境变量（自定义 OpenAI 兼容端点）
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
        api_key = os.getenv("OPENAI_API_KEY", "")

    # ---- 2. 确定 model ----
    if purpose == "jd":
        # JD 结构化抽取（原正则解析的 LLM 替代）— 默认与 parse 同级小模型
        model = os.getenv("JD_MODEL", "")
        if not model:
            model = provider["parse_model"] if provider else "Qwen/Qwen2.5-7B-Instruct"
    elif purpose == "resume":
        model = os.getenv("RESUME_MODEL", "")
        if not model:
            model = provider["resume_model"] if provider else "Qwen/Qwen2.5-72B-Instruct"
    elif purpose == "parse":
        model = os.getenv("RESUME_PARSE_MODEL", "")
        if not model:
            model = provider["parse_model"] if provider else "Qwen/Qwen2.5-7B-Instruct"
    elif purpose == "match":
        model = os.getenv("MATCH_MODEL", "")
        if not model:
            model = provider.get("resume_model", provider["default_model"]) if provider else "Qwen/Qwen2.5-72B-Instruct"
    else:
        if provider:
            model = provider["default_model"]
        else:
            model = os.getenv("OPENAI_MODEL", "")
            if not model:
                model = "Qwen/Qwen2.5-7B-Instruct"

    return api_key, base_url, model


def get_vision_config() -> Tuple[str, str, str]:
    """
    获取视觉 (VL) 模型配置 (api_key, base_url, model)。

    启用规则（必须显式配置，避免误用文本 key 导致 4xx）:
      VISION_API_KEY 或 VISION_MODEL 任一非空 → 启用云转录
    配置优先级:
      1. 独立环境变量 VISION_API_KEY / VISION_BASE_URL / VISION_MODEL
      2. 缺失项回落 LLM_PROVIDER 预设 (base_url / vision_model / api_key_env)

    未显式配置 → 返回 ("", "", "")，OCR_ENGINE=auto 时回落本地 OCR。
    VISION_MODEL=none|off|0|false 可显式禁用视觉。
    """
    api_key = os.getenv("VISION_API_KEY", "")
    base_url = os.getenv("VISION_BASE_URL", "")
    model = os.getenv("VISION_MODEL", "")

    # 显式禁用
    if model.lower() in ("none", "off", "0", "false"):
        return "", "", ""

    # 必须显式启用（VISION_API_KEY 或 VISION_MODEL 至少配一个）
    if not api_key and not model:
        return "", "", ""

    # 缺失项从当前 provider 回落
    provider_name = os.getenv("LLM_PROVIDER", "").lower().strip()
    provider = PROVIDERS.get(provider_name)
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key and provider:
            api_key = os.getenv(provider["api_key_env"], "")
    if not base_url:
        base_url = provider["base_url"] if provider else os.getenv("OPENAI_BASE_URL", "")
    if not model:
        if provider:
            model = provider.get("vision_model") or provider["default_model"]
        else:
            model = os.getenv("OPENAI_MODEL", "")

    return api_key, base_url, model


def create_openai_client(purpose: str = "default"):
    """
    创建 OpenAI 兼容客户端。

    Args:
        purpose: 用途，可选 "default" | "resume" | "parse" | "match" | "jd"

    Returns:
        (client, model) 二元组
    """
    from openai import OpenAI

    api_key, base_url, model = get_llm_config(purpose)
    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


def create_vision_client():
    """
    创建视觉 (VL) 客户端。

    Returns:
        (client, model) 二元组；未配置视觉能力时返回 (None, "")
    """
    from openai import OpenAI

    api_key, base_url, model = get_vision_config()
    if not api_key or not base_url or not model:
        return None, ""
    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model


def print_llm_status():
    """打印当前 LLM 配置状态"""
    provider_name = os.getenv("LLM_PROVIDER", "").lower().strip() or "custom"
    provider = PROVIDERS.get(provider_name)
    provider_display = provider["name"] if provider else "自定义 (OPENAI_BASE_URL)"

    _, base_url, default_model = get_llm_config("default")
    _, _, resume_model = get_llm_config("resume")
    _, _, parse_model = get_llm_config("parse")

    print(f"[LLM] 提供商: {provider_display}")
    print(f"[LLM] Base URL: {base_url}")
    print(f"[LLM] 对话模型: {default_model}")
    print(f"[LLM] 简历优化模型: {resume_model}")
    print(f"[LLM] 简历解析模型: {parse_model}")
