"""TD-007: patentes do XP.md e cargos institucionais

`membros.cargo_slug` (Membro/Cavalaria/Lorde/Conselheiro/Administrador) vira
`membros.patente_slug` (Neófito→Omni, `Institucional/XP.md` Art. 2º), e os dois
cargos fora da escala de XP viram flags independentes (`conselheiro`,
`administrador` — Carta Art. VIII).

Migração de dados:

* quem tinha cargo `administrador` passa a ter `administrador = true`;
* quem tinha cargo `conselheiro` passa a ter `conselheiro = true` — preserva as
  permissões de hoje; um Administrador revisa com `/cargo-institucional`, já que
  pela Carta o Conselheiro é eleito, não alcançado por XP;
* a patente de todos é recalculada a partir do XP (Cavalaria/Lorde não existem
  mais na escala).

Colunas de XP passam a BigInteger: a escala vai até 300 bilhões (Omni).

O downgrade é aproximado: recria o cargo antigo a partir das flags e do XP com
os limiares antigos (500/1.500/3.500), sem recuperar exatamente o que existia.

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-09-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b7c8d9e0f1a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Cópia congelada de `domain/hierarchy.py` no momento desta migração — uma
# migração não pode depender do código atual, que pode mudar depois.
_LIMIARES_PATENTE: tuple[tuple[str, int], ...] = (
    ('neofito', 0),
    ('escudeiro', 104),
    ('armeiro', 415),
    ('veterano', 1_660),
    ('mestre-de-armas', 6_600),
    ('desafiante-legionario', 26_500),
    ('oficial', 106_000),
    ('centuriao', 425_000),
    ('comandante', 1_702_400),
    ('dom', 6_809_600),
    ('lorde', 27_238_400),
    ('senhor-da-guerra', 108_973_600),
    ('suserano', 435_814_400),
    ('monarca', 1_743_257_600),
    ('dominador', 12_202_803_200),
    ('renovek', 60_000_000_000),
    ('omni', 300_000_000_000),
)

_LIMIARES_CARGO_ANTIGO: tuple[tuple[str, int], ...] = (
    ('membro', 0),
    ('cavalaria', 500),
    ('lorde', 1_500),
    ('conselheiro', 3_500),
)


def _por_xp(limiares: tuple[tuple[str, int], ...], xp: int) -> str:
    alcancado = limiares[0][0]
    for slug, minimo in limiares:
        if xp >= minimo:
            alcancado = slug
    return alcancado


def upgrade() -> None:
    with op.batch_alter_table('membros', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('conselheiro', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column('administrador', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.drop_index(batch_op.f('ix_membros_cargo_slug'))
        batch_op.alter_column(
            'cargo_slug',
            new_column_name='patente_slug',
            existing_type=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'xp', type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=False
        )

    # Índices num segundo batch: no SQLite o batch recria a tabela, e um índice
    # sobre a coluna renomeada só pode ser criado depois dessa recriação.
    with op.batch_alter_table('membros', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_membros_patente_slug'), ['patente_slug'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_membros_administrador'), ['administrador'], unique=False
        )

    membros = sa.table(
        'membros',
        sa.column('id', sa.Integer()),
        sa.column('patente_slug', sa.String()),
        sa.column('xp', sa.BigInteger()),
        sa.column('conselheiro', sa.Boolean()),
        sa.column('administrador', sa.Boolean()),
    )
    conexao = op.get_bind()
    for membro_id, cargo_antigo, xp in conexao.execute(
        sa.select(membros.c.id, membros.c.patente_slug, membros.c.xp)
    ).all():
        conexao.execute(
            membros.update()
            .where(membros.c.id == membro_id)
            .values(
                patente_slug=_por_xp(_LIMIARES_PATENTE, int(xp or 0)),
                conselheiro=cargo_antigo == 'conselheiro',
                administrador=cargo_antigo == 'administrador',
            )
        )

    with op.batch_alter_table('xp_audit', schema=None) as batch_op:
        for coluna in ('quantidade', 'saldo_anterior', 'saldo_posterior'):
            batch_op.alter_column(
                coluna, type_=sa.BigInteger(), existing_type=sa.Integer(), existing_nullable=False
            )

    with op.batch_alter_table('promocoes', schema=None) as batch_op:
        batch_op.alter_column(
            'xp_no_momento',
            type_=sa.BigInteger(),
            existing_type=sa.Integer(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('promocoes', schema=None) as batch_op:
        batch_op.alter_column(
            'xp_no_momento',
            type_=sa.Integer(),
            existing_type=sa.BigInteger(),
            existing_nullable=False,
        )

    with op.batch_alter_table('xp_audit', schema=None) as batch_op:
        for coluna in ('quantidade', 'saldo_anterior', 'saldo_posterior'):
            batch_op.alter_column(
                coluna, type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=False
            )

    membros = sa.table(
        'membros',
        sa.column('id', sa.Integer()),
        sa.column('patente_slug', sa.String()),
        sa.column('xp', sa.BigInteger()),
        sa.column('conselheiro', sa.Boolean()),
        sa.column('administrador', sa.Boolean()),
    )
    conexao = op.get_bind()
    for membro_id, xp, conselheiro, administrador in conexao.execute(
        sa.select(membros.c.id, membros.c.xp, membros.c.conselheiro, membros.c.administrador)
    ).all():
        if administrador:
            cargo = 'administrador'
        elif conselheiro:
            cargo = 'conselheiro'
        else:
            cargo = _por_xp(_LIMIARES_CARGO_ANTIGO, int(xp or 0))
        conexao.execute(
            membros.update().where(membros.c.id == membro_id).values(patente_slug=cargo)
        )

    with op.batch_alter_table('membros', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_membros_administrador'))
        batch_op.drop_index(batch_op.f('ix_membros_patente_slug'))

    with op.batch_alter_table('membros', schema=None) as batch_op:
        batch_op.alter_column(
            'xp', type_=sa.Integer(), existing_type=sa.BigInteger(), existing_nullable=False
        )
        batch_op.alter_column(
            'patente_slug',
            new_column_name='cargo_slug',
            existing_type=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.drop_column('administrador')
        batch_op.drop_column('conselheiro')

    with op.batch_alter_table('membros', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_membros_cargo_slug'), ['cargo_slug'], unique=False)
