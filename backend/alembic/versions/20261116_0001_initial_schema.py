"""Create initial identity, channel and video schema."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261116_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("username", sa.String(30), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column("description", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_user_roles_user_id_users")),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE", name=op.f("fk_user_roles_role_id_roles")),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_roles")),
    )
    op.create_table(
        "channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("handle", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("avatar_key", sa.String(512)),
        sa.Column("banner_key", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_channels_owner_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint("owner_id", name=op.f("uq_channels_owner_id")),
        sa.UniqueConstraint("handle", name=op.f("uq_channels_handle")),
    )
    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("visibility", sa.String(20), server_default="private", nullable=False),
        sa.Column("storage_key", sa.String(512)),
        sa.Column("thumbnail_key", sa.String(512)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("file_size_bytes", sa.BigInteger()),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'uploading', 'processing', 'ready', 'failed', 'blocked')", name=op.f("ck_videos_valid_status")),
        sa.CheckConstraint("visibility IN ('public', 'unlisted', 'private')", name=op.f("ck_videos_valid_visibility")),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name=op.f("ck_videos_nonnegative_duration")),
        sa.CheckConstraint("file_size_bytes IS NULL OR file_size_bytes >= 0", name=op.f("ck_videos_nonnegative_file_size")),
        sa.CheckConstraint("width IS NULL OR width > 0", name=op.f("ck_videos_positive_width")),
        sa.CheckConstraint("height IS NULL OR height > 0", name=op.f("ck_videos_positive_height")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE", name=op.f("fk_videos_channel_id_channels")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_videos")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_videos_storage_key")),
    )
    op.create_index("ix_videos_channel_created_at", "videos", ["channel_id", "created_at"])
    op.create_index("ix_videos_status_created_at", "videos", ["status", "created_at"])
    op.create_index("ix_videos_visibility_published_at", "videos", ["visibility", "published_at"])
    op.create_table(
        "video_access_grants",
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_video_access_grants_video_id_videos")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_video_access_grants_user_id_users")),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_video_access_grants_granted_by_id_users")),
        sa.PrimaryKeyConstraint("video_id", "user_id", name=op.f("pk_video_access_grants")),
    )
    op.create_index("ix_video_access_grants_user_id", "video_access_grants", ["user_id"])

    roles_table = sa.table("roles", sa.column("name", sa.String()), sa.column("description", sa.String()))
    op.bulk_insert(
        roles_table,
        [
            {"name": "user", "description": "Standard registered user"},
            {"name": "moderator", "description": "Content moderation permissions"},
            {"name": "admin", "description": "Administrative permissions"},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_video_access_grants_user_id", table_name="video_access_grants")
    op.drop_table("video_access_grants")
    op.drop_index("ix_videos_visibility_published_at", table_name="videos")
    op.drop_index("ix_videos_status_created_at", table_name="videos")
    op.drop_index("ix_videos_channel_created_at", table_name="videos")
    op.drop_table("videos")
    op.drop_table("channels")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
