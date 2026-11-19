from collections.abc import Iterator

import pytest


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expirations[key] = ex
        return True

    def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        return int(existed)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRedis]:
    redis = FakeRedis()
    monkeypatch.setattr("app.api.routes.social.get_redis_client", lambda: redis)
    yield redis
