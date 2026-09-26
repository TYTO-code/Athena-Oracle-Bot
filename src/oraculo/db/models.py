"""Modelo de dados do Bot Oráculo (Atena v1.0).

Princípios estruturais:

* **RN-001** — a patente vive em uma única coluna (`Membro.patente_slug`); não
  há tabela de associação que permita acúmulo de patentes. Cargos
  institucionais (TD-007) são flags à parte (`conselheiro`, `administrador`),
  acumuláveis com qualquer patente — Carta Art. VIII.
* **RN-005 / RN-010** — `xp_audit`, `promocoes` e `audit_log` são *append-only*:
  não existe caminho de código que atualize ou apague linhas dessas tabelas.
* **RN-010** — desativações usam soft-delete (`Membro.ativo`,
  `Agendamento.status = CANCELADO`), preservando o histórico.
* **Fase 2** — `Membro.dracmas` e `carteira_atualizada_em` já existem no schema
  (US-405) sem qualquer comando exposto.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from oraculo.db.base import Base, agora
from oraculo.domain.hierarchy import PATENTE_INICIAL, Perfil, patente_por_slug


def enum_col(enum_cls: type[Enum], tamanho: int = 16) -> SAEnum:
    """Enum persistido como VARCHAR pelo *valor*.

    `native_enum=False` mantém o schema idêntico em SQLite e PostgreSQL e evita
    migrações de tipo nativo a cada valor novo.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=tamanho,
        values_callable=lambda e: [membro.value for membro in e],
        validate_strings=True,
    )


class TipoAgendamento(StrEnum):
    """Distingue reuniões (RN-006) de eventos oficiais (RN-007)."""

    REUNIAO = "reuniao"
    EVENTO = "evento"


class StatusAgendamento(StrEnum):
    AGENDADO = "agendado"
    CANCELADO = "cancelado"
    CONCLUIDO = "concluido"


class StatusPresenca(StrEnum):
    """UC-006 — confirmar / recusar / pendente."""

    PENDENTE = "pendente"
    CONFIRMADO = "confirmado"
    RECUSADO = "recusado"


class StatusComunicado(StrEnum):
    """Ciclo de vida de um comunicado programado — RN-018.

    `PUBLICANDO` é o estado de reserva: a linha foi tomada por um ciclo do
    publicador e ainda não voltou com resposta do Discord. Existe para que uma
    queda do bot no meio do envio seja *visível* em vez de virar publicação
    repetida no próximo ciclo.
    """

    AGENDADO = "agendado"
    PUBLICANDO = "publicando"
    PUBLICADO = "publicado"
    CANCELADO = "cancelado"
    FALHOU = "falhou"


class TipoMencao(StrEnum):
    """Quem o comunicado tem direito de notificar — RN-018.

    O valor é traduzido em `discord.AllowedMentions` na hora do envio; o texto
    do comunicado nunca decide isso sozinho.
    """

    NENHUMA = "nenhuma"
    AQUI = "aqui"
    TODOS = "todos"


class TipoMovimentacaoXp(StrEnum):
    CONCESSAO = "concessao"
    REMOCAO = "remocao"
    """Só em linhas históricas: XP é irrevogável desde TD-007 (XP.md Art. 1º §1º)."""


class TipoMovimentacaoDracmas(StrEnum):
    """Origens oficiais de movimentação de Dracmas — `Institucional/DRACMAS.md` §2.

    Nem todo valor listado aqui tem um caminho de código que o produz ainda —
    a tabela completa existe para que um novo fluxo (missão, taxa de admissão,
    investimento de Pote Régio...) só precise de uma linha nova aqui e no
    serviço correspondente, nunca de uma migração de schema.
    """

    DOACAO = "doacao"  # DRACMAS.md §2 "Doação livre entre membros"
    PAGAMENTO_MARKETPLACE = "pagamento_marketplace"  # §2 "Pagamento de pedido/oferta"
    # §2 "Taxa mensal de manutenção" — só Clube (COMUNIDADE_E_CLUBE.md Art. 4º §4º)
    TAXA_MENSAL = "taxa_mensal"
    INGRESSO_COMUNIDADE = "ingresso_comunidade"  # COMUNIDADE_E_CLUBE.md Art. 3º §1º — 30.000
    INGRESSO_CLUBE = "ingresso_clube"  # COMUNIDADE_E_CLUBE.md Art. 4º §1º — 70.000
    PREMIO_TORNEIO = "premio_torneio"  # DRACMAS.md §2 "Prêmio de torneio (pódio)"
    BONUS_VENDA_MERCADOR = "bonus_venda_mercador"  # MERCADOR.md Art. 4º §13º–§14º
    OUTRA = "outra"  # fallback para movimentações ainda sem tipo próprio catalogado


