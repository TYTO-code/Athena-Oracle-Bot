# Rastreabilidade — requisito → código

Fecha a cadeia `Visão → RN/RF/RNF → Casos de Uso → Dívida Técnica → ADR → Backlog` com a camada de implementação (Atena v1.0).

## Regras de negócio

| RN | Onde é aplicada | Teste |
|----|-----------------|-------|
| RN-001 Patente única | Coluna única `Membro.patente_slug` ([models.py](../../src/oraculo/db/models.py)); remoção de todos os papéis de patente em [role_sync.py](../../src/oraculo/bot/role_sync.py); cargos institucionais como flags `conselheiro`/`administrador` | `test_role_sync.py`, `test_promocao.py`, `test_cargo_institucional.py` |
| RN-002 Progressão por XP | `patente_para_xp` ([hierarchy.py](../../src/oraculo/domain/hierarchy.py)); `PromocaoService` só sobe patente | `test_hierarquia.py`, `test_promocao.py` |
| RN-003 Promoção automática | `PromocaoService.aplicar` ([promocao_service.py](../../src/oraculo/services/promocao_service.py)) | `test_promocao.py` |
| RN-004 Controle de XP | `exigir(autor.perfil, Acao.CONCEDER_XP)` em [xp_service.py](../../src/oraculo/services/xp_service.py); não existe `remover` | `test_xp_service.py` |
| RN-005 Auditoria de XP | Tabela `xp_audit` + validação de motivo em `XpService._movimentar` | `test_xp_service.py` |
| RN-006 Criação de reuniões | `_POLITICA[Acao.CRIAR_REUNIAO] = VETERANO` ([permissions.py](../../src/oraculo/domain/permissions.py)) | `test_permissoes.py`, `test_agenda.py` |
| RN-007 Eventos oficiais | `_POLITICA[Acao.CRIAR_EVENTO] = OFICIAL` | `test_permissoes.py`, `test_agenda.py` |
| RN-008 Controle de permissões | Política central + decorator `requer` ([bot/permissions.py](../../src/oraculo/bot/permissions.py)) | `test_permissoes.py` |
| RN-009 Google Agenda | [google_calendar.py](../../src/oraculo/integrations/google_calendar.py) + `AgendaService` | `test_agenda.py` |
| RN-010 Histórico imutável | Tabelas append-only; soft-delete de membro e agendamento | `test_agenda.py`, `test_xp_service.py` |
| RN-011 Camada Comunidade separada de cargo | `Aldeao` ([models.py](../../src/oraculo/db/models.py)), `bot/cogs/comunidade.py` não usa `bot/permissions.py` | `test_dracmas_service.py` |
| RN-012 Movimentação exige motivo/origem | `DracmasService._validar_motivo`/`_validar_valor` ([dracmas_service.py](../../src/oraculo/services/dracmas_service.py)) | `test_dracmas_service.py` |
| RN-013 Ledger de Dracmas imutável | Tabela `dracmas_ledger` append-only ([repositories/dracmas.py](../../src/oraculo/repositories/dracmas.py)) | `test_dracmas_service.py` |
| RN-014 Suspensão automática | `DracmasService.debitar` marca `Aldeao.suspenso` quando o saldo fica negativo | `test_dracmas_service.py` |
| RN-015 Ingresso na Comunidade | `DracmasService._cobrar_ingresso`, `CUSTO_INGRESSO_COMUNIDADE` | `test_dracmas_service.py` |
| RN-016 Prova de posse para autovínculo | `solicitar_vinculo`/`confirmar_vinculo` ([vinculo_service.py](../../src/oraculo/services/vinculo_service.py)), tabela `vinculos_pendentes`; `bot/cogs/vinculo.py` não usa `bot/permissions.py` (mesmo motivo de RN-011: não pode criar `Membro` antes do vínculo existir); válvula de escape para Administrador quando `confirmar_vinculo` recusa por já existir registro no bot: `reconciliar_manualmente` + `/reconciliar-conta` ([cogs/admin.py](../../src/oraculo/bot/cogs/admin.py)) | `test_vinculo_service.py` |
| RN-017 Autorização na recuperação | `PerguntaService._projetos_autorizados`/`_carregar_projetos` ([pergunta_service.py](../../src/oraculo/services/pergunta_service.py)); filtro obrigatório em [projetos_db.py](../../src/oraculo/integrations/projetos_db.py); leitura pontual em `FirestoreMembros.projetos_de` ([plataforma.py](../../src/oraculo/integrations/plataforma.py)); resposta efêmera em [cogs/pergunta.py](../../src/oraculo/bot/cogs/pergunta.py) | `test_pergunta_service.py`, `test_projetos_db.py`, `test_autorizacao_projetos.py` |
| RN-018 Comunicado publica uma vez | `ComunicadoService.publicar_pendentes` / `_encerrar_orfaos` / `_expirar` ([comunicado_service.py](../../src/oraculo/services/comunicado_service.py)); reserva atômica em `reservar_vencidos` ([repositories/comunicados.py](../../src/oraculo/repositories/comunicados.py)); menção explícita em `permissoes_de_mencao` ([bot/comunicador.py](../../src/oraculo/bot/comunicador.py)) | `test_comunicado_service.py`, `test_comunicador_discord.py` |

