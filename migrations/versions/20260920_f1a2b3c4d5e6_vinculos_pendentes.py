"""vinculo: verificação Discord <-> plataforma pendente

Revision ID: f1a2b3c4d5e6
Revises: a1b2c3d4e5f6
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'vinculos_pendentes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('membro_id', sa.Integer(), nullable=False),
        sa.Column('discord_id', sa.BigInteger(), nullable=False),
        sa.Column('codigo_hash', sa.String(length=64), nullable=False),
        sa.Column('tentativas', sa.Integer(), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['membro_id'], ['membros.id'],
            name=op.f('fk_vinculos_pendentes_membro_id_membros'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_vinculos_pendentes')),
        sa.UniqueConstraint('membro_id', name='uma_solicitacao_por_membro'),
    )
    with op.batch_alter_table('vinculos_pendentes', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_vinculos_pendentes_discord_id'), ['discord_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('vinculos_pendentes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_vinculos_pendentes_discord_id'))
    op.drop_table('vinculos_pendentes')
