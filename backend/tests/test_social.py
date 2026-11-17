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


def upload_public_video(client: TestClient, token: str) -> dict:
    response = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Social test video", "visibility": "public"},
        files={"file": ("test.mp4", BytesIO(VALID_MP4), "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()


def test_reactions_comments_shares_and_subscriptions(monkeypatch) -> None:
    client, engine = make_client()
    try:
        owner_token = register(client, "creator")
        viewer_token = register(client, "viewer")
        monkeypatch.setattr(
            "app.api.routes.videos.upload_video",
            lambda file_obj, object_key, content_type: None,
        )
        video = upload_public_video(client, owner_token)
        video_id = video["id"]
        owner = {"Authorization": f"Bearer {owner_token}"}
        viewer = {"Authorization": f"Bearer {viewer_token}"}

        liked = client.put(
            f"/api/v1/videos/{video_id}/reaction",
            headers=viewer,
            json={"reaction": "like"},
        )
        assert liked.status_code == 200
        assert liked.json()["likes"] == 1
        assert liked.json()["viewer_reaction"] == "like"

        disliked = client.put(
            f"/api/v1/videos/{video_id}/reaction",
            headers=viewer,
            json={"reaction": "dislike"},
        )
        assert disliked.json()["likes"] == 0
        assert disliked.json()["dislikes"] == 1

        removed = client.put(
            f"/api/v1/videos/{video_id}/reaction",
            headers=viewer,
            json={"reaction": None},
        )
        assert removed.json()["dislikes"] == 0
        assert removed.json()["viewer_reaction"] is None

        root = client.post(
            f"/api/v1/videos/{video_id}/comments",
            headers=viewer,
            json={"body": "Great video!"},
        )
        assert root.status_code == 201
        root_id = root.json()["id"]
        reply = client.post(
            f"/api/v1/videos/{video_id}/comments",
            headers=owner,
            json={"body": "Thank you!", "parent_id": root_id},
        )
        assert reply.status_code == 201
        assert reply.json()["parent_id"] == root_id

        comments = client.get(f"/api/v1/videos/{video_id}/comments")
        assert comments.status_code == 200
        assert comments.json()["total"] == 2

        edited = client.patch(
            f"/api/v1/comments/{root_id}",
            headers=viewer,
            json={"body": "Really great video!"},
        )
        assert edited.status_code == 200
        assert edited.json()["body"] == "Really great video!"

        forbidden_edit = client.patch(
            f"/api/v1/comments/{root_id}",
            headers=owner,
            json={"body": "I am not the author"},
        )
        assert forbidden_edit.status_code == 404

        shared = client.post(f"/api/v1/videos/{video_id}/share", headers=viewer)
        assert shared.status_code == 200
        assert shared.json()["shares"] == 1
        shared_again = client.post(f"/api/v1/videos/{video_id}/share", headers=viewer)
        assert shared_again.json()["shares"] == 1
        assert f"?video={video_id}" in shared.json()["share_url"]

        reposted = client.put(f"/api/v1/videos/{video_id}/repost", headers=viewer)
        assert reposted.status_code == 200
        assert reposted.json()["reposts"] == 1
        assert reposted.json()["viewer_reposted"] is True
        reposted_again = client.put(f"/api/v1/videos/{video_id}/repost", headers=viewer)
        assert reposted_again.json()["reposts"] == 1
        undone = client.delete(f"/api/v1/videos/{video_id}/repost", headers=viewer)
        assert undone.json()["reposts"] == 0
        assert undone.json()["viewer_reposted"] is False

        subscription = client.put("/api/v1/channels/creator/subscription", headers=viewer)
        assert subscription.status_code == 200
        assert subscription.json() == {"subscribed": True, "subscribers": 1}
        unsubscribed = client.delete("/api/v1/channels/creator/subscription", headers=viewer)
        assert unsubscribed.json() == {"subscribed": False, "subscribers": 0}

        first_view = client.post(f"/api/v1/videos/{video_id}/view")
        second_view = client.post(f"/api/v1/videos/{video_id}/view")
        assert first_view.json()["views"] == 1
        assert second_view.json()["views"] == 2

        deleted = client.delete(f"/api/v1/comments/{root_id}", headers=owner)
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/videos/{video_id}/comments").json()["total"] == 0
    finally:
        close_client(client, engine)
