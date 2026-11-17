import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_current_user
from app.db.session import get_db
from app.models import Channel, User, Video
from app.schemas.video import VideoList, VideoRead, VideoUpdate
from app.services.storage import (
    delete_object,
    get_video_object,
    upload_thumbnail,
    upload_video,
)

router = APIRouter(prefix="/videos", tags=["videos"])
ALLOWED_VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_VIDEO_SIZE = 500 * 1024 * 1024
MAX_THUMBNAIL_SIZE = 5 * 1024 * 1024


def _ensure_channel(db: Session, user: User) -> Channel:
    channel = db.scalar(select(Channel).where(Channel.owner_id == user.id))
    if channel is None:
        channel = Channel(owner_id=user.id, handle=user.username, name=user.display_name)
        db.add(channel)
        db.flush()
    return channel


def _file_size(file: UploadFile) -> int:
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    return size


def _validate_video(file: UploadFile) -> tuple[str, str, int]:
    content_type = (file.content_type or "").lower()
    extension = ALLOWED_VIDEO_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="Supported formats: MP4, WebM and MOV")

    size = _file_size(file)
    if size == 0:
        raise HTTPException(status_code=400, detail="The selected video is empty")
    if size > MAX_VIDEO_SIZE:
        raise HTTPException(status_code=413, detail="Maximum video size is 500 MB")

    signature = file.file.read(12)
    file.file.seek(0)
    is_mp4 = len(signature) >= 8 and signature[4:8] == b"ftyp"
    is_webm = signature.startswith(b"\x1aE\xdf\xa3")
    if (content_type in {"video/mp4", "video/quicktime"} and not is_mp4) or (
        content_type == "video/webm" and not is_webm
    ):
        raise HTTPException(
            status_code=415, detail="The file content does not match its video format"
        )
    return content_type, extension, size


def _validate_thumbnail(file: UploadFile) -> tuple[str, str, int]:
    content_type = (file.content_type or "").lower()
    extension = ALLOWED_IMAGE_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=415, detail="Thumbnail must be JPEG, PNG or WebP")

    size = _file_size(file)
    if size == 0:
        raise HTTPException(status_code=400, detail="The selected thumbnail is empty")
    if size > MAX_THUMBNAIL_SIZE:
        raise HTTPException(status_code=413, detail="Maximum thumbnail size is 5 MB")

    signature = file.file.read(12)
    file.file.seek(0)
    valid = (
        (content_type == "image/jpeg" and signature.startswith(b"\xff\xd8\xff"))
        or (content_type == "image/png" and signature.startswith(b"\x89PNG\r\n\x1a\n"))
        or (
            content_type == "image/webp"
            and signature.startswith(b"RIFF")
            and signature[8:12] == b"WEBP"
        )
    )
    if not valid:
        raise HTTPException(
            status_code=415, detail="The thumbnail content does not match its image format"
        )
    return content_type, extension, size


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
        thumbnail_url=f"/api/v1/videos/{video.id}/thumbnail" if video.thumbnail_key else None,
    )


def _get_accessible_video(
    video_id: UUID,
    db: Session,
    current_user: User | None,
) -> Video:
    video = db.scalar(select(Video).where(Video.id == video_id, Video.status == "ready"))
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.visibility == "private" and (
        current_user is None or video.channel.owner_id != current_user.id
    ):
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def _delete_storage_object(object_key: str | None) -> None:
    if object_key:
        try:
            delete_object(object_key)
        except Exception:
            pass


