"""Initial schema — all tables

Revision ID: 0001
Revises:
Create Date: 2026-05-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id",            sa.Integer(),     nullable=False),
        sa.Column("username",      sa.String(100),   nullable=False),
        sa.Column("password_hash", sa.String(255),   nullable=False),
        sa.Column("role",          sa.String(50),    nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "assets",
        sa.Column("id",         sa.Integer(),    nullable=False),
        sa.Column("item_name",  sa.String(255),  nullable=False),
        sa.Column("sl_no",      sa.Integer(),    nullable=True),
        sa.Column("asset_code", sa.String(100),  nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_asset_code", "assets", ["asset_code"], unique=True)

    op.create_table(
        "classes",
        sa.Column("id",                sa.Integer(),    nullable=False),
        sa.Column("class_name",        sa.String(100),  nullable=False),
        sa.Column("assigned_to",       sa.String(100),  nullable=True),
        sa.Column("locked",            sa.Boolean(),    nullable=True, server_default="false"),
        sa.Column("locked_by",         sa.String(100),  nullable=True),
        sa.Column("lock_timestamp",    sa.String(100),  nullable=True),
        sa.Column("sticker_locked",    sa.Boolean(),    nullable=True, server_default="false"),
        sa.Column("sticker_locked_by", sa.String(100),  nullable=True),
        sa.Column("sticker_timestamp", sa.String(100),  nullable=True),
        sa.Column("display_order",     sa.Integer(),    nullable=True, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_classes_class_name", "classes", ["class_name"], unique=True)

    op.create_table(
        "asset_class_counts",
        sa.Column("id",       sa.Integer(),          nullable=False),
        sa.Column("asset_id", sa.Integer(),          nullable=False),
        sa.Column("class_id", sa.Integer(),          nullable=False),
        sa.Column("count",    sa.Numeric(10, 2),     nullable=True, server_default="0"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "class_id"),
    )

    op.create_table(
        "edit_log",
        sa.Column("id",         sa.Integer(),                              nullable=False),
        sa.Column("username",   sa.String(100),                            nullable=False),
        sa.Column("item_name",  sa.String(255),                            nullable=True),
        sa.Column("asset_code", sa.String(100),                            nullable=True),
        sa.Column("class_name", sa.String(100),                            nullable=True),
        sa.Column("qty",        sa.Numeric(10, 2),                         nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "barcodes",
        sa.Column("id",         sa.Integer(),    nullable=False),
        sa.Column("sl_no",      sa.Integer(),    nullable=True),
        sa.Column("code_text",  sa.String(255),  nullable=True),
        sa.Column("item_name",  sa.String(255),  nullable=True),
        sa.Column("class_name", sa.String(100),  nullable=True),
        sa.Column("remarks",    sa.String(255),  nullable=True, server_default="''"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "stickering",
        sa.Column("id",         sa.Integer(),    nullable=False),
        sa.Column("sl_no",      sa.Integer(),    nullable=True),
        sa.Column("bar_code",   sa.String(255),  nullable=True),
        sa.Column("item_name",  sa.String(255),  nullable=True),
        sa.Column("class_name", sa.String(100),  nullable=True),
        sa.Column("remarks",    sa.String(255),  nullable=True, server_default="''"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bar_code"),
    )

    op.create_table(
        "app_state",
        sa.Column("key",   sa.String(100), nullable=False),
        sa.Column("value", sa.String(),    nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_state")
    op.drop_table("stickering")
    op.drop_table("barcodes")
    op.drop_table("edit_log")
    op.drop_table("asset_class_counts")
    op.drop_index("ix_classes_class_name", table_name="classes")
    op.drop_table("classes")
    op.drop_index("ix_assets_asset_code",  table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_users_username",     table_name="users")
    op.drop_table("users")
