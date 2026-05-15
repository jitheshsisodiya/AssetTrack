"""Add branches table; branch_id to users and classes; wipe non-user data

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id",         sa.Integer(),     nullable=False),
        sa.Column("name",       sa.String(200),   nullable=False),
        sa.Column("code",       sa.String(50),    nullable=False),
        sa.Column("is_active",  sa.Boolean(),     nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("code"),
    )

    op.add_column("users",   sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True))
    op.add_column("classes", sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True))

    # Wipe all non-user data so branches can be set up fresh
    op.execute("DELETE FROM asset_class_counts")
    op.execute("DELETE FROM edit_log")
    op.execute("DELETE FROM barcodes")
    op.execute("DELETE FROM stickering")
    op.execute("DELETE FROM assets")
    op.execute("DELETE FROM classes")


def downgrade() -> None:
    op.drop_column("classes", "branch_id")
    op.drop_column("users",   "branch_id")
    op.drop_table("branches")
