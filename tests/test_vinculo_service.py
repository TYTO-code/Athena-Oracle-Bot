"""Vínculo self-service Discord ↔ plataforma — RF-001 (extensão).

Cobre especificamente os riscos de segurança do desenho: nunca revelar se um
identificador existe, nunca aceitar um vínculo sem prova de posse do e-mail,
nunca sobrescrever atividade real, e nunca deixar força bruta no código.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from oraculo.db.base import agora
from oraculo.db.models import Membro, RegistroAuditoria, VinculoPendente
from oraculo.domain.errors import (
    CodigoInvalidoOuExpiradoError,
    ConflitoDeVinculoError,
    VinculoJaSolicitadoError,
)
from oraculo.domain.hierarchy import CAVALARIA, MEMBRO
from oraculo.services.vinculo_service import confirmar_vinculo, solicitar_vinculo


async def _plataforma(session, *, id_externo="u1", email="perseu@tyto.example", xp=700) -> Membro:
    membro = Membro(id_externo=id_externo, nome_exibicao="Perseu", email=email, xp=xp)
    session.add(membro)
    await session.flush()
    return membro


async def _codigo_pendente(session, membro_id: int) -> str:
    """Pede o vínculo e devolve o código gerado, sem passar pelo e-mail de verdade."""
    resultado = await solicitar_vinculo(
        session, discord_id=555, identificador="perseu@tyto.example"
    )
    assert resultado.enviado is True
    assert resultado.codigo is not None
    return resultado.codigo


# --- solicitar_vinculo -------------------------------------------------------


async def test_solicita_por_email(session):
    await _plataforma(session)

    resultado = await solicitar_vinculo(
        session, discord_id=555, identificador="perseu@tyto.example"
    )

    assert resultado.enviado is True
    assert resultado.email_destino == "perseu@tyto.example"
    assert resultado.codigo is not None and len(resultado.codigo) == 6


async def test_solicita_por_id_externo(session):
    await _plataforma(session)

    resultado = await solicitar_vinculo(session, discord_id=555, identificador="u1")

    assert resultado.enviado is True


async def test_identificador_inexistente_nao_revela_nada(session):
    """RN-008-adjacente: enumeração de e-mail/ID não pode ter resposta diferente."""
    resultado = await solicitar_vinculo(session, discord_id=555, identificador="ninguem@nada.com")

    assert resultado.enviado is False
    assert resultado.codigo is None
    assert await session.scalar(select(VinculoPendente)) is None


async def test_ja_vinculado_a_outra_conta_nao_revela_nada(session):
    """Mesma resposta do "não existe" — nunca confirma que o e-mail pertence a alguém."""
    membro = await _plataforma(session)
    membro.discord_id = 999
    await session.flush()

    resultado = await solicitar_vinculo(
        session, discord_id=555, identificador="perseu@tyto.example"
    )

    assert resultado.enviado is False
    assert await session.scalar(select(VinculoPendente)) is None


async def test_ja_vinculado_a_propria_conta_avisa(session):
    """Aqui é seguro revelar: é o próprio dono perguntando pela própria conta."""
    membro = await _plataforma(session)
    membro.discord_id = 555
    await session.flush()

    with pytest.raises(VinculoJaSolicitadoError):
        await solicitar_vinculo(session, discord_id=555, identificador="perseu@tyto.example")


async def test_email_ambiguo_e_tratado_como_nao_encontrado(session):
    session.add(Membro(id_externo="u1", nome_exibicao="A", email="dup@tyto.example"))
    session.add(Membro(id_externo="u2", nome_exibicao="B", email="dup@tyto.example"))
    await session.flush()

    resultado = await solicitar_vinculo(session, discord_id=555, identificador="dup@tyto.example")

    assert resultado.enviado is False


async def test_pedido_duplicado_e_recusado_enquanto_pendente(session):
    membro = await _plataforma(session)
    await solicitar_vinculo(session, discord_id=555, identificador="perseu@tyto.example")

    with pytest.raises(VinculoJaSolicitadoError):
        await solicitar_vinculo(session, discord_id=555, identificador=str(membro.id_externo))


async def test_codigo_enviado_fica_registrado_na_auditoria(session):
    await _plataforma(session)
    await solicitar_vinculo(session, discord_id=555, identificador="perseu@tyto.example")

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "vinculo.codigo_enviado")
    )
    assert registro is not None


# --- confirmar_vinculo -------------------------------------------------------


async def test_confirma_e_liga_discord_id(session):
    membro = await _plataforma(session)
    codigo = await _codigo_pendente(session, membro.id)

    confirmado = await confirmar_vinculo(session, discord_id=555, codigo=codigo)

    assert confirmado.id == membro.id
    assert confirmado.discord_id == 555


async def test_confirmar_sem_solicitacao_pendente_falha(session):
    with pytest.raises(CodigoInvalidoOuExpiradoError):
        await confirmar_vinculo(session, discord_id=555, codigo="123456")


async def test_codigo_errado_incrementa_tentativas(session):
    membro = await _plataforma(session)
    await _codigo_pendente(session, membro.id)

    with pytest.raises(CodigoInvalidoOuExpiradoError, match="restantes: 4"):
        await confirmar_vinculo(session, discord_id=555, codigo="000000")

    pendente = await session.scalar(
        select(VinculoPendente).where(VinculoPendente.membro_id == membro.id)
    )
    assert pendente.tentativas == 1


async def test_apos_cinco_erros_precisa_pedir_novo_codigo(session):
    membro = await _plataforma(session)
    await _codigo_pendente(session, membro.id)

    for _ in range(5):
        with pytest.raises(CodigoInvalidoOuExpiradoError):
            await confirmar_vinculo(session, discord_id=555, codigo="000000")

    assert (
        await session.scalar(select(VinculoPendente).where(VinculoPendente.membro_id == membro.id))
        is None
    )

    # O código antigo (mesmo que fosse o certo) não serve mais.
    with pytest.raises(CodigoInvalidoOuExpiradoError):
        await confirmar_vinculo(session, discord_id=555, codigo="000000")


async def test_codigo_expirado_e_recusado(session):
    membro = await _plataforma(session)
    codigo = await _codigo_pendente(session, membro.id)

    pendente = await session.scalar(
        select(VinculoPendente).where(VinculoPendente.membro_id == membro.id)
    )
    pendente.expira_em = agora() - timedelta(seconds=1)
    await session.flush()

    with pytest.raises(CodigoInvalidoOuExpiradoError):
        await confirmar_vinculo(session, discord_id=555, codigo=codigo)


async def test_confirma_recusa_mesclar_mesmo_registro_zerado(session):
    """Mesmo sem nenhuma atividade, mesclar sozinho exigiria violar a identidade do
    registro (zerar o único canal que ele tem) ou apagá-lo (risco de FK de RSVP) —
    então nem esse caso "inofensivo" mescla automaticamente."""
    membro = await _plataforma(session)
    session.add(
        Membro(discord_id=555, nome_exibicao="Perseu (Discord)", cargo_slug=MEMBRO.slug, xp=0)
    )
    await session.flush()

    codigo = await _codigo_pendente(session, membro.id)

    with pytest.raises(ConflitoDeVinculoError):
        await confirmar_vinculo(session, discord_id=555, codigo=codigo)

    assert (await session.get(Membro, membro.id)).discord_id is None


async def test_confirma_recusa_mesclar_registro_com_atividade_real(session):
    """XP ganho de verdade no bot nunca pode ser apagado por um vínculo automático."""
    membro = await _plataforma(session)
    session.add(
        Membro(discord_id=555, nome_exibicao="Perseu (Discord)", cargo_slug=CAVALARIA.slug, xp=600)
    )
    await session.flush()

    codigo = await _codigo_pendente(session, membro.id)

    with pytest.raises(ConflitoDeVinculoError):
        await confirmar_vinculo(session, discord_id=555, codigo=codigo)

    # Nada mudou nos dois registros.
    intacto = await session.scalar(select(Membro).where(Membro.discord_id == 555))
    assert intacto.xp == 600
    assert (await session.get(Membro, membro.id)).discord_id is None


async def test_confirmado_fica_registrado_na_auditoria(session):
    membro = await _plataforma(session)
    codigo = await _codigo_pendente(session, membro.id)

    await confirmar_vinculo(session, discord_id=555, codigo=codigo)

    registro = await session.scalar(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "vinculo.confirmado")
    )
    assert registro is not None
    assert registro.dados["discord_id"] == 555
