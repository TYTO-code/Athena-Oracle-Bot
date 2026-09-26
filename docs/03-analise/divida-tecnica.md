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

## Dívida técnica pós-baseline (não é do legado Bot-XP-Discord)

Itens descobertos depois da baseline Atena v1.0, comparando esta implementação com o vault
`Institucional/` do Clube TYTO — diferente da tabela acima (achados da análise do legado, todos já
fechados), este é código atual divergindo da lei institucional vigente. Segue o mesmo regime de
rastreamento por ID.

| ID | Problema | Situação / risco | Correção exigida | Viola | Severidade | Sprint alvo |
|----|----------|------------------|------------------|-------|------------|-------------|
| TD-007 | Hierarquia de cargos não reflete `Institucional/XP.md` | **Fechada (2026-09-26).** Decisão do Clube TYTO: **unificar** com `XP.md`. `hierarchy.py` agora modela os eixos da Carta Art. VIII: patente por XP (17 patamares Neófito→Omni, irrevogável — `XP.md` Art. 1º §3º) e cargos institucionais independentes (`Conselheiro`, `Administrador`) como flags em `Membro`. "Membro" deixou de ser degrau: é a filiação ao Clube (`COMUNIDADE_E_CLUBE.md` Art. 1º §3º). Privilégios aprovados pelo Clube: reunião Veterano+, evento/comunicado Oficial+, XP/auditoria/`@everyone` cargo Conselheiro, sistema Administrador. `/remover-xp` removido (XP irrevogável, `XP.md` Art. 1º §1º). Migração `c3d4e5f6a7b8`. | — | `Institucional/XP.md` Art. 1º–2º, `CARTA_INSTITUCIONAL.md` Art. VIII | Alta | Fechada |

### Política (pós-baseline)

4. TD-007 bloqueava F2-007 (camadas Comunidade/Clube) e F2-008 (Crédito de Mérito), que dependiam
   de saber a que, na Carta, "Membro" deste bot corresponde — com a unificação, `Membro` é a
   filiação ao Clube, e os dois itens estão desbloqueados.
5. Os limiares de patente seguem `XP.md` Art. 2º (patamares 1–8 e 16–17 provisórios até
   ratificação do Dominatium) e os valores exatos de `CLAN_TIERS` da plataforma, para que bot e
   plataforma nunca discordem da patente de um mesmo XP.
