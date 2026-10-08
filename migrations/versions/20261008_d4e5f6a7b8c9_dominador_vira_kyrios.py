"""Patente "Dominador" vira "Kyrios"; entram Invictus e Dominus no nível divino

O slug `dominador` (15) passa a `kyrios` em `membros.patente_slug` e no histórico de
`promocoes` (`cargo_anterior`/`cargo_novo`). O patamar e o limiar são os mesmos, então nenhuma
patente muda de posição. Invictus (16) e Dominus (17) são títulos novos, sem membros: nada a
migrar. Renovek e Omni mudam de ordem (16→18 e 17→19), mas a ordem não é gravada — só o slug.

A patente de um membro nunca é rebaixada por esta migração (XP.md Art. 1º §3º): ela só renomeia.
O downgrade devolve `kyrios` a `dominador`; membros que já tenham sido promovidos a Invictus ou
Dominus ficam com esses slugs (não existem na escala antiga), então o downgrade deve ser usado só
antes de alguém alcançar esses títulos.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-08 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ATUALIZACOES = (
    sa.text("UPDATE membros SET patente_slug = :novo WHERE patente_slug = :antigo"),
    sa.text("UPDATE promocoes SET cargo_anterior = :novo WHERE cargo_anterior = :antigo"),
    sa.text("UPDATE promocoes SET cargo_novo = :novo WHERE cargo_novo = :antigo"),
)


def _renomear(antigo: str, novo: str) -> None:
    conexao = op.get_bind()
    for comando in _ATUALIZACOES:
        conexao.execute(comando, {"antigo": antigo, "novo": novo})


def upgrade() -> None:
    _renomear("dominador", "kyrios")


def downgrade() -> None:
    _renomear("kyrios", "dominador")
