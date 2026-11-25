"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import redis

from app.config import settings


def create_redis_client():
    """Create a Redis client from REDIS_URL without pinging at import time."""
    if not settings.redis_url:
        return None
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )


r = create_redis_client()


def redis_healthy() -> bool:
    """Return True if Redis responds to PING, False otherwise."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False
