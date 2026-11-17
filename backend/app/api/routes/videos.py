from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import Channel, User, Video
from app.schemas.video import VideoList, VideoRead
from app.services.storage import create_playback_url, upload_video

router = APIRouter(prefix="/videos", tags=["videos"])
ALLOWED_VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
MAX_VIDEO_SIZE = 500 * 1024 * 1024


def _ensure_channel(db: Session, user: User) -> Channel:
    channel = db.scalar(select(Channel).where(Channel.owner_id == user.id))
    if channel is None:
        channel = Channel(
            owner_id=user.id,
            handle=user.username,
            name=user.display_name,
        )
        db.add(channel)
        db.flush()
    return channel


def _video_read(video: Video) -> VideoRead:
    if not video.storage_key:
        raise HTTPException(status_code=404, detail="Video file is unavailable")
    return VideoRead(
        id=video.id,
        title=video.title,
        description=video.description,
        status=video.status,
        visibility=video.visibility,
        file_size_bytes=video.file_size_bytes,
        mime_type=video.mime_type,
        created_at=video.created_at,
        channel_name=video.channel.name,
        channel_handle=video.channel.handle,
        playback_url=f"/api/v1/videos/{video.id}/play",
    )


@router.get("", response_model=VideoList)
def list_videos(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VideoList:
    statement = (
        select(Video)
        .join(Channel)
        .where(Video.status == "ready", Video.visibility == "public")
        .order_by(Video.created_at.desc())
    )
    count_statement = (
        select(func.count(Video.id))
        .join(Channel)
        .where(Video.status == "ready", Video.visibility == "public")
    )
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(Video.title.ilike(pattern))
        count_statement = count_statement.where(Video.title.ilike(pattern))
    videos = db.scalars(statement.offset(offset).limit(limit)).unique().all()
    return VideoList(items=[_video_read(video) for video in videos], total=db.scalar(count_statement) or 0)


@router.post("/upload", response_model=VideoRead, status_code=status.HTTP_201_CREATED)
def upload_video_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    title: Annotated[str, Form(min_length=1, max_length=120)],
    description: Annotated[str | None, Form(max_length=5000)] = None,
    file: UploadFile = File(...),
) -> VideoRead:
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="Title cannot be empty")
    content_type = (file.content_type or "").lower()
    extension = ALLOWED_VIDEO_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="Supported formats: MP4, WebM and MOV")
    if file.size is not None and file.size > MAX_VIDEO_SIZE:
        raise HTTPException(status_code=413, detail="Maximum video size is 500 MB")

    channel = _ensure_channel(db, current_user)
    object_key = f"videos/{current_user.id}/{uuid4().hex}{extension}"
    try:
        file.file.seek(0)
        upload_video(file.file, object_key, content_type)
        video = Video(
            channel_id=channel.id,
            title=clean_title,
            description=description.strip() if description else None,
            status="ready",
            visibility="public",
            storage_key=object_key,
            file_size_bytes=file.size,
            mime_type=content_type,
            published_at=datetime.now(UTC),
        )
        db.add(video)
        db.commit()
        db.refresh(video)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=502, detail="Video storage is temporarily unavailable")
    return _video_read(video)


@router.get("/{video_id}", response_model=VideoRead)
def get_video(
    video_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> VideoRead:
    video = db.scalar(
        select(Video).where(
            Video.id == video_id,
            Video.status == "ready",
            Video.visibility == "public",
        )
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return _video_read(video)


@router.get("/{video_id}/play")
def play_video(
    video_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    video = db.scalar(
        select(Video).where(
            Video.id == video_id,
            Video.status == "ready",
            Video.visibility == "public",
        )
    )
    if video is None or not video.storage_key:
        raise HTTPException(status_code=404, detail="Video not found")
    try:
        url = create_playback_url(video.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Video playback is temporarily unavailable") from exc
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
