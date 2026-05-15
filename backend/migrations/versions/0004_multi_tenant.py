"""Add multi-tenancy — institutions table, institution_id on all tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clear all existing data (fresh start for multi-tenancy)
    op.execute(
        "TRUNCATE TABLE asset_class_counts, edit_log, barcodes, stickering, "
        "app_state, assets, classes, user_branches, users, branches RESTART IDENTITY CASCADE"
    )

    # institutions table
    op.create_table(
        "institutions",
        sa.Column("id",         sa.Integer(),               nullable=False),
        sa.Column("name",       sa.String(200),             nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # branches: drop old global uniques, add institution_id, composite uniques
    op.drop_constraint("branches_name_key", "branches", type_="unique")
    op.drop_constraint("branches_code_key", "branches", type_="unique")
    op.add_column("branches", sa.Column(
        "institution_id", sa.Integer(),
        sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False,
    ))
    op.create_unique_constraint("uq_branches_inst_name", "branches", ["institution_id", "name"])
    op.create_unique_constraint("uq_branches_inst_code", "branches", ["institution_id", "code"])

    # users: drop global unique index, add institution_id, composite unique
    op.drop_index("ix_users_username", table_name="users")
    op.add_column("users", sa.Column(
        "institution_id", sa.Integer(),
        sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False,
    ))
    op.create_index("ix_users_username", "users", ["username"])
    op.create_unique_constraint("uq_users_inst_username", "users", ["institution_id", "username"])

    # classes: drop global unique index, add institution_id, composite unique
    op.drop_index("ix_classes_class_name", table_name="classes")
    op.add_column("classes", sa.Column(
        "institution_id", sa.Integer(),
        sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False,
    ))
    op.create_index("ix_classes_class_name", "classes", ["class_name"])
    op.create_unique_constraint("uq_classes_inst_name", "classes", ["institution_id", "class_name"])

    # assets: drop global unique index, add institution_id, composite unique
    op.drop_index("ix_assets_asset_code", table_name="assets")
    op.add_column("assets", sa.Column(
        "institution_id", sa.Integer(),
        sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False,
    ))
    op.create_index("ix_assets_asset_code", "assets", ["asset_code"])
    op.create_unique_constraint("uq_assets_inst_code", "assets", ["institution_id", "asset_code"])

    # edit_log, barcodes: simple add
    op.add_column("edit_log", sa.Column(
        "institution_id", sa.Integer(),
        sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False,
    ))
    op.add_column("barcodes", sa.Column(
        "institution_id", sa.Integer(),
        sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False,
    ))

    # stickering: drop global unique on bar_code, add institution_id, composite unique
    op.drop_constraint("stickering_bar_code_key", "stickering", type_="unique")
    op.add_column("stickering", sa.Column(
        "institution_id", sa.Integer(),
        sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False,
    ))
    op.create_unique_constraint("uq_stickering_inst_barcode", "stickering", ["institution_id", "bar_code"])


def downgrade() -> None:
    pass
