# Catálogo de Requisitos Não Funcionais — Atena v1.0

> **Nota de normalização:** no documento de origem, `RNF-001` aparece duas vezes (escalabilidade e segurança). Aqui os IDs foram desambiguados sem alterar o conteúdo.

| ID (normalizado) | ID origem | Nome | Descrição | Prioridade |
|------------------|-----------|------|-----------|------------|
| RNF-001 | RNF-001 / RNF-002 | Escalabilidade | Priorizar escalabilidade para crescimento contínuo e horários de pico. | Alta |
| RNF-002 | RNF-002 (par) | Capacidade em pico | Suportar picos de uso sem degradação inaceitável dos comandos críticos. | Alta |
| RNF-003 | RNF-001 (Segurança) | Segurança de operações | Validação de permissões em operações críticas; segredos fora do código; HMAC em webhooks. | Crítica |
| RNF-004 | RNF-004 | Auditoria administrativa | Registro de ações administrativas com rastreabilidade. | Crítica |
| RNF-005 | RNF-005 | Backup | Backup automático diário. | Alta |

## Qualidades derivadas da análise do legado

| Qualidade | Exigência | Referência |
|-----------|-----------|------------|
| Confidencialidade | Tokens apenas em `.env` / secrets do ambiente | TD-001 |
| Integridade de dados | Persistência relacional (PostgreSQL/SQLite + SQLAlchemy async); evitar race conditions de JSON | TD-002 |
| Integridade de webhook | Validar `X-Signature` com HMAC-SHA256 | TD-003 |
| Consistência de domínio | Hierarquia real TYTO (não níveis arbitrários) | TD-004 |
| Observabilidade | Health check e canal de logs persistente | Sprint 4 |

## Critérios de aceite sugeridos (RNF)

- **RNF-003:** nenhuma credencial no repositório; webhooks rejeitam payload sem assinatura válida.
- **RNF-004:** toda alteração de XP e promoção gera registro auditável (RN-005, RN-010).
- **RNF-005:** job diário de backup documentado e verificável.
