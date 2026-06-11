"""add price_history dead_letter last_refreshed_at

Revision ID: 0d5c4492046a
Revises: 04b2b242144f
Create Date: 2026-06-11 19:36:32.272168

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0d5c4492046a"
down_revision: str | None = "04b2b242144f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cryptocurrencies",
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "price_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_history_external_id", "price_history", ["external_id"])
    op.create_index("ix_price_history_recorded_at", "price_history", ["recorded_at"])
    op.create_index(
        "ix_price_history_external_id_recorded_at",
        "price_history",
        ["external_id", "recorded_at"],
    )

    op.create_table(
        "refresh_dead_letter",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("batch_page", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(2000), nullable=False),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("refresh_dead_letter")
    op.drop_index("ix_price_history_external_id_recorded_at", table_name="price_history")
    op.drop_index("ix_price_history_recorded_at", table_name="price_history")
    op.drop_index("ix_price_history_external_id", table_name="price_history")
    op.drop_table("price_history")
    op.drop_column("cryptocurrencies", "last_refreshed_at")
