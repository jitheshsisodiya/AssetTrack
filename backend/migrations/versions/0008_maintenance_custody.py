"""Warranty expiry on fixed assets, maintenance tasks/log, custody log."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _inst():
    return sa.Column("institution_id", sa.Integer, sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)


def _asset():
    return sa.Column("fixed_asset_id", sa.Integer, sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False)


def upgrade():
    op.add_column("fixed_assets", sa.Column("warranty_expiry", sa.Date, nullable=True))
    op.create_table(
        "maintenance_tasks",
        sa.Column("id", sa.Integer, primary_key=True), _inst(), _asset(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("frequency_days", sa.Integer, nullable=True),
        sa.Column("next_due", sa.Date, nullable=True),
        sa.Column("last_done", sa.Date, nullable=True),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_maintenance_tasks_id", "maintenance_tasks", ["id"])
    op.create_table(
        "maintenance_log",
        sa.Column("id", sa.Integer, primary_key=True), _inst(),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("maintenance_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("done_on", sa.Date, nullable=False),
        sa.Column("done_by", sa.String(200), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text),
        sa.Column("recorded_by", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_maintenance_log_id", "maintenance_log", ["id"])
    op.create_table(
        "custody_log",
        sa.Column("id", sa.Integer, primary_key=True), _inst(), _asset(),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("issued_to", sa.String(200), nullable=False),
        sa.Column("issued_by", sa.String(100), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("due_back", sa.Date, nullable=True),
        sa.Column("condition_out", sa.String(200)),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_to", sa.String(100)),
        sa.Column("condition_in", sa.String(200)),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_custody_log_id", "custody_log", ["id"])


def downgrade():
    op.drop_table("custody_log")
    op.drop_table("maintenance_log")
    op.drop_table("maintenance_tasks")
    op.drop_column("fixed_assets", "warranty_expiry")
