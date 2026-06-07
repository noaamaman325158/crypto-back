"""initial_schema

Revision ID: 04b2b242144f
Revises: 
Create Date: 2026-06-08 00:51:32.268401

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '04b2b242144f'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="user"),
        sa.Column("refresh_token", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "cryptocurrencies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("price_change_percentage_24h", sa.Float(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("market_cap_rank", sa.Integer(), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cryptocurrencies_external_id", "cryptocurrencies", ["external_id"], unique=True)
    op.create_index("ix_cryptocurrencies_symbol", "cryptocurrencies", ["symbol"])

    op.create_table(
        "watchlist",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("cryptocurrency_id", sa.UUID(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cryptocurrency_id"], ["cryptocurrencies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "cryptocurrency_id", name="uq_user_crypto"),
    )


def downgrade() -> None:
    op.drop_table("watchlist")
    op.drop_table("cryptocurrencies")
    op.drop_table("users")
