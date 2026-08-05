# Catálogo de Regras de Negócio — Atena v1.0

| ID | Nome | Descrição | Prioridade | Rastreabilidade |
|----|------|-----------|------------|-----------------|
| RN-001 | Cargo único | Cada membro poderá possuir apenas um cargo de hierarquia ativo. | Crítica | RF-005, RF-006, UC-003, TD-005 |
| RN-002 | Progressão por XP | A progressão ocorre automaticamente conforme o XP acumulado. | Alta | RF-005, UC-003 |
| RN-003 | Promoção automática | Ao promover, o sistema remove o cargo anterior, concede o novo e registra a promoção em log. | Crítica | RF-005, RF-006, RF-012, UC-003, TD-005 |
| RN-004 | Controle de XP | Somente usuários autorizados (Conselheiros+) podem adicionar ou remover XP. | Crítica | RF-003, UC-001 |
| RN-005 | Auditoria de XP | Toda alteração de XP deve registrar: autor, membro, quantidade, motivo e data/hora. | Crítica | RF-003, RF-012, UC-001, TD-006 |
| RN-006 | Criação de reuniões | Somente cargos superiores à Cavalaria podem criar reuniões. | Alta | RF-007, UC-004 |
| RN-007 | Criação de eventos oficiais | Somente Lordes ou superiores podem criar eventos oficiais. | Alta | RF-008, UC-005 |
| RN-008 | Controle de permissões | Todo acesso a comandos deve ser validado conforme o cargo do membro. | Crítica | RF-* privilegiados |
| RN-009 | Integração Google Agenda | Integração obrigatória com Google Agenda para reuniões e eventos. | Alta | RF-011, UC-004, UC-005 |
| RN-010 | Histórico imutável | Nenhuma movimentação crítica poderá ser excluída fisicamente. | Crítica | RF-012 |

## Notas de implementação

- **RN-001 / RN-003:** ao atribuir cargo, remover **todos** os cargos TYTO anteriores antes da nova atribuição (ver TD-005).
- **RN-005:** persistir em tabela de auditoria (ex.: `xp_audit`); o legado não registra autor/motivo (TD-006).
- **RN-010:** preferir soft-delete e append-only em logs/auditoria.
