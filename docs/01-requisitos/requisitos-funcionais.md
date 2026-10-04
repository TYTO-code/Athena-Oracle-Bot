# Catálogo de Requisitos Funcionais — Atena v1.0

| ID | Nome | Descrição | Prioridade | RN | Casos de uso |
|----|------|-----------|------------|----|--------------|
| RF-001 | Autenticação | Reconhecer **apenas membros cadastrados na TYTO.club** (conta de Clube ativa com o ID do Discord no perfil); sem auto-registro (RN-020). | Alta | RN-020 | — |
| RF-002 | Consulta de perfil | Exibir cargo, XP atual, próximo cargo, XP necessário e ranking. | Alta | RN-001 | — |
| RF-003 | Gerenciamento de XP | **Revogado (RN-021):** o bot não concede XP; ele é concedido na TYTO.club e espelhado. | — | RN-021 | ~~UC-001~~ |
| RF-004 | Ranking | Rankings geral, por servidor e por período. | Alta | — | UC-002 |
| RF-005 | Promoções | Atribuição automática de cargos com base no XP. | Crítica | RN-002, RN-003 | UC-003 |
| RF-006 | Sincronização de cargos | Remoção/atribuição de cargos sincronizada com o Discord; cargo único. | Crítica | RN-001, RN-003 | UC-003 |
| RF-007 | Reuniões | Criar, editar, cancelar e convidar participantes (Veterano+). | Alta | RN-006, RN-009 | UC-004 |
| RF-008 | Eventos | Criar, editar, cancelar e convidar participantes em eventos oficiais (Oficial+). | Alta | RN-007, RN-009 | UC-005 |
| RF-009 | Presença (RSVP) | Confirmar, recusar ou marcar presença como pendente. | Alta | — | UC-006 |
| RF-010 | Notificações | Avisos de promoção, XP, convites e agendas via Discord e e-mail. | Média | RN-003 | UC-001, UC-003, UC-004, UC-005 |
| RF-011 | Integração Google Agenda | Sincronização automática e lembretes. | Alta | RN-009 | UC-004, UC-005 |
| RF-012 | Sistema de logs | Registro de todas as movimentações críticas e eventos. | Crítica | RN-005, RN-010 | UC-001, UC-003 |
| RF-013 | ~~Consulta de saldo/extrato de Dracmas~~ | **Revogado (RN-021).** | — | — | — |
| RF-014 | ~~Doação de Dracmas~~ | **Revogado (RN-021).** | — | — | — |
| RF-015 | Comunicados oficiais | Publicar um aviso do clube num canal (o `#comunicados`), na hora ou programado para depois; listar e cancelar o que está na fila. | Média | RN-008, RN-010, RN-018 | — |

## Comandos Discord previstos (Sprint 2+)

| Comando | RF | Permissão mínima |
|---------|----|------------------|
| `/perfil` | RF-002 | Membro |
| `/ranking` | RF-004 | Membro |
| Comandos de reunião | RF-007 | Veterano+ |
| Comandos de evento | RF-008 | Oficial+ |
| `/comunicar`, `/agendar-comunicado`, `/comunicados`, `/cancelar-comunicado` | RF-015 | Oficial+ para publicar; cargo Conselheiro para `@here`/`@everyone` (RN-018) |