## Requisitos funcionais

| RF | Implementação |
|----|---------------|
| RF-001 Autenticação | `obter_ou_criar_por_discord` ([repositories/membros.py](../../src/oraculo/repositories/membros.py)); autovínculo por prova de posse quando a plataforma não trouxe `discordId` — `/vincular-conta`, `/confirmar-vinculo` ([cogs/vinculo.py](../../src/oraculo/bot/cogs/vinculo.py), RN-016) |
| RF-002 Perfil | `/perfil` ([cogs/perfil.py](../../src/oraculo/bot/cogs/perfil.py)) + `RankingService.perfil` |
| RF-003 Gestão de XP | `/conceder-xp`, `/historico-xp` ([cogs/xp.py](../../src/oraculo/bot/cogs/xp.py)) — sem remoção (XP irrevogável) |
| RF-004 Ranking | `/ranking` ([cogs/ranking.py](../../src/oraculo/bot/cogs/ranking.py)) + cache |
| RF-005 / RF-006 Promoções e cargos | `PromocaoService` (patente) + `CargoInstitucionalService` ([cargo_institucional_service.py](../../src/oraculo/services/cargo_institucional_service.py)) + `SincronizadorDiscord`; `/cargo-institucional`, `/confirmar-patente`, `/sincronizar-papeis` ([cogs/admin.py](../../src/oraculo/bot/cogs/admin.py)) |
| RF-007 / RF-008 Reuniões e eventos | `/criar-reuniao`, `/criar-evento`, `/cancelar-agendamento` ([cogs/agenda.py](../../src/oraculo/bot/cogs/agenda.py)) |
| RF-009 RSVP | `BotaoRsvp` / `PainelRsvp` + `AgendaService.responder_rsvp` |
| RF-010 Notificações | [notificacao_service.py](../../src/oraculo/services/notificacao_service.py), canais Discord e e-mail |
| RF-011 Google Agenda | `GoogleAgenda.criar/atualizar/cancelar` (bot → Google) e `alteracoes_desde` + `loop_agenda_google` (Google → bot: edições e cancelamentos feitos no calendário) |
| RF-012 Logs | Tabela `audit_log` ([repositories/auditoria.py](../../src/oraculo/repositories/auditoria.py)) + `/auditoria` |
| RF-013 Saldo/extrato de Dracmas | `/saldo`, `/extrato-dracmas` ([cogs/comunidade.py](../../src/oraculo/bot/cogs/comunidade.py)) |
| RF-014 Doação de Dracmas | `/doar-dracmas`, `DracmasService.doar` |
| RF-015 Comunicados oficiais | `/comunicar`, `/agendar-comunicado`, `/comunicados`, `/cancelar-comunicado` e o ciclo `publicar_programados` ([cogs/comunicados.py](../../src/oraculo/bot/cogs/comunicados.py)) |

## Requisitos não funcionais

| RNF | Implementação |
|-----|---------------|
| RNF-001 / RNF-002 Escala e pico | Pool de conexões, cache Redis, `/health/ready` |
| RNF-003 Segurança | [config.py](../../src/oraculo/config.py) (segredos por ambiente), [api/security.py](../../src/oraculo/api/security.py) (HMAC), `validate_for_production`, container sem root |
| RNF-004 Auditoria administrativa | `audit_log` com ator, alvo, origem e dados |
| RNF-005 Backup | [tasks/backup.py](../../src/oraculo/tasks/backup.py) (`pg_dump` / `VACUUM INTO`) |

