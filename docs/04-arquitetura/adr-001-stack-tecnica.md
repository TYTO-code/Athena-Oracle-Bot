# ADR-001 — Stack técnica do Bot Oráculo

| Campo | Valor |
|-------|-------|
| Status | Aceito (recomendação do documento de origem) |
| Data | 2026-08-04 |
| Contexto | Atena v1.0 — Bot Oráculo / Clube TYTO |

## Contexto

O sistema precisa de bot Discord com cogs, API/webhooks seguros, persistência relacional assíncrona, cache para rankings, integração Google Agenda e deploy containerizado, corrigindo a dívida técnica do legado (JSON, tokens hardcoded, webhook sem HMAC).

## Decisão

Adotar a stack abaixo como baseline de implementação.

| Camada | Tecnologia | Justificativa |
|--------|------------|---------------|
| Bot Discord | `discord.py` + cogs | Modularidade de comandos e eventos |
| Banco de dados | PostgreSQL + SQLAlchemy async | Persistência relacional; elimina race conditions de JSON (TD-002) |
| Cache | Redis | Rankings e dados frequentes (Sprint 4 / RNF-001) |
| API / Webhook | FastAPI | Endpoints de webhook (ClickUp) e health check |
| Google Agenda | `google-api-python-client` + OAuth2 | RN-009 / RF-011 |
| Infraestrutura | Docker + Render / Railway | Deploy reprodutível |
| Segredos | `python-dotenv` + secrets do ambiente | TD-001 / RNF-003 |

## Alternativas consideradas

| Alternativa | Motivo da rejeição (neste baseline) |
|-------------|-------------------------------------|
| Persistência só em JSON | Race conditions e baixa auditorabilidade (TD-002) |
| SQLite em produção multi-instância | Aceitável apenas em MVP single-node; PostgreSQL preferido para escala |
| Framework Discord alternativo | Documento recomenda `discord.py`; mudança exigiria novo ADR |

## Consequências

- **Positivas:** alinhamento com RN/RNF; caminho claro para auditoria, HMAC e cache.
- **Negativas:** maior complexidade operacional (Postgres, Redis, OAuth2) vs. legado JSON.
- **Follow-ups:** ADR futuros para modelo de dados, estratégia WhatsApp e soft-delete (RN-010).
