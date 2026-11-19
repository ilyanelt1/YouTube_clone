import os
from uuid import uuid4

import pytest
from redis import Redis

from app.core.config import get_settings
from app.services import ephemeral_store


@pytest.mark.skipif(
    not os.getenv("REDIS_TEST_URL"),
    reason="REDIS_TEST_URL is set only by the GitHub Actions Redis service",
)
def test_view_claim_uses_real_redis_and_expires_with_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_url = os.environ["REDIS_TEST_URL"]
    client = Redis.from_url(redis_url, decode_responses=True)
    video_id = uuid4()
    viewer_identity = f"integration-user:{uuid4()}"

    try:
        assert client.ping() is True
        client.flushdb()
        monkeypatch.setattr(ephemeral_store, "get_redis_client", lambda: client)

        first_claim = ephemeral_store.claim_video_view(video_id, viewer_identity)
        duplicate_claim = ephemeral_store.claim_video_view(video_id, viewer_identity)
        another_viewer_claim = ephemeral_store.claim_video_view(
            video_id, f"integration-user:{uuid4()}"
        )

        assert first_claim is True
        assert duplicate_claim is False
        assert another_viewer_claim is True

        keys = list(client.scan_iter(match=f"youtube:video-view:{video_id}:*"))
        assert len(keys) == 2
        ttl = client.ttl(keys[0])
        assert 0 < ttl <= get_settings().view_dedup_ttl_seconds

        ephemeral_store.release_video_view(video_id, viewer_identity)
        assert client.exists(keys[0]) + client.exists(keys[1]) == 1
    finally:
        client.flushdb()
        client.close()
