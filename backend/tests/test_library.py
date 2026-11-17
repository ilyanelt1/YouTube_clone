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

VALID_MP4 = b"\x00\x00\x00\x18ftypisomvideo-data"


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


def register(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "display_name": username.title(),
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def upload_public_video(client: TestClient, token: str, title: str) -> dict:
    response = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": title, "visibility": "public"},
        files={"file": ("test.mp4", BytesIO(VALID_MP4), "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()


def test_channels_feed_history_favorites_playlists_and_notifications(monkeypatch) -> None:
    client, engine = make_client()
    try:
        owner_token = register(client, "creator")
        viewer_token = register(client, "viewer")
        owner = {"Authorization": f"Bearer {owner_token}"}
        viewer = {"Authorization": f"Bearer {viewer_token}"}
        monkeypatch.setattr(
            "app.api.routes.videos.upload_video",
            lambda file_obj, object_key, content_type: None,
        )

        first_video = upload_public_video(client, owner_token, "First channel video")
        channel = client.get("/api/v1/channels/creator", headers=viewer)
        assert channel.status_code == 200
        assert channel.json()["name"] == "Creator"
        assert channel.json()["videos"]["total"] == 1

        subscription = client.put(
            "/api/v1/channels/creator/subscription", headers=viewer
        )
        assert subscription.status_code == 200
        owner_notifications = client.get("/api/v1/notifications", headers=owner)
        assert owner_notifications.json()["unread_count"] == 1
        assert owner_notifications.json()["items"][0]["kind"] == "new_subscriber"

        second_video = upload_public_video(client, owner_token, "Second channel video")
        feed = client.get("/api/v1/feed/subscriptions", headers=viewer)
        assert feed.status_code == 200
        assert feed.json()["total"] == 2
        viewer_notifications = client.get("/api/v1/notifications", headers=viewer)
        assert viewer_notifications.json()["unread_count"] == 1
        assert viewer_notifications.json()["items"][0]["kind"] == "new_video"

        view = client.post(
            f"/api/v1/videos/{first_video['id']}/view", headers=viewer
        )
        assert view.status_code == 200
        history = client.get("/api/v1/users/me/history", headers=viewer)
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["id"] == first_video["id"]

        saved = client.put(
            f"/api/v1/videos/{first_video['id']}/favorite", headers=viewer
        )
        assert saved.json()["saved"] is True
        favorites = client.get("/api/v1/users/me/favorites", headers=viewer)
        assert favorites.json()["total"] == 1

        playlist = client.post(
            "/api/v1/playlists",
            headers=viewer,
            json={"title": "Weekend", "visibility": "private"},
        )
        assert playlist.status_code == 201
        playlist_id = playlist.json()["id"]
        added = client.post(
            f"/api/v1/playlists/{playlist_id}/videos/{second_video['id']}",
            headers=viewer,
        )
        assert added.status_code == 200
        details = client.get(f"/api/v1/playlists/{playlist_id}", headers=viewer)
        assert details.status_code == 200
        assert details.json()["videos"]["total"] == 1

        marked = client.post(
            f"/api/v1/notifications/{viewer_notifications.json()['items'][0]['id']}/read",
            headers=viewer,
        )
        assert marked.status_code == 200
        assert client.get("/api/v1/notifications", headers=viewer).json()["unread_count"] == 0

        cleared = client.delete("/api/v1/users/me/history", headers=viewer)
        assert cleared.status_code == 200
        assert client.get("/api/v1/users/me/history", headers=viewer).json()["total"] == 0
    finally:
        close_client(client, engine)
