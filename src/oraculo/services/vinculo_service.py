"""Vínculo self-service Discord ↔ plataforma — RF-001 (extensão).

A importação (`importacao_service.py`) só liga `Membro.discord_id` quando o
documento do Firestore já traz um `discordId` correto. Quando a plataforma
nunca capturou isso, não existe vínculo nenhum — o bot não tem como
"adivinhar" a quem um registro pertence.

Este serviço resolve isso com prova de posse: quem pede o vínculo precisa
comprovar que controla o e-mail **já cadastrado** na plataforma, nunca um que
informe na hora. Sem essa prova, qualquer pessoa que soubesse o e-mail ou o
ID de outro membro poderia "roubar" o registro dela — XP, cargo e tudo.

Princípios de segurança do fluxo:

* **Nunca revela se um identificador existe.** `solicitar_vinculo` sempre
  devolve o mesmo formato ao usuário (silencioso), exista ou não o registro,
  esteja ou não vinculado a outra conta — só dispara e-mail quando há mesmo
  o que verificar. Um terceiro tentando enumerar e-mails não aprende nada.
* **O código nunca é armazenado em claro** — só o hash, como uma senha.
* **Só liga o `discord_id`.** Cargo e XP não são tocados aqui: ficam por
  conta do job de importação normal (que já aplica o teto de segurança de
  `importacao_service.CARGO_MAXIMO_AUTOMATICO`) — não duplicamos essa
  política de escalada em dois lugares.
* **Nunca mescla registros sozinho.** Se a conta Discord que está vinculando
  já tem *qualquer* registro no bot — mesmo "zerado" (auto-criado no primeiro
  `/perfil`, sem XP nem cargo) — o vínculo automático é recusado: mesclar com
  segurança exigiria zerar a única identidade desse registro ou apagá-lo
  (arriscando referências como RSVP), então fica para um Administrador.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from oraculo.db.base import agora
from oraculo.db.models import Membro, OrigemAcao, VinculoPendente
from oraculo.domain.errors import (
    CodigoInvalidoOuExpiradoError,
    ConflitoDeVinculoError,
    VinculoJaSolicitadoError,
)
from oraculo.repositories import auditoria
from oraculo.repositories import membros as repo_membros

TTL_CODIGO = timedelta(minutes=10)
MAX_TENTATIVAS = 5
TAMANHO_CODIGO = 6


@dataclass(slots=True)
class ResultadoSolicitacao:
    """`email_destino`/`codigo` só vêm preenchidos quando `enviado=True`.

    A resposta mostrada ao usuário deve ser **a mesma frase genérica** nos
    dois casos — só o chamador (o cog) decide, com base em `enviado`, se
    dispara o e-mail; ele nunca deve variar o texto de volta ao Discord.
    """

    enviado: bool
    email_destino: str | None = None
    codigo: str | None = None


def _gerar_codigo() -> str:
    numero = secrets.randbelow(10**TAMANHO_CODIGO)
    return str(numero).zfill(TAMANHO_CODIGO)


def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()


async def _buscar_candidato(session: AsyncSession, identificador: str) -> Membro | None:
    """Localiza por `id_externo` (exato) ou e-mail (case-insensitive).

    Ambiguidade (mais de um membro com o mesmo e-mail, cadastro nunca exigiu
    unicidade) é tratada como "não encontrado" — nunca escolhemos um dos dois
    por adivinhação.
    """
    valor = identificador.strip()
    if not valor:
        return None

    candidatos = (
        await session.scalars(
            select(Membro).where(
                Membro.ativo.is_(True),
                or_(
                    Membro.id_externo == valor,
                    func.lower(Membro.email) == valor.casefold(),
                ),
            )
        )
    ).all()
    if len(candidatos) != 1:
        return None
    return candidatos[0]


async def solicitar_vinculo(
    session: AsyncSession, *, discord_id: int, identificador: str
) -> ResultadoSolicitacao:
    """Prepara (e devolve os dados de) um código de verificação, se aplicável.

    Quem chama deve mostrar sempre a mesma mensagem genérica ao usuário,
    independentemente de `enviado` — só usa o valor pra decidir se dispara
    o e-mail de fato.
    """
    pendente_existente = await session.scalar(
        select(VinculoPendente).where(
            VinculoPendente.discord_id == discord_id,
            VinculoPendente.expira_em > agora(),
        )
    )
    if pendente_existente is not None:
        raise VinculoJaSolicitadoError(
            "Você já pediu um código recentemente — confira seu e-mail ou espere expirar "
            "para pedir de novo."
        )

    candidato = await _buscar_candidato(session, identificador)
    if candidato is None or candidato.discord_id not in (None, discord_id):
        # Identificador inexistente, ambíguo, ou já vinculado a OUTRA conta:
        # mesmo resultado silencioso do caminho sem e-mail real.
        return ResultadoSolicitacao(enviado=False)

    if candidato.discord_id == discord_id:
        # Já vinculado a esta mesma conta — seguro revelar (é o próprio dono perguntando).
        raise VinculoJaSolicitadoError("Sua conta já está vinculada a este cadastro.")

    pendente_do_alvo = await session.scalar(
        select(VinculoPendente).where(
            VinculoPendente.membro_id == candidato.id,
            VinculoPendente.expira_em > agora(),
        )
    )
    if pendente_do_alvo is not None:
        # Alguém já pediu um código pra este registro (o dono de verdade, ou um
        # terceiro que só sabe o e-mail/ID tentando forçar reenvio). Não apagamos
        # nem substituímos o pedido em andamento — senão um terceiro sem o código
        # conseguiria invalidar repetidamente a verificação legítima de outra
        # pessoa. Mesma resposta silenciosa do caminho "não encontrado".
        return ResultadoSolicitacao(enviado=False)

    if not candidato.email:
        return ResultadoSolicitacao(enviado=False)

    codigo = _gerar_codigo()
    # Só sobra aqui um pendente *expirado* (o `select` acima já garantiu que não
    # há nenhum ativo) — limpar antes de inserir, já que `membro_id` é único.
    await session.execute(delete(VinculoPendente).where(VinculoPendente.membro_id == candidato.id))
    session.add(
        VinculoPendente(
            membro_id=candidato.id,
            discord_id=discord_id,
            codigo_hash=_hash_codigo(codigo),
            expira_em=agora() + TTL_CODIGO,
        )
    )
    await session.flush()

    await auditoria.registrar(
        session,
        acao="vinculo.codigo_enviado",
        resumo=f"Código de vínculo enviado para membro id={candidato.id}",
        ator_descricao=f"discord:{discord_id}",
        alvo_tipo="membro",
        alvo_id=candidato.id,
        dados={"discord_id": discord_id},
        origem=OrigemAcao.DISCORD,
    )

    return ResultadoSolicitacao(enviado=True, email_destino=candidato.email, codigo=codigo)


async def confirmar_vinculo(session: AsyncSession, *, discord_id: int, codigo: str) -> Membro:
    """Confirma o código e efetiva o vínculo. Levanta em qualquer falha."""
    pendente = await session.scalar(
        select(VinculoPendente).where(
            VinculoPendente.discord_id == discord_id,
            VinculoPendente.expira_em > agora(),
        )
    )
    if pendente is None:
        raise CodigoInvalidoOuExpiradoError(
            "Nenhuma verificação pendente (ou expirou). Peça um novo código com /vincular-conta."
        )

    if not hmac.compare_digest(_hash_codigo(codigo.strip()), pendente.codigo_hash):
        pendente.tentativas += 1
        if pendente.tentativas >= MAX_TENTATIVAS:
            await session.delete(pendente)
            await session.flush()
            raise CodigoInvalidoOuExpiradoError(
                "Muitas tentativas erradas. Peça um novo código com /vincular-conta."
            )
        await session.flush()
        restantes = MAX_TENTATIVAS - pendente.tentativas
        raise CodigoInvalidoOuExpiradoError(f"Código incorreto. Tentativas restantes: {restantes}.")

    alvo = await session.get(Membro, pendente.membro_id)
    if alvo is None or alvo.discord_id not in (None, discord_id):
        await session.delete(pendente)
        await session.flush()
        raise CodigoInvalidoOuExpiradoError(
            "Este registro não está mais disponível para vínculo. Peça um novo código."
        )

    duplicado = await repo_membros.buscar_por_discord_id(session, discord_id)
    if duplicado is not None and duplicado.id != alvo.id:
        # Mesmo um registro "zerado" (auto-criado no primeiro /perfil) não pode ser
        # mesclado sozinho aqui: ele pode ter RSVP (FK RESTRICT) e, sem `id_externo`
        # nem WhatsApp, zerar seu discord_id violaria a própria regra de identidade
        # do Membro (`ao_menos_um_canal`). Simples e seguro: manual quando colide.
        raise ConflitoDeVinculoError(
            "Sua conta do Discord já está associada a outro registro no bot — o vínculo "
            "automático foi recusado para não arriscar perder dados. Peça a um "
            "Administrador para reconciliar manualmente."
        )

    alvo.discord_id = discord_id
    await session.delete(pendente)
    await session.flush()

    await auditoria.registrar(
        session,
        acao="vinculo.confirmado",
        resumo=f"Membro id={alvo.id} vinculado à conta Discord {discord_id}",
        ator_descricao=f"discord:{discord_id}",
        alvo_tipo="membro",
        alvo_id=alvo.id,
        dados={"discord_id": discord_id},
        origem=OrigemAcao.DISCORD,
    )

    return alvo
