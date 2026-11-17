from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.models import Role, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.services.auth import (
    authenticate_user,
    create_refresh_session,
    revoke_refresh_session,
    rotate_refresh_session,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
REFRESH_COOKIE_PATH = "/api/v1"


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client is not None else None
    return user_agent, ip_address


def _build_token_response(user: User) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead(
            id=user.id,
            email=user.email,
            username=user.username,
            display_name=user.display_name,
            is_verified=user.is_verified,
            roles=sorted(role.name for role in user.roles),
        ),
    )


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.app_env.casefold() not in {"development", "dev", "test"},
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.app_env.casefold() not in {"development", "dev", "test"},
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    email = str(payload.email).strip().casefold()
    username = payload.username.strip().casefold()
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Display name cannot be empty",
        )

    existing_user = db.scalar(
        select(User.id).where(or_(User.email == email, User.username == username))
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already registered",
        )

    default_role = db.scalar(select(Role).where(Role.name == "user"))
    if default_role is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default user role is not configured",
        )

    user = User(
        email=email,
        username=username,
        display_name=display_name,
        password_hash=hash_password(payload.password),
    )
    user.roles.append(default_role)
    db.add(user)

    try:
        db.flush()
        user_agent, ip_address = _request_metadata(request)
        refresh_token = create_refresh_session(db, user, user_agent, ip_address)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already registered",
        ) from exc

    db.refresh(user)
    _set_refresh_cookie(response, refresh_token)
    return _build_token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = authenticate_user(db, payload.identifier, payload.password)
    if user is None:
        raise _unauthorized()

    user_agent, ip_address = _request_metadata(request)
    refresh_token = create_refresh_session(db, user, user_agent, ip_address)
    db.commit()
    _set_refresh_cookie(response, refresh_token)
    return _build_token_response(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    refresh_token = request.cookies.get(get_settings().refresh_cookie_name)
    if not refresh_token:
        raise _unauthorized()

    user_agent, ip_address = _request_metadata(request)
    result = rotate_refresh_session(db, refresh_token, user_agent, ip_address)
    if result is None:
        raise _unauthorized()

    user, new_refresh_token = result
    _set_refresh_cookie(response, new_refresh_token)
    return _build_token_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    refresh_token = request.cookies.get(get_settings().refresh_cookie_name)
    if refresh_token:
        revoke_refresh_session(db, refresh_token)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    return UserRead(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        display_name=current_user.display_name,
        is_verified=current_user.is_verified,
        roles=sorted(role.name for role in current_user.roles),
    )
