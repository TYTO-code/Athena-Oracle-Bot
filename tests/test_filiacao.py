"""Filiação ao Clube: migração do saldo da Comunidade — F2-007 (Art. 4º §1º-A)."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest
from sqlalchemy import select

from oraculo.db.models import (
    Membro,
    MovimentacaoDracmas,
    RegistroAuditoria,
    TipoMovimentacaoDracmas,
)
from oraculo.domain.errors import (
    ContaComunidadeMigradaError,
    ContaDracmasSuspensaError,
    IntegracaoIndisponivelError,
    PermissaoNegadaError,
    RecursoNaoEncontradoError,
)
from oraculo.domain.hierarchy import OFICIAL, CargoInstitucional
from oraculo.integrations.economia_plataforma import EconomiaPlataformaHttp
from oraculo.services.dracmas_service import DracmasService
from oraculo.services.filiacao_service import FiliacaoService, MembroSemVinculoNaPlataformaError

ADMINISTRADOR = CargoInstitucional.ADMINISTRADOR


@dataclass
class EconomiaFalsa:
    chamadas: list[tuple[str, int, str]] = field(default_factory=list)
    falhar: bool = False

    async def migrar_saldo_comunidade(self, *, id_externo: str, valor: int, referencia: str):
        if self.falhar:
            raise IntegracaoIndisponivelError("Plataforma", "fora do ar")
        self.chamadas.append((id_externo, valor, referencia))


async def _aldeao_com_saldo(session, discord_id: int, saldo: int):
    resultado = await DracmasService().creditar(
        session,
        discord_id=discord_id,
        valor=saldo,
        tipo=TipoMovimentacaoDracmas.PREMIO_TORNEIO,
        motivo="Prêmio",
        dispensa_taxa_ingresso=True,
    )
    return resultado.aldeao


async def _novo_membro(session, discord_id: int, *, id_externo: str | None = "uid-1"):
    membro = Membro(
        discord_id=discord_id, nome_exibicao="Novo membro", id_externo=id_externo, xp=0
    )
    session.add(membro)
    await session.flush()
    return membro


async def test_saldo_inteiro_vai_para_a_plataforma_e_aldeao_fica_zerado(session, criar_membro):
    economia = EconomiaFalsa()
    admin = await criar_membro(ADMINISTRADOR)
    aldeao = await _aldeao_com_saldo(session, 77, 1_200)
    membro = await _novo_membro(session, 77)

    resultado = await FiliacaoService(economia).migrar_saldo_para_clube(
        session, membro=membro, autor=admin
    )

    assert resultado.valor == 1_200
    assert economia.chamadas == [("uid-1", 1_200, f"aldeao:{aldeao.id}")]
    assert aldeao.saldo_dracmas == 0
    assert aldeao.migrado_para_membro_id == membro.id
    saida = await session.scalar(
        select(MovimentacaoDracmas).where(
            MovimentacaoDracmas.tipo == TipoMovimentacaoDracmas.MIGRACAO_CLUBE
        )
    )
    assert (saida.valor, saida.saldo_posterior) == (-1_200, 0)
    assert await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "comunidade.saldo_migrado")
    )


async def test_conta_migrada_nao_recebe_mais_dracmas_na_comunidade(session, criar_membro):
    admin = await criar_membro(ADMINISTRADOR)
    await _aldeao_com_saldo(session, 78, 10)
    membro = await _novo_membro(session, 78)
    await FiliacaoService(EconomiaFalsa()).migrar_saldo_para_clube(
        session, membro=membro, autor=admin
    )

    with pytest.raises(ContaComunidadeMigradaError):
        await DracmasService().creditar(
            session,
            discord_id=78,
            valor=5,
            tipo=TipoMovimentacaoDracmas.DOACAO,
            motivo="Doação",
        )
    with pytest.raises(ContaComunidadeMigradaError):
        await FiliacaoService(EconomiaFalsa()).migrar_saldo_para_clube(
            session, membro=membro, autor=admin
        )


async def test_falha_na_plataforma_nao_zera_o_aldeao(session, criar_membro):
    admin = await criar_membro(ADMINISTRADOR)
    aldeao = await _aldeao_com_saldo(session, 79, 300)
    membro = await _novo_membro(session, 79)

    with pytest.raises(IntegracaoIndisponivelError):
        await FiliacaoService(EconomiaFalsa(falhar=True)).migrar_saldo_para_clube(
            session, membro=membro, autor=admin
        )

    assert aldeao.saldo_dracmas == 300
    assert aldeao.migrado is False


async def test_recusas(session, criar_membro):
    admin = await criar_membro(ADMINISTRADOR)
    servico = FiliacaoService(EconomiaFalsa())

    sem_conta = await _novo_membro(session, 80)
    with pytest.raises(RecursoNaoEncontradoError):
        await servico.migrar_saldo_para_clube(session, membro=sem_conta, autor=admin)

    await _aldeao_com_saldo(session, 81, 50)
    sem_vinculo = await _novo_membro(session, 81, id_externo=None)
    with pytest.raises(MembroSemVinculoNaPlataformaError):
        await servico.migrar_saldo_para_clube(session, membro=sem_vinculo, autor=admin)

    suspenso = await _aldeao_com_saldo(session, 82, 50)
    suspenso.suspenso = True
    membro_suspenso = await _novo_membro(session, 82, id_externo="uid-82")
    with pytest.raises(ContaDracmasSuspensaError):
        await servico.migrar_saldo_para_clube(session, membro=membro_suspenso, autor=admin)

    nao_admin = await criar_membro(OFICIAL)
    with pytest.raises(PermissaoNegadaError):
        await servico.migrar_saldo_para_clube(session, membro=sem_vinculo, autor=nao_admin)


async def test_saldo_zero_so_marca_a_migracao(session, criar_membro):
    economia = EconomiaFalsa()
    admin = await criar_membro(ADMINISTRADOR)
    aldeao = await _aldeao_com_saldo(session, 83, 10)
    aldeao.saldo_dracmas = 0
    membro = await _novo_membro(session, 83, id_externo="uid-83")

    await FiliacaoService(economia).migrar_saldo_para_clube(session, membro=membro, autor=admin)

    assert economia.chamadas == []
    assert aldeao.migrado is True


async def test_cliente_http_envia_chave_e_trata_recusa(monkeypatch):
    recebidas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        recebidas.append(request)
        if b'"amount":5' in request.content:
            return httpx.Response(400, json={"success": False, "message": "valor divergente"})
        return httpx.Response(201, json={"success": True, "data": {}})

    transporte = httpx.MockTransport(responder)
    original = httpx.AsyncClient

    def cliente_falso(*args, **kwargs):
        return original(*args, transport=transporte, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", cliente_falso)
    cliente = EconomiaPlataformaHttp("https://api.tyto.example/", "chave-secreta")

    await cliente.migrar_saldo_comunidade(id_externo="u1", valor=100, referencia="aldeao:1")
    assert recebidas[0].url == "https://api.tyto.example/api/internal/community-migrations"
    assert recebidas[0].headers["X-Service-Key"] == "chave-secreta"

    with pytest.raises(IntegracaoIndisponivelError, match="valor divergente"):
        await cliente.migrar_saldo_comunidade(id_externo="u1", valor=5, referencia="aldeao:1")
