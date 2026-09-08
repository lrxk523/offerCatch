"""Redis 对话历史存储 — 取代 Agent 内存中的 _conversation_history"""
import json
from typing import List, Dict, Optional
from app.db.redis_client import get_redis, _key

DEFAULT_TTL = 1800  # 30 分钟无操作自动过期


def _history_key(session_id: str) -> str:
    return _key(f"history:{session_id}")


def save_message(session_id: str, message: Dict) -> None:
    """追加一条消息到对话历史"""
    r = get_redis()
    key = _history_key(session_id)
    r.rpush(key, json.dumps(message, ensure_ascii=False))
    r.expire(key, DEFAULT_TTL)


def load_history(session_id: str, max_turns: int = 20) -> List[Dict]:
    """加载最近 N 轮对话历史（返回最旧的在前）"""
    r = get_redis()
    key = _history_key(session_id)
    raw = r.lrange(key, 0, -1)
    if not raw:
        return []
    # 只保留最近 max_turns*2 条（每条含 user + assistant）
    limit = max_turns * 2
    raw = raw[-limit:] if len(raw) > limit else raw
    return [json.loads(m) for m in raw]


def clear_history(session_id: str) -> None:
    """清空对话历史"""
    r = get_redis()
    r.delete(_history_key(session_id))


def append_history(session_id: str, messages: List[Dict]) -> None:
    """批量追加多条消息（原子操作）"""
    r = get_redis()
    key = _history_key(session_id)
    if messages:
        r.rpush(key, *[json.dumps(m, ensure_ascii=False) for m in messages])
        r.expire(key, DEFAULT_TTL)
