"""Confirmação da interação — evita "O aplicativo não respondeu".

O Discord invalida a interação se nada for confirmado em 3 segundos. Como a
checagem de permissão lê (e às vezes escreve) no banco, ela precisa confirmar
**antes** de qualquer I/O. Estes testes travam esse contrato.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from oraculo.bot.client import COGS, OraculoBot
from oraculo.bot.permissions import PermissaoInsuficiente
from oraculo.db.models import Membro
from oraculo.domain.hierarchy import NEOFITO

# Comandos cuja resposta deve ser visível só para quem chamou.
COMANDOS_EFEMEROS = {
    "ajuda",
    "hierarquia",
    "historico-xp",
    "auditoria",
    "cargo-institucional",
    "confirmar-patente",
    "sincronizar-papeis",
    "migrar-para-clube",
    "verificar-cargos",
}


@dataclass
class RespostaFalsa:
    adiada: bool = False
    efemera: bool | None = None
    eventos: list[str] = field(default_factory=list)

    def is_done(self) -> bool:
        return self.adiada

    async def defer(self, ephemeral: bool = False) -> None:
        self.adiada = True
        self.efemera = ephemeral
        self.eventos.append("defer")


@dataclass
class UsuarioFalso:
    id: int
    display_name: str = "Usuário de Teste"


@dataclass
class InteracaoFalsa:
    user: UsuarioFalso
    response: RespostaFalsa = field(default_factory=RespostaFalsa)
    guild_id: int | None = 1


@pytest.fixture
async def bot(settings):
    cliente = OraculoBot(settings)
    for cog in COGS:
        await cliente.load_extension(cog)
    try:
        yield cliente
    finally:
        await cliente.container.fechar()


def comando(bot, nome):
    return next(c for c in bot.tree.walk_commands() if c.qualified_name == nome)


async def executar_checagens(bot, nome, interacao):
    for verificacao in comando(bot, nome).checks:
        await verificacao(interacao)


async def test_checagem_confirma_antes_de_consultar_o_banco(bot, session, engine):
    """Sem isto, o primeiro comando de cada usuário estoura os 3 segundos."""
    interacao = InteracaoFalsa(user=UsuarioFalso(id=4242))

    await executar_checagens(bot, "perfil", interacao)

    assert interacao.response.adiada, "a interação precisa ser confirmada na checagem"
    assert interacao.response.eventos == ["defer"]


async def test_permissao_negada_tambem_confirma_a_interacao(bot, session, engine):
    """Mesmo recusando, a interação foi confirmada — o erro chega ao usuário."""
    interacao = InteracaoFalsa(user=UsuarioFalso(id=99))

    with pytest.raises(PermissaoInsuficiente):
        await executar_checagens(bot, "conceder-xp", interacao)

    assert interacao.response.adiada
    assert interacao.response.efemera is False


async def test_autor_e_registrado_no_primeiro_contato(bot, session, engine):
    """RF-001 — auto-onboarding: quem nunca usou o bot nasce Neófito, sem cargo."""
    interacao = InteracaoFalsa(user=UsuarioFalso(id=777, display_name="Novato"))

    await executar_checagens(bot, "perfil", interacao)

    membro = await session.scalar(select(Membro).where(Membro.discord_id == 777))
    assert membro is not None
    assert membro.nome_exibicao == "Novato"
    assert membro.patente_slug == NEOFITO.slug
    assert membro.conselheiro is False and membro.administrador is False


async def test_conselheiro_passa_na_checagem_de_xp(bot, session, engine):
    session.add(
        Membro(discord_id=555, nome_exibicao="Atena", patente_slug="veterano", xp=4000,
               conselheiro=True)
    )
    await session.commit()
    interacao = InteracaoFalsa(user=UsuarioFalso(id=555, display_name="Atena"))

    await executar_checagens(bot, "conceder-xp", interacao)

    assert interacao.response.adiada


@pytest.mark.parametrize("nome", sorted(COMANDOS_EFEMEROS))
async def test_comandos_sensiveis_respondem_de_forma_efemera(bot, session, engine, nome):
    interacao = InteracaoFalsa(user=UsuarioFalso(id=1234))

    try:
        await executar_checagens(bot, nome, interacao)
    except PermissaoInsuficiente:
        pass  # A visibilidade é decidida no defer, antes da recusa.

    assert interacao.response.efemera is True, f"/{nome} deveria responder só a quem chamou"


async def test_comandos_publicos_respondem_no_canal(bot, session, engine):
    for nome in ("perfil", "ranking", "agenda", "criar-reuniao"):
        interacao = InteracaoFalsa(user=UsuarioFalso(id=1234))
        try:
            await executar_checagens(bot, nome, interacao)
        except PermissaoInsuficiente:
            pass
        assert interacao.response.efemera is False, f"/{nome} deveria responder no canal"
