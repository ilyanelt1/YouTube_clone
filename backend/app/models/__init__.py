from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
import sqlalchemy.orm as orm

from app.db.base import Base

user_roles = sa.Table(
    "user_roles",
    Base.metadata,
    sa.Column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("role_id", sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    sa.Column(
        "assigned_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
)


class User(Base):
    __tablename__ = "users"

    id: orm.Mapped[UUID] = orm.mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: orm.Mapped[str] = orm.mapped_column(sa.String(320), unique=True, nullable=False)
    username: orm.Mapped[str] = orm.mapped_column(sa.String(30), unique=True, nullable=False)
    display_name: orm.Mapped[str] = orm.mapped_column(sa.String(80), nullable=False)
    password_hash: orm.Mapped[str] = orm.mapped_column(sa.String(255), nullable=False)
    is_active: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean, nullable=False, default=True, server_default="true"
    )
    is_verified: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    roles: orm.Mapped[list[Role]] = orm.relationship(secondary=user_roles, back_populates="users")
    channel: orm.Mapped[Channel | None] = orm.relationship(
        back_populates="owner", cascade="all, delete-orphan", uselist=False
    )
    access_grants: orm.Mapped[list[VideoAccessGrant]] = orm.relationship(
        back_populates="user",
        foreign_keys="VideoAccessGrant.user_id",
        cascade="all, delete-orphan",
    )
    auth_sessions: orm.Mapped[list[AuthSession]] = orm.relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Role(Base):
    __tablename__ = "roles"

    id: orm.Mapped[int] = orm.mapped_column(sa.Integer, primary_key=True)
    name: orm.Mapped[str] = orm.mapped_column(sa.String(30), unique=True, nullable=False)
    description: orm.Mapped[str | None] = orm.mapped_column(sa.String(255))
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    users: orm.Mapped[list[User]] = orm.relationship(secondary=user_roles, back_populates="roles")


class Channel(Base):
    __tablename__ = "channels"

    id: orm.Mapped[UUID] = orm.mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    handle: orm.Mapped[str] = orm.mapped_column(sa.String(30), unique=True, nullable=False)
    name: orm.Mapped[str] = orm.mapped_column(sa.String(100), nullable=False)
    description: orm.Mapped[str | None] = orm.mapped_column(sa.Text)
    avatar_key: orm.Mapped[str | None] = orm.mapped_column(sa.String(512))
    banner_key: orm.Mapped[str | None] = orm.mapped_column(sa.String(512))
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    owner: orm.Mapped[User] = orm.relationship(back_populates="channel")
    videos: orm.Mapped[list[Video]] = orm.relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('draft', 'uploading', 'processing', 'ready', 'failed', 'blocked')",
            name="valid_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('public', 'unlisted', 'private')", name="valid_visibility"
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0", name="nonnegative_duration"
        ),
        sa.CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes >= 0", name="nonnegative_file_size"
        ),
        sa.CheckConstraint("width IS NULL OR width > 0", name="positive_width"),
        sa.CheckConstraint("height IS NULL OR height > 0", name="positive_height"),
        sa.Index("ix_videos_channel_created_at", "channel_id", "created_at"),
        sa.Index("ix_videos_status_created_at", "status", "created_at"),
        sa.Index("ix_videos_visibility_published_at", "visibility", "published_at"),
    )

    id: orm.Mapped[UUID] = orm.mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid4)
    channel_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: orm.Mapped[str] = orm.mapped_column(sa.String(120), nullable=False)
    description: orm.Mapped[str | None] = orm.mapped_column(sa.Text)
    status: orm.Mapped[str] = orm.mapped_column(
        sa.String(20), nullable=False, default="draft", server_default="draft"
    )
    visibility: orm.Mapped[str] = orm.mapped_column(
        sa.String(20), nullable=False, default="private", server_default="private"
    )
    storage_key: orm.Mapped[str | None] = orm.mapped_column(sa.String(512), unique=True)
    thumbnail_key: orm.Mapped[str | None] = orm.mapped_column(sa.String(512))
    duration_seconds: orm.Mapped[int | None] = orm.mapped_column(sa.Integer)
    file_size_bytes: orm.Mapped[int | None] = orm.mapped_column(sa.BigInteger)
    mime_type: orm.Mapped[str | None] = orm.mapped_column(sa.String(100))
    width: orm.Mapped[int | None] = orm.mapped_column(sa.Integer)
    height: orm.Mapped[int | None] = orm.mapped_column(sa.Integer)
    published_at: orm.Mapped[datetime | None] = orm.mapped_column(sa.DateTime(timezone=True))
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    channel: orm.Mapped[Channel] = orm.relationship(back_populates="videos")
    access_grants: orm.Mapped[list[VideoAccessGrant]] = orm.relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    view_count: orm.Mapped[int] = orm.mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default="0"
    )


