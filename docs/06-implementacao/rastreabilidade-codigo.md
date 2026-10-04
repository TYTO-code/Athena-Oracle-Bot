# Rastreabilidade — requisito → código

Fecha a cadeia `Visão → RN/RF/RNF → Casos de Uso → Dívida Técnica → ADR → Backlog` com a camada de implementação (Atena v1.0).

## Regras de negócio

| RN | Onde é aplicada | Teste |
|----|-----------------|-------|
| RN-001 Patente única | Coluna única `Membro.patente_slug` ([models.py](../../src/oraculo/db/models.py)); remoção de todos os papéis de patente em [role_sync.py](../../src/oraculo/bot/role_sync.py); cargos institucionais como flags `conselheiro`/`administrador` | `test_role_sync.py`, `test_promocao.py`, `test_cargo_institucional.py` |
| RN-002 Progressão por XP | `patente_para_xp` ([hierarchy.py](../../src/oraculo/domain/hierarchy.py)); `PromocaoService` só sobe patente | `test_hierarquia.py`, `test_promocao.py` |
| RN-003 Promoção automática | `PromocaoService.aplicar` ([promocao_service.py](../../src/oraculo/services/promocao_service.py)) | `test_promocao.py` |
| RN-004 Controle de XP | Sem comando de XP: `Acao` não tem concessão; XP é espelhado em [importacao_service.py](../../src/oraculo/services/importacao_service.py) e só sobe | `test_permissoes.py`, `test_importacao.py`, `test_comandos.py` |
| RN-005 Auditoria de XP | Tabela `xp_audit`: cada subida espelhada vira uma linha (`ImportacaoService._espelhar_progressao`) | `test_importacao.py`, `test_ranking_e_perfil.py` |
| RN-006 Criação de reuniões | `_POLITICA[Acao.CRIAR_REUNIAO] = VETERANO` ([permissions.py](../../src/oraculo/domain/permissions.py)) | `test_permissoes.py`, `test_agenda.py` |
| RN-007 Eventos oficiais | `_POLITICA[Acao.CRIAR_EVENTO] = OFICIAL` | `test_permissoes.py`, `test_agenda.py` |
| RN-008 Controle de permissões | Política central + decorator `requer` ([bot/permissions.py](../../src/oraculo/bot/permissions.py)) | `test_permissoes.py` |
| RN-009 Google Agenda | [google_calendar.py](../../src/oraculo/integrations/google_calendar.py) + `AgendaService` | `test_agenda.py` |
| RN-010 Histórico imutável | Tabelas append-only; soft-delete de membro e agendamento | `test_agenda.py`, `test_importacao.py` |
| RN-011 Camada Comunidade separada de cargo | *Revogada (RN-021): o código foi removido do bot* | — |
| RN-012 Movimentação exige motivo/origem | *Revogada (RN-021): o código foi removido do bot* | — |
| RN-013 Ledger de Dracmas imutável | *Revogada (RN-021): o código foi removido do bot* | — |
| RN-014 Suspensão automática | *Revogada (RN-021): o código foi removido do bot* | — |
| RN-015 Ingresso na Comunidade | *Revogada (RN-021): o código foi removido do bot* | — |
| RN-016 Prova de posse para autovínculo | *Revogada (RN-021): o código foi removido do bot* | — |
| RN-017 Autorização na recuperação | `PerguntaService._projetos_autorizados`/`_carregar_projetos` ([pergunta_service.py](../../src/oraculo/services/pergunta_service.py)); filtro obrigatório em [projetos_db.py](../../src/oraculo/integrations/projetos_db.py); leitura pontual em `FirestoreMembros.projetos_de` ([plataforma.py](../../src/oraculo/integrations/plataforma.py)); resposta efêmera em [cogs/pergunta.py](../../src/oraculo/bot/cogs/pergunta.py) | `test_pergunta_service.py`, `test_projetos_db.py`, `test_autorizacao_projetos.py` |
| RN-018 Comunicado publica uma vez | `ComunicadoService.publicar_pendentes` / `_encerrar_orfaos` / `_expirar` ([comunicado_service.py](../../src/oraculo/services/comunicado_service.py)); reserva atômica em `reservar_vencidos` ([repositories/comunicados.py](../../src/oraculo/repositories/comunicados.py)); menção explícita em `permissoes_de_mencao` ([bot/comunicador.py](../../src/oraculo/bot/comunicador.py)) | `test_comunicado_service.py`, `test_comunicador_discord.py` |
| RN-019 Migração de saldo na filiação | *Revogada (RN-021): o código foi removido do bot* | — |
| RN-020 Acesso só para cadastrados | `obter_cadastrado_por_discord` ([repositories/membros.py](../../src/oraculo/repositories/membros.py)), `AcessoService` ([acesso_service.py](../../src/oraculo/services/acesso_service.py)), gate em `requer` ([bot/permissions.py](../../src/oraculo/bot/permissions.py)); elegibilidade em `MembroExterno.elegivel` | `test_interacao.py`, `test_importacao.py` |
| RN-021 Bot só consulta | Sem comandos nem serviços de escrita; `FirestoreMembros` só lê; trava estrutural | `test_somente_leitura.py`, `test_comandos.py` |

## Requisitos funcionais

| RF | Implementação |
|----|---------------|
| RF-001 Autenticação | Cadastro vem da TYTO.club: `ImportacaoService` (espelho) + `AcessoService` (consulta pontual); o bot nunca registra ninguém (RN-020) | `test_importacao.py`, `test_interacao.py` |
| RF-002 Perfil | `/perfil` ([cogs/perfil.py](../../src/oraculo/bot/cogs/perfil.py)) + `RankingService.perfil` |
| RF-003 Gestão de XP | *Fora do bot (RN-021): XP é concedido na TYTO.club e espelhado* | `test_importacao.py` |
| RF-004 Ranking | `/ranking` ([cogs/ranking.py](../../src/oraculo/bot/cogs/ranking.py)) + cache |
| RF-005 / RF-006 Promoções e cargos | `PromocaoService` (patente) + espelho de cargos em `ImportacaoService._espelhar_cargos` + `SincronizadorDiscord`; `/sincronizar-papeis` ([cogs/admin.py](../../src/oraculo/bot/cogs/admin.py)) |
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
| Cargos institucionais | Conselheiro e Administrador como flags independentes da patente, **espelhadas** da plataforma (RN-021); o bot não os concede | Carta Art. VIII (eixos independentes); fonte única da verdade na TYTO.club |
| Teto da importação | *Removido (ADR-002):* sem `/confirmar-patente`, a patente da plataforma é aplicada direto; a proteção de `tier`/`xp`/`admin` é das regras do Firestore da TYTO.club | O bot não escreve; reter patente sem ninguém para liberar só travaria o Clube |
| WhatsApp | Schema e origem de ação já preveem o canal; adaptador não implementado | Fora da Sprint 1–4; exige ADR próprio (follow-up do ADR-001) |
| Dracmas do Clube | Vivem só na plataforma; o bot guarda só a Comunidade e migra o saldo na filiação (RN-019). `Membro.dracmas` (US-405) fica sem uso | Decisão do Clube TYTO (F2-006): a plataforma já cobra a taxa mensal — manter um segundo saldo no bot cobraria em dobro |
