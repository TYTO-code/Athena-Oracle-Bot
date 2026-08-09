"""Modelo de dados do Bot Oráculo (Atena v1.0).

Princípios estruturais:

* **RN-001** — o cargo vive em uma única coluna (`Membro.cargo_slug`); não há
  tabela de associação que permita acúmulo de cargos.
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
from oraculo.domain.hierarchy import CARGO_INICIAL


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


class TipoMovimentacaoXp(StrEnum):
    CONCESSAO = "concessao"
    REMOCAO = "remocao"


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
            "discord_id IS NOT NULL OR whatsapp_e164 IS NOT NULL",
            name="ao_menos_um_canal",
        ),
        Index("ix_membros_ranking", "ativo", "xp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    discord_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    whatsapp_e164: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)

    nome_exibicao: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))

    #: RN-001 — cargo único de hierarquia; slug validado contra o catálogo TYTO.
    cargo_slug: Mapped[str] = mapped_column(
        String(32), default=CARGO_INICIAL.slug, nullable=False, index=True
    )
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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

    def __repr__(self) -> str:  # pragma: no cover - depuração
        return (
            f"<Membro id={self.id} nome={self.nome_exibicao!r} "
            f"cargo={self.cargo_slug} xp={self.xp}>"
        )


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
    #: Positiva em concessões, negativa em remoções — soma = XP atual.
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    saldo_anterior: Mapped[int] = mapped_column(Integer, nullable=False)
    saldo_posterior: Mapped[int] = mapped_column(Integer, nullable=False)

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
    """RN-003 / RF-005 — histórico imutável de mudanças de cargo."""

    __tablename__ = "promocoes"
    __table_args__ = (Index("ix_promocoes_membro_data", "membro_id", "criado_em"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    membro_id: Mapped[int] = mapped_column(
        ForeignKey("membros.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    cargo_anterior: Mapped[str] = mapped_column(String(32), nullable=False)
    cargo_novo: Mapped[str] = mapped_column(String(32), nullable=False)
    xp_no_momento: Mapped[int] = mapped_column(Integer, nullable=False)

    #: True quando decorrente da progressão automática por XP (RN-002).
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
