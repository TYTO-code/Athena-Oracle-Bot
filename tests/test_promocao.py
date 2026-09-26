"""Promoção de patente e patente única — UC-003 / RN-001, RN-002, RN-003, TD-005, TD-007."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from oraculo.db.models import Promocao
from oraculo.domain.hierarchy import (
    ARMEIRO,
    ESCUDEIRO,
    MESTRE_DE_ARMAS,
    NEOFITO,
    OFICIAL,
    VETERANO,
    CargoInstitucional,
    Patente,
)
from oraculo.services.promocao_service import PromocaoService
from oraculo.services.xp_service import XpService


@dataclass
class SincronizadorEspiao:
    """Registra as chamadas de sincronização em vez de falar com o Discord."""

    chamadas: list[tuple[int, str]] = field(default_factory=list)
    institucionais: list[tuple[int, str, bool]] = field(default_factory=list)
    falhar: bool = False

    async def sincronizar(self, *, discord_id: int, patente: Patente, guild_id: int | None = None):
        if self.falhar:
            raise RuntimeError("Discord fora do ar")
        self.chamadas.append((discord_id, patente.slug))

    async def definir_cargo_institucional(
        self, *, discord_id: int, cargo: CargoInstitucional, ativo: bool, guild_id=None
    ):
        if self.falhar:
            raise RuntimeError("Discord fora do ar")
        self.institucionais.append((discord_id, cargo.value, ativo))


CONSELHEIRO = CargoInstitucional.CONSELHEIRO


async def test_promocao_automatica_ao_cruzar_o_limiar(session, criar_membro):
    """RN-002 / RN-003 — patente trocada, promoção registrada e Discord sincronizado."""
    espiao = SincronizadorEspiao()
    xp_service = XpService(promocoes=PromocaoService(sincronizador=espiao))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(NEOFITO, xp=90)

    resultado = await xp_service.conceder(
        session, membro=alvo, quantidade=20, motivo="Vitória em torneio", autor=autor
    )

    assert resultado.promovido
    assert resultado.promocao.patente_anterior == NEOFITO
    assert resultado.promocao.patente_atual == ESCUDEIRO
    assert alvo.patente_slug == "escudeiro"
    assert espiao.chamadas == [(alvo.discord_id, "escudeiro")]

    registro = await session.scalar(select(Promocao))
    assert registro.cargo_anterior == "neofito"
    assert registro.cargo_novo == "escudeiro"
    assert registro.xp_no_momento == 110
    assert registro.automatica is True
    assert registro.sincronizado_discord is True


async def test_membro_possui_uma_unica_patente_apos_multiplas_promocoes(session, criar_membro):
    """RN-001 — a patente é uma coluna única: não há como acumular (TD-005)."""
    espiao = SincronizadorEspiao()
    xp_service = XpService(promocoes=PromocaoService(sincronizador=espiao))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(NEOFITO, xp=0)

    await xp_service.conceder(session, membro=alvo, quantidade=200, motivo="Etapa 1", autor=autor)
    await xp_service.conceder(session, membro=alvo, quantidade=300, motivo="Etapa 2", autor=autor)

    assert alvo.patente_slug == ARMEIRO.slug
    promocoes = list((await session.execute(select(Promocao))).scalars())
    assert [(p.cargo_anterior, p.cargo_novo) for p in promocoes] == [
        ("neofito", "escudeiro"),
        ("escudeiro", "armeiro"),
    ]
    assert [slug for _, slug in espiao.chamadas] == ["escudeiro", "armeiro"]


async def test_promocao_pula_patamares_quando_o_xp_salta(session, criar_membro):
    espiao = SincronizadorEspiao()
    xp_service = XpService(promocoes=PromocaoService(sincronizador=espiao))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(NEOFITO, xp=0)

    resultado = await xp_service.conceder(
        session, membro=alvo, quantidade=7_000, motivo="Campanha anual", autor=autor
    )

    assert resultado.promocao.patente_atual == MESTRE_DE_ARMAS
    assert alvo.patente_slug == "mestre-de-armas"


async def test_falha_no_discord_nao_desfaz_a_promocao(session, criar_membro):
    """A promoção é registrada mesmo com o Discord indisponível, marcada para retentativa."""
    espiao = SincronizadorEspiao(falhar=True)
    xp_service = XpService(promocoes=PromocaoService(sincronizador=espiao))
    autor = await criar_membro(CONSELHEIRO)
    alvo = await criar_membro(NEOFITO, xp=100)

    resultado = await xp_service.conceder(
        session, membro=alvo, quantidade=20, motivo="Missão especial", autor=autor
    )

    assert resultado.promovido
    assert alvo.patente_slug == "escudeiro"
    assert resultado.promocao.sincronizado is False
    registro = await session.scalar(select(Promocao))
    assert registro.sincronizado_discord is False
    assert "Discord fora do ar" in registro.erro_sincronizacao


async def test_patente_nunca_e_rebaixada(session, criar_membro):
    """XP.md Art. 1º §3º — patente alcançada é permanente, mesmo com XP abaixo do limiar."""
    servico = PromocaoService(sincronizador=SincronizadorEspiao())
    membro = await criar_membro(VETERANO, xp=0)

    resultado = await servico.avaliar(session, membro)

    assert resultado.promovido is False
    assert membro.patente_slug == "veterano"


async def test_aplicar_recusa_patente_igual_ou_inferior(session, criar_membro):
    servico = PromocaoService(sincronizador=SincronizadorEspiao())
    membro = await criar_membro(OFICIAL, xp=106_000)

    with pytest.raises(ValueError, match="irrevogável"):
        await servico.aplicar(
            session,
            membro,
            patente_nova=VETERANO,
            automatica=False,
            autor_descricao="alguém",
            motivo="tentativa de rebaixar",
        )
    assert membro.patente_slug == "oficial"


async def test_confirmar_aplica_so_a_patente_que_o_xp_determina(session, criar_membro):
    """`/confirmar-patente` — o Administrador libera, não escolhe a patente."""
    espiao = SincronizadorEspiao()
    servico = PromocaoService(sincronizador=espiao)
    membro = await criar_membro(NEOFITO, xp=500_000)

    resultado = await servico.confirmar(session, membro, autor_descricao="Admin")

    assert resultado.promovido
    assert membro.patente_slug == "centuriao"
    registro = await session.scalar(select(Promocao))
    assert registro.automatica is False
    assert registro.autor_descricao == "Admin"

    de_novo = await servico.confirmar(session, membro, autor_descricao="Admin")
    assert de_novo.promovido is False


@pytest.mark.parametrize(
    ("xp", "patente"),
    [(0, NEOFITO), (104, ESCUDEIRO), (1_660, VETERANO), (106_000, OFICIAL)],
)
async def test_avaliar_e_idempotente(session, criar_membro, xp, patente):
    """Reavaliar sem mudança de XP não gera promoção duplicada."""
    servico = PromocaoService(sincronizador=SincronizadorEspiao())
    membro = await criar_membro(patente, xp=xp)

    resultado = await servico.avaliar(session, membro)

    assert resultado.promovido is False
    assert await session.scalar(select(Promocao)) is None
