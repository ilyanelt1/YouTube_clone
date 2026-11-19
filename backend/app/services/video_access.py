from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Channel, User, Video, VideoAccessGrant


def video_access_filter(user: User | None):
    """Return the SQL condition shared by detail and collection queries."""
    if user is None:
        return Video.visibility != "private"

    return or_(
        Video.visibility != "private",
        Channel.owner_id == user.id,
        Video.id.in_(
            select(VideoAccessGrant.video_id).where(VideoAccessGrant.user_id == user.id)
        ),
    )


def get_accessible_video(video_id: UUID, db: Session, user: User | None) -> Video:
    """Load a ready video only when the caller is allowed to know it exists."""
    video = db.scalar(
        select(Video)
        .join(Channel)
        .where(
            Video.id == video_id,
            Video.status == "ready",
            video_access_filter(user),
        )
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
