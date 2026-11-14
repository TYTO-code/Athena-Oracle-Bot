"""Uso e custo estimado da API do Claude por dia e modelo (teto diário e orçamento do mês)

Tabela agregada, sem pessoa (D15 em docs/DECISOES.md). `dia` é a data UTC em ISO (`AAAA-MM-DD`),
o que deixa a soma do mês num `LIKE 'AAAA-MM-%'` simples em SQLite e Postgres.

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-11-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uso_llm_diario",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dia", sa.String(length=10), nullable=False),
        sa.Column("modelo", sa.String(length=80), nullable=False),
        sa.Column("chamadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_entrada", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_saida", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_cache_escrita", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tokens_cache_leitura", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("custo_microdolares", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dia", "modelo", name="uso_llm_dia_modelo"),
    )
    op.create_index("ix_uso_llm_diario_dia", "uso_llm_diario", ["dia"])


def downgrade() -> None:
    op.drop_index("ix_uso_llm_diario_dia", table_name="uso_llm_diario")
    op.drop_table("uso_llm_diario")
