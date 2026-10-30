"""Append-only register audit trail and asset file attachments."""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _inst():
    return sa.Column("institution_id", sa.Integer, sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)


def upgrade():
    op.create_table(
        "far_audit",
        sa.Column("id", sa.Integer, primary_key=True), _inst(),
        sa.Column("fixed_asset_id", sa.Integer, nullable=True),
        sa.Column("far_no", sa.String(30)),
        sa.Column("description", sa.String(255)),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("details", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_far_audit_id", "far_audit", ["id"])
    op.create_index("ix_far_audit_asset", "far_audit", ["institution_id", "fixed_asset_id"])
    op.create_table(
        "asset_files",
        sa.Column("id", sa.Integer, primary_key=True), _inst(),
        sa.Column("fixed_asset_id", sa.Integer, sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("stored_name", sa.String(100), nullable=False),
        sa.Column("uploaded_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_asset_files_id", "asset_files", ["id"])


def downgrade():
    op.drop_table("asset_files")
    op.drop_table("far_audit")
