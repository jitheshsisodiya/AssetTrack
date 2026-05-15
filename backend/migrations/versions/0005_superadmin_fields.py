"""Add last_login to users and is_active to institutions."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("institutions", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("last_login", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("users", "last_login")
    op.drop_column("institutions", "is_active")
