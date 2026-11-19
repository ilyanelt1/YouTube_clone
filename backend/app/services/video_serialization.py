from fastapi import HTTPException

from app.models import Video
from app.schemas.video import VideoRead


def serialize_video(video: Video) -> VideoRead:
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
