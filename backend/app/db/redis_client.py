"""Redis 连接工具 — 连接池 + 常用操作封装（连接失败时静默降级为内存空实现）"""

import os
import json
import time
import logging
from typing import Optional, Any, Union
from redis import Redis, ConnectionPool

logger = logging.getLogger(__name__)


class RedisConfig:
    """Redis 连接配置 — 优先从环境变量读取"""

    HOST = os.getenv("REDIS_HOST", "localhost")
    PORT = int(os.getenv("REDIS_PORT", "6379"))
    DB = int(os.getenv("REDIS_DB", "0"))
    PASSWORD = os.getenv("REDIS_PASSWORD", "")
    PREFIX = "offercatch:"


class _NullRedis:
    """Redis 不可用时的内存降级存根。

    所有方法返回类型安全的空值（不抛异常），使上层（chat_history/resume_store/
    缓存）在无 Redis 时静默降级：对话退化为纯内存、缓存不命中但功能不中断。
    """

    def ping(self) -> bool:
        return False

    def get(self, *a, **k):
        return None

    def set(self, *a, **k) -> bool:
        return True

    def delete(self, *a, **k) -> int:
        return 0

    def exists(self, *a, **k) -> int:
        return 0

    def ttl(self, *a, **k) -> int:
        return -2

    def expire(self, *a, **k) -> bool:
        return True

    def rpush(self, *a, **k) -> int:
        return 0

    def lpush(self, *a, **k) -> int:
        return 0

    def rpop(self, *a, **k):
        return None

    def lrange(self, *a, **k) -> list:
        return []

    def hset(self, *a, **k) -> int:
        return 0

    def hget(self, *a, **k):
        return None

    def hgetall(self, *a, **k) -> dict:
        return {}

    def incrby(self, *a, **k) -> int:
        return 0

    def close(self):
        pass

    def disconnect(self):
        pass


_pool: Optional[ConnectionPool] = None
_client: Optional[Union[Redis, _NullRedis]] = None
_null: Optional[_NullRedis] = None
_last_fail_ts: float = 0.0
_RETRY_INTERVAL = 30.0  # 失败后 30s 内不再重连，避免每次调用都等超时
_connect_warned = False


def _get_null() -> _NullRedis:
    global _null
    if _null is None:
        _null = _NullRedis()
    return _null


def get_redis() -> Union[Redis, _NullRedis]:
    """获取 Redis 客户端单例（连接池复用）。

    连接失败时静默降级为 _NullRedis（内存空实现），并带 30s 退避自动重连；
    Redis 中途恢复后无需重启进程即可自动重新生效。
    """
    global _pool, _client, _last_fail_ts, _connect_warned

    # 已有可用连接
    if _client is not None and not isinstance(_client, _NullRedis):
        return _client

    # 降级态且在退避期内 → 直接用空实现，不阻塞
    if isinstance(_client, _NullRedis) and time.monotonic() - _last_fail_ts < _RETRY_INTERVAL:
        return _client

    # 首次尝试或退避期满 → 尝试建立真实连接
    try:
        kwargs = {
            "host": RedisConfig.HOST,
            "port": RedisConfig.PORT,
            "db": RedisConfig.DB,
            "decode_responses": True,
            "socket_connect_timeout": 2,
            "socket_keepalive": True,
            "protocol": 2,  # RESP2，兼容旧版 Redis
        }
        if RedisConfig.PASSWORD:
            kwargs["password"] = RedisConfig.PASSWORD

        pool = ConnectionPool(max_connections=10, **kwargs)
        client = Redis(connection_pool=pool)
        if client.ping():
            _pool, _client = pool, client
            if _connect_warned:
                logger.info("[Redis] 连接恢复，已切换为真实 Redis")
                _connect_warned = False
            return client
        pool.disconnect()
        raise ConnectionError("ping failed")
    except Exception as e:
        _last_fail_ts = time.monotonic()
        if not _connect_warned:
            logger.warning("[Redis] 连接失败(%s)，降级为内存模式(对话不持久化/缓存不生效)，30s 后自动重试", e)
            _connect_warned = True
        _client = _get_null()
        return _client


