from collections.abc import Generator
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import password_hasher
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import AuthSession, Role, User


def make_client() -> tuple[TestClient, sessionmaker[Session], sa.Engine]:
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
    return TestClient(app), factory, engine


def close_client(client: TestClient, engine: sa.Engine) -> None:
    client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def test_register_login_refresh_and_logout_flow() -> None:
    client, factory, engine = make_client()
    try:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "username": "Test_User",
                "display_name": "Test User",
                "password": "correct-horse-battery",
            },
        )
        assert registration.status_code == 201
        body = registration.json()
        assert body["user"]["email"] == "user@example.com"
        assert body["user"]["username"] == "test_user"
        assert body["user"]["roles"] == ["user"]
        assert "refresh_token" not in body
        assert "youtube_refresh" in registration.cookies

        with factory() as db:
            user = db.scalar(sa.select(User).where(User.email == "user@example.com"))
            assert user is not None
            assert user.password_hash.startswith("$argon2")
            assert user.password_hash != "correct-horse-battery"
            assert password_hasher.verify("correct-horse-battery", user.password_hash)
            stored_session = db.scalar(sa.select(AuthSession).where(AuthSession.user_id == user.id))
            assert stored_session is not None
            assert stored_session.refresh_token_hash != registration.cookies["youtube_refresh"]
            assert len(stored_session.refresh_token_hash) == 64

        access_token = body["access_token"]
        profile = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert profile.status_code == 200
        assert profile.json()["username"] == "test_user"

        old_refresh_token = client.cookies["youtube_refresh"]
        refreshed = client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200
        new_refresh_token = client.cookies["youtube_refresh"]
        assert new_refresh_token != old_refresh_token

        logged_out = client.post("/api/v1/auth/logout")
        assert logged_out.status_code == 204
        assert "youtube_refresh" not in client.cookies
        rejected_refresh = client.post(
            "/api/v1/auth/refresh",
            cookies={"youtube_refresh": new_refresh_token},
        )
        assert rejected_refresh.status_code == 401

        logged_in = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": "TEST_USER",
                "password": "correct-horse-battery",
            },
        )
        assert logged_in.status_code == 200
        assert logged_in.json()["user"]["id"] == body["user"]["id"]
        assert "youtube_refresh" in client.cookies
    finally:
        close_client(client, engine)


def test_refresh_token_replay_revokes_the_entire_family() -> None:
    client, _, engine = make_client()
    try:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "replay@example.com",
                "username": "replay_user",
                "display_name": "Replay User",
                "password": "correct-horse-battery",
            },
        )
        assert registration.status_code == 201
        old_token = client.cookies["youtube_refresh"]

        refreshed = client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200
        current_token = client.cookies["youtube_refresh"]

        replay = client.post(
            "/api/v1/auth/refresh",
            cookies={"youtube_refresh": old_token},
        )
        assert replay.status_code == 401

        family_revoked = client.post(
            "/api/v1/auth/refresh",
            cookies={"youtube_refresh": current_token},
        )
        assert family_revoked.status_code == 401
    finally:
        close_client(client, engine)


def test_duplicate_registration_and_generic_login_error() -> None:
    client, _, engine = make_client()
    try:
        payload = {
            "email": "duplicate@example.com",
            "username": "duplicate_user",
            "display_name": "Duplicate User",
            "password": "correct-horse-battery",
        }
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201

        duplicate_email = {**payload, "username": "another_user"}
        assert client.post("/api/v1/auth/register", json=duplicate_email).status_code == 409

        duplicate_username = {**payload, "email": "another@example.com"}
        assert client.post("/api/v1/auth/register", json=duplicate_username).status_code == 409

        unknown_user = client.post(
            "/api/v1/auth/login",
            json={"identifier": "nobody@example.com", "password": "incorrect-password"},
        )
        wrong_password = client.post(
            "/api/v1/auth/login",
            json={"identifier": "duplicate_user", "password": "incorrect-password"},
        )
        assert unknown_user.status_code == 401
        assert wrong_password.status_code == 401
        assert unknown_user.json() == wrong_password.json()
    finally:
        close_client(client, engine)


def test_me_rejects_missing_invalid_and_expired_access_tokens() -> None:
    from datetime import UTC, datetime, timedelta

    import jwt

    from app.core.config import get_settings
    from app.core.security import JWT_ALGORITHM, JWT_ISSUER

    client, _, engine = make_client()
    try:
        assert client.get("/api/v1/auth/me").status_code == 401
        assert (
            client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer not-a-jwt"},
            ).status_code
            == 401
        )

        now = datetime.now(UTC)
        expired_token = jwt.encode(
            {
                "sub": "ba1f75af-4f61-4a86-a6c7-c72a92be5d50",
                "type": "access",
                "iat": now - timedelta(minutes=5),
                "exp": now - timedelta(minutes=1),
                "iss": JWT_ISSUER,
            },
            get_settings().secret_key.get_secret_value(),
            algorithm=JWT_ALGORITHM,
        )
        expired_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert expired_response.status_code == 401
    finally:
        close_client(client, engine)


def test_inactive_user_cannot_login_or_refresh() -> None:
    client, factory, engine = make_client()
    try:
        registration = client.post(
            "/api/v1/auth/register",
            json={
                "email": "inactive@example.com",
                "username": "inactive_user",
                "display_name": "Inactive User",
                "password": "correct-horse-battery",
            },
        )
        assert registration.status_code == 201
        user_id = registration.json()["user"]["id"]

        with factory() as db:
            user = db.get(User, UUID(user_id))
            assert user is not None
            user.is_active = False
            db.commit()

        login = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": "inactive_user",
                "password": "correct-horse-battery",
            },
        )
        assert login.status_code == 401

        current_refresh = client.cookies["youtube_refresh"]
        refresh = client.post(
            "/api/v1/auth/refresh",
            cookies={"youtube_refresh": current_refresh},
        )
        assert refresh.status_code == 401
    finally:
        close_client(client, engine)
