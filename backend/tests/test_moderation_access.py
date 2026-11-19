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
from app.models import Role, User

VALID_MP4 = b"\x00\x00\x00\x18ftypisomvideo-data"


def make_client() -> tuple[TestClient, sessionmaker[Session], sa.Engine]:
    engine = sa.create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                Role(name="user", description="Обычный пользователь"),
                Role(name="moderator", description="Модератор"),
                Role(name="admin", description="Администратор"),
            ]
        )
        db.commit()

    def override_get_db() -> Generator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), factory, engine


def close_client(client: TestClient, engine: sa.Engine) -> None:
    client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def register(client: TestClient, username: str) -> tuple[str, str]:
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
    body = response.json()
    return body["access_token"], body["user"]["id"]


def upload_video(client: TestClient, token: str, visibility: str, monkeypatch) -> dict:
    monkeypatch.setattr(
        "app.api.routes.videos.upload_video",
        lambda file_obj, object_key, content_type: None,
    )
    response = client.post(
        "/api/v1/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Проверочное видео", "visibility": visibility},
        files={"file": ("test.mp4", BytesIO(VALID_MP4), "video/mp4")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_roles_private_video_grants_and_moderation(monkeypatch) -> None:
    client, factory, engine = make_client()
    try:
        owner_token, owner_id = register(client, "creator")
        viewer_token, viewer_id = register(client, "viewer")
        reporter_token, _ = register(client, "another_viewer")
        moderator_token, moderator_id = register(client, "moderator_user")
        owner = {"Authorization": f"Bearer {owner_token}"}
        viewer = {"Authorization": f"Bearer {viewer_token}"}
        moderator = {"Authorization": f"Bearer {moderator_token}"}

        private_video = upload_video(client, owner_token, "private", monkeypatch)
        video_id = private_video["id"]

        assert client.get(f"/api/v1/videos/{video_id}").status_code == 404
        assert client.get(f"/api/v1/videos/{video_id}", headers=viewer).status_code == 404
        assert client.get(f"/api/v1/videos/{video_id}/comments", headers=viewer).status_code == 404
        assert (
            client.get(f"/api/v1/videos/{video_id}/engagement", headers=viewer).status_code == 404
        )
        assert client.post(f"/api/v1/videos/{video_id}/view", headers=viewer).status_code == 404
        assert client.get(f"/api/v1/videos/{video_id}", headers=owner).status_code == 200

        granted = client.put(
            f"/api/v1/videos/{video_id}/access-grants",
            headers=owner,
            json={"username": "VIEWER"},
        )
        assert granted.status_code == 200
        assert client.get(f"/api/v1/videos/{video_id}", headers=viewer).status_code == 200
        assert client.get(f"/api/v1/videos/{video_id}/comments", headers=viewer).status_code == 200
        assert (
            client.get(f"/api/v1/videos/{video_id}/engagement", headers=viewer).status_code == 200
        )
        assert client.post(f"/api/v1/videos/{video_id}/view", headers=viewer).status_code == 200
        assert client.get("/api/v1/users/me/history", headers=viewer).json()["total"] == 1
        assert (
            client.get(f"/api/v1/videos/{video_id}/access-grants", headers=viewer).status_code
            == 404
        )

        revoked = client.delete(
            f"/api/v1/videos/{video_id}/access-grants/{viewer_id}",
            headers=owner,
        )
        assert revoked.status_code == 204
        assert client.get(f"/api/v1/videos/{video_id}", headers=viewer).status_code == 404
        assert client.get("/api/v1/users/me/history", headers=viewer).json()["total"] == 0

        public_video = upload_video(client, owner_token, "public", monkeypatch)
        report = client.post(
            f"/api/v1/moderation/videos/{public_video['id']}/reports",
            headers=viewer,
            json={"reason": "spam", "description": "Проверочная жалоба"},
        )
        assert report.status_code == 201
        assert (
            client.post(
                f"/api/v1/moderation/videos/{public_video['id']}/reports",
                headers=viewer,
                json={"reason": "spam"},
            ).status_code
            == 409
        )
        second_report = client.post(
            f"/api/v1/moderation/videos/{public_video['id']}/reports",
            headers={"Authorization": f"Bearer {reporter_token}"},
            json={"reason": "copyright"},
        )
        assert second_report.status_code == 201

        assert client.get("/api/v1/moderation/reports", headers=viewer).status_code == 403
        assert client.get("/api/v1/moderation/reports").status_code == 401

        with factory() as db:
            moderator_user = db.get(User, UUID(moderator_id))
            admin_role = db.scalar(sa.select(Role).where(Role.name == "admin"))
            assert moderator_user is not None and admin_role is not None
            moderator_user.roles.append(db.scalar(sa.select(Role).where(Role.name == "moderator")))
            db.commit()

        reports = client.get("/api/v1/moderation/reports", headers=moderator)
        assert reports.status_code == 200
        assert len(reports.json()) == 2
        decision = client.patch(
            f"/api/v1/moderation/reports/{report.json()['id']}",
            headers=moderator,
            json={"action": "hide"},
        )
        assert decision.status_code == 200
        assert decision.json()["video_status"] == "blocked"
        assert client.get(f"/api/v1/videos/{public_video['id']}").status_code == 404
        assert client.get("/api/v1/moderation/reports", headers=moderator).json() == []
        resolved_reports = client.get(
            "/api/v1/moderation/reports?status=resolved", headers=moderator
        )
        assert len(resolved_reports.json()) == 2
        mine = client.get("/api/v1/videos/mine", headers=owner)
        blocked_owner_video = next(
            item for item in mine.json()["items"] if item["id"] == public_video["id"]
        )
        assert blocked_owner_video["status"] == "blocked"

        blocked = client.get("/api/v1/moderation/blocked-videos", headers=moderator)
        assert blocked.status_code == 200
        assert blocked.json()[0]["id"] == public_video["id"]
        restored = client.post(
            f"/api/v1/moderation/videos/{public_video['id']}/restore",
            headers=moderator,
        )
        assert restored.status_code == 200
        assert client.get(f"/api/v1/videos/{public_video['id']}").status_code == 200

        with factory() as db:
            owner_user = db.get(User, UUID(owner_id))
            admin_role = db.scalar(sa.select(Role).where(Role.name == "admin"))
            assert owner_user is not None and admin_role is not None
            owner_user.roles.append(admin_role)
            db.commit()

        admin_login = client.post(
            "/api/v1/auth/login",
            json={"identifier": "creator", "password": "correct-horse-battery"},
        )
        assert admin_login.status_code == 200
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        role_update = client.put(
            f"/api/v1/moderation/users/{viewer_id}/roles",
            headers=admin_headers,
            json={"roles": ["user", "moderator"]},
        )
        assert role_update.status_code == 200
        assert role_update.json()["roles"] == ["moderator", "user"]
        assert (
            client.put(
                f"/api/v1/moderation/users/{owner_id}/roles",
                headers=admin_headers,
                json={"roles": ["user"]},
            ).status_code
            == 400
        )
    finally:
        close_client(client, engine)
