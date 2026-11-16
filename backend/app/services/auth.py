from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.models import AuthSession, User


def authenticate_user(db: Session, identifier: str, password: str) -> User | None:
    normalized_identifier = identifier.strip().casefold()
    user = db.scalar(
        select(User).where(
            or_(
                User.email == normalized_identifier,
                User.username == normalized_identifier,
            )
        )
    )
    stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password, stored_hash)

    if user is None or not password_is_valid or not user.is_active:
        return None

    return user


def create_refresh_session(
    db: Session,
    user: User,
    user_agent: str | None,
    ip_address: str | None,
) -> str:
    settings = get_settings()
    raw_token = create_refresh_token()
    db.add(
        AuthSession(
            user_id=user.id,
            family_id=uuid4(),
            refresh_token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address[:45] if ip_address else None,
        )
    )
    return raw_token


def _revoke_session_family(db: Session, family_id: UUID, now: datetime) -> None:
    sessions = db.scalars(
        select(AuthSession)
        .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
        .with_for_update()
    )
    for auth_session in sessions:
        auth_session.revoked_at = now


def rotate_refresh_session(
    db: Session,
    raw_token: str,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[User, str] | None:
    token_hash = hash_refresh_token(raw_token)
    auth_session = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_token_hash == token_hash)
        .with_for_update()
    )
    if auth_session is None:
        return None

    now = datetime.now(UTC)
    if auth_session.revoked_at is not None:
        _revoke_session_family(db, auth_session.family_id, now)
        db.commit()
        return None

    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        auth_session.revoked_at = now
        db.commit()
        return None

    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        _revoke_session_family(db, auth_session.family_id, now)
        db.commit()
        return None

    auth_session.revoked_at = now
    new_raw_token = create_refresh_token()
    settings = get_settings()
    db.add(
        AuthSession(
            user_id=user.id,
            family_id=auth_session.family_id,
            refresh_token_hash=hash_refresh_token(new_raw_token),
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address[:45] if ip_address else None,
        )
    )
    db.commit()
    return user, new_raw_token


def revoke_refresh_session(db: Session, raw_token: str) -> None:
    auth_session = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    if auth_session is not None and auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(UTC)
        db.commit()
