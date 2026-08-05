# Catálogo de Requisitos Funcionais — Atena v1.0

| ID | Nome | Descrição | Prioridade | RN | Casos de uso |
|----|------|-----------|------------|----|--------------|
| RF-001 | Autenticação | Reconhecer usuários do Discord e WhatsApp. | Alta | — | — |
| RF-002 | Consulta de perfil | Exibir cargo, XP atual, próximo cargo, XP necessário e ranking. | Alta | RN-001 | — |
| RF-003 | Gerenciamento de XP | Conselheiros+ podem adicionar/remover XP, consultar histórico e saldo. Motivo obrigatório. | Crítica | RN-004, RN-005 | UC-001 |
| RF-004 | Ranking | Rankings geral, por servidor e por período. | Alta | — | UC-002 |
| RF-005 | Promoções | Atribuição automática de cargos com base no XP. | Crítica | RN-002, RN-003 | UC-003 |
| RF-006 | Sincronização de cargos | Remoção/atribuição de cargos sincronizada com o Discord; cargo único. | Crítica | RN-001, RN-003 | UC-003 |
| RF-007 | Reuniões | Criar, editar, cancelar e convidar participantes (Cavalaria+). | Alta | RN-006, RN-009 | UC-004 |
| RF-008 | Eventos | Criar, editar, cancelar e convidar participantes em eventos oficiais (Lorde+). | Alta | RN-007, RN-009 | UC-005 |
| RF-009 | Presença (RSVP) | Confirmar, recusar ou marcar presença como pendente. | Alta | — | UC-006 |
| RF-010 | Notificações | Avisos de promoção, XP, convites e agendas via Discord e e-mail. | Média | RN-003 | UC-001, UC-003, UC-004, UC-005 |
| RF-011 | Integração Google Agenda | Sincronização automática e lembretes. | Alta | RN-009 | UC-004, UC-005 |
| RF-012 | Sistema de logs | Registro de todas as movimentações críticas e eventos. | Crítica | RN-005, RN-010 | UC-001, UC-003 |

## Comandos Discord previstos (Sprint 2+)

| Comando | RF | Permissão mínima |
|---------|----|------------------|
| `/perfil` | RF-002 | Membro |
| `/ranking` | RF-004 | Membro |
| `/historico-xp` | RF-003, RF-012 | Conselheiro+ (ou conforme política) |
| `/conceder-xp` | RF-003 | Conselheiro+ |
| `/remover-xp` | RF-003 | Conselheiro+ |
| Comandos de reunião | RF-007 | Cavalaria+ |
| Comandos de evento | RF-008 | Lorde+ |