def close_redis():
    """关闭 Redis 连接池"""
    global _pool, _client
    if _client is not None and not isinstance(_client, _NullRedis):
        _client.close()
    if _pool:
        _pool.disconnect()
    _pool = None
    _client = None


def _key(name: str) -> str:
    """生成带前缀的 key"""
    return f"{RedisConfig.PREFIX}{name}"


# ---- 字符串操作 ----


def set_str(key: str, value: str, ttl: Optional[int] = None) -> bool:
    """设置字符串，可选过期时间（秒）"""
    return get_redis().set(_key(key), value, ex=ttl) or True


def get_str(key: str) -> Optional[str]:
    """获取字符串"""
    return get_redis().get(_key(key))


def delete(*keys: str):
    """批量删除 key"""
    if keys:
        get_redis().delete(*[_key(k) for k in keys])


def exists(key: str) -> bool:
    """检查 key 是否存在"""
    return bool(get_redis().exists(_key(key)))


def ttl(key: str) -> int:
    """获取 key 剩余过期时间（秒），-1 永不过期，-2 不存在"""
    return get_redis().ttl(_key(key))


# ---- JSON 序列化 ----


def set_json(key: str, data: Union[dict, list], ttl: Optional[int] = None) -> bool:
    """存入 JSON 对象"""
    return set_str(key, json.dumps(data, ensure_ascii=False), ttl=ttl)


def get_json(key: str) -> Optional[Union[dict, list]]:
    """取出 JSON 对象"""
    raw = get_str(key)
    return json.loads(raw) if raw else None


# ---- 哈希操作 ----


def hset(key: str, mapping: dict) -> int:
    """设置哈希字段"""
    return get_redis().hset(_key(key), mapping=mapping)


def hget(key: str, field: str) -> Optional[str]:
    """获取哈希字段"""
    return get_redis().hget(_key(key), field)


def hgetall(key: str) -> dict:
    """获取哈希全部字段"""
    return get_redis().hgetall(_key(key))


# ---- 列表操作 ----


def lpush(key: str, *values: str) -> int:
    """左入队"""
    return get_redis().lpush(_key(key), *values)


def rpop(key: str, count: Optional[int] = None) -> Optional[Any]:
    """右出队"""
    if count:
        return get_redis().rpop(_key(key), count=count)  # type: ignore
    return get_redis().rpop(_key(key))


def lrange(key: str, start: int = 0, end: int = -1) -> list:
    """获取列表范围"""
    return get_redis().lrange(_key(key), start, end)


# ---- 计数器 ----


def incr(key: str, amount: int = 1) -> int:
    """自增"""
    return get_redis().incrby(_key(key), amount)


# ---- 健康检查 ----

def ping() -> bool:
    """测试连接是否正常"""
    try:
        return get_redis().ping()
    except Exception:
        return False

# ============ 便捷入口 ============

if __name__ == "__main__":
    print(f"连接 Redis: {RedisConfig.HOST}:{RedisConfig.PORT} (db={RedisConfig.DB})")
    if ping():
        print("✓ 连接成功")

        # 简单读写测试
        set_str("test_key", "hello from offercatch", ttl=60)
        print(f"  set: test_key = '{get_str('test_key')}'")
        print(f"  ttl: {ttl('test_key')} 秒")
        delete("test_key")
        print(f"  删除后 exists: {exists('test_key')}")

        set_json("test_json", {"name": "张三", "score": 95})
        print(f"  JSON: {get_json('test_json')}")
        delete("test_json")

        print("✓ 功能验证通过")
    else:
        print("✗ 连接失败，请确认 Redis 服务已启动")
