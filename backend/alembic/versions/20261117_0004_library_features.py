"""Add channel discovery, history, playlists and notifications.

Revision ID: 20261117_0004
Revises: 20261117_0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261117_0004"
down_revision: str | Sequence[str] | None = "20261117_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_view_history",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("watched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_video_view_history_user_id_users")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_video_view_history_video_id_videos")),
        sa.PrimaryKeyConstraint("user_id", "video_id", name=op.f("pk_video_view_history")),
    )
    op.create_index("ix_video_view_history_user_watched", "video_view_history", ["user_id", "watched_at"])

    op.create_table(
        "saved_videos",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_saved_videos_user_id_users")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_saved_videos_video_id_videos")),
        sa.PrimaryKeyConstraint("user_id", "video_id", name=op.f("pk_saved_videos")),
    )

    op.create_table(
        "playlists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("visibility", sa.String(20), server_default="private", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_playlists_owner_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_playlists")),
        sa.CheckConstraint("visibility IN ('public', 'unlisted', 'private')", name=op.f("ck_playlists_valid_visibility")),
    )
    op.create_index("ix_playlists_owner_created", "playlists", ["owner_id", "created_at"])

    op.create_table(
        "playlist_items",
        sa.Column("playlist_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE", name=op.f("fk_playlist_items_playlist_id_playlists")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_playlist_items_video_id_videos")),
        sa.PrimaryKeyConstraint("playlist_id", "video_id", name=op.f("pk_playlist_items")),
        sa.UniqueConstraint("playlist_id", "position", name=op.f("uq_playlist_position")),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("video_id", sa.Uuid(), nullable=True),
        sa.Column("comment_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("message", sa.String(255), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_notifications_recipient_id_users")),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_notifications_actor_id_users")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_notifications_video_id_videos")),
        sa.ForeignKeyConstraint(["comment_id"], ["comments.id"], ondelete="CASCADE", name=op.f("fk_notifications_comment_id_comments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index("ix_notifications_recipient_created", "notifications", ["recipient_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("playlist_items")
    op.drop_index("ix_playlists_owner_created", table_name="playlists")
    op.drop_table("playlists")
    op.drop_table("saved_videos")
    op.drop_index("ix_video_view_history_user_watched", table_name="video_view_history")
    op.drop_table("video_view_history")