@router.get("", response_model=VideoList)
def list_videos(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VideoList:
    filters = [
        Video.status == "ready",
        Video.visibility == "public",
    ]
    statement = select(Video).join(Channel).where(*filters).order_by(Video.created_at.desc())
    count_statement = select(func.count(Video.id)).join(Channel).where(*filters)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(Video.title.ilike(pattern))
        count_statement = count_statement.where(Video.title.ilike(pattern))
    videos = db.scalars(statement.offset(offset).limit(limit)).unique().all()
    return VideoList(
        items=[_video_read(video) for video in videos], total=db.scalar(count_statement) or 0
    )


@router.get("/mine", response_model=VideoList)
def list_my_videos(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VideoList:
    statement = (
        select(Video)
        .join(Channel)
        .where(Channel.owner_id == current_user.id, Video.status == "ready")
        .order_by(Video.created_at.desc())
    )
    count_statement = (
        select(func.count(Video.id))
        .join(Channel)
        .where(Channel.owner_id == current_user.id, Video.status == "ready")
    )
    videos = db.scalars(statement.offset(offset).limit(limit)).unique().all()
    return VideoList(
        items=[_video_read(video) for video in videos], total=db.scalar(count_statement) or 0
    )


@router.post("/upload", response_model=VideoRead, status_code=status.HTTP_201_CREATED)
def upload_video_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=120)],
    description: Annotated[str | None, Form(max_length=5000)] = None,
    visibility: Annotated[str, Form()] = "public",
    thumbnail: Annotated[UploadFile | None, File()] = None,
) -> VideoRead:
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="Title cannot be empty")
    if visibility not in {"public", "unlisted", "private"}:
        raise HTTPException(
            status_code=422, detail="Visibility must be public, unlisted or private"
        )

    content_type, extension, video_size = _validate_video(file)
    thumbnail_metadata = _validate_thumbnail(thumbnail) if thumbnail is not None else None
    channel = _ensure_channel(db, current_user)
    video_key = f"videos/{current_user.id}/{uuid4().hex}{extension}"
    thumbnail_key = (
        f"thumbnails/{current_user.id}/{uuid4().hex}{thumbnail_metadata[1]}"
        if thumbnail_metadata
        else None
    )
    video_uploaded = False
    thumbnail_uploaded = False

    try:
        file.file.seek(0)
        upload_video(file.file, video_key, content_type)
        video_uploaded = True
        if thumbnail is not None and thumbnail_metadata is not None and thumbnail_key:
            thumbnail.file.seek(0)
            upload_thumbnail(thumbnail.file, thumbnail_key, thumbnail_metadata[0])
            thumbnail_uploaded = True

        video = Video(
            channel_id=channel.id,
            title=clean_title,
            description=description.strip() if description else None,
            status="ready",
            visibility=visibility,
            storage_key=video_key,
            thumbnail_key=thumbnail_key,
            file_size_bytes=video_size,
            mime_type=content_type,
            published_at=datetime.now(UTC) if visibility != "private" else None,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
    except Exception as exc:
        db.rollback()
        if video_uploaded:
            _delete_storage_object(video_key)
        if thumbnail_uploaded:
            _delete_storage_object(thumbnail_key)
        raise HTTPException(
            status_code=502, detail="Video upload failed. Please try again."
        ) from exc
    return _video_read(video)


@router.patch("/{video_id}", response_model=VideoRead)
def update_video(
    video_id: UUID,
    payload: VideoUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> VideoRead:
    video = db.scalar(
        select(Video).join(Channel).where(Video.id == video_id, Channel.owner_id == current_user.id)
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        title = (changes["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail="Title cannot be empty")
        video.title = title
    if "description" in changes:
        video.description = changes["description"].strip() if changes["description"] else None
    if "visibility" in changes:
        if changes["visibility"] not in {"public", "unlisted", "private"}:
            raise HTTPException(status_code=422, detail="Invalid visibility")
        video.visibility = changes["visibility"]
        video.published_at = datetime.now(UTC) if video.visibility != "private" else None

    db.commit()
    db.refresh(video)
    return _video_read(video)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    video = db.scalar(
        select(Video)
        .join(Channel)
        .where(Video.id == video_id, Channel.owner_id == current_user.id)
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    video_key = video.storage_key
    thumbnail_key = video.thumbnail_key
    db.delete(video)
    db.commit()
    _delete_storage_object(video_key)
    _delete_storage_object(thumbnail_key)


@router.get("/{video_id}/thumbnail")
def get_thumbnail(
    video_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> StreamingResponse:
    video = _get_accessible_video(video_id, db, current_user)
    if not video.thumbnail_key:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    try:
        result = get_video_object(video.thumbnail_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Thumbnail is temporarily unavailable") from exc
    return StreamingResponse(
        result["Body"].iter_chunks(chunk_size=64 * 1024),
        media_type=result.get("ContentType") or "image/jpeg",
    )


@router.get("/{video_id}", response_model=VideoRead)
def get_video(
    video_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> VideoRead:
    return _video_read(_get_accessible_video(video_id, db, current_user))


@router.get("/{video_id}/play")
def play_video(
    video_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_optional_current_user)],
) -> StreamingResponse:
    video = _get_accessible_video(video_id, db, current_user)
    if not video.storage_key:
        raise HTTPException(status_code=404, detail="Video not found")

    range_header = request.headers.get("range")
    byte_range = None
    status_code = status.HTTP_200_OK
    headers = {"Accept-Ranges": "bytes"}
    try:
        total_size = video.file_size_bytes
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or total_size is None:
                raise HTTPException(status_code=416, detail="Invalid byte range")
            start_text, end_text = match.groups()
            if start_text:
                start = int(start_text)
                end = int(end_text) if end_text else total_size - 1
            else:
                if not end_text or int(end_text) <= 0:
                    raise HTTPException(
                        status_code=416,
                        detail="Invalid byte range",
                        headers={"Content-Range": f"bytes */{total_size}"},
                    )
                suffix_length = int(end_text)
                start = max(total_size - suffix_length, 0)
                end = total_size - 1
            if start >= total_size or end < start:
                raise HTTPException(
                    status_code=416,
                    detail="Requested range is not satisfiable",
                    headers={"Content-Range": f"bytes */{total_size}"},
                )
            end = min(end, total_size - 1)
            byte_range = f"bytes={start}-{end}"
            status_code = status.HTTP_206_PARTIAL_CONTENT
            headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
            headers["Content-Length"] = str(end - start + 1)

        result = get_video_object(video.storage_key, byte_range)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Video playback is temporarily unavailable"
        ) from exc

    if total_size is None:
        total_size = result["TotalLength"]
    headers["Content-Type"] = (
        result.get("ContentType") or video.mime_type or "application/octet-stream"
    )
    if not range_header:
        headers["Content-Length"] = str(total_size)
    body = result["Body"]
    return StreamingResponse(
        body.iter_chunks(chunk_size=1024 * 1024),
        status_code=status_code,
        headers=headers,
        media_type=None,
    )