class OrigemAcao(StrEnum):
    """De onde partiu a ação — parte da trilha de auditoria (RNF-004)."""

    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    API = "api"
    SISTEMA = "sistema"


class TimestampMixin:
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora, nullable=False
    )


# ---------------------------------------------------------------------------
# Identidade e progressão — RF-001, RF-002, RN-001
# ---------------------------------------------------------------------------


class Membro(TimestampMixin, Base):
    """Membro do Clube TYTO, identificado por Discord e/ou WhatsApp (RF-001)."""

    __tablename__ = "membros"
    __table_args__ = (
        CheckConstraint("xp >= 0", name="xp_nao_negativo"),
        CheckConstraint(
            "discord_id IS NOT NULL OR whatsapp_e164 IS NOT NULL "
            "OR id_externo IS NOT NULL",
            name="ao_menos_um_canal",
        ),
        Index("ix_membros_ranking", "ativo", "xp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    discord_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    whatsapp_e164: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)

    #: Identidade na plataforma externa; chave estável da importação, pois um
    #: membro pode existir lá antes de aparecer no Discord.
    id_externo: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    sincronizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    nome_exibicao: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))

    #: RN-001 — patente única (XP.md Art. 2º); slug validado contra a escala.
    #: Derivada do XP e irrevogável — só sobe (XP.md Art. 1º §3º).
    patente_slug: Mapped[str] = mapped_column(
        String(32), default=PATENTE_INICIAL.slug, nullable=False, index=True
    )
    #: BigInteger: a escala vai até Omni, 300 bilhões de XP (XP.md Art. 2º).
    xp: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    #: Cargos institucionais (TD-007) — nunca vêm do XP; concedidos/revogados
    #: por um Administrador via `/cargo-institucional`, sempre auditados.
    conselheiro: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    administrador: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    #: RN-010 — soft-delete; membros inativos somem das consultas, não do banco.
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    desativado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Preparação Fase 2 (US-405) — sem comandos expostos na Atena v1.0.
    dracmas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    carteira_atualizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    movimentacoes: Mapped[list[MovimentacaoXp]] = relationship(
        back_populates="membro",
        foreign_keys="MovimentacaoXp.membro_id",
        lazy="raise",
    )
    promocoes: Mapped[list[Promocao]] = relationship(back_populates="membro", lazy="raise")

    @property
    def perfil(self) -> Perfil:
        """Posição do membro nos eixos da Carta Art. VIII — base de toda permissão."""
        return Perfil(
            patente=patente_por_slug(self.patente_slug),
            conselheiro=bool(self.conselheiro),
            administrador=bool(self.administrador),
        )

    def __repr__(self) -> str:  # pragma: no cover - depuração
        return (
            f"<Membro id={self.id} nome={self.nome_exibicao!r} "
            f"patente={self.patente_slug} xp={self.xp}>"
        )


class VinculoPendente(Base):
    """Verificação de vínculo Discord ↔ plataforma pendente de confirmação.

    RF-001 (extensão) — a importação sozinha não cria esse vínculo: ele só
    existe se o documento do Firestore já trouxer `discordId` correto. Quando
    não traz, este fluxo deixa o próprio dono provar que controla o e-mail
    cadastrado na plataforma, em vez de qualquer um poder "reivindicar" um
    registro só citando um identificador.

    Tabela efêmera (expira em minutos) — fica separada de `Membro` para não
    misturar estado transitório de verificação com o cadastro estável.
    """

    __tablename__ = "vinculos_pendentes"
    __table_args__ = (
        UniqueConstraint("membro_id", name="uma_solicitacao_por_membro"),
        Index("ix_vinculos_pendentes_discord_id", "discord_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    membro_id: Mapped[int] = mapped_column(
        ForeignKey("membros.id", ondelete="CASCADE"), nullable=False
    )
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Nunca o código em claro — só o hash, como uma senha de uso único.
    codigo_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tentativas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )

    membro: Mapped[Membro] = relationship(lazy="raise")


