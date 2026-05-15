"""User multi-branch: replace branch_id FK with junction table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_branches",
        sa.Column("user_id",   sa.Integer(), sa.ForeignKey("users.id",    ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "branch_id"),
    )
    # Migrate existing single branch_id assignments
    op.execute("""
        INSERT INTO user_branches (user_id, branch_id)
        SELECT id, branch_id FROM users WHERE branch_id IS NOT NULL
    """)
    op.drop_column("users", "branch_id")


def downgrade() -> None:
    op.add_column("users", sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True))
    op.drop_table("user_branches")
