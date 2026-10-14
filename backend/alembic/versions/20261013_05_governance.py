"""Add authorization/approval tables only; preserve all existing records."""
from alembic import op
from backend.app.models import TrustedDevice, PolicyApproval
import sqlalchemy as sa

revision = "20261013_05"
down_revision = "20261013_04"
branch_labels = None
depends_on = None


def upgrade():
    TrustedDevice.__table__.create(op.get_bind(), checkfirst=True)
    PolicyApproval.__table__.create(op.get_bind(), checkfirst=True)
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("quick_submissions")}
    if "ai_catalog_digest" not in columns:
        op.add_column("quick_submissions", sa.Column("ai_catalog_digest", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("quick_submissions", "ai_catalog_digest")
    PolicyApproval.__table__.drop(op.get_bind(), checkfirst=True)
    TrustedDevice.__table__.drop(op.get_bind(), checkfirst=True)
