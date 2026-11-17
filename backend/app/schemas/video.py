from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    status: str
    visibility: str
    file_size_bytes: int | None
    mime_type: str | None
    created_at: datetime
    channel_name: str
    channel_handle: str
    playback_url: str
    thumbnail_url: str | None = None


class VideoList(BaseModel):
    items: list[VideoRead]
    total: int


class VideoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    visibility: Literal["public", "unlisted", "private"] | None = None
