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
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "resume_model": "deepseek-chat",
        "parse_model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
        "resume_model": "glm-4-plus",
        "parse_model": "glm-4-flash",
        "api_key_env": "ZHIPU_API_KEY",
    },
    "moonshot": {
        "name": "Moonshot Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "resume_model": "moonshot-v1-8k",
        "parse_model": "moonshot-v1-8k",
        "api_key_env": "MOONSHOT_API_KEY",
    },
    "qwen": {
        "name": "通义千问 DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "resume_model": "qwen-max",
        "parse_model": "qwen-plus",
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    "doubao": {
        "name": "字节豆包",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-pro-4k",
        "resume_model": "doubao-pro-4k",
        "parse_model": "doubao-lite-4k",
        "api_key_env": "DOUBAO_API_KEY",
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
        # 使用预设提供商
        base_url = os.getenv("OPENAI_BASE_URL", provider["base_url"])
        api_key = os.getenv("OPENAI_API_KEY", os.getenv(provider["api_key_env"], ""))
        if not api_key:
            # 尝试所有可能的 API key 环境变量
            for env_name in ["OPENAI_API_KEY", provider["api_key_env"]]:
                val = os.getenv(env_name, "")
                if val and not val.startswith("sk-your-"):
                    api_key = val
                    break
    else:
        # 使用传统环境变量
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
        api_key = os.getenv("OPENAI_API_KEY", "")

    # ---- 2. 确定 model ----
    if purpose == "resume":
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
        model = os.getenv("OPENAI_MODEL", "")
        if not model:
            model = provider["default_model"] if provider else "Qwen/Qwen2.5-7B-Instruct"

    return api_key, base_url, model


def create_openai_client(purpose: str = "default"):
    """
    创建 OpenAI 兼容客户端。

    Args:
        purpose: 用途，可选 "default" | "resume" | "parse" | "match"

    Returns:
        (client, model) 二元组
    """
    from openai import OpenAI

    api_key, base_url, model = get_llm_config(purpose)
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