## Dívida técnica do legado

| TD | Situação | Onde |
|----|----------|------|
| TD-001 Credenciais hardcoded | **Fechada** | `Settings` + `.env.example` + `.gitignore` + verificação no CI |
| TD-002 Armazenamento em JSON | **Fechada** | SQLAlchemy async + Alembic + `SELECT ... FOR UPDATE` |
| TD-003 Webhook sem HMAC | **Fechada** | `validar_assinatura` (falha fechado, tolerância de replay) |
| TD-004 Hierarquia incorreta | **Fechada** | `hierarchy.py` (substituída pela escala de `XP.md` em TD-007) |
| TD-005 Acúmulo de cargos | **Fechada** | `SincronizadorDiscord` remove antes de atribuir |
| TD-006 Auditoria incompleta | **Fechada** | `xp_audit` com autor, motivo, saldos e origem |
| TD-007 Hierarquia não reflete `Institucional/XP.md` | **Fechada** — unificação decidida pelo Clube TYTO | `hierarchy.py` com as 17 patentes de `XP.md` + `CargoInstitucional`; `permissions.py` com requisitos por patente ou cargo; migração `c3d4e5f6a7b8` |

## Backlog

| Sprint | Itens cobertos pela base | Pendente |
|--------|--------------------------|----------|
| 1 | US-101 a US-105 | — |
| 2 | US-201 a US-205 | — |
| 3 | US-301 a US-305 (bidirecional: `tasks/agenda_google.py` + `AgendaService.aplicar_alteracoes_externas`) | — |
| 4 | US-401 a US-405; painel de métricas (`/metrics`, `/painel` — [metricas_service.py](../../src/oraculo/services/metricas_service.py)); backup com cópia e retenção remotas ([armazenamento_backup.py](../../src/oraculo/integrations/armazenamento_backup.py)) | — |

## Decisões tomadas na implementação

| Tema | Decisão | Motivo |
|------|---------|--------|
| Limiares de XP | Escala de `XP.md` Art. 2º com os valores exatos de `CLAN_TIERS` da plataforma | O regulamento arredonda ("1,7M+"); bot e plataforma precisam concordar na patente de um mesmo XP (TD-007) |
| Privilégios por patente | Reunião Veterano+, evento/comunicado Oficial+; XP, auditoria e `@everyone` só com o cargo Conselheiro | Mapa aprovado pelo Clube TYTO ao fechar TD-007; Conselheiro satisfaz requisitos de patente (eleito já é Comandante+) |
| Rebaixamento | Nunca: não há remoção de XP nem rebaixamento de patente; a importação ignora XP menor da plataforma e registra em auditoria | XP e patente irrevogáveis (`XP.md` Art. 1º §1º e §3º) |
| Reuniões e eventos | Uma tabela `agendamentos` com `tipo` | Mesmo ciclo de vida, RSVP e sync; muda apenas a permissão de criação |
| Cargos institucionais | Conselheiro e Administrador como flags independentes da patente, concedidos por `/cargo-institucional` (Admin); o último Administrador não pode ser revogado | Carta Art. VIII (eixos independentes); evita trancar a governança do bot |
| Teto da importação | Patente acima de Oficial trazida pela plataforma fica pendente até `/confirmar-patente`, que aplica só a patente que o XP determina | A plataforma não está sob RN-008 deste bot; Oficial é a patente mais alta que libera privilégio |
| WhatsApp | Schema e origem de ação já preveem o canal; adaptador não implementado | Fora da Sprint 1–4; exige ADR próprio (follow-up do ADR-001) |
| Ingresso na Comunidade (RN-015) | Cobrado automaticamente no primeiro crédito de Dracmas, mesmo se deixar o saldo negativo (suspende a conta, RN-014) | `COMUNIDADE_E_CLUBE.md` Art. 3º §1º e §3º dão duas leituras possíveis para conciliar; decisão documentada em `services/dracmas_service.py`, vale revisar com o Clube TYTO se a leitura ficar contestada |
| `Membro.dracmas` (US-405) | Segue sem nenhum comando — só a camada Comunidade (`Aldeao`) foi implementada | Migração de saldo Aldeão→Membro na filiação (`COMUNIDADE_E_CLUBE.md` Art. 4º §1º-A) e taxa mensal de manutenção ficam para uma fase seguinte |
