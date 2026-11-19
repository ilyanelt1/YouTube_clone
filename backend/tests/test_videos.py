from collections.abc import Generator
from io import BytesIO
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Role, Video

VALID_MP4 = b"\x00\x00\x00\x18ftypisomvideo-data"
VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


class FakeStreamingBody:
    def iter_chunks(self, chunk_size: int = 1024 * 1024):
        yield b"te"


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


def upload(
    client: TestClient,
    token: str,
    *,
    title: str = "Demo video",
    visibility: str = "public",
    thumbnail: bool = False,
):
    files = {"file": ("demo.mp4", BytesIO(VALID_MP4), "video/mp4")}
    if thumbnail:
        files["thumbnail"] = ("cover.png", BytesIO(VALID_PNG), "image/png")
    return client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": title, "description": "A short test clip", "visibility": visibility},
        files=files,
    )


def test_upload_list_and_get_video(monkeypatch) -> None:
    client, engine = make_client()
    try:
        token = register_user(client)
        monkeypatch.setattr(
            "app.api.routes.videos.upload_video",
            lambda file_obj, object_key, content_type: None,
        )
        response = upload(client, token)
        assert response.status_code == 201
        video = response.json()
        assert video["title"] == "Demo video"
        assert video["channel_handle"] == "video_user"
        assert video["status"] == "ready"
        assert video["visibility"] == "public"

        feed = client.get("/api/v1/videos")
        assert feed.status_code == 200
        assert feed.json()["total"] == 1
        assert feed.json()["items"][0]["id"] == video["id"]

        detail = client.get(f"/api/v1/videos/{video['id']}")
        assert detail.status_code == 200
        assert detail.json()["title"] == "Demo video"

        mine = client.get("/api/v1/videos/mine", headers={"Authorization": f"Bearer {token}"})
        assert mine.status_code == 200
        assert mine.json()["total"] == 1

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
            files={"file": ("demo.mp4", BytesIO(VALID_MP4), "video/mp4")},
        )
        assert response.status_code == 401
    finally:
        close_client(client, engine)


def test_upload_rejects_invalid_video_signature() -> None:
    client, engine = make_client()
    try:
        token = register_user(client)
        response = client.post(
            "/api/v1/videos/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"title": "Not a video"},
            files={"file": ("fake.mp4", BytesIO(b"not-a-video"), "video/mp4")},
        )
        assert response.status_code == 415
    finally:
        close_client(client, engine)


def test_upload_thumbnail_and_private_video(monkeypatch) -> None:
    client, engine = make_client()
    try:
        token = register_user(client)
        monkeypatch.setattr(
            "app.api.routes.videos.upload_video",
            lambda file_obj, object_key, content_type: None,
        )
        monkeypatch.setattr(
            "app.api.routes.videos.upload_thumbnail",
            lambda file_obj, object_key, content_type: None,
        )
        response = upload(client, token, title="Private clip", visibility="private", thumbnail=True)
        assert response.status_code == 201
        video = response.json()
        assert video["thumbnail_url"] == f"/api/v1/videos/{video['id']}/thumbnail"
        assert video["visibility"] == "private"

        private_detail = client.get(f"/api/v1/videos/{video['id']}")
        assert private_detail.status_code == 200

        anonymous_client = TestClient(app)
        anonymous_response = anonymous_client.get(f"/api/v1/videos/{video['id']}")
        assert anonymous_response.status_code == 404
        anonymous_client.close()
    finally:
        close_client(client, engine)


def test_owner_can_update_and_delete_video(monkeypatch) -> None:
    client, engine = make_client()
    try:
        token = register_user(client)
        monkeypatch.setattr(
            "app.api.routes.videos.upload_video",
            lambda file_obj, object_key, content_type: None,
        )
        deleted_objects: list[str] = []
        monkeypatch.setattr(
            "app.api.routes.videos.delete_object",
            lambda object_key: deleted_objects.append(object_key),
        )
        response = upload(client, token)
        video_id = response.json()["id"]

        updated = client.patch(
            f"/api/v1/videos/{video_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Updated title", "visibility": "unlisted"},
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Updated title"
        assert updated.json()["visibility"] == "unlisted"
        assert client.get("/api/v1/videos").json()["total"] == 0

        deleted = client.delete(
            f"/api/v1/videos/{video_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert deleted.status_code == 204
        assert len(deleted_objects) == 1
        assert client.get(f"/api/v1/videos/{video_id}").status_code == 404
    finally:
        close_client(client, engine)




def test_same_visibility_patch_preserves_published_at(monkeypatch) -> None:
    client, engine = make_client()
    try:
        token = register_user(client)
        monkeypatch.setattr(
            "app.api.routes.videos.upload_video",
            lambda file_obj, object_key, content_type: None,
        )
        uploaded = upload(client, token, visibility="public")
        assert uploaded.status_code == 201
        video_id = UUID(uploaded.json()["id"])

        with Session(engine) as db:
            original_published_at = db.get(Video, video_id).published_at

        response = client.patch(
            f"/api/v1/videos/{video_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"visibility": "public"},
        )
        assert response.status_code == 200

        with Session(engine) as db:
            updated_published_at = db.get(Video, video_id).published_at

        assert updated_published_at == original_published_at
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
        uploaded = upload(client, token, title="Range test")
        assert uploaded.status_code == 201
        video_id = uploaded.json()["id"]
        calls = []

        def fake_get_video_object(object_key: str, byte_range: str | None = None) -> dict:
            calls.append(byte_range)
            return {
                "Body": FakeStreamingBody(),
                "ContentType": "video/mp4",
                "TotalLength": len(VALID_MP4),
            }

        monkeypatch.setattr("app.api.routes.videos.get_video_object", fake_get_video_object)
        response = client.get(
            f"/api/v1/videos/{video_id}/play",
            headers={"Range": "bytes=0-1"},
        )
        assert response.status_code == 206
        assert response.headers["content-range"] == f"bytes 0-1/{len(VALID_MP4)}"
        assert response.headers["content-length"] == "2"
        assert calls == ["bytes=0-1"]
    finally:
        close_client(client, engine)
