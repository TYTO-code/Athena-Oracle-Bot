"""Movimentação de XP e auditoria — UC-001 / RF-003 / RN-004, RN-005, RN-010, TD-006."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from oraculo.db.models import (
    MovimentacaoXp,
    OrigemAcao,
    Promocao,
    RegistroAuditoria,
    TipoMovimentacaoXp,
)
from oraculo.domain.errors import (
    MotivoObrigatorioError,
    PermissaoNegadaError,
    QuantidadeInvalidaError,
)
from oraculo.domain.hierarchy import NEOFITO, OFICIAL, OMNI, VETERANO, CargoInstitucional
from oraculo.services.xp_service import XpService

CONSELHEIRO = CargoInstitucional.CONSELHEIRO
MEMBRO = NEOFITO


@pytest.fixture
def servico() -> XpService:
    return XpService()


async def test_conceder_xp_atualiza_saldo_e_grava_auditoria(session, criar_membro, servico):
    """RN-005 / TD-006 — autor, membro, quantidade, motivo e data são gravados."""
    autor = await criar_membro(CONSELHEIRO, nome="Conselheira Atena")
    alvo = await criar_membro(MEMBRO, xp=100)

    resultado = await servico.conceder(
        session,
        membro=alvo,
        quantidade=50,
        motivo="Participação na assembleia",
        autor=autor,
        guild_id=42,
    )

    assert resultado.saldo_anterior == 100
    assert resultado.saldo_atual == 150
    assert alvo.xp == 150

    movimentacao = await session.scalar(select(MovimentacaoXp))
    assert movimentacao.autor_id == autor.id
    assert movimentacao.autor_descricao == "Conselheira Atena"
    assert movimentacao.membro_id == alvo.id
    assert movimentacao.quantidade == 50
    assert movimentacao.motivo == "Participação na assembleia"
    assert movimentacao.tipo is TipoMovimentacaoXp.CONCESSAO
    assert movimentacao.saldo_anterior == 100
    assert movimentacao.saldo_posterior == 150
    assert movimentacao.guild_id == 42
    assert movimentacao.criado_em is not None


def test_nao_existe_remocao_de_xp(servico):
    """XP é irrevogável (XP.md Art. 1º §1º) — o serviço não oferece como descontar."""
    assert not hasattr(servico, "remover")


@pytest.mark.parametrize("cargo", [MEMBRO, VETERANO, OFICIAL, OMNI])
async def test_sem_permissao_nao_altera_nada(session, criar_membro, servico, cargo):
    """RN-004 — sem o cargo Conselheiro a operação é rejeitada, qualquer que seja a patente."""
    autor = await criar_membro(cargo)
    alvo = await criar_membro(MEMBRO, xp=100)

    with pytest.raises(PermissaoNegadaError):
        await servico.conceder(
            session, membro=alvo, quantidade=10, motivo="Tentativa indevida", autor=autor
        )

    assert alvo.xp == 100
    assert await session.scalar(select(func.count()).select_from(MovimentacaoXp)) == 0


@pytest.mark.parametrize("motivo", ["", "   ", "ok"])
async def test_motivo_obrigatorio(session, criar_membro, servico, motivo):
    """RN-005 — motivo ausente ou vazio bloqueia a operação."""
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(MEMBRO, xp=10)

    with pytest.raises(MotivoObrigatorioError):
        await servico.conceder(session, membro=alvo, quantidade=10, motivo=motivo, autor=autor)

    assert alvo.xp == 10
    assert await session.scalar(select(func.count()).select_from(MovimentacaoXp)) == 0


@pytest.mark.parametrize("quantidade", [0, -5, 10**9])
async def test_quantidade_invalida(session, criar_membro, servico, quantidade):
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(MEMBRO)

    with pytest.raises(QuantidadeInvalidaError):
        await servico.conceder(
            session, membro=alvo, quantidade=quantidade, motivo="Motivo válido", autor=autor
        )


async def test_automacao_do_sistema_dispensa_autor(session, criar_membro, servico):
    alvo = await criar_membro(MEMBRO, xp=0)

    resultado = await servico.conceder(
        session,
        membro=alvo,
        quantidade=25,
        motivo="Bônus automático de presença",
        autor=None,
        origem=OrigemAcao.SISTEMA,
    )

    assert resultado.movimentacao.autor_id is None
    assert resultado.movimentacao.autor_descricao == "sistema"


async def test_historico_exige_permissao(session, criar_membro, servico):
    alvo = await criar_membro(MEMBRO, xp=10)

    with pytest.raises(PermissaoNegadaError):
        await servico.historico(session, membro=alvo, solicitante=alvo.perfil)


async def test_trilha_reconstroi_o_saldo(session, criar_membro, servico):
    """RN-010 — a soma da trilha imutável precisa bater com o saldo atual."""
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(MEMBRO, xp=0)

    for quantidade in (100, 250, 75):
        await servico.conceder(
            session, membro=alvo, quantidade=quantidade, motivo="Missão cumprida", autor=autor
        )

    saldo, soma_da_trilha = await servico.conciliar(session, membro=alvo)
    assert saldo == soma_da_trilha == 425


async def test_movimentacao_gera_registro_de_auditoria_na_promocao(session, criar_membro, servico):
    """RF-012 — promoção decorrente do XP entra no log de auditoria."""
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(MEMBRO, xp=0)

    await servico.conceder(
        session, membro=alvo, quantidade=2_000, motivo="Torneio de verão", autor=autor
    )

    assert await session.scalar(select(func.count()).select_from(Promocao)) == 1
    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "promocao.aplicada")
    )
    assert registro is not None
    assert registro.dados["patente_nova"] == "veterano"
