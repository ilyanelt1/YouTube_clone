from functools import lru_cache
from hashlib import sha256
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

VIEW_DEDUPLICATION_TTL_SECONDS = 30 * 60


class ViewStoreUnavailable(Exception):
    """Raised when Redis cannot safely deduplicate a view."""


@lru_cache
def get_redis_client() -> Redis:
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
        health_check_interval=30,
    )


def make_view_key(
    video_id: UUID,
    user_id: UUID | None,
    client_ip: str | None,
    user_agent: str | None,
) -> str:
    if user_id is not None:
        viewer_identity = f"user:{user_id}"
    else:
        viewer_identity = f"anonymous:{client_ip or 'unknown'}:{user_agent or 'unknown'}"

    viewer_hash = sha256(viewer_identity.encode("utf-8")).hexdigest()
    return f"views:dedupe:{video_id}:{viewer_hash}"


def mark_view_once(redis_client: Redis, key: str) -> bool:
    try:
        return bool(redis_client.set(key, "1", nx=True, ex=VIEW_DEDUPLICATION_TTL_SECONDS))
    except RedisError as exc:
        raise ViewStoreUnavailable from exc


def release_view_key(redis_client: Redis, key: str) -> None:
    try:
        redis_client.delete(key)
    except RedisError:
        # A stale key expires automatically; the failed DB transaction is not counted.
        pass