class MovimentacaoXp(Base):
    """Tabela `xp_audit` — TD-006 / RN-005.

    Append-only: registra autor, membro, quantidade, motivo e data/hora, além
    dos saldos antes/depois, permitindo reconstruir o XP por replay.
    """

    __tablename__ = "xp_audit"
    __table_args__ = (
        CheckConstraint("quantidade <> 0", name="quantidade_nao_nula"),
        CheckConstraint("length(trim(motivo)) > 0", name="motivo_obrigatorio"),
        Index("ix_xp_audit_membro_data", "membro_id", "criado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    membro_id: Mapped[int] = mapped_column(
        ForeignKey("membros.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: Autor da ação. `None` apenas quando a origem é SISTEMA (job automático).
    autor_id: Mapped[int | None] = mapped_column(
        ForeignKey("membros.id", ondelete="RESTRICT"), index=True
    )
    autor_descricao: Mapped[str] = mapped_column(String(120), default="sistema", nullable=False)

    tipo: Mapped[TipoMovimentacaoXp] = mapped_column(enum_col(TipoMovimentacaoXp), nullable=False)
    #: Positiva em concessões. Negativa só em linhas históricas de remoção,
    #: anteriores a TD-007 — XP é irrevogável (XP.md Art. 1º §1º). Soma = XP atual.
    quantidade: Mapped[int] = mapped_column(BigInteger, nullable=False)
    saldo_anterior: Mapped[int] = mapped_column(BigInteger, nullable=False)
    saldo_posterior: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: RN-005 — obrigatório; validado no serviço e por CheckConstraint.
    motivo: Mapped[str] = mapped_column(String(500), nullable=False)
    origem: Mapped[OrigemAcao] = mapped_column(enum_col(OrigemAcao), default=OrigemAcao.DISCORD)
    guild_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False, index=True
    )

    membro: Mapped[Membro] = relationship(
        back_populates="movimentacoes", foreign_keys=[membro_id], lazy="raise"
    )


class Promocao(Base):
    """RN-003 / RF-005 — histórico imutável de mudanças de patente.

    As colunas mantêm o nome `cargo_*` por compatibilidade com o histórico
    anterior a TD-007 (que guardava slugs de Membro/Cavalaria/…); linhas novas
    guardam slugs de patente.
    """

    __tablename__ = "promocoes"
    __table_args__ = (Index("ix_promocoes_membro_data", "membro_id", "criado_em"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    membro_id: Mapped[int] = mapped_column(
        ForeignKey("membros.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    cargo_anterior: Mapped[str] = mapped_column(String(32), nullable=False)
    cargo_novo: Mapped[str] = mapped_column(String(32), nullable=False)
    xp_no_momento: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: True quando decorrente da progressão automática por XP (RN-002); False
    #: quando um Administrador confirmou uma patente retida pela importação.
    automatica: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    autor_descricao: Mapped[str] = mapped_column(String(120), default="sistema", nullable=False)
    motivo: Mapped[str] = mapped_column(String(500), default="Progressão automática por XP")

    #: Resultado da sincronização de cargos no Discord (RF-006 / TD-005).
    sincronizado_discord: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    erro_sincronizacao: Mapped[str | None] = mapped_column(Text)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False, index=True
    )

    membro: Mapped[Membro] = relationship(back_populates="promocoes", lazy="raise")


# ---------------------------------------------------------------------------
# Comunidade e Dracmas — RN-011 a RN-015, RF-013/RF-014
#
# Implementa `Institucional/COMUNIDADE_E_CLUBE.md` e `Institucional/DRACMAS.md` — eixo
# inteiramente separado da hierarquia de patentes (Art. VIII da Carta trata os dois como eixos
# independentes). `Aldeao` é a camada Comunidade (registro só pelo Atena, sem conta na
# plataforma — COMUNIDADE_E_CLUBE.md Art. 1º §2º); `Membro` acima já é a camada Clube.
# ---------------------------------------------------------------------------


class Aldeao(TimestampMixin, Base):
    """Titular da camada Comunidade — `COMUNIDADE_E_CLUBE.md` Art. 2º.

    Criado automaticamente no primeiro crédito de Dracmas recebido por um `discord_id` sem
    registro (Art. 3º §3º: "não há Dracmas sem conta que os receba") — nunca por um comando de
    "cadastro" isolado, porque não existe Dracmas para um Visitante guardar antes desse momento
    (Art. 1º §1º). Ver `services/dracmas_service.py` para a decisão de implementação sobre como
    isso se concilia com o custo de ingresso do Art. 3º §1º.
    """

    __tablename__ = "aldeoes"
    __table_args__ = (Index("ix_aldeoes_suspenso", "suspenso"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)

    saldo_dracmas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: DRACMAS.md §4 — suspensão automática por saldo negativo; reversão é sempre manual, nunca
    #: um novo crédito reativa a conta sozinho.
    suspenso: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suspenso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reativado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: COMUNIDADE_E_CLUBE.md Art. 4º §1º-A — ao migrar pro Clube, o saldo inteiro é transferido
    #: pra conta de `Membro`; esta linha permanece (nunca é apagada) só como referência histórica
    #: do que já foi Aldeão, com o saldo zerado no momento da migração.
    migrado_para_membro_id: Mapped[int | None] = mapped_column(ForeignKey("membros.id"))
    migrado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    movimentacoes: Mapped[list[MovimentacaoDracmas]] = relationship(
        back_populates="aldeao", foreign_keys="MovimentacaoDracmas.aldeao_id", lazy="raise"
    )

    @property
    def migrado(self) -> bool:
        return self.migrado_para_membro_id is not None

    def __repr__(self) -> str:  # pragma: no cover - depuração
        return f"<Aldeao id={self.id} discord_id={self.discord_id} saldo={self.saldo_dracmas}>"


class MovimentacaoDracmas(Base):
    """Ledger append-only de Dracmas — `DRACMAS.md` §3 (registro obrigatório de toda movimentação).

    Titular é sempre exatamente um `Aldeao` OU um `Membro`, nunca os dois nem nenhum — daí o
    `CheckConstraint` abaixo. Diferente de `RegistroAuditoria` (que usa `alvo_tipo`/`alvo_id` como
    texto livre), aqui a referência é uma FK de verdade em cada coluna: é dinheiro (ainda que
    virtual), então integridade referencial pesa mais que a economia de uma tabela polimórfica
    genérica.
    """

    __tablename__ = "dracmas_ledger"
    __table_args__ = (
        CheckConstraint(
            "(aldeao_id IS NOT NULL AND membro_id IS NULL) "
            "OR (aldeao_id IS NULL AND membro_id IS NOT NULL)",
            name="titular_unico",
        ),
        CheckConstraint("valor <> 0", name="valor_nao_nulo"),
        CheckConstraint("length(trim(motivo)) > 0", name="motivo_obrigatorio"),
        Index("ix_dracmas_ledger_aldeao_data", "aldeao_id", "criado_em"),
        Index("ix_dracmas_ledger_membro_data", "membro_id", "criado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    aldeao_id: Mapped[int | None] = mapped_column(
        ForeignKey("aldeoes.id", ondelete="RESTRICT"), index=True
    )
    membro_id: Mapped[int | None] = mapped_column(
        ForeignKey("membros.id", ondelete="RESTRICT"), index=True
    )

    tipo: Mapped[TipoMovimentacaoDracmas] = mapped_column(
        enum_col(TipoMovimentacaoDracmas, tamanho=24), nullable=False
    )
    #: Positivo em crédito, negativo em débito — soma = saldo atual (mesmo princípio de `xp_audit`).
    valor: Mapped[int] = mapped_column(Integer, nullable=False)
    saldo_anterior: Mapped[int] = mapped_column(Integer, nullable=False)
    saldo_posterior: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Referência externa opcional — ex.: "torneio:123", "mercador:contrato:456" — para rastrear
    #: até o evento de origem em outro serviço/agente sem acoplar uma FK a um sistema externo.
    origem_referencia: Mapped[str | None] = mapped_column(String(120), index=True)

    motivo: Mapped[str] = mapped_column(String(500), nullable=False)
    autor_descricao: Mapped[str] = mapped_column(String(120), default="sistema", nullable=False)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False, index=True
    )

    aldeao: Mapped[Aldeao | None] = relationship(
        back_populates="movimentacoes", foreign_keys=[aldeao_id], lazy="raise"
    )
    membro: Mapped[Membro | None] = relationship(foreign_keys=[membro_id], lazy="raise")


# ---------------------------------------------------------------------------
# Agenda — RF-007, RF-008, RF-009, RF-011
# ---------------------------------------------------------------------------


class Agendamento(TimestampMixin, Base):
    """Reunião (RN-006) ou evento oficial (RN-007).

    Reuniões e eventos compartilham ciclo de vida, RSVP e sincronização com o
    Google Agenda; o que muda é apenas a permissão de criação. Uma tabela única
    com `tipo` evita duplicar toda a lógica de agenda.
    """

    __tablename__ = "agendamentos"
    __table_args__ = (
        CheckConstraint("fim_em IS NULL OR fim_em > inicio_em", name="intervalo_valido"),
        Index("ix_agendamentos_agenda", "tipo", "status", "inicio_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoAgendamento] = mapped_column(enum_col(TipoAgendamento), nullable=False)
    status: Mapped[StatusAgendamento] = mapped_column(
        enum_col(StatusAgendamento), default=StatusAgendamento.AGENDADO, nullable=False
    )

    titulo: Mapped[str] = mapped_column(String(160), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    local: Mapped[str | None] = mapped_column(String(200))

    inicio_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    fim_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organizador_id: Mapped[int] = mapped_column(
        ForeignKey("membros.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    guild_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    canal_anuncio_id: Mapped[int | None] = mapped_column(BigInteger)
    mensagem_anuncio_id: Mapped[int | None] = mapped_column(BigInteger)

    #: RN-009 / RF-011 — id do evento espelhado no Google Agenda.
    google_event_id: Mapped[str | None] = mapped_column(String(200), index=True)
    google_sincronizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: RN-010 — cancelamento é lógico; a linha permanece para auditoria.
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_por_id: Mapped[int | None] = mapped_column(ForeignKey("membros.id"))
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(500))

    organizador: Mapped[Membro] = relationship(foreign_keys=[organizador_id], lazy="raise")
    presencas: Mapped[list[Presenca]] = relationship(
        back_populates="agendamento", lazy="raise", cascade="save-update, merge"
    )

    @property
    def ativo(self) -> bool:
        return self.status == StatusAgendamento.AGENDADO


class Presenca(TimestampMixin, Base):
    """RSVP de um convidado — RF-009 / UC-006."""

    __tablename__ = "presencas"
    __table_args__ = (
        UniqueConstraint("agendamento_id", "membro_id", name="convite_unico"),
        Index("ix_presencas_status", "agendamento_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    agendamento_id: Mapped[int] = mapped_column(
        ForeignKey("agendamentos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membro_id: Mapped[int] = mapped_column(
        ForeignKey("membros.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    status: Mapped[StatusPresenca] = mapped_column(
        enum_col(StatusPresenca), default=StatusPresenca.PENDENTE, nullable=False
    )
    respondido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observacao: Mapped[str | None] = mapped_column(String(300))

    agendamento: Mapped[Agendamento] = relationship(back_populates="presencas", lazy="raise")
    membro: Mapped[Membro] = relationship(lazy="raise")


# ---------------------------------------------------------------------------
# Comunicados — RF-015 / RN-018
# ---------------------------------------------------------------------------


class Comunicado(TimestampMixin, Base):
    """Aviso oficial publicado pelo bot num canal do servidor — RN-018.

    Separado de `Agendamento` de propósito: um comunicado não tem RSVP, não tem
    duração, não vai para o Google Agenda e não tem organizador — tem um autor,
    um canal e uma hora de publicação. Juntar os dois numa tabela só obrigaria
    metade das colunas a ficar nula em cada uso.

    O par `status`/`reservado_em` é o que torna a publicação segura contra
    reinício: o ciclo do publicador *reserva* a linha (AGENDADO → PUBLICANDO) e
    só então fala com o Discord. Se o processo morrer no meio, a linha fica
    marcada como PUBLICANDO e é encerrada como FALHOU — nunca republicada
    automaticamente, porque um `@everyone` duplicado é pior que um atrasado.
    """

    __tablename__ = "comunicados"
    __table_args__ = (
        CheckConstraint("length(trim(titulo)) > 0", name="titulo_obrigatorio"),
        CheckConstraint("length(trim(corpo)) > 0", name="corpo_obrigatorio"),
        Index("ix_comunicados_fila", "status", "publicar_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    titulo: Mapped[str] = mapped_column(String(160), nullable=False)
    corpo: Mapped[str] = mapped_column(Text, nullable=False)

    #: Canal de destino, resolvido e congelado na criação: mudar a variável de
    #: ambiente depois não deve mover um comunicado já programado.
    canal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    guild_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    mencao: Mapped[TipoMencao] = mapped_column(
        enum_col(TipoMencao), default=TipoMencao.NENHUMA, nullable=False
    )

    publicar_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[StatusComunicado] = mapped_column(
        enum_col(StatusComunicado), default=StatusComunicado.AGENDADO, nullable=False
    )

    autor_id: Mapped[int] = mapped_column(
        ForeignKey("membros.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    #: Momento em que o ciclo tomou a linha para publicar (ver docstring).
    reservado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tentativas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    erro: Mapped[str | None] = mapped_column(Text)

    publicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mensagem_id: Mapped[int | None] = mapped_column(BigInteger)

    #: RN-010 — cancelar é lógico; a linha permanece para auditoria.
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_por_id: Mapped[int | None] = mapped_column(ForeignKey("membros.id"))
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(500))

    autor: Mapped[Membro] = relationship(foreign_keys=[autor_id], lazy="raise")

    @property
    def pendente(self) -> bool:
        return self.status == StatusComunicado.AGENDADO

    def __repr__(self) -> str:  # pragma: no cover - depuração
        return (
            f"<Comunicado id={self.id} titulo={self.titulo!r} "
            f"status={self.status} publicar_em={self.publicar_em}>"
        )


# ---------------------------------------------------------------------------
# Governança — RF-012, RNF-004, RN-010
# ---------------------------------------------------------------------------


class RegistroAuditoria(Base):
    """RF-012 — log append-only de toda movimentação crítica.

    Complementa (não substitui) `xp_audit` e `promocoes`: aqui entram também
    criação/cancelamento de agendamentos, RSVP, webhooks e ações de admin.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_acao_data", "acao", "criado_em"),
        Index("ix_audit_log_alvo", "alvo_tipo", "alvo_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    acao: Mapped[str] = mapped_column(String(64), nullable=False)
    origem: Mapped[OrigemAcao] = mapped_column(enum_col(OrigemAcao), default=OrigemAcao.SISTEMA)

    ator_id: Mapped[int | None] = mapped_column(ForeignKey("membros.id"), index=True)
    ator_descricao: Mapped[str] = mapped_column(String(120), default="sistema", nullable=False)

    alvo_tipo: Mapped[str | None] = mapped_column(String(40))
    alvo_id: Mapped[str | None] = mapped_column(String(64))

    resumo: Mapped[str] = mapped_column(String(500), nullable=False)
    #: Detalhes estruturados; nunca deve conter segredos (RNF-003).
    dados: Mapped[dict | None] = mapped_column(JSON)

    guild_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False, index=True
    )


class EventoWebhook(Base):
    """Recebimentos de webhook externo (ClickUp) — TD-003 / RNF-003.

    Persistir o `event_id` permite rejeitar reenvios (replay) além da própria
    validação HMAC.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("origem", "evento_id", name="evento_unico"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    origem: Mapped[str] = mapped_column(String(40), nullable=False)
    evento_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tipo_evento: Mapped[str | None] = mapped_column(String(80))
    payload: Mapped[dict | None] = mapped_column(JSON)
    processado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False, index=True
    )
