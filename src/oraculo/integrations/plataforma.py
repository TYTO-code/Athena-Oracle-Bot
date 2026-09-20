"""Leitura dos membros na plataforma do clube (Firebase).

A importação é dividida em duas peças propositalmente:

* **`FonteMembros`** — porta que apenas *produz* documentos crus. Trocar o
  Firestore por Realtime Database, ou por um dump JSON, é escrever outro
  adaptador; nada além deste módulo muda.
* **`normalizar`** — traduz o documento cru para `MembroExterno`, usando um mapa
  campo-a-campo configurável por ambiente. Assim, o nome dos campos na
  plataforma (`discordId`, `nome`, `pontos`…) não vaza para o resto do sistema
  e é ajustável sem alterar código.

Nada aqui escreve no Firebase: a integração é **somente leitura** (RN-010 vale
para os dois lados — não corrompemos a base de origem).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from oraculo.config import Settings, get_settings
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.logging_config import get_logger

log = get_logger(__name__)

MAPA_PADRAO_FIREBASE: dict[str, str] = {
    "id_externo": "id",
    "nome": "nome",
    "discord_id": "discordId",
    "email": "email",
    "cargo": "cargo",
    "xp": "xp",
    "ativo": "ativo",
    "projetos": "projetos",
}
"""Nomes assumidos por padrão. Sobrescreva com `ORACULO_FIREBASE_CAMPOS`, ex.:

    ORACULO_FIREBASE_CAMPOS={"nome":"displayName","discord_id":"discord","xp":"pontos"}
"""


@dataclass(slots=True)
class MembroExterno:
    """Um membro conforme a plataforma, já normalizado e sem campos exóticos."""

    id_externo: str
    nome: str
    discord_id: int | None = None
    email: str | None = None
    cargo: str | None = None
    xp: int | None = None
    ativo: bool = True
    #: RN-017 — IDs dos projetos em que o membro participa. É a **única** fonte
    #: de autorização de `/perguntar` sobre projetos; lista vazia = sem acesso.
    projetos: list[str] = field(default_factory=list)
    #: Resumo do documento original, para diagnóstico. Valores longos (fotos em
    #: base64, por exemplo) são descartados: guardá-los multiplicaria o uso de
    #: memória por todo o tamanho da coleção.
    bruto: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def identificavel_no_discord(self) -> bool:
        return self.discord_id is not None


class FonteMembros(Protocol):
    """Origem de membros — qualquer coisa que saiba listar documentos crus."""

    async def listar(self) -> AsyncIterator[Mapping[str, Any]]: ...


@runtime_checkable
class FonteProjetosDoMembro(Protocol):
    """Autorização de `/perguntar` (RN-017): em que projetos alguém está.

    Deliberadamente **não** reaproveita o ciclo de importação: aquele roda de 6
    em 6 horas, e uma lista de acesso com até 6h de atraso significaria alguém
    removido de um projeto continuar lendo o projeto. Aqui a leitura é pontual,
    no momento da pergunta.
    """

    async def projetos_de(self, id_externo: str) -> list[str]: ...


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------


def _para_int(valor: object) -> int | None:
    """Converte com tolerância: a plataforma pode mandar número como string."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor)
    if isinstance(valor, str):
        limpo = valor.strip()
        if limpo.isdigit() or (limpo.startswith("-") and limpo[1:].isdigit()):
            return int(limpo)
    return None


def _para_bool(valor: object, padrao: bool = True) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().casefold() not in {"false", "0", "nao", "não", "inativo", ""}
    if isinstance(valor, (int, float)):
        return bool(valor)
    return padrao


def _para_lista_de_ids(valor: object) -> list[str]:
    """Normaliza a lista de projetos do documento (RN-017).

    Aceita os formatos plausíveis de uma plataforma que não foi feita pensando
    neste bot: lista de strings, lista de objetos com `id`, mapa `{id: true}`
    (padrão comum no Firestore), ou string separada por vírgula. Qualquer coisa
    fora disso vira lista vazia — em autorização, o silêncio é "não".
    """
    if valor is None or isinstance(valor, bool):
        return []
    if isinstance(valor, str):
        return [parte.strip() for parte in valor.split(",") if parte.strip()]
    if isinstance(valor, Mapping):
        # `{"projeto-a": true, "projeto-b": false}` — só o que está ligado.
        return [str(chave) for chave, ligado in valor.items() if ligado]
    if isinstance(valor, (list, tuple, set)):
        ids: list[str] = []
        for item in valor:
            if isinstance(item, Mapping):
                identificador = item.get("id") or item.get("projetoId")
                if identificador:
                    ids.append(str(identificador))
            elif item is not None and not isinstance(item, bool):
                ids.append(str(item))
        return [i for i in (v.strip() for v in ids) if i]
    return []


def _buscar(documento: Mapping[str, Any], caminho: str) -> Any:
    """Lê `campo` ou `campo.aninhado` dentro do documento."""
    atual: Any = documento
    for parte in caminho.split("."):
        if not isinstance(atual, Mapping) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


LIMITE_VALOR_BRUTO = 300
"""Acima disso o valor é considerado carga inútil (imagem embutida, blob…)."""


def _resumir(documento: Mapping[str, Any]) -> dict[str, Any]:
    """Cópia enxuta do documento, sem campos volumosos."""
    resumo: dict[str, Any] = {}
    for chave, valor in documento.items():
        if isinstance(valor, str) and len(valor) > LIMITE_VALOR_BRUTO:
            resumo[chave] = f"<{len(valor)} caracteres omitidos>"
        elif isinstance(valor, (str, int, float, bool)) or valor is None:
            resumo[chave] = valor
        # Estruturas aninhadas ficam de fora: só interessam para diagnóstico.
    return resumo


def normalizar(
    documento: Mapping[str, Any],
    *,
    mapa: Mapping[str, str] | None = None,
    id_documento: str | None = None,
) -> MembroExterno | None:
    """Converte um documento cru em `MembroExterno`.

    Devolve `None` para documentos sem identidade utilizável — é melhor pular e
    reportar do que gravar um membro fantasma no banco.
    """
    campos = {**MAPA_PADRAO_FIREBASE, **(mapa or {})}

    id_externo = _buscar(documento, campos["id_externo"]) or id_documento
    if id_externo is None:
        return None

    nome = _buscar(documento, campos["nome"])
    discord_id = _para_int(_buscar(documento, campos["discord_id"]))

    return MembroExterno(
        id_externo=str(id_externo),
        nome=str(nome).strip() if nome else f"Membro {id_externo}",
        discord_id=discord_id,
        email=(lambda e: str(e).strip() or None)(_buscar(documento, campos["email"]) or ""),
        cargo=(lambda c: str(c).strip() or None)(_buscar(documento, campos["cargo"]) or ""),
        xp=_para_int(_buscar(documento, campos["xp"])),
        ativo=_para_bool(_buscar(documento, campos["ativo"])),
        projetos=_para_lista_de_ids(_buscar(documento, campos["projetos"])),
        bruto=_resumir(documento),
    )


# ---------------------------------------------------------------------------
# Adaptadores
# ---------------------------------------------------------------------------


class FonteEmMemoria:
    """Fonte a partir de uma lista — usada em testes e em importação de dump."""

    def __init__(
        self, documentos: Iterable[Mapping[str, Any]], *, mapa: Mapping[str, str] | None = None
    ) -> None:
        self._documentos = list(documentos)
        self._mapa = dict(mapa or {})

    async def listar(self) -> AsyncIterator[Mapping[str, Any]]:
        for documento in self._documentos:
            yield documento

    async def projetos_de(self, id_externo: str) -> list[str]:
        for documento in self._documentos:
            externo = normalizar(documento, mapa=self._mapa)
            if externo is not None and externo.id_externo == id_externo:
                return externo.projetos
        return []


class FirestoreMembros:
    """Lê a coleção de membros no Cloud Firestore.

    Usa o cliente assíncrono oficial (`AsyncClient`), então a leitura não bloqueia
    o event loop do bot. A paginação por cursor evita carregar a coleção inteira
    de uma vez em clubes grandes.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._cliente: Any | None = None

    def _conectar(self) -> Any:
        if self._cliente is not None:
            return self._cliente
        if not self._cfg.firebase_project_id:
            raise IntegracaoIndisponivelError(
                "Firebase", "ORACULO_FIREBASE_PROJECT_ID não definido."
            )
        try:
            from google.cloud.firestore import AsyncClient

            credenciais_arquivo = self._cfg.credenciais_firebase()
            if credenciais_arquivo:
                from google.oauth2 import service_account

                credenciais = service_account.Credentials.from_service_account_file(
                    str(credenciais_arquivo)
                )
                self._cliente = AsyncClient(
                    project=self._cfg.firebase_project_id, credentials=credenciais
                )
            else:
                # Application Default Credentials (útil no Cloud Run / GCE).
                self._cliente = AsyncClient(project=self._cfg.firebase_project_id)
        except IntegracaoIndisponivelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IntegracaoIndisponivelError("Firebase", str(exc)) from exc
        return self._cliente

    def _campos_necessarios(self) -> list[str]:
        """Projeção enviada ao Firestore: só os campos que a importação usa.

        Documentos do clube trazem a foto do membro embutida em base64
        (`photoUrl`), o que faz cada um pesar centenas de KB. Sem projeção, uma
        sincronização baixaria dezenas de MB inúteis a cada ciclo.
        """
        mapa = {**MAPA_PADRAO_FIREBASE, **(self._cfg.firebase_campos or {})}
        # `select` aceita caminho aninhado ("discord.id"); o id do documento vem
        # de graça em `documento.id` e não precisa ser projetado.
        return sorted({caminho for chave, caminho in mapa.items() if chave != "id_externo"})

    async def listar(self) -> AsyncIterator[Mapping[str, Any]]:
        cliente = self._conectar()
        colecao = cliente.collection(self._cfg.firebase_colecao)
        tamanho = self._cfg.firebase_pagina_tamanho
        cursor: Any = None
        total = 0

        while True:
            # `order_by("__name__")` dá ordem estável — sem ela o cursor
            # `start_after` não tem significado definido e a paginação pode
            # repetir ou pular documentos.
            consulta = colecao.order_by("__name__").limit(tamanho)
            if self._cfg.firebase_projecao:
                consulta = consulta.select(self._campos_necessarios())
            if cursor is not None:
                consulta = consulta.start_after(cursor)

            try:
                pagina = await asyncio.wait_for(
                    _coletar(consulta), timeout=self._cfg.firebase_timeout
                )
            except TimeoutError as exc:
                raise IntegracaoIndisponivelError(
                    "Firebase", f"tempo esgotado após {self._cfg.firebase_timeout}s"
                ) from exc

            if not pagina:
                break

            for documento in pagina:
                dados = documento.to_dict() or {}
                # O id do documento costuma ser a chave estável do membro.
                dados.setdefault("id", documento.id)
                total += 1
                yield dados

            cursor = pagina[-1]
            if len(pagina) < tamanho:
                break

        log.info("Firestore: %d documentos lidos de '%s'.", total, self._cfg.firebase_colecao)

    async def projetos_de(self, id_externo: str) -> list[str]:
        """RN-017 — projetos do membro, lidos **na hora** da pergunta.

        Uma falha de leitura não devolve lista vazia silenciosamente: propaga
        `IntegracaoIndisponivelError` para o chamador poder dizer "não consegui
        verificar seu acesso" em vez de "você não tem acesso a nada" — os dois
        negam a resposta, mas só um deles é honesto sobre o motivo.
        """
        if not id_externo:
            return []

        cliente = self._conectar()
        colecao = cliente.collection(self._cfg.firebase_colecao)
        mapa = {**MAPA_PADRAO_FIREBASE, **(self._cfg.firebase_campos or {})}

        nome_projetos = mapa["projetos"]
        documento = colecao.document(id_externo)

        try:
            # Formato principal do clube: **subcoleção** `membros/{id}/projetos`,
            # um documento por projeto — o id do documento é o id do projeto.
            subcolecao = await asyncio.wait_for(
                _coletar(documento.collection(nome_projetos)),
                timeout=self._cfg.firebase_timeout,
            )
            if subcolecao:
                return _ids_da_subcolecao(subcolecao)

            # Sem subcoleção: talvez o vínculo esteja como campo no documento
            # (lista, mapa ou string) — custa uma leitura e evita um "sem acesso"
            # falso só por diferença de formato.
            snapshot = await asyncio.wait_for(
                documento.get(), timeout=self._cfg.firebase_timeout
            )
            dados: Mapping[str, Any] | None = snapshot.to_dict() if snapshot.exists else None

            if dados is None:
                # O id do documento pode não ser a chave estável: procura pelo campo.
                consulta = colecao.where(mapa["id_externo"], "==", id_externo).limit(1)
                pagina = await asyncio.wait_for(
                    _coletar(consulta), timeout=self._cfg.firebase_timeout
                )
                if not pagina:
                    return []
                achado = pagina[0]
                dados = achado.to_dict()
                subcolecao = await asyncio.wait_for(
                    _coletar(achado.reference.collection(nome_projetos)),
                    timeout=self._cfg.firebase_timeout,
                )
                if subcolecao:
                    return _ids_da_subcolecao(subcolecao)
        except TimeoutError as exc:
            raise IntegracaoIndisponivelError(
                "Firebase", f"tempo esgotado após {self._cfg.firebase_timeout}s"
            ) from exc
        except IntegracaoIndisponivelError:
            raise
        except Exception as exc:  # noqa: BLE001 — traduzido para erro de integração
            raise IntegracaoIndisponivelError("Firebase", str(exc)) from exc

        if not dados:
            return []
        return _para_lista_de_ids(_buscar(dados, nome_projetos))


async def _coletar(consulta: Any) -> list[Any]:
    """Materializa uma página do Firestore, para poder aplicar timeout nela."""
    return [documento async for documento in consulta.stream()]


def _ids_da_subcolecao(documentos: list[Any]) -> list[str]:
    """IDs dos projetos a partir da subcoleção `membros/{id}/projetos` (RN-017).

    O id do documento é o id do projeto. Um documento com `ativo: false` (ou
    `removido: true`) é tratado como vínculo encerrado — quem sai de um projeto
    costuma ser desativado, não apagado, e ler isso como acesso válido seria
    devolver o projeto a quem já saiu.
    """
    ids: list[str] = []
    for documento in documentos:
        dados = documento.to_dict() or {}
        if dados.get("ativo") is False or dados.get("removido") is True:
            continue
        identificador = str(dados.get("projetoId") or dados.get("id") or documento.id or "").strip()
        if identificador:
            ids.append(identificador)
    return list(dict.fromkeys(ids))


def criar_fonte_membros(settings: Settings | None = None) -> FonteMembros | None:
    """Fonte configurada, ou `None` quando a integração não está habilitada."""
    cfg = settings or get_settings()
    if not cfg.plataforma_habilitada:
        return None
    log.info(
        "Plataforma: Firestore (projeto=%s, coleção=%s).",
        cfg.firebase_project_id,
        cfg.firebase_colecao,
    )
    return FirestoreMembros(cfg)
