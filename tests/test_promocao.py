"""Promoção automática e cargo único — UC-003 / RN-001, RN-002, RN-003, TD-005."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from oraculo.db.models import Promocao
from oraculo.domain.hierarchy import (
    ADMINISTRADOR,
    CAVALARIA,
    CONSELHEIRO,
    LORDE,
    MEMBRO,
    Cargo,
)
from oraculo.services.promocao_service import PromocaoService
from oraculo.services.xp_service import XpService


@dataclass
class SincronizadorEspiao:
    """Registra as chamadas de sincronização em vez de falar com o Discord."""

    chamadas: list[tuple[int, str]] = field(default_factory=list)
    falhar: bool = False

    async def sincronizar(self, *, discord_id: int, cargo: Cargo, guild_id: int | None = None):
        if self.falhar:
            raise RuntimeError("Discord fora do ar")
        self.chamadas.append((discord_id, cargo.slug))


async def test_promocao_automatica_ao_cruzar_o_limiar(session, criar_membro):
    """RN-002 / RN-003 — cargo trocado, promoção registrada e Discord sincronizado."""
    espiao = SincronizadorEspiao()
    xp_service = XpService(promocoes=PromocaoService(sincronizador=espiao))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(MEMBRO, xp=450)

    resultado = await xp_service.conceder(
        session, membro=alvo, quantidade=100, motivo="Vitória em torneio", autor=autor
    )

    assert resultado.promovido
    assert resultado.promocao.cargo_anterior is MEMBRO
    assert resultado.promocao.cargo_atual is CAVALARIA
    assert alvo.cargo_slug == "cavalaria"
    assert espiao.chamadas == [(alvo.discord_id, "cavalaria")]

    registro = await session.scalar(select(Promocao))
    assert registro.cargo_anterior == "membro"
    assert registro.cargo_novo == "cavalaria"
    assert registro.xp_no_momento == 550
    assert registro.automatica is True
    assert registro.sincronizado_discord is True


async def test_membro_possui_um_unico_cargo_apos_multiplas_promocoes(session, criar_membro):
    """RN-001 — o cargo é uma coluna única: não há como acumular (TD-005)."""
    espiao = SincronizadorEspiao()
    xp_service = XpService(promocoes=PromocaoService(sincronizador=espiao))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(MEMBRO, xp=0)

    await xp_service.conceder(session, membro=alvo, quantidade=600, motivo="Etapa 1", autor=autor)
    await xp_service.conceder(session, membro=alvo, quantidade=1000, motivo="Etapa 2", autor=autor)

    assert alvo.cargo_slug == LORDE.slug
    promocoes = list((await session.execute(select(Promocao))).scalars())
    assert [(p.cargo_anterior, p.cargo_novo) for p in promocoes] == [
        ("membro", "cavalaria"),
        ("cavalaria", "lorde"),
    ]
    assert [slug for _, slug in espiao.chamadas] == ["cavalaria", "lorde"]


async def test_promocao_pula_niveis_quando_o_xp_salta(session, criar_membro):
    espiao = SincronizadorEspiao()
    xp_service = XpService(promocoes=PromocaoService(sincronizador=espiao))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(MEMBRO, xp=0)

    resultado = await xp_service.conceder(
        session, membro=alvo, quantidade=4_000, motivo="Campanha anual", autor=autor
    )

    assert resultado.promocao.cargo_atual is CONSELHEIRO
    assert alvo.cargo_slug == "conselheiro"


async def test_falha_no_discord_nao_desfaz_a_promocao(session, criar_membro):
    """A promoção é registrada mesmo com o Discord indisponível, marcada para retentativa."""
    espiao = SincronizadorEspiao(falhar=True)
    xp_service = XpService(promocoes=PromocaoService(sincronizador=espiao))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(MEMBRO, xp=490)

    resultado = await xp_service.conceder(
        session, membro=alvo, quantidade=20, motivo="Missão especial", autor=autor
    )

    assert resultado.promovido
    assert alvo.cargo_slug == "cavalaria"
    assert resultado.promocao.sincronizado is False
    registro = await session.scalar(select(Promocao))
    assert registro.sincronizado_discord is False
    assert "Discord fora do ar" in registro.erro_sincronizacao


async def test_remocao_de_xp_nao_rebaixa_por_padrao(session, criar_membro):
    """Decisão documentada em `REBAIXAMENTO_AUTOMATICO`: XP removido não perde cargo."""
    xp_service = XpService(promocoes=PromocaoService(sincronizador=SincronizadorEspiao()))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(CAVALARIA, xp=600)

    resultado = await xp_service.remover(
        session, membro=alvo, quantidade=300, motivo="Estorno de lançamento", autor=autor
    )

    assert resultado.promovido is False
    assert alvo.cargo_slug == "cavalaria"


async def test_administrador_nao_e_rebaixado_pela_progressao(session, criar_membro):
    servico = PromocaoService(sincronizador=SincronizadorEspiao())
    admin = await criar_membro(ADMINISTRADOR, xp=0)

    resultado = await servico.avaliar(session, admin)

    assert resultado.promovido is False
    assert admin.cargo_slug == "administrador"


async def test_atribuicao_manual_registra_promocao_nao_automatica(session, criar_membro):
    espiao = SincronizadorEspiao()
    servico = PromocaoService(sincronizador=espiao)
    alvo = await criar_membro(MEMBRO, xp=0)

    resultado = await servico.aplicar(
        session,
        alvo,
        cargo_novo=ADMINISTRADOR,
        automatica=False,
        autor_descricao="Fundador",
        motivo="Nomeação do conselho",
    )

    assert resultado.cargo_atual is ADMINISTRADOR
    registro = await session.scalar(select(Promocao))
    assert registro.automatica is False
    assert registro.autor_descricao == "Fundador"
    assert registro.motivo == "Nomeação do conselho"


@pytest.mark.parametrize(
    ("xp", "cargo_esperado"),
    [(0, MEMBRO), (500, CAVALARIA), (1_500, LORDE), (3_500, CONSELHEIRO)],
)
async def test_avaliar_e_idempotente(session, criar_membro, xp, cargo_esperado):
    """Reavaliar sem mudança de XP não gera promoção duplicada."""
    servico = PromocaoService(sincronizador=SincronizadorEspiao())
    membro = await criar_membro(cargo_esperado, xp=xp)

    resultado = await servico.avaliar(session, membro)

    assert resultado.promovido is False
    assert await session.scalar(select(Promocao)) is None
