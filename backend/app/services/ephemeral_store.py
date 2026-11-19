import hashlib
import logging
from functools import lru_cache
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """Create a lazy Redis connection pool shared by the API process."""
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
        health_check_interval=30,
    )


def close_redis_client() -> None:
    """Close the shared Redis connection pool during application shutdown."""
    if get_redis_client.cache_info().currsize:
        get_redis_client().close()
    get_redis_client.cache_clear()


def claim_video_view(video_id: UUID, viewer_identity: str) -> bool:
    """Atomically claim one view per video/viewer until the configured TTL expires.

    Only a SHA-256 digest of the viewer identity is stored in Redis. Redis SET NX
    makes the check atomic across concurrent API workers.
    """
    viewer_digest = hashlib.sha256(viewer_identity.encode("utf-8")).hexdigest()
    key = f"youtube:video-view:{video_id}:{viewer_digest}"

    try:
        return bool(
            get_redis_client().set(
                key,
                "1",
                nx=True,
                ex=get_settings().view_dedup_ttl_seconds,
            )
        )
    except RedisError:
        # View counting is auxiliary: keep the endpoint available when Redis is
        # temporarily down, while making the reduced deduplication explicit.
        logger.warning("Redis unavailable; skipping video-view deduplication", exc_info=True)
        return True
