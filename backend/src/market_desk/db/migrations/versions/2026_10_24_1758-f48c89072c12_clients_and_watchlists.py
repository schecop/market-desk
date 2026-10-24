"""clients and watchlists

Revision ID: f48c89072c12
Revises: 9a35677e1004
Create Date: 2026-10-24 17:58:19.350551

Written by hand: autogenerate can't backfill data, and it sees a renamed table as one table
dropped and another created (which would lose the rows).

Expand → backfill → contract, because existing watchlist rows have no client yet:
1. expand: create clients with a default client; add watchlists.client_id as nullable
2. backfill: give every existing row the default client
3. contract: make client_id NOT NULL; unique per (client_id, ticker) instead of per ticker
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f48c89072c12"
down_revision: str | Sequence[str] | None = "9a35677e1004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
        sa.UniqueConstraint("slug", name=op.f("uq_clients_slug")),
    )
    op.execute("INSERT INTO clients (slug, name) VALUES ('default', 'Default client')")

    # Postgres renames only the table: its key, index and id sequence keep the old names,
    # so rename them too and keep them matching the naming convention.
    op.rename_table("watchlist", "watchlists")
    op.execute("ALTER TABLE watchlists RENAME CONSTRAINT pk_watchlist TO pk_watchlists")
    op.execute("ALTER INDEX ix_watchlist_cik RENAME TO ix_watchlists_cik")
    op.execute("ALTER SEQUENCE watchlist_id_seq RENAME TO watchlists_id_seq")

    # 1. expand: nullable, because the existing rows have no value for it yet
    op.add_column("watchlists", sa.Column("client_id", sa.Integer(), nullable=True))
    # 2. backfill
    op.execute("UPDATE watchlists SET client_id = (SELECT id FROM clients WHERE slug = 'default')")
    # 3. contract
    op.alter_column("watchlists", "client_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_watchlists_client_id_clients"),
        "watchlists",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_watchlist_ticker", "watchlists", type_="unique")
    op.create_unique_constraint(
        op.f("uq_watchlists_client_id_ticker"), "watchlists", ["client_id", "ticker"]
    )


def downgrade() -> None:
    """Downgrade schema.

    Loses data: one watchlist can't hold two clients' copies of a ticker, so only the default
    client's rows survive.
    """
    op.execute(
        "DELETE FROM watchlists WHERE client_id <> (SELECT id FROM clients WHERE slug = 'default')"
    )
    op.drop_constraint(op.f("uq_watchlists_client_id_ticker"), "watchlists", type_="unique")
    op.create_unique_constraint(op.f("uq_watchlist_ticker"), "watchlists", ["ticker"])
    op.drop_constraint(op.f("fk_watchlists_client_id_clients"), "watchlists", type_="foreignkey")
    op.drop_column("watchlists", "client_id")

    op.execute("ALTER SEQUENCE watchlists_id_seq RENAME TO watchlist_id_seq")
    op.execute("ALTER INDEX ix_watchlists_cik RENAME TO ix_watchlist_cik")
    op.execute("ALTER TABLE watchlists RENAME CONSTRAINT pk_watchlists TO pk_watchlist")
    op.rename_table("watchlists", "watchlist")

    op.drop_table("clients")
