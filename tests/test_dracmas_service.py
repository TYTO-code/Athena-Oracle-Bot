"""Carteira de Dracmas da Comunidade — RN-011 a RN-015 / `DRACMAS.md` / `COMUNIDADE_E_CLUBE.md`."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from oraculo.db.models import Aldeao, MovimentacaoDracmas, TipoMovimentacaoDracmas
from oraculo.domain.errors import (
    ContaDracmasSuspensaError,
    MotivoDracmasObrigatorioError,
    QuantidadeDracmasInvalidaError,
    SaldoDracmasInsuficienteError,
)
from oraculo.services.dracmas_service import CUSTO_INGRESSO_COMUNIDADE, DracmasService

DISCORD_ID_1 = 10_001
DISCORD_ID_2 = 10_002


@pytest.fixture
def servico() -> DracmasService:
    return DracmasService()


async def test_credito_a_conta_nova_cria_aldeao_e_cobra_ingresso(session, servico):
    """COMUNIDADE_E_CLUBE.md Art. 3º §1º/§3º — primeiro crédito cria a conta e cobra 30.000."""
    resultado = await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=50_000,
        tipo=TipoMovimentacaoDracmas.PREMIO_TORNEIO,
        motivo="Pódio do Torneio X",
    )

    assert resultado.criado_agora is True
    assert resultado.ingresso_cobrado is True
    assert resultado.saldo_atual == 50_000 - CUSTO_INGRESSO_COMUNIDADE
    assert resultado.aldeao.saldo_dracmas == 20_000
    assert resultado.aldeao.suspenso is False

    aldeao = await session.scalar(select(Aldeao).where(Aldeao.discord_id == DISCORD_ID_1))
    assert aldeao is not None
    assert aldeao.saldo_dracmas == 20_000

    movimentacoes = (
        await session.execute(
            select(MovimentacaoDracmas)
            .where(MovimentacaoDracmas.aldeao_id == aldeao.id)
            .order_by(MovimentacaoDracmas.id)
        )
    ).scalars().all()
    assert len(movimentacoes) == 2
    assert movimentacoes[0].tipo is TipoMovimentacaoDracmas.PREMIO_TORNEIO
    assert movimentacoes[0].valor == 50_000
    assert movimentacoes[1].tipo is TipoMovimentacaoDracmas.INGRESSO_COMUNIDADE
    assert movimentacoes[1].valor == -CUSTO_INGRESSO_COMUNIDADE


async def test_credito_com_dispensa_de_taxa_nao_cobra_ingresso(session, servico):
    """TORNEIOS.md Art. 7º §5º — 1º colocado do Torneio de Hacking é dispensado da taxa."""
    resultado = await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=5_000,
        tipo=TipoMovimentacaoDracmas.PREMIO_TORNEIO,
        motivo="1º lugar Torneio de Hacking",
        dispensa_taxa_ingresso=True,
    )

    assert resultado.criado_agora is True
    assert resultado.ingresso_cobrado is False
    assert resultado.saldo_atual == 5_000


async def test_credito_menor_que_taxa_deixa_conta_negativa_e_suspensa(session, servico):
    """A cobrança do Art. 3º §1º é incondicional no primeiro crédito — mesmo saldo insuficiente."""
    resultado = await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=1_000,
        tipo=TipoMovimentacaoDracmas.BONUS_VENDA_MERCADOR,
        motivo="Bônus de venda por porte micro",
    )

    assert resultado.saldo_atual == 1_000 - CUSTO_INGRESSO_COMUNIDADE
    assert resultado.saldo_atual < 0
    assert resultado.suspenso_agora is True
    assert resultado.aldeao.suspenso is True
    assert resultado.aldeao.suspenso_em is not None


async def test_segundo_credito_nao_cobra_ingresso_de_novo(session, servico):
    primeiro = await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=40_000,
        tipo=TipoMovimentacaoDracmas.PREMIO_TORNEIO,
        motivo="Pódio",
    )
    segundo = await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=5_000,
        tipo=TipoMovimentacaoDracmas.BONUS_VENDA_MERCADOR,
        motivo="Bônus de venda",
    )

    assert segundo.criado_agora is False
    assert segundo.ingresso_cobrado is False
    assert segundo.saldo_atual == primeiro.saldo_atual + 5_000


async def test_debito_pode_deixar_saldo_negativo_e_suspende(session, servico):
    credito = await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=40_000,
        tipo=TipoMovimentacaoDracmas.PREMIO_TORNEIO,
        motivo="Pódio",
    )
    saldo_antes = credito.saldo_atual

    resultado = await servico.debitar(
        session,
        aldeao=credito.aldeao,
        valor=saldo_antes + 500,
        tipo=TipoMovimentacaoDracmas.PAGAMENTO_MARKETPLACE,
        motivo="Compra no Marketplace",
    )

    assert resultado.saldo_atual == -500
    assert resultado.suspenso_agora is True


async def test_debito_em_conta_suspensa_e_recusado(session, servico):
    credito = await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=1_000,  # menor que a taxa de ingresso — já nasce suspensa
        tipo=TipoMovimentacaoDracmas.BONUS_VENDA_MERCADOR,
        motivo="Bônus pequeno",
    )
    assert credito.aldeao.suspenso is True

    with pytest.raises(ContaDracmasSuspensaError):
        await servico.debitar(
            session,
            aldeao=credito.aldeao,
            valor=10,
            tipo=TipoMovimentacaoDracmas.PAGAMENTO_MARKETPLACE,
            motivo="Nova compra",
        )


async def test_debitar_exigindo_saldo_recusa_sem_fundos(session, servico):
    credito = await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=35_000,
        tipo=TipoMovimentacaoDracmas.PREMIO_TORNEIO,
        motivo="Pódio",
    )

    with pytest.raises(SaldoDracmasInsuficienteError):
        await servico.debitar_exigindo_saldo(
            session,
            aldeao=credito.aldeao,
            valor=credito.saldo_atual + 1,
            tipo=TipoMovimentacaoDracmas.DOACAO,
            motivo="Doação maior que o saldo",
        )


async def test_doacao_move_saldo_entre_contas_e_cria_destino(session, servico):
    await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=40_000,
        tipo=TipoMovimentacaoDracmas.PREMIO_TORNEIO,
        motivo="Pódio",
    )

    resultado_debito, resultado_credito = await servico.doar(
        session,
        discord_id_origem=DISCORD_ID_1,
        discord_id_destino=DISCORD_ID_2,
        valor=2_000,
        motivo="Ajudando um colega novo",
        autor_descricao="Doador Um",
    )

    assert resultado_debito.aldeao.discord_id == DISCORD_ID_1
    assert resultado_credito.aldeao.discord_id == DISCORD_ID_2
    # destino era conta nova: cobra ingresso também, igual a qualquer outro primeiro crédito.
    assert resultado_credito.criado_agora is True
    assert resultado_credito.ingresso_cobrado is True
    assert resultado_credito.saldo_atual == 2_000 - CUSTO_INGRESSO_COMUNIDADE


async def test_doacao_sem_conta_de_origem_e_recusada(session, servico):
    with pytest.raises(SaldoDracmasInsuficienteError):
        await servico.doar(
            session,
            discord_id_origem=DISCORD_ID_1,
            discord_id_destino=DISCORD_ID_2,
            valor=100,
            motivo="Tentativa sem saldo",
            autor_descricao="Ninguém",
        )


async def test_valor_invalido_e_recusado(session, servico):
    with pytest.raises(QuantidadeDracmasInvalidaError):
        await servico.creditar(
            session,
            discord_id=DISCORD_ID_1,
            valor=0,
            tipo=TipoMovimentacaoDracmas.OUTRA,
            motivo="Valor inválido",
        )
    with pytest.raises(QuantidadeDracmasInvalidaError):
        await servico.creditar(
            session,
            discord_id=DISCORD_ID_1,
            valor=-10,
            tipo=TipoMovimentacaoDracmas.OUTRA,
            motivo="Valor negativo",
        )


async def test_motivo_vazio_e_recusado(session, servico):
    with pytest.raises(MotivoDracmasObrigatorioError):
        await servico.creditar(
            session,
            discord_id=DISCORD_ID_1,
            valor=100,
            tipo=TipoMovimentacaoDracmas.OUTRA,
            motivo="  ",
        )


async def test_saldo_de_e_extrato_de_sem_conta_retornam_vazio(session, servico):
    assert await servico.saldo_de(session, DISCORD_ID_1) is None
    assert await servico.extrato_de(session, DISCORD_ID_1) == []


async def test_extrato_de_lista_movimentacoes_mais_recentes_primeiro(session, servico):
    await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=40_000,
        tipo=TipoMovimentacaoDracmas.PREMIO_TORNEIO,
        motivo="Pódio",
    )
    await servico.creditar(
        session,
        discord_id=DISCORD_ID_1,
        valor=1_000,
        tipo=TipoMovimentacaoDracmas.BONUS_VENDA_MERCADOR,
        motivo="Bônus de venda",
    )

    extrato = await servico.extrato_de(session, DISCORD_ID_1, limite=1)

    assert len(extrato) == 1
    assert extrato[0].tipo is TipoMovimentacaoDracmas.BONUS_VENDA_MERCADOR
