"""转录文本缓存 — 文件内容 MD5 为 key，避免同一文件重复调用云转录/OCR。

存储: Redis key `offercatch:ocr:<md5>` → plain_text，TTL 24h。
Redis 不可用时静默跳过（缓存只是优化，不影响主流程）。
"""

import hashlib
from typing import Optional

from app.db.redis_client import get_redis, _key

DEFAULT_TTL = 86400  # 24 小时


def file_md5(contents: bytes) -> str:
    """计算文件内容 MD5（缓存 key 用，同一文件重复上传命中）"""
    return hashlib.md5(contents).hexdigest()


def get_text_cache(content_hash: str) -> str:
    """按文件 hash 取缓存文本；无缓存/Redis 异常返回空串"""
    try:
        r = get_redis()
        cached = r.get(_key(f"ocr:{content_hash}"))
        return cached if cached else ""
    except Exception as e:
        print(f"[OCR-Cache] 读取缓存失败(忽略): {e}")
        return ""


def set_text_cache(content_hash: str, text: str, ttl: int = DEFAULT_TTL) -> None:
    """写入转录缓存；Redis 异常静默忽略"""
    if not text or not content_hash:
        return
    try:
        r = get_redis()
        r.set(_key(f"ocr:{content_hash}"), text, ex=ttl)
    except Exception as e:
        print(f"[OCR-Cache] 写入缓存失败(忽略): {e}")
