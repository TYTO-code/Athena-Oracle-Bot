"""comunicados: avisos oficiais publicados e programados (RN-018)

Revision ID: b7c8d9e0f1a2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7c8d9e0f1a2'
down_revision: str | None = 'f1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'comunicados',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('titulo', sa.String(length=160), nullable=False),
        sa.Column('corpo', sa.Text(), nullable=False),
        sa.Column('canal_id', sa.BigInteger(), nullable=False),
        sa.Column('guild_id', sa.BigInteger(), nullable=True),
        sa.Column(
            'mencao',
            sa.Enum('nenhuma', 'aqui', 'todos', name='tipomencao', native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column('publicar_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'agendado', 'publicando', 'publicado', 'cancelado', 'falhou',
                name='statuscomunicado', native_enum=False, length=16,
            ),
            nullable=False,
        ),
        sa.Column('autor_id', sa.Integer(), nullable=False),
        sa.Column('reservado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tentativas', sa.Integer(), nullable=False),
        sa.Column('erro', sa.Text(), nullable=True),
        sa.Column('publicado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('mensagem_id', sa.BigInteger(), nullable=True),
        sa.Column('cancelado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelado_por_id', sa.Integer(), nullable=True),
        sa.Column('motivo_cancelamento', sa.String(length=500), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            'length(trim(titulo)) > 0', name=op.f('ck_comunicados_titulo_obrigatorio')
        ),
        sa.CheckConstraint(
            'length(trim(corpo)) > 0', name=op.f('ck_comunicados_corpo_obrigatorio')
        ),
        sa.ForeignKeyConstraint(
            ['autor_id'], ['membros.id'],
            name=op.f('fk_comunicados_autor_id_membros'), ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['cancelado_por_id'], ['membros.id'],
            name=op.f('fk_comunicados_cancelado_por_id_membros'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_comunicados')),
    )
    with op.batch_alter_table('comunicados', schema=None) as batch_op:
        batch_op.create_index('ix_comunicados_fila', ['status', 'publicar_em'], unique=False)
        batch_op.create_index(batch_op.f('ix_comunicados_autor_id'), ['autor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_comunicados_guild_id'), ['guild_id'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_comunicados_publicar_em'), ['publicar_em'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('comunicados', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_comunicados_publicar_em'))
        batch_op.drop_index(batch_op.f('ix_comunicados_guild_id'))
        batch_op.drop_index(batch_op.f('ix_comunicados_autor_id'))
        batch_op.drop_index('ix_comunicados_fila')
    op.drop_table('comunicados')
