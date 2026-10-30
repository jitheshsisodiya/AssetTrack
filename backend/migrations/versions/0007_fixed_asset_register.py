"""Fixed asset register: categories, assets, revaluations, verification runs."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _inst():
    return sa.Column("institution_id", sa.Integer, sa.ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)


def upgrade():
    op.create_table(
        "asset_categories",
        sa.Column("id", sa.Integer, primary_key=True),
        _inst(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("schedule_iii_class", sa.String(60), nullable=False),
        sa.Column("schedule_ii_life", sa.Numeric(5, 2), nullable=True),
        sa.Column("default_method", sa.String(10), nullable=False, server_default="SLM"),
        sa.Column("residual_pct", sa.Numeric(5, 2), nullable=False, server_default="5"),
        sa.Column("is_intangible", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_immovable", sa.Boolean, nullable=False, server_default="false"),
        sa.UniqueConstraint("institution_id", "name", name="uq_asset_categories_inst_name"),
    )
    op.create_index("ix_asset_categories_id", "asset_categories", ["id"])
    op.create_table(
        "fixed_assets",
        sa.Column("id", sa.Integer, primary_key=True),
        _inst(),
        sa.Column("far_no", sa.String(30), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("asset_categories.id"), nullable=False),
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("class_id", sa.Integer, sa.ForeignKey("classes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("purchase_date", sa.Date, nullable=False),
        sa.Column("put_to_use_date", sa.Date, nullable=True),
        sa.Column("vendor", sa.String(200)),
        sa.Column("invoice_no", sa.String(100)),
        sa.Column("serial_no", sa.String(100)),
        sa.Column("method", sa.String(10), nullable=False, server_default="SLM"),
        sa.Column("useful_life_years", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("residual_pct", sa.Numeric(5, 2), nullable=False, server_default="5"),
        sa.Column("policy_note", sa.Text),
        sa.Column("disposal_date", sa.Date, nullable=True),
        sa.Column("disposal_proceeds", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("title_in_company_name", sa.Boolean, nullable=True),
        sa.Column("title_holder", sa.String(200)),
        sa.Column("title_holder_related", sa.Boolean, nullable=True),
        sa.Column("title_held_since", sa.Date, nullable=True),
        sa.Column("title_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("institution_id", "far_no", name="uq_fixed_assets_inst_farno"),
    )
    op.create_index("ix_fixed_assets_id", "fixed_assets", ["id"])
    op.create_table(
        "revaluations",
        sa.Column("id", sa.Integer, primary_key=True),
        _inst(),
        sa.Column("fixed_asset_id", sa.Integer, sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reval_date", sa.Date, nullable=False),
        sa.Column("valuer_name", sa.String(200)),
        sa.Column("valuer_reg_no", sa.String(100)),
        sa.Column("prior_net_carrying", sa.Numeric(14, 2), nullable=False),
        sa.Column("revalued_net_carrying", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_revaluations_id", "revaluations", ["id"])
    op.create_table(
        "verification_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        _inst(),
        sa.Column("as_on", sa.Date, nullable=False),
        sa.Column("verified_by", sa.String(200), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="Open"),
        sa.Column("remarks", sa.Text),
        sa.Column("snapshot", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_verification_runs_id", "verification_runs", ["id"])


def downgrade():
    op.drop_table("verification_runs")
    op.drop_table("revaluations")
    op.drop_table("fixed_assets")
    op.drop_table("asset_categories")
