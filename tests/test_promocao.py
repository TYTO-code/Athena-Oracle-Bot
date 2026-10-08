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


async def _creditar(session, servico: PromocaoService, membro, quantidade: int):
    """O XP chega da plataforma (espelho); o bot só reavalia a patente (RN-002)."""
    membro.xp += quantidade
    return await servico.avaliar(session, membro)


async def test_promocao_automatica_ao_cruzar_o_limiar(session, criar_membro):
    """RN-002 / RN-003 — patente trocada, promoção registrada e Discord sincronizado."""
    espiao = SincronizadorEspiao()
    servico = PromocaoService(sincronizador=espiao)
    alvo = await criar_membro(NEOFITO, xp=ESCUDEIRO.xp_minimo - 10)

    resultado = await _creditar(session, servico, alvo, 20)

    assert resultado.promovido
    assert resultado.patente_anterior == NEOFITO
    assert resultado.patente_atual == ESCUDEIRO
    assert alvo.patente_slug == "escudeiro"
    assert espiao.chamadas == [(alvo.discord_id, "escudeiro")]

    registro = await session.scalar(select(Promocao))
    assert registro.cargo_anterior == "neofito"
    assert registro.cargo_novo == "escudeiro"
    assert registro.xp_no_momento == ESCUDEIRO.xp_minimo + 10
    assert registro.automatica is True
    assert registro.sincronizado_discord is True


async def test_membro_possui_uma_unica_patente_apos_multiplas_promocoes(session, criar_membro):
    """RN-001 — a patente é uma coluna única: não há como acumular (TD-005)."""
    espiao = SincronizadorEspiao()
    servico = PromocaoService(sincronizador=espiao)
    alvo = await criar_membro(NEOFITO, xp=0)

    await _creditar(session, servico, alvo, ESCUDEIRO.xp_minimo)
    await _creditar(session, servico, alvo, ARMEIRO.xp_minimo - ESCUDEIRO.xp_minimo)

    assert alvo.patente_slug == ARMEIRO.slug
    promocoes = list((await session.execute(select(Promocao))).scalars())
    assert [(p.cargo_anterior, p.cargo_novo) for p in promocoes] == [
        ("neofito", "escudeiro"),
        ("escudeiro", "armeiro"),
    ]
    assert [slug for _, slug in espiao.chamadas] == ["escudeiro", "armeiro"]


async def test_promocao_pula_patamares_quando_o_xp_salta(session, criar_membro):
    espiao = SincronizadorEspiao()
    servico = PromocaoService(sincronizador=espiao)
    alvo = await criar_membro(NEOFITO, xp=0)

    resultado = await _creditar(session, servico, alvo, MESTRE_DE_ARMAS.xp_minimo + 1)

    assert resultado.patente_atual == MESTRE_DE_ARMAS
    assert alvo.patente_slug == "mestre-de-armas"


async def test_falha_no_discord_nao_desfaz_a_promocao(session, criar_membro):
    """A promoção é registrada mesmo com o Discord indisponível, marcada para retentativa."""
    espiao = SincronizadorEspiao(falhar=True)
    servico = PromocaoService(sincronizador=espiao)
    alvo = await criar_membro(NEOFITO, xp=ESCUDEIRO.xp_minimo - 20)

    resultado = await _creditar(session, servico, alvo, 20)

    assert resultado.promovido
    assert alvo.patente_slug == "escudeiro"
    assert resultado.sincronizado is False
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
    membro = await criar_membro(OFICIAL, xp=OFICIAL.xp_minimo - 1)

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


@pytest.mark.parametrize(
    ("xp", "patente"),
    [
        (0, NEOFITO),
        (ESCUDEIRO.xp_minimo, ESCUDEIRO),
        (VETERANO.xp_minimo, VETERANO),
        (OFICIAL.xp_minimo, OFICIAL),
    ],
)
async def test_avaliar_e_idempotente(session, criar_membro, xp, patente):
    """Reavaliar sem mudança de XP não gera promoção duplicada."""
    servico = PromocaoService(sincronizador=SincronizadorEspiao())
    membro = await criar_membro(patente, xp=xp)

    resultado = await servico.avaliar(session, membro)

    assert resultado.promovido is False
    assert await session.scalar(select(Promocao)) is None
