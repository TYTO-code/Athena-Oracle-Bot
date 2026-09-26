# Casos de Uso — Atena v1.0

Formato textual estruturado (UML Use Case).

---

## UC-001 — Conceder XP

| Campo | Valor |
|-------|-------|
| Ator primário | Conselheiro (cargo institucional) |
| Pré-condições | Ator autenticado; permissão RN-004 |
| Pós-condições | XP atualizado; auditoria gravada (RN-005); ranking atualizado; promoção avaliada (UC-003) |
| RF | RF-003, RF-012, RF-004 |
| RN | RN-004, RN-005 |

### Fluxo principal

1. Conselheiro solicita adição de XP (membro, quantidade, motivo).
2. Sistema valida permissão e dados.
3. Sistema adiciona XP e justifica no registro de auditoria.
4. Sistema atualiza ranking.
5. Sistema dispara verificação de promoção (UC-003).

### Fluxos alternativos

- **A1 — Sem permissão:** operação rejeitada; nenhum XP alterado.
- **A2 — Motivo ausente:** operação rejeitada (motivo obrigatório).

---

## UC-002 — Consultar Ranking

| Campo | Valor |
|-------|-------|
| Ator primário | Membro |
| Pré-condições | Ator autenticado |
| Pós-condições | Ranking exibido conforme filtros |
| RF | RF-004 |
| RN | — |

### Fluxo principal

1. Membro solicita ranking (geral / servidor / período).
2. Bot calcula o ranking.
3. Ranking é exibido ao membro.

---

## UC-003 — Promoção Automática

| Campo | Valor |
|-------|-------|
| Ator primário | Sistema (Bot) |
| Ator secundário | Membro promovido |
| Pré-condições | XP do membro atingiu limiar do próximo cargo |
| Pós-condições | Cargo único atualizado (RN-001); log de promoção; notificação |
| RF | RF-005, RF-006, RF-010, RF-012 |
| RN | RN-001, RN-002, RN-003 |

### Fluxo principal

1. Bot verifica requisitos após atualização de XP.
2. Remove todos os cargos TYTO anteriores.
3. Atribui o novo cargo (sincroniza Discord).
4. Registra promoção em log.
5. Notifica o membro / canais configurados.

---

## UC-004 — Criar Reunião

| Campo | Valor |
|-------|-------|
| Ator primário | Patente Veterano+ |
| Pré-condições | Permissão RN-006; integração Google Agenda disponível (RN-009) |
| Pós-condições | Reunião registrada; evento no Google Agenda; convites/notificações enviados |
| RF | RF-007, RF-010, RF-011 |
| RN | RN-006, RN-008, RN-009 |

### Fluxo principal

1. Membro Veterano+ cria reunião e define informações.
2. Bot valida permissão e dados.
3. Bot registra a reunião e sincroniza no Google Agenda.
4. Convites e notificações são enviados.
5. Participantes podem responder via UC-006.

---

## UC-005 — Criar Evento Oficial

| Campo | Valor |
|-------|-------|
| Ator primário | Patente Oficial+ |
| Pré-condições | Permissão RN-007; integração Google Agenda disponível |
| Pós-condições | Evento registrado; sync Agenda; convites/notificações |
| RF | RF-008, RF-010, RF-011 |
| RN | RN-007, RN-008, RN-009 |

### Fluxo principal

1. Membro Oficial+ cria evento oficial e define informações.
2. Bot valida permissão e dados.
3. Bot registra, sincroniza no Google Agenda e notifica.

---

## UC-006 — Confirmar Presença (RSVP)

| Campo | Valor |
|-------|-------|
| Ator primário | Membro convidado |
| Ator secundário | Organizador |
| Pré-condições | Convite existente (reunião ou evento) |
| Pós-condições | Status de presença atualizado; organizador informado |
| RF | RF-009, RF-010 |
| RN | — |

### Fluxo principal

1. Membro recebe convite.
2. Seleciona status: confirmar, recusar ou pendente.
3. Sistema atualiza o organizador / registro do evento.

### Notas de UI (Discord)

RSVP via botões interativos (Sprint 3).
