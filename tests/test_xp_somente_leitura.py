"""Modo espelho: o bot exibe o XP, mas não o altera — RF-002 / RF-003.

Quando o XP vem da plataforma, aceitar `/conceder-xp` seria enganoso: a
sincronização seguinte sobrescreveria o saldo e a concessão sumiria sem aviso.
Estes testes garantem que a recusa é explícita.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from oraculo.config import Settings
from oraculo.container import Container
from oraculo.db.models import MovimentacaoXp
from oraculo.domain.errors import XpSomenteLeituraError
from oraculo.domain.hierarchy import NEOFITO, CargoInstitucional, Perfil
from oraculo.services.xp_service import XpService

CONSELHEIRO = CargoInstitucional.CONSELHEIRO
ADMINISTRADOR = CargoInstitucional.ADMINISTRADOR
MEMBRO = NEOFITO


@pytest.fixture
def espelho() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        firebase_project_id="clube-tyto",
        importacao_politica="espelho",
    )


def test_modo_espelho_marca_o_xp_como_somente_leitura(espelho):
    assert espelho.xp_somente_leitura is True


def test_politica_padrao_mantem_o_bot_dono_do_xp():
    cfg = Settings(_env_file=None, firebase_project_id="clube-tyto")
    assert cfg.xp_somente_leitura is False


def test_sem_plataforma_o_xp_continua_editavel():
    assert Settings(_env_file=None, importacao_politica="espelho").xp_somente_leitura is False


def test_container_propaga_a_politica_para_o_servico(espelho):
    container = Container.criar(espelho)
    assert container.xp._somente_leitura is True


@pytest.mark.parametrize("cargo", [CONSELHEIRO, ADMINISTRADOR])
async def test_conceder_xp_e_recusado_mesmo_para_administrador(session, criar_membro, cargo):
    servico = XpService(somente_leitura=True)
    autor = await criar_membro(cargo)
    alvo = await criar_membro(MEMBRO, xp=100)

    with pytest.raises(XpSomenteLeituraError) as excecao:
        await servico.conceder(
            session, membro=alvo, quantidade=50, motivo="tentativa", autor=autor
        )

    assert "plataforma" in str(excecao.value)
    assert alvo.xp == 100
    assert await session.scalar(select(func.count()).select_from(MovimentacaoXp)) == 0


async def test_consulta_de_historico_continua_liberada(session, criar_membro):
    """Somente a escrita é bloqueada; auditoria e leitura seguem funcionando."""
    servico = XpService(somente_leitura=True)
    alvo = await criar_membro(MEMBRO, xp=100)

    assert await servico.historico(
        session, membro=alvo, solicitante=Perfil(NEOFITO, conselheiro=True)
    ) == []


async def test_importacao_escreve_xp_mesmo_no_modo_espelho(session, criar_membro):
    """O bloqueio vale para comandos; a sincronização é justamente a exceção."""
    from oraculo.integrations.plataforma import FonteEmMemoria
    from oraculo.services.importacao_service import ImportacaoService, PoliticaImportacao

    servico = ImportacaoService(
        FonteEmMemoria([{"id": "u1", "nome": "Perseu", "discordId": 1, "xp": 800}]),
        politica=PoliticaImportacao.ESPELHO,
    )

    relatorio = await servico.importar(session)

    assert relatorio.criados == 1
