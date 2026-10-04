"""Confirmação da interação e gate de cadastro — RN-020.

O Discord invalida a interação se nada for confirmado em 3 segundos. Como a
checagem de permissão lê o banco (e pode consultar a plataforma), ela precisa
confirmar **antes** de qualquer I/O. E ela é também a porta do bot: quem não
tem cadastro de membro ativo na TYTO.club é recusado e **nunca** registrado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import func, select

from oraculo.bot.client import COGS, OraculoBot
from oraculo.bot.permissions import PermissaoInsuficiente
from oraculo.db.models import Membro
from oraculo.domain.errors import IntegracaoIndisponivelError, NaoCadastradoError
from oraculo.integrations.plataforma import FonteEmMemoria
from oraculo.services.acesso_service import AcessoService
from oraculo.services.importacao_service import ImportacaoService

# Comandos cuja resposta deve ser visível só para quem chamou.
COMANDOS_EFEMEROS = {
    "ajuda",
    "hierarquia",
    "auditoria",
    "sincronizar-papeis",
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
    client: object = None
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


def interacao_de(bot, usuario_id: int, nome: str = "Usuário de Teste") -> InteracaoFalsa:
    return InteracaoFalsa(user=UsuarioFalso(id=usuario_id, display_name=nome), client=bot)


async def cadastrar(session, *, discord_id: int, **campos) -> Membro:
    membro = Membro(
        discord_id=discord_id,
        id_externo=f"uid-{discord_id}",
        nome_exibicao=campos.pop("nome_exibicao", "Membro"),
        patente_slug=campos.pop("patente_slug", "neofito"),
        **campos,
    )
    session.add(membro)
    await session.commit()
    return membro


async def test_checagem_confirma_antes_de_consultar_o_banco(bot, session, engine):
    """Sem isto, o primeiro comando de cada usuário estoura os 3 segundos."""
    await cadastrar(session, discord_id=4242)
    interacao = interacao_de(bot, 4242)

    await executar_checagens(bot, "perfil", interacao)

    assert interacao.response.adiada, "a interação precisa ser confirmada na checagem"
    assert interacao.response.eventos == ["defer"]


async def test_permissao_negada_tambem_confirma_a_interacao(bot, session, engine):
    """Mesmo recusando, a interação foi confirmada — o erro chega ao usuário."""
    await cadastrar(session, discord_id=99)
    interacao = interacao_de(bot, 99)

    with pytest.raises(PermissaoInsuficiente):
        await executar_checagens(bot, "sincronizar-papeis", interacao)

    assert interacao.response.adiada
    assert interacao.response.efemera is True


async def test_quem_nao_tem_cadastro_e_recusado_e_nao_e_registrado(bot, session, engine):
    """RN-020 — o bot não faz mais auto-onboarding: sem cadastro na TYTO, sem acesso."""
    interacao = interacao_de(bot, 777, "Visitante")

    with pytest.raises(NaoCadastradoError):
        await executar_checagens(bot, "perfil", interacao)

    assert interacao.response.adiada, "a recusa também precisa chegar ao usuário"
    assert await session.scalar(select(func.count()).select_from(Membro)) == 0


async def test_todo_comando_recusa_quem_nao_tem_cadastro(bot, session, engine):
    """RN-020 — nenhum comando (nem /ajuda) responde a quem não é membro."""
    for comando_ in bot.tree.walk_commands():
        interacao = interacao_de(bot, 31337)
        with pytest.raises(NaoCadastradoError):
            await executar_checagens(bot, comando_.qualified_name, interacao)


async def test_membro_desativado_nao_passa(bot, session, engine):
    """Suspenso/removido na plataforma → desativado no espelho → sem acesso."""
    await cadastrar(session, discord_id=555, ativo=False)

    with pytest.raises(NaoCadastradoError):
        await executar_checagens(bot, "perfil", interacao_de(bot, 555))


async def test_registro_sem_vinculo_com_a_plataforma_nao_passa(session, bot, engine):
    """Um `Membro` sem `id_externo` não veio da TYTO.club: não vale como cadastro."""
    session.add(Membro(discord_id=556, nome_exibicao="Órfão", patente_slug="neofito"))
    await session.commit()

    with pytest.raises(NaoCadastradoError):
        await executar_checagens(bot, "perfil", interacao_de(bot, 556))


async def test_membro_cadastrado_passa_na_checagem(bot, session, engine):
    await cadastrar(session, discord_id=558, patente_slug="veterano", xp=4000, conselheiro=True)
    interacao = interacao_de(bot, 558, "Atena")

    await executar_checagens(bot, "auditoria", interacao)

    assert interacao.response.adiada


async def test_cadastro_recente_e_espelhado_sob_demanda(bot, session, engine):
    """Quem acabou de preencher o ID no perfil não espera o ciclo de 6h."""
    documentos = [{"id": "novo1", "name": "Recém-chegada", "discordId": "9001", "xp": 0}]
    fonte = FonteEmMemoria(documentos)
    bot.container.acesso = AcessoService(fonte, ImportacaoService(fonte))

    await executar_checagens(bot, "perfil", interacao_de(bot, 9001))

    membro = await session.scalar(select(Membro).where(Membro.discord_id == 9001))
    assert membro is not None and membro.id_externo == "novo1" and membro.ativo


async def test_sob_demanda_recusa_conta_suspensa_e_nao_cria_registro(bot, session, engine):
    fonte = FonteEmMemoria(
        [{"id": "s1", "name": "Suspenso", "discordId": "9002", "suspended": True}]
    )
    bot.container.acesso = AcessoService(fonte, ImportacaoService(fonte))

    with pytest.raises(NaoCadastradoError):
        await executar_checagens(bot, "perfil", interacao_de(bot, 9002))

    assert await session.scalar(select(func.count()).select_from(Membro)) == 0


async def test_recusa_e_lembrada_e_nao_consulta_a_plataforma_de_novo(bot, session, engine):
    """Cache negativo: repetir o comando não vira leitura no Firestore a cada vez."""
    consultas: list[int] = []

    class FonteContadora(FonteEmMemoria):
        async def buscar_por_discord(self, discord_id):
            consultas.append(discord_id)
            return await super().buscar_por_discord(discord_id)

    fonte = FonteContadora([])
    bot.container.acesso = AcessoService(fonte, ImportacaoService(fonte))

    for _ in range(3):
        with pytest.raises(NaoCadastradoError):
            await executar_checagens(bot, "perfil", interacao_de(bot, 9003))

    assert consultas == [9003]


async def test_plataforma_fora_do_ar_nao_vira_acesso_liberado(bot, session, engine):
    """Falha de leitura nega (e diz o motivo) — nunca abre a porta."""

    class FonteQuebrada(FonteEmMemoria):
        async def buscar_por_discord(self, discord_id):
            raise IntegracaoIndisponivelError("Firebase", "fora do ar")

    fonte = FonteQuebrada([])
    bot.container.acesso = AcessoService(fonte, ImportacaoService(fonte))

    with pytest.raises(IntegracaoIndisponivelError):
        await executar_checagens(bot, "perfil", interacao_de(bot, 9004))

    assert await session.scalar(select(func.count()).select_from(Membro)) == 0


@pytest.mark.parametrize("nome", sorted(COMANDOS_EFEMEROS))
async def test_comandos_sensiveis_respondem_de_forma_efemera(bot, session, engine, nome):
    await cadastrar(session, discord_id=1234)
    interacao = interacao_de(bot, 1234)

    try:
        await executar_checagens(bot, nome, interacao)
    except PermissaoInsuficiente:
        pass  # A visibilidade é decidida no defer, antes da recusa.

    assert interacao.response.efemera is True, f"/{nome} deveria responder só a quem chamou"


async def test_comandos_publicos_respondem_no_canal(bot, session, engine):
    await cadastrar(session, discord_id=1235)
    for nome in ("perfil", "ranking", "agenda", "criar-reuniao"):
        interacao = interacao_de(bot, 1235)
        try:
            await executar_checagens(bot, nome, interacao)
        except PermissaoInsuficiente:
            pass
        assert interacao.response.efemera is False, f"/{nome} deveria responder no canal"
