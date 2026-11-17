from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Role, User, Video, VideoReport

router = APIRouter(prefix="/moderation", tags=["moderation"])


class ReportCreate(BaseModel):
    reason: Literal[
        "spam", "copyright", "harassment", "violence", "adult", "misinformation", "other"
    ]
    description: str | None = Field(default=None, max_length=1000)


class ReportDecision(BaseModel):
    action: Literal["hide", "dismiss"]


class UserRolesUpdate(BaseModel):
    roles: list[Literal["user", "moderator", "admin"]] = Field(min_length=1, max_length=3)


@router.post("/videos/{video_id}/reports", status_code=status.HTTP_201_CREATED)
def create_report(
    video_id: UUID,
    payload: ReportCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    video = db.get(Video, video_id)
    if video is None or video.status != "ready" or video.visibility == "private":
        raise HTTPException(status_code=404, detail="Видео не найдено")
    if video.channel.owner_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя пожаловаться на собственное видео")
    report = VideoReport(
        video_id=video.id,
        reporter_id=current_user.id,
        reason=payload.reason,
        description=payload.description.strip() if payload.description else None,
    )
    db.add(report)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Вы уже отправляли жалобу на это видео"
        ) from exc
    db.refresh(report)
    return {
        "id": str(report.id),
        "video_id": str(report.video_id),
        "reason": report.reason,
        "status": report.status,
        "created_at": report.created_at,
    }


@router.get("/reports")
def list_reports(
    current_user: Annotated[User, Depends(require_roles("moderator", "admin"))],
    db: Annotated[Session, Depends(get_db)],
    report_status: Literal["open", "resolved", "dismissed"] | None = Query(
        default="open", alias="status"
    ),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    statement = select(VideoReport).options(
        joinedload(VideoReport.video).joinedload(Video.channel),
        joinedload(VideoReport.reporter),
    )
    if report_status is not None:
        statement = statement.where(VideoReport.status == report_status)
    reports = (
        db.scalars(statement.order_by(VideoReport.created_at.asc()).limit(limit)).unique().all()
    )
    return [
        {
            "id": str(report.id),
            "video_id": str(report.video_id),
            "video_title": report.video.title,
            "video_status": report.video.status,
            "channel": report.video.channel.handle,
            "reporter": report.reporter.username,
            "reason": report.reason,
            "description": report.description,
            "status": report.status,
            "created_at": report.created_at,
        }
        for report in reports
    ]


@router.patch("/reports/{report_id}")
def decide_report(
    report_id: UUID,
    payload: ReportDecision,
    current_user: Annotated[User, Depends(require_roles("moderator", "admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    report = db.scalar(
        select(VideoReport)
        .options(joinedload(VideoReport.video))
        .where(VideoReport.id == report_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Жалоба не найдена")
    if report.status != "open":
        raise HTTPException(status_code=409, detail="Жалоба уже обработана")
    if payload.action == "hide":
        report.video.status = "blocked"
        report.status = "resolved"
    else:
        report.status = "dismissed"
    report.reviewed_by_id = current_user.id
    report.reviewed_at = datetime.now(UTC)
    db.commit()
    return {"id": str(report.id), "status": report.status, "video_status": report.video.status}


@router.get("/blocked-videos")
def list_blocked_videos(
    current_user: Annotated[User, Depends(require_roles("moderator", "admin"))],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    videos = (
        db.scalars(
            select(Video)
            .options(joinedload(Video.channel))
            .where(Video.status == "blocked")
            .order_by(Video.updated_at.desc())
            .limit(limit)
        )
        .unique()
        .all()
    )
    return [
        {
            "id": str(video.id),
            "title": video.title,
            "channel": video.channel.handle,
            "visibility": video.visibility,
        }
        for video in videos
    ]


@router.post("/videos/{video_id}/restore")
def restore_video(
    video_id: UUID,
    current_user: Annotated[User, Depends(require_roles("moderator", "admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    video = db.scalar(select(Video).where(Video.id == video_id, Video.status == "blocked"))
    if video is None:
        raise HTTPException(status_code=404, detail="Скрытое видео не найдено")
    video.status = "ready"
    db.commit()
    return {"id": str(video.id), "status": video.status}


@router.put("/users/{user_id}/roles")
def update_user_roles(
    user_id: UUID,
    payload: UserRolesUpdate,
    current_user: Annotated[User, Depends(require_roles("admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Нельзя изменять собственные роли через этот метод"
        )
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    roles = db.scalars(select(Role).where(Role.name.in_(payload.roles))).all()
    if len(roles) != len(set(payload.roles)):
        raise HTTPException(status_code=422, detail="Одна или несколько ролей не настроены")
    target.roles = roles
    db.commit()
    return {
        "user_id": str(target.id),
        "username": target.username,
        "roles": sorted(role.name for role in target.roles),
    }
