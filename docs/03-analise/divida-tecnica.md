# Registro de Dívida Técnica — Bot-XP-Discord (legado)

Problemas críticos identificados na análise do repositório **Bot-XP-Discord**. Devem ser corrigidos **antes** de novas funcionalidades (Sprint 1).

| ID | Problema | Situação / risco | Correção exigida | Viola | Severidade | Sprint alvo |
|----|----------|------------------|------------------|-------|------------|-------------|
| TD-001 | Credenciais hardcoded | `DISCORD_BOT_TOKEN` e `CLICKUP_API_TOKEN` expostos em `main.py` | Usar `python-dotenv` e variáveis de ambiente em `.env` (não versionar segredos) | RNF-003 | Crítica | Sprint 1 |
| TD-002 | Armazenamento em JSON | `xp_data.json` e `teams_data.json` com risco de race conditions | Migrar para PostgreSQL ou SQLite com SQLAlchemy async | RNF-001, integridade | Crítica | Sprint 1 |
| TD-003 | Webhook vulnerável | Endpoint ClickUp não valida assinatura HMAC; permite injeção de dados falsos | Validar header `X-Signature` com HMAC-SHA256 | RNF-003 | Crítica | Sprint 1 |
| TD-004 | Hierarquia incorreta | Níveis arbitrários ("Novice", etc.) em vez da estrutura real TYTO | Reescrever `catalog.py` com hierarquia correta (Membro → Admin) | RN-001, domínio | Alta | Sprint 1 |
| TD-005 | Acúmulo de cargos | Função de cargo não remove cargos anteriores | Remover todos os cargos TYTO antes de atribuir o novo | RN-001, RN-003 | Crítica | Sprint 1 |
| TD-006 | Auditoria incompleta | Ação de XP não registra autor ou motivo | Criar tabela `xp_audit` (autor, membro, quantidade, motivo, data/hora) | RN-005, RN-010 | Crítica | Sprint 1–2 |

## Política

1. Nenhum item de Sprint 2+ entra em desenvolvimento com TD-001 a TD-005 abertos.
2. TD-006 deve estar completo no máximo ao fim da Sprint 2 (comandos de XP).
3. Cada correção deve referenciar o ID `TD-xxx` no commit/PR.
