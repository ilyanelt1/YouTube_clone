from collections.abc import Generator
from io import BytesIO

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Role


class FakeStreamingBody:
    def iter_chunks(self, chunk_size: int = 1024 * 1024):
        yield b"test"


def make_client() -> tuple[TestClient, sa.Engine]:
    engine = sa.create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(Role(name="user", description="Standard registered user"))
        db.commit()

    def override_get_db() -> Generator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), engine


def close_client(client: TestClient, engine: sa.Engine) -> None:
    client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def register_user(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "video@example.com",
            "username": "video_user",
            "display_name": "Video User",
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_upload_list_and_get_video(monkeypatch) -> None:
    client, engine = make_client()
    try:
        token = register_user(client)
        monkeypatch.setattr(
            "app.api.routes.videos.upload_video",
            lambda file_obj, object_key, content_type: None,
        )
        response = client.post(
            "/api/v1/videos/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"title": "Demo video", "description": "A short test clip"},
            files={"file": ("demo.mp4", BytesIO(b"video-data"), "video/mp4")},
        )
        assert response.status_code == 201
        video = response.json()
        assert video["title"] == "Demo video"
        assert video["channel_handle"] == "video_user"
        assert video["status"] == "ready"

        feed = client.get("/api/v1/videos")
        assert feed.status_code == 200
        assert feed.json()["total"] == 1
        assert feed.json()["items"][0]["id"] == video["id"]

        detail = client.get(f"/api/v1/videos/{video['id']}")
        assert detail.status_code == 200
        assert detail.json()["title"] == "Demo video"

        missing = client.get("/api/v1/videos/00000000-0000-0000-0000-000000000000")
        assert missing.status_code == 404
    finally:
        close_client(client, engine)


def test_upload_requires_authentication() -> None:
    client, engine = make_client()
    try:
        response = client.post(
            "/api/v1/videos/upload",
            data={"title": "Demo video"},
            files={"file": ("demo.mp4", BytesIO(b"video-data"), "video/mp4")},
        )
        assert response.status_code == 401
    finally:
        close_client(client, engine)


def test_playback_supports_byte_ranges(monkeypatch) -> None:
    client, engine = make_client()
    try:
        token = register_user(client)
        monkeypatch.setattr(
            "app.api.routes.videos.upload_video",
            lambda file_obj, object_key, content_type: None,
        )
        uploaded = client.post(
            "/api/v1/videos/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"title": "Range test"},
            files={"file": ("range.mp4", BytesIO(b"data"), "video/mp4")},
        )
        assert uploaded.status_code == 201
        video_id = uploaded.json()["id"]
        calls = []

        def fake_get_video_object(object_key: str, byte_range: str | None = None) -> dict:
            calls.append(byte_range)
            return {
                "Body": FakeStreamingBody(),
                "ContentType": "video/mp4",
                "TotalLength": 4,
            }

        monkeypatch.setattr("app.api.routes.videos.get_video_object", fake_get_video_object)
        response = client.get(
            f"/api/v1/videos/{video_id}/play",
            headers={"Range": "bytes=0-1"},
        )
        assert response.status_code == 206
        assert response.headers["content-range"] == "bytes 0-1/4"
        assert response.headers["content-length"] == "2"
        assert calls == ["bytes=0-1"]
    finally:
        close_client(client, engine)
