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
| TD-007 | Hierarquia de cargos não reflete `Institucional/XP.md` | `hierarchy.py` define `Membro/Cavalaria/Lorde/Conselheiro/Administrador` (5 cargos, limiares 0/500/1.500/3.500/manual), derivados de um "Documento Único" externo a este repositório. O vault `Institucional/` define uma hierarquia diferente e vigente: `CARTA_INSTITUCIONAL.md` Art. VIII descreve três eixos independentes — patente por XP (`XP.md` Art. 2º, 17 patamares, Neófito→Omni), cargo institucional eletivo (Conselheiro do Conselho Régio, Tribuno, Rex) e função operacional por concessão (Dux Vecturium, Guarda Pretoriana) — nenhum dos quais existe neste código. O próprio `hierarchy.py` já assume os limiares atuais como placeholder ("premissa a validar com o Clube TYTO"). | Decisão do Clube TYTO, não da engenharia sozinha: unificar as duas hierarquias (ex.: "Membro" deste bot passa a corresponder à filiação ao Clube — `Institucional/COMUNIDADE_E_CLUBE.md` Art. 1º §3º —, com a progressão de patente rodando em paralelo à de cargo operacional) ou mantê-las deliberadamente como eixos independentes, com a relação entre elas documentada explicitamente em vez de implícita | `Institucional/XP.md` Art. 2º, `CARTA_INSTITUCIONAL.md` Art. VIII | Alta | Antes de F2-007/F2-008 ([fase-2.md](../05-roadmap/fase-2.md)) |

### Política (pós-baseline)

4. TD-007 não bloqueia as Sprints 1–4 nem os itens F2-001 a F2-006 — bloqueia especificamente
   F2-007 (camadas Comunidade/Clube) e F2-008 (Crédito de Mérito), que dependem de saber a que,
   na Carta, "Membro" deste bot corresponde.
5. TD-007 fica **aberta** até decisão explícita do Clube TYTO — nenhuma correção de código deve
   assumir uma reconciliação de hierarquia sem essa decisão documentada primeiro.
