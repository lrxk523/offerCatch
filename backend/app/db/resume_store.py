"""Redis 简历存储 — 上传简历后自动缓存，供后续匹配/优化复用"""

import json
from typing import Optional, Tuple
from app.db.redis_client import get_redis, _key


# 默认过期时间：24 小时
DEFAULT_TTL = 86400


def save_resume(
    session_id: str,
    raw_text: str,
    parsed: Optional[dict] = None,
    keywords: Optional[dict] = None,
    optimized: Optional[dict] = None,
    meta: Optional[dict] = None,
    ttl: int = DEFAULT_TTL,
):
    """
    将一份简历的全部数据存入 Redis 哈希。

    存储结构:
        offercatch:resume:<session_id>  (hash)
            raw_text      — OCR / 原始文本
            parsed        — 结构化解析结果 (JSON)
            keywords      — 提取的关键词 (JSON)
            optimized     — LLM 优化结果 (JSON)
            meta          — 元信息 (文件名/解析时间/引擎等) (JSON)
    """
    r = get_redis()
    key = _key(f"resume:{session_id}")

    r.hset(key, "raw_text", raw_text)

    if parsed:
        r.hset(key, "parsed", json.dumps(parsed, ensure_ascii=False))
    if keywords:
        r.hset(key, "keywords", json.dumps(keywords, ensure_ascii=False))
    if optimized:
        r.hset(key, "optimized", json.dumps(optimized, ensure_ascii=False))
    if meta:
        r.hset(key, "meta", json.dumps(meta, ensure_ascii=False))

    if ttl > 0:
        r.expire(key, ttl)


def get_resume(session_id: str) -> dict:
    """
    从 Redis 取回简历全部数据。

    Returns:
        { raw_text, parsed, keywords, optimized, meta } 均为 dict/str
        不存在的 key 不会出现在结果中
    """
    r = get_redis()
    key = _key(f"resume:{session_id}")
    data = r.hgetall(key)

    if not data:
        return {}

    result = {"raw_text": data.get("raw_text", "")}

    for field in ["parsed", "keywords", "optimized", "meta"]:
        raw = data.get(field)
        if raw:
            try:
                result[field] = json.loads(raw)
            except json.JSONDecodeError:
                result[field] = raw

    return result


def has_resume(session_id: str) -> bool:
    """检查是否有缓存简历"""
    r = get_redis()
    return bool(r.exists(_key(f"resume:{session_id}")))


def get_raw_text(session_id: str) -> Optional[str]:
    """只取原始文本"""
    r = get_redis()
    return r.hget(_key(f"resume:{session_id}"), "raw_text")


def load_resume_text(session_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    从 Redis 加载简历原始文本和姓名。
    封装的统一加载函数，避免各 Skill 重复实现相同的 Redis 读取逻辑。

    Returns:
        (raw_text, name) 二元组。找不到时 raw_text=None。
    """
    stored = get_resume(session_id)
    if not stored or not stored.get("raw_text"):
        return None, None
    raw_text = stored["raw_text"]
    parsed = stored.get("parsed", {})
    name = ""
    if isinstance(parsed, dict):
        name = parsed.get("name", "")
    return raw_text, name


def delete_resume(session_id: str):
    """删除缓存的简历"""
    r = get_redis()
    r.delete(_key(f"resume:{session_id}"))


# ============ 快捷测试 ============

if __name__ == "__main__":
    save_resume(
        session_id="test001",
        raw_text="Zhang San / 5y Python / Django Flask / Bachelor",
        parsed={"name": "Zhang San", "skills": ["Python", "Django", "Flask"]},
        meta={"source": "pdf", "pages": 1},
    )
    data = get_resume("test001")
    print("Store OK")
    print(f"  raw_text: {data.get('raw_text', '')[:50]}...")
    print(f"  parsed:   {data.get('parsed', {})}")
    print(f"  meta:     {data.get('meta', {})}")
    delete_resume("test001")
    print("Clean OK")
