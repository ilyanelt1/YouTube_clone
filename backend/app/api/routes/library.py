from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_current_user
from app.db.session import get_db
from app.models import (
    Channel,
    ChannelSubscription,
    Notification,
    Playlist,
    PlaylistItem,
    SavedVideo,
    User,
    Video,
    VideoViewHistory,
)
from app.schemas.video import VideoList
from app.services.video_access import get_accessible_video, video_access_filter
from app.services.video_serialization import serialize_video

router = APIRouter(tags=["channels", "library", "notifications"])


class PlaylistCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    visibility: Literal["public", "unlisted", "private"] = "private"


class PlaylistUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    visibility: Literal["public", "unlisted", "private"] | None = None


def _video_list(videos: list[Video], total: int) -> VideoList:
    return VideoList(items=[serialize_video(video) for video in videos], total=total)


def _playlist_access(playlist_id: UUID, db: Session, user: User | None) -> Playlist:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or (
        playlist.visibility == "private" and (user is None or playlist.owner_id != user.id)
    ):
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist


def _playlist_summary(playlist: Playlist, db: Session) -> dict:
    count = (
        db.scalar(
            select(func.count())
            .select_from(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist.id)
        )
        or 0
    )
    return {
        "id": playlist.id,
        "title": playlist.title,
        "description": playlist.description,
        "visibility": playlist.visibility,
        "created_at": playlist.created_at,
        "video_count": count,
    }


