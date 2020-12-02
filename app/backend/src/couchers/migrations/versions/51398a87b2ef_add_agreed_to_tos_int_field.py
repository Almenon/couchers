"""Add agreed to TOS int field

Revision ID: 51398a87b2ef
Revises: 95c58503e9c0
Create Date: 2020-12-02 09:43:04.949189

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "51398a87b2ef"
down_revision = "95c58503e9c0"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("users", sa.Column("accepted_tos", sa.Integer(), nullable=False, server_default="0"))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "accepted_tos")
    # ### end Alembic commands ###