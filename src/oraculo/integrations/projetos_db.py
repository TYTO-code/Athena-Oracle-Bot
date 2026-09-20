"""Base externa de projetos (PostgreSQL somente leitura) — RN-017.

Banco **separado** do banco do bot de propósito: credencial distinta, escopo
distinto, e nada aqui pode escrever. O Oráculo só lê o que precisa para montar
o contexto de uma pergunta.

**O filtro de projeto não é um detalhe de consulta — é a fronteira de
autorização.** Toda consulta daqui exige a lista de projetos que o autor da
pergunta já provou ter acesso (vinda do Firebase, em `plataforma.py`); lista
vazia devolve vazio sem nem tocar o banco. Não existe caminho de código aqui
que leia projeto sem esse filtro, e é isso que faz com que uma injeção de
prompt não tenha nada para extrair: o dado alheio nunca chega a ser carregado.

**Contrato de schema.** As tabelas abaixo descrevem o que o bot espera
encontrar — não são criadas nem migradas por ele. Se o banco real tiver outros
nomes, exponha uma `VIEW` com estes. Nomes de tabela/coluna são fixos no código
de propósito: identificador de SQL não é parametrizável, então torná-los
configuráveis por variável de ambiente abriria uma via de injeção.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from oraculo.config import Settings, get_settings
from oraculo.domain.errors import IntegracaoIndisponivelError
from oraculo.logging_config import get_logger

log = get_logger(__name__)

LIMITE_DECISOES_POR_PROJETO = 15
"""Decisões mais recentes por projeto. Teto de contexto (e de custo): um
projeto com anos de histórico não pode arrastar tudo para dentro do prompt."""

LIMITE_CARACTERES_TEXTO = 4000
"""Corte por campo de texto livre. Evita que um único registro gigante coma o
contexto inteiro e empurre o resto para fora."""

_metadata = MetaData()

projetos_tabela = Table(
    "projetos",
    _metadata,
    Column("id", String, primary_key=True),
    Column("nome", String),
    Column("descricao", Text),
    Column("status", String),
    Column("atualizado_em", DateTime(timezone=True)),
)

decisoes_tabela = Table(
    "projeto_decisoes",
    _metadata,
    Column("id", BigInteger, primary_key=True),
    Column("projeto_id", String),
    Column("titulo", String),
    Column("conteudo", Text),
    Column("decidido_em", DateTime(timezone=True)),
)


@dataclass(frozen=True, slots=True)
class Decisao:
    titulo: str | None
    conteudo: str
    decidido_em: datetime | None


@dataclass(frozen=True, slots=True)
class ProjetoContexto:
    """Um projeto que o autor da pergunta tem direito de ver, com seu histórico."""

    id: str
    nome: str
    descricao: str | None = None
    status: str | None = None
    atualizado_em: datetime | None = None
    decisoes: list[Decisao] = field(default_factory=list)


class BaseDeProjetos(Protocol):
    """Porta de leitura da base externa — trocável por um dublê em teste."""

    async def contexto(self, projetos_autorizados: list[str]) -> list[ProjetoContexto]: ...

    async def fechar(self) -> None: ...


def _truncar(valor: object) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if len(texto) <= LIMITE_CARACTERES_TEXTO:
        return texto
    return texto[:LIMITE_CARACTERES_TEXTO] + "… (truncado)"


class ProjetosPostgres:
    """Implementação sobre o PostgreSQL externo configurado."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._engine: AsyncEngine | None = None

    def _obter_engine(self) -> AsyncEngine:
        if self._engine is None:
            if not self._cfg.projetos_database_url:
                raise IntegracaoIndisponivelError(
                    "Base de projetos", "ORACULO_PROJETOS_DATABASE_URL não definida."
                )
            url = self._cfg.projetos_database_url
            # SQLite não aceita dimensionamento de pool (usa Static/NullPool) —
            # mesmo tratamento de `db/base.py`, para o banco externo poder ser
            # um arquivo local em desenvolvimento.
            extras: dict[str, object] = (
                {}
                if url.startswith("sqlite")
                else {"pool_size": 5, "max_overflow": 5, "pool_pre_ping": True}
            )
            self._engine = create_async_engine(url, **extras)
        return self._engine

    async def contexto(self, projetos_autorizados: list[str]) -> list[ProjetoContexto]:
        """Projetos autorizados + decisões recentes de cada um.

        Sem autorização não há consulta: a lista vazia retorna antes de abrir
        conexão. É a diferença entre "não encontrei nada" e "não perguntei".
        """
        autorizados = [p for p in dict.fromkeys(projetos_autorizados) if p]
        if not autorizados:
            return []

        engine = self._obter_engine()
        try:
            async with engine.connect() as conexao:
                linhas_projetos = (
                    await conexao.execute(
                        select(
                            projetos_tabela.c.id,
                            projetos_tabela.c.nome,
                            projetos_tabela.c.descricao,
                            projetos_tabela.c.status,
                            projetos_tabela.c.atualizado_em,
                        ).where(projetos_tabela.c.id.in_(autorizados))
                    )
                ).all()

                linhas_decisoes = (
                    await conexao.execute(
                        select(
                            decisoes_tabela.c.projeto_id,
                            decisoes_tabela.c.titulo,
                            decisoes_tabela.c.conteudo,
                            decisoes_tabela.c.decidido_em,
                        )
                        .where(decisoes_tabela.c.projeto_id.in_(autorizados))
                        .order_by(decisoes_tabela.c.decidido_em.desc())
                    )
                ).all()
        except IntegracaoIndisponivelError:
            raise
        except Exception as exc:  # noqa: BLE001 — falha externa vira erro de integração
            log.exception("Falha ao consultar a base de projetos")
            raise IntegracaoIndisponivelError("Base de projetos", str(exc)) from exc

        por_projeto: dict[str, list[Decisao]] = {}
        for linha in linhas_decisoes:
            # Segunda barreira: mesmo que a consulta acima mudasse, só entra
            # decisão de projeto autorizado.
            if linha.projeto_id not in autorizados:
                continue
            decisoes = por_projeto.setdefault(linha.projeto_id, [])
            if len(decisoes) >= LIMITE_DECISOES_POR_PROJETO:
                continue
            conteudo = _truncar(linha.conteudo)
            if conteudo:
                decisoes.append(
                    Decisao(
                        titulo=_truncar(linha.titulo),
                        conteudo=conteudo,
                        decidido_em=linha.decidido_em,
                    )
                )

        return [
            ProjetoContexto(
                id=linha.id,
                nome=str(linha.nome or linha.id),
                descricao=_truncar(linha.descricao),
                status=_truncar(linha.status),
                atualizado_em=linha.atualizado_em,
                decisoes=por_projeto.get(linha.id, []),
            )
            for linha in linhas_projetos
        ]

    async def fechar(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None


def criar_base_de_projetos(settings: Settings | None = None) -> BaseDeProjetos | None:
    """Base configurada, ou `None` quando a integração não está habilitada."""
    cfg = settings or get_settings()
    if not cfg.projetos_habilitado:
        return None
    return ProjetosPostgres(cfg)