class VideoAccessGrant(Base):
    __tablename__ = "video_access_grants"
    __table_args__ = (sa.Index("ix_video_access_grants_user_id", "user_id"),)

    video_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("videos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    granted_by_id: orm.Mapped[UUID | None] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    video: orm.Mapped[Video] = orm.relationship(back_populates="access_grants")
    user: orm.Mapped[User] = orm.relationship(
        back_populates="access_grants", foreign_keys=[user_id]
    )
    granted_by: orm.Mapped[User | None] = orm.relationship(foreign_keys=[granted_by_id])


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        sa.Index("ix_auth_sessions_user_id", "user_id"),
        sa.Index("ix_auth_sessions_family_id", "family_id"),
        sa.Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id: orm.Mapped[UUID] = orm.mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    family_id: orm.Mapped[UUID] = orm.mapped_column(sa.Uuid(as_uuid=True), nullable=False)
    refresh_token_hash: orm.Mapped[str] = orm.mapped_column(
        sa.String(64), unique=True, nullable=False
    )
    expires_at: orm.Mapped[datetime] = orm.mapped_column(sa.DateTime(timezone=True), nullable=False)
    revoked_at: orm.Mapped[datetime | None] = orm.mapped_column(sa.DateTime(timezone=True))
    user_agent: orm.Mapped[str | None] = orm.mapped_column(sa.String(512))
    ip_address: orm.Mapped[str | None] = orm.mapped_column(sa.String(45))
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    user: orm.Mapped[User] = orm.relationship(back_populates="auth_sessions")



class VideoReaction(Base):
    __tablename__ = "video_reactions"
    __table_args__ = (
        sa.CheckConstraint("reaction IN ('like', 'dislike')", name="valid_reaction"),
        sa.Index("ix_video_reactions_user_id", "user_id"),
    )

    video_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    reaction: orm.Mapped[str] = orm.mapped_column(sa.String(10), nullable=False)
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        sa.CheckConstraint("length(trim(body)) > 0 AND length(body) <= 2000", name="valid_body"),
        sa.Index("ix_comments_video_created_at", "video_id", "created_at"),
        sa.Index("ix_comments_parent_id", "parent_id"),
    )

    id: orm.Mapped[UUID] = orm.mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid4)
    video_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    user_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: orm.Mapped[UUID | None] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("comments.id", ondelete="CASCADE")
    )
    body: orm.Mapped[str] = orm.mapped_column(sa.Text, nullable=False)
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )
    author: orm.Mapped[User] = orm.relationship()


class VideoShare(Base):
    __tablename__ = "video_shares"

    video_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class ChannelSubscription(Base):
    __tablename__ = "channel_subscriptions"
    __table_args__ = (sa.Index("ix_channel_subscriptions_channel_id", "channel_id"),)

    subscriber_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: orm.Mapped[UUID] = orm.mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: orm.Mapped[datetime] = orm.mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


__all__ = [
    "AuthSession",
    "ChannelSubscription",
    "Comment",
    "Base",
    "Channel",
    "Role",
    "User",
    "Video",
    "VideoReaction",
    "VideoShare",
    "VideoAccessGrant",
    "user_roles",
]