@router.get("/channels/{handle}")
def get_channel(
    handle: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    channel = db.scalar(select(Channel).where(Channel.handle == handle))
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    videos_query = (
        select(Video)
        .where(
            Video.channel_id == channel.id,
            Video.status == "ready",
            Video.visibility == "public",
        )
        .order_by(Video.published_at.desc(), Video.created_at.desc())
    )
    total = (
        db.scalar(
            select(func.count())
            .select_from(Video)
            .where(
                Video.channel_id == channel.id,
                Video.status == "ready",
                Video.visibility == "public",
            )
        )
        or 0
    )
    videos = db.scalars(videos_query.offset(offset).limit(limit)).unique().all()
    public_playlists = db.scalars(
        select(Playlist)
        .where(Playlist.owner_id == channel.owner_id, Playlist.visibility == "public")
        .order_by(Playlist.created_at.desc())
    ).all()
    subscribers = (
        db.scalar(
            select(func.count())
            .select_from(ChannelSubscription)
            .where(ChannelSubscription.channel_id == channel.id)
        )
        or 0
    )
    subscribed = user is not None and db.get(ChannelSubscription, (user.id, channel.id)) is not None
    return {
        "id": channel.id,
        "handle": channel.handle,
        "name": channel.name,
        "description": channel.description,
        "created_at": channel.created_at,
        "subscribers": subscribers,
        "subscribed": subscribed,
        "videos": _video_list(videos, total),
        "playlists": [_playlist_summary(playlist, db) for playlist in public_playlists],
    }


@router.get("/feed/subscriptions", response_model=VideoList)
def subscription_feed(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VideoList:
    filters = (
        ChannelSubscription.subscriber_id == user.id,
        Video.status == "ready",
        Video.visibility == "public",
    )
    statement = (
        select(Video)
        .join(Channel, Video.channel_id == Channel.id)
        .join(ChannelSubscription, ChannelSubscription.channel_id == Channel.id)
        .where(*filters)
        .order_by(Video.published_at.desc(), Video.created_at.desc())
    )
    count = (
        select(func.count(Video.id))
        .join(Channel, Video.channel_id == Channel.id)
        .join(ChannelSubscription, ChannelSubscription.channel_id == Channel.id)
        .where(*filters)
    )
    videos = db.scalars(statement.offset(offset).limit(limit)).unique().all()
    return _video_list(videos, db.scalar(count) or 0)


@router.get("/users/me/history", response_model=VideoList)
def get_watch_history(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VideoList:
    access_filter = video_access_filter(user)
    history_filters = (
        VideoViewHistory.user_id == user.id,
        Video.status == "ready",
        access_filter,
    )
    statement = (
        select(Video)
        .join(VideoViewHistory, VideoViewHistory.video_id == Video.id)
        .join(Channel, Channel.id == Video.channel_id)
        .where(*history_filters)
        .order_by(VideoViewHistory.watched_at.desc())
    )
    total = (
        db.scalar(
            select(func.count(Video.id))
            .join(VideoViewHistory, VideoViewHistory.video_id == Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .where(*history_filters)
        )
        or 0
    )
    return _video_list(db.scalars(statement.offset(offset).limit(limit)).unique().all(), total)


@router.delete("/users/me/history")
def clear_watch_history(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    db.query(VideoViewHistory).filter(VideoViewHistory.user_id == user.id).delete()
    db.commit()
    return {"cleared": True}


@router.get("/users/me/favorites", response_model=VideoList)
def get_favorites(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VideoList:
    filters = (
        SavedVideo.user_id == user.id,
        Video.status == "ready",
        Video.visibility != "private",
    )
    statement = (
        select(Video)
        .join(SavedVideo, SavedVideo.video_id == Video.id)
        .where(*filters)
        .order_by(SavedVideo.created_at.desc())
    )
    total = (
        db.scalar(
            select(func.count())
            .select_from(SavedVideo)
            .join(Video, SavedVideo.video_id == Video.id)
            .where(*filters)
        )
        or 0
    )
    return _video_list(db.scalars(statement.offset(offset).limit(limit)).unique().all(), total)


@router.put("/videos/{video_id}/favorite")
def save_favorite(
    video_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    get_accessible_video(video_id, db, None)
    if db.get(SavedVideo, (user.id, video_id)) is None:
        db.add(SavedVideo(user_id=user.id, video_id=video_id))
        db.commit()
    return {"saved": True}


@router.delete("/videos/{video_id}/favorite")
def remove_favorite(
    video_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    saved = db.get(SavedVideo, (user.id, video_id))
    if saved is not None:
        db.delete(saved)
        db.commit()
    return {"saved": False}


@router.get("/playlists/mine")
def list_my_playlists(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    playlists = db.scalars(
        select(Playlist).where(Playlist.owner_id == user.id).order_by(Playlist.created_at.desc())
    ).all()
    return [_playlist_summary(playlist, db) for playlist in playlists]


@router.post("/playlists", status_code=status.HTTP_201_CREATED)
def create_playlist(
    payload: PlaylistCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Playlist title cannot be empty")
    playlist = Playlist(
        owner_id=user.id,
        title=title,
        description=payload.description.strip() if payload.description else None,
        visibility=payload.visibility,
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return _playlist_summary(playlist, db)


@router.get("/playlists/{playlist_id}")
def get_playlist(
    playlist_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_current_user)],
) -> dict:
    playlist = _playlist_access(playlist_id, db, user)
    item_filters = [
        PlaylistItem.playlist_id == playlist.id,
        Video.status == "ready",
        Video.visibility != "private",
    ]
    if playlist.visibility != "private":
        item_filters.append(Video.visibility == "public")
    items = (
        db.scalars(
            select(Video)
            .join(PlaylistItem, PlaylistItem.video_id == Video.id)
            .where(*item_filters)
            .order_by(PlaylistItem.position.asc(), PlaylistItem.added_at.asc())
        )
        .unique()
        .all()
    )
    return {**_playlist_summary(playlist, db), "videos": _video_list(items, len(items))}


@router.patch("/playlists/{playlist_id}")
def update_playlist(
    playlist_id: UUID,
    payload: PlaylistUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or playlist.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Playlist not found")
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        title = changes["title"].strip()
        if not title:
            raise HTTPException(status_code=422, detail="Playlist title cannot be empty")
        playlist.title = title
    if "description" in changes:
        playlist.description = changes["description"].strip() if changes["description"] else None
    if "visibility" in changes:
        playlist.visibility = changes["visibility"]
    db.commit()
    db.refresh(playlist)
    return _playlist_summary(playlist, db)


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playlist(
    playlist_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or playlist.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Playlist not found")
    db.delete(playlist)
    db.commit()


@router.post("/playlists/{playlist_id}/videos/{video_id}")
def add_playlist_video(
    playlist_id: UUID,
    video_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or playlist.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Playlist not found")
    get_accessible_video(video_id, db, None)
    if playlist.visibility != "private" and video.visibility != "public":
        raise HTTPException(
            status_code=400, detail="Only public videos can be added to a public playlist"
        )
    if db.get(PlaylistItem, (playlist_id, video_id)) is None:
        position = (
            db.scalar(
                select(func.coalesce(func.max(PlaylistItem.position), -1) + 1).where(
                    PlaylistItem.playlist_id == playlist_id
                )
            )
            or 0
        )
        db.add(PlaylistItem(playlist_id=playlist_id, video_id=video_id, position=position))
        db.commit()
    return _playlist_summary(playlist, db)


@router.delete("/playlists/{playlist_id}/videos/{video_id}")
def remove_playlist_video(
    playlist_id: UUID,
    video_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    playlist = db.get(Playlist, playlist_id)
    if playlist is None or playlist.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Playlist not found")
    item = db.get(PlaylistItem, (playlist_id, video_id))
    if item is not None:
        db.delete(item)
        db.commit()
    return _playlist_summary(playlist, db)


@router.get("/notifications")
def list_notifications(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict:
    items = db.scalars(
        select(Notification)
        .where(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    ).all()
    unread = (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )
    return {
        "items": [
            {
                "id": item.id,
                "kind": item.kind,
                "message": item.message,
                "video_id": item.video_id,
                "comment_id": item.comment_id,
                "actor_id": item.actor_id,
                "read": item.read_at is not None,
                "created_at": item.created_at,
            }
            for item in items
        ],
        "unread_count": unread,
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.recipient_id == user.id
        )
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.commit()
    return {"read": True}


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    db.query(Notification).filter(
        Notification.recipient_id == user.id, Notification.read_at.is_(None)
    ).update({"read_at": datetime.now(UTC)})
    db.commit()
    return {"read_all": True}
