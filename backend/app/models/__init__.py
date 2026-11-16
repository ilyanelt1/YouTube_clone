from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="users")
    channel: Mapped["Channel | None"] = relationship(
        back_populates="owner", cascade="all, delete-orphan", uselist=False
    )
    access_grants: Mapped[list["VideoAccessGrant"]] = relationship(
        back_populates="user",
        foreign_keys="VideoAccessGrant.user_id",
        cascade="all, delete-orphan",
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    handle: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    avatar_key: Mapped[str | None] = mapped_column(String(512))
    banner_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[User] = relationship(back_populates="channel")
    videos: Mapped[list["Video"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'uploading', 'processing', 'ready', 'failed', 'blocked')",
            name="valid_status",
        ),
        CheckConstraint(
            "visibility IN ('public', 'unlisted', 'private')", name="valid_visibility"
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0", name="nonnegative_duration"
        ),
        CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes >= 0", name="nonnegative_file_size"
        ),
        CheckConstraint("width IS NULL OR width > 0", name="positive_width"),
        CheckConstraint("height IS NULL OR height > 0", name="positive_height"),
        Index("ix_videos_channel_created_at", "channel_id", "created_at"),
        Index("ix_videos_status_created_at", "status", "created_at"),
        Index("ix_videos_visibility_published_at", "visibility", "published_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    channel_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    visibility: Mapped[str] = mapped_column(String(20), default="private", server_default="private")
    storage_key: Mapped[str | None] = mapped_column(String(512), unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(512))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    channel: Mapped[Channel] = relationship(back_populates="videos")
    access_grants: Mapped[list["VideoAccessGrant"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class VideoAccessGrant(Base):
    __tablename__ = "video_access_grants"

    video_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    granted_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped[Video] = relationship(back_populates="access_grants")
    user: Mapped[User] = relationship(back_populates="access_grants", foreign_keys=[user_id])
    granted_by: Mapped[User | None] = relationship(foreign_keys=[granted_by_id])


__all__ = ["Base", "Channel", "Role", "User", "Video", "VideoAccessGrant", "user_roles"]
