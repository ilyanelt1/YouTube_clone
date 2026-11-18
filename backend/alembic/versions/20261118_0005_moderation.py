"""Добавляет жалобы на видео и процесс модерации."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261118_0005"
down_revision: str | Sequence[str] | None = "20261117_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("reporter_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name=op.f("ck_video_reports_valid_status")),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE", name=op.f("fk_video_reports_video_id_videos")),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_video_reports_reporter_id_users")),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_video_reports_reviewed_by_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_reports")),
        sa.UniqueConstraint("video_id", "reporter_id", name=op.f("uq_video_report_reporter")),
    )
    op.create_index("ix_video_reports_status_created", "video_reports", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_video_reports_status_created", table_name="video_reports")
    op.drop_table("video_reports")
