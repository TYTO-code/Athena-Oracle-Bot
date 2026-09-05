"""comunidade: Aldeao e ledger de Dracmas

Revision ID: a1b2c3d4e5f6
Revises: 176262d4a0d3
Create Date: 2026-09-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '176262d4a0d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'aldeoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('discord_id', sa.BigInteger(), nullable=False),
        sa.Column('saldo_dracmas', sa.Integer(), nullable=False),
        sa.Column('suspenso', sa.Boolean(), nullable=False),
        sa.Column('suspenso_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reativado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('migrado_para_membro_id', sa.Integer(), nullable=True),
        sa.Column('migrado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['migrado_para_membro_id'], ['membros.id'],
            name=op.f('fk_aldeoes_migrado_para_membro_id_membros'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_aldeoes')),
    )
    with op.batch_alter_table('aldeoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_aldeoes_discord_id'), ['discord_id'], unique=True)
        batch_op.create_index('ix_aldeoes_suspenso', ['suspenso'], unique=False)

    op.create_table(
        'dracmas_ledger',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('aldeao_id', sa.Integer(), nullable=True),
        sa.Column('membro_id', sa.Integer(), nullable=True),
        sa.Column(
            'tipo',
            sa.Enum(
                'doacao', 'pagamento_marketplace', 'taxa_mensal', 'ingresso_comunidade',
                'ingresso_clube', 'premio_torneio', 'bonus_venda_mercador', 'outra',
                name='tipomovimentacaodracmas', native_enum=False, length=24,
            ),
            nullable=False,
        ),
        sa.Column('valor', sa.Integer(), nullable=False),
        sa.Column('saldo_anterior', sa.Integer(), nullable=False),
        sa.Column('saldo_posterior', sa.Integer(), nullable=False),
        sa.Column('origem_referencia', sa.String(length=120), nullable=True),
        sa.Column('motivo', sa.String(length=500), nullable=False),
        sa.Column('autor_descricao', sa.String(length=120), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            '(aldeao_id IS NOT NULL AND membro_id IS NULL) '
            'OR (aldeao_id IS NULL AND membro_id IS NOT NULL)',
            name=op.f('ck_dracmas_ledger_titular_unico'),
        ),
        sa.CheckConstraint('valor <> 0', name=op.f('ck_dracmas_ledger_valor_nao_nulo')),
        sa.CheckConstraint(
            "length(trim(motivo)) > 0", name=op.f('ck_dracmas_ledger_motivo_obrigatorio')
        ),
        sa.ForeignKeyConstraint(
            ['aldeao_id'], ['aldeoes.id'],
            name=op.f('fk_dracmas_ledger_aldeao_id_aldeoes'), ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['membro_id'], ['membros.id'],
            name=op.f('fk_dracmas_ledger_membro_id_membros'), ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_dracmas_ledger')),
    )
    with op.batch_alter_table('dracmas_ledger', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dracmas_ledger_aldeao_id'), ['aldeao_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dracmas_ledger_membro_id'), ['membro_id'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_dracmas_ledger_origem_referencia'), ['origem_referencia'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_dracmas_ledger_criado_em'), ['criado_em'], unique=False)
        batch_op.create_index(
            'ix_dracmas_ledger_aldeao_data', ['aldeao_id', 'criado_em'], unique=False
        )
        batch_op.create_index(
            'ix_dracmas_ledger_membro_data', ['membro_id', 'criado_em'], unique=False
        )


def downgrade() -> None:
    op.drop_table('dracmas_ledger')
    with op.batch_alter_table('aldeoes', schema=None) as batch_op:
        batch_op.drop_index('ix_aldeoes_suspenso')
        batch_op.drop_index(batch_op.f('ix_aldeoes_discord_id'))
    op.drop_table('aldeoes')
