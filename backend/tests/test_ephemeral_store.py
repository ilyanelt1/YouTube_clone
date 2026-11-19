from uuid import UUID

from redis.exceptions import RedisError

from app.services.ephemeral_store import claim_video_view, release_video_view

VIDEO_ID = UUID("c059ba60-8bad-4ceb-bc99-e93ec2de2e12")


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool | None:
        if nx and key in self.values:
            return None
        self.values[key] = value
        self.expirations[key] = ex
        return True

    def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        return int(existed)


def test_claim_video_view_uses_an_atomic_temporary_key(monkeypatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr("app.services.ephemeral_store.get_redis_client", lambda: redis)

    first = claim_video_view(VIDEO_ID, "user:viewer-1")
    repeated = claim_video_view(VIDEO_ID, "user:viewer-1")
    another_viewer = claim_video_view(VIDEO_ID, "user:viewer-2")

    assert first is True
    assert repeated is False
    assert another_viewer is True
    assert len(redis.values) == 2
    assert set(redis.expirations.values()) == {1800}
    assert all("viewer-1" not in key and "viewer-2" not in key for key in redis.values)


def test_release_video_view_removes_a_claim_after_database_failure(monkeypatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr("app.services.ephemeral_store.get_redis_client", lambda: redis)

    assert claim_video_view(VIDEO_ID, "user:viewer-1") is True
    release_video_view(VIDEO_ID, "user:viewer-1")

    assert redis.values == {}
    assert redis.expirations == {}


def test_claim_video_view_fails_open_if_redis_is_unavailable(monkeypatch) -> None:
    class UnavailableRedis:
        def set(self, *_args, **_kwargs):
            raise RedisError("Redis is unavailable")

    monkeypatch.setattr(
        "app.services.ephemeral_store.get_redis_client",
        lambda: UnavailableRedis(),
    )

    assert claim_video_view(VIDEO_ID, "user:viewer-1") is True
