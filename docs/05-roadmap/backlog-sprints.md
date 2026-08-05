# Product Backlog / Roadmap — Sprints (60 dias)

Ciclo: **4 sprints × 15 dias**. Itens derivados do documento de origem, com IDs de user story (`US-xxx`) e rastreabilidade.

## Visão do roadmap

| Sprint | Dias | Foco | Pré-requisito |
|--------|------|------|---------------|
| 1 | 1–15 | Fundação: segurança e persistência | — |
| 2 | 16–30 | Core: comandos e auditoria de XP | Sprint 1 concluída |
| 3 | 31–45 | Eventos, reuniões, notificações | Sprint 2 |
| 4 | 46–60 | Logs, escala, base Fase 2 | Sprint 3 |

---

## Sprint 1 — Fundação sólida (dias 1–15)

**Objetivo:** Segurança e persistência de dados. Zerar TD-001 a TD-005.

| ID | Item | Tipo | Refs |
|----|------|------|------|
| US-101 | Remover tokens hardcoded e configurar `.env` | Débito / segurança | TD-001, RNF-003 |
| US-102 | Validar HMAC no webhook ClickUp (`X-Signature` / HMAC-SHA256) | Débito / segurança | TD-003, RNF-003 |
| US-103 | Corrigir remoção de cargos anteriores na progressão | Débito / domínio | TD-005, RN-001, RN-003 |
| US-104 | Migrar dados JSON → banco relacional (SQLAlchemy async) | Débito / infra | TD-002, ADR-001 |
| US-105 | Reescrever hierarquia de cargos (Membro → Admin) | Débito / domínio | TD-004 |

**Critério de saída:** TD-001–TD-005 fechados; app sobe sem segredos no código; persistência relacional em uso.

---

## Sprint 2 — Core funcional (dias 16–30)

**Objetivo:** Comandos diários e auditoria de XP.

| ID | Item | Tipo | Refs |
|----|------|------|------|
| US-201 | Comando `/perfil` (XP, cargos, ranking) | Feature | RF-002 |
| US-202 | Comando `/ranking` com filtros (geral/período) | Feature | RF-004, UC-002 |
| US-203 | Auditoria completa de XP + `/historico-xp` | Feature / débito | TD-006, RN-005, RF-003, RF-012 |
| US-204 | Decorators de permissão por cargo TYTO | Feature | RN-008 |
| US-205 | `/conceder-xp` e `/remover-xp` com motivo obrigatório | Feature | RF-003, UC-001, RN-004 |

**Critério de saída:** TD-006 fechado; fluxo UC-001 e UC-002 operacionais no Discord.

---

## Sprint 3 — Eventos, reuniões e notificações (dias 31–45)

**Objetivo:** Agendas, RSVP e integrações.

| ID | Item | Tipo | Refs |
|----|------|------|------|
| US-301 | RSVP com botões interativos no Discord | Feature | RF-009, UC-006 |
| US-302 | Notificações em embeds no Discord | Feature | RF-010 |
| US-303 | Gestão de reuniões (Cavalaria+) | Feature | RF-007, UC-004, RN-006 |
| US-304 | Gestão de eventos (Lorde+) | Feature | RF-008, UC-005, RN-007 |
| US-305 | Integração bidirecional Google Agenda via OAuth2 | Feature | RF-011, RN-009 |

**Critério de saída:** UC-004, UC-005 e UC-006 cobertos; sync Agenda ativo.

---

## Sprint 4 — Logs, escalabilidade e base da Fase 2 (dias 46–60)

**Objetivo:** Infraestrutura e preparação.

| ID | Item | Tipo | Refs |
|----|------|------|------|
| US-401 | Canal `#logs-oráculo` persistente | Feature | RF-012, RNF-004 |
| US-402 | Rotina de backup automático diário | Infra | RNF-005 |
| US-403 | Endpoint de health check e monitoramento | Infra | RNF-001, ADR-001 |
| US-404 | Cache Redis para rankings e dados frequentes | Infra | RNF-001, ADR-001 |
| US-405 | Estrutura base no banco para Sistema de Dracmas | Prep. Fase 2 | [fase-2.md](fase-2.md) |

**Critério de saída:** Atena v1.0 operacional com observabilidade e backup; schema base para Dracmas sem expor loja ainda.
