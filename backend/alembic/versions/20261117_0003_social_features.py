"""Add reactions, comments, shares and channel subscriptions.

Revision ID: 20261117_0003
Revises: 20261116_0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261117_0003"
down_revision: str | Sequence[str] | None = "20261116_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("view_count", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.create_check_constraint("nonnegative_view_count", "videos", "view_count >= 0")

    op.create_table(
        "video_reactions",
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reaction", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_video_reactions_video_id_videos")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_video_reactions_user_id_users")),
        sa.PrimaryKeyConstraint("video_id", "user_id", name=op.f("pk_video_reactions")),
        sa.CheckConstraint("reaction IN ('like', 'dislike')", name=op.f("ck_video_reactions_valid_reaction")),
    )
    op.create_index("ix_video_reactions_user_id", "video_reactions", ["user_id"])

    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_comments_video_id_videos")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_comments_user_id_users")),
        sa.ForeignKeyConstraint(["parent_id"], ["comments.id"], ondelete="CASCADE", name=op.f("fk_comments_parent_id_comments")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
        sa.CheckConstraint("length(trim(body)) > 0 AND length(body) <= 2000", name=op.f("ck_comments_valid_body")),
    )
    op.create_index("ix_comments_video_created_at", "comments", ["video_id", "created_at"])
    op.create_index("ix_comments_parent_id", "comments", ["parent_id"])

    op.create_table(
        "video_shares",
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_video_shares_video_id_videos")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_video_shares_user_id_users")),
        sa.PrimaryKeyConstraint("video_id", "user_id", name=op.f("pk_video_shares")),
    )

    op.create_table(
        "channel_subscriptions",
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["subscriber_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_channel_subscriptions_subscriber_id_users")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE", name=op.f("fk_channel_subscriptions_channel_id_channels")),
        sa.PrimaryKeyConstraint("subscriber_id", "channel_id", name=op.f("pk_channel_subscriptions")),
    )
    op.create_index("ix_channel_subscriptions_channel_id", "channel_subscriptions", ["channel_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_subscriptions_channel_id", table_name="channel_subscriptions")
    op.drop_table("channel_subscriptions")
    op.drop_table("video_shares")
    op.drop_index("ix_comments_parent_id", table_name="comments")
    op.drop_index("ix_comments_video_created_at", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_video_reactions_user_id", table_name="video_reactions")
    op.drop_table("video_reactions")
    op.drop_constraint(op.f("ck_videos_nonnegative_view_count"), "videos", type_="check")
    op.drop_column("videos", "view_count")
