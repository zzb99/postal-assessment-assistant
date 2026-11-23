"""document archives and validated workforce fields

Revision ID: 20260906_02
Revises: 20260821_01
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa

revision = "20260906_02"
down_revision = "20260821_01"
branch_labels = None
depends_on = None


def _columns(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "master_data_items" in tables and "parent_name" not in _columns(inspector, "master_data_items"):
        op.add_column("master_data_items", sa.Column("parent_name", sa.String(100), nullable=True))
        op.create_index("ix_master_data_items_parent_name", "master_data_items", ["parent_name"])
    if "assessments" in tables:
        columns = _columns(inspector, "assessments")
        if "team" not in columns:
            op.add_column("assessments", sa.Column("team", sa.String(32), nullable=False, server_default="一班"))
            op.create_index("ix_assessments_team", "assessments", ["team"])
        if "quantity" not in columns:
            op.add_column("assessments", sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"))
        if bind.dialect.name == "postgresql":
            check_names = {item.get("name") for item in sa.inspect(bind).get_check_constraints("assessments")}
            if "ck_assessments_quantity_positive" not in check_names:
                op.create_check_constraint("ck_assessments_quantity_positive", "assessments", "quantity >= 1 AND quantity <= 100000")
            if "ck_assessments_penalty_integer" not in check_names:
                op.create_check_constraint("ck_assessments_penalty_integer", "assessments", "penalty_amount >= 1 AND penalty_amount <= 100000000 AND penalty_amount = CAST(penalty_amount AS INTEGER)")
    if "assessment_documents" not in tables:
        op.create_table(
            "assessment_documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("template_version", sa.String(64), nullable=False),
            sa.Column("template_sha256", sa.String(64), nullable=False),
            sa.Column("docx_path", sa.String(500), nullable=False),
            sa.Column("pdf_path", sa.String(500), nullable=False),
            sa.Column("docx_sha256", sa.String(64), nullable=False),
            sa.Column("pdf_sha256", sa.String(64), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("assessment_id"),
        )
        op.create_index("ix_assessment_documents_assessment_id", "assessment_documents", ["assessment_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "assessment_documents" in tables:
        op.drop_index("ix_assessment_documents_assessment_id", table_name="assessment_documents")
        op.drop_table("assessment_documents")
    if "assessments" in tables:
        if bind.dialect.name == "postgresql":
            check_names = {item.get("name") for item in sa.inspect(bind).get_check_constraints("assessments")}
            if "ck_assessments_penalty_integer" in check_names:
                op.drop_constraint("ck_assessments_penalty_integer", "assessments", type_="check")
            if "ck_assessments_quantity_positive" in check_names:
                op.drop_constraint("ck_assessments_quantity_positive", "assessments", type_="check")
        columns = _columns(sa.inspect(bind), "assessments")
        if "quantity" in columns:
            op.drop_column("assessments", "quantity")
        if "team" in columns:
            op.drop_index("ix_assessments_team", table_name="assessments")
            op.drop_column("assessments", "team")
    if "master_data_items" in tables and "parent_name" in _columns(sa.inspect(bind), "master_data_items"):
        op.drop_index("ix_master_data_items_parent_name", table_name="master_data_items")
        op.drop_column("master_data_items", "parent_name")
