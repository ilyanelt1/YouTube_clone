from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, Video, VideoAccessGrant


def get_accessible_video(
    db: Session,
    video_id: UUID,
    user: User | None,
    *,
    allow_private: bool = True,
) -> Video:
    """Return a ready video only when the caller may access its visibility level.

    Private videos are intentionally indistinguishable from missing videos to
    callers without an owner or explicit access grant.
    """
    video = db.scalar(select(Video).where(Video.id == video_id, Video.status == "ready"))
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.visibility == "private":
        has_access = (
            allow_private
            and user is not None
            and (
                video.channel.owner_id == user.id
                or db.get(VideoAccessGrant, (video.id, user.id)) is not None
            )
        )
        if not has_access:
            raise HTTPException(status_code=404, detail="Video not found")

    return video
