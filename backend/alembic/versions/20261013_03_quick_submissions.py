"""Add device-scoped anonymous submissions; existing records remain unchanged."""
from alembic import op
import sqlalchemy as sa

revision = "20261013_03"
down_revision = "20260906_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The historical initial migration imports current metadata on fresh installs.
    if "quick_submissions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "quick_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id"), nullable=False, unique=True),
        sa.Column("device_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("device_hash", "request_id", name="uq_quick_device_request"),
    )
    op.create_index("ix_quick_submissions_device_hash", "quick_submissions", ["device_hash"])


def downgrade() -> None:
    # This drops device access links only, never assessments or archived documents.
    op.drop_index("ix_quick_submissions_device_hash", table_name="quick_submissions")
    op.drop_table("quick_submissions")
