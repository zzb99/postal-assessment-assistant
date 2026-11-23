"""Add metadata-only AI usage counters. No assessment or document changes."""
from alembic import op
import sqlalchemy as sa

revision = "20261013_04"
down_revision = "20261013_03"
branch_labels = None
depends_on = None


def upgrade():
    if "ai_usage" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table("ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("event_kind", sa.String(24), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_miss_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("estimated_cny", sa.Numeric(18, 10), nullable=True),
        sa.Column("price_band", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(32), nullable=True))
    op.create_index("ix_ai_usage_started_at", "ai_usage", ["started_at"])


def downgrade():
    op.drop_index("ix_ai_usage_started_at", table_name="ai_usage")
    op.drop_table("ai_usage")
