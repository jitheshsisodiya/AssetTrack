"""Add group_label and industry to institutions."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("institutions", sa.Column("industry",    sa.String(50),  nullable=False, server_default="Other"))
    op.add_column("institutions", sa.Column("group_label", sa.String(50),  nullable=False, server_default="Class"))


def downgrade():
    op.drop_column("institutions", "group_label")
    op.drop_column("institutions", "industry")
