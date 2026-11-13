# Estado atual da Atena (diagnóstico, 2026-11-13)

Fase 0 do plano "Atena como gerente dos projetos" (`docs/GERENTE_PLANO.md`). Este documento descreve
o que o código faz **hoje**, lido do código (`main` em `1be897a`), não do que se imagina que ele faz.
Decisões e divergências entre o pedido e o código estão em `docs/DECISOES.md`.

## 1. Visão geral

| Item | Como é hoje |
|---|---|
| Linguagem e stack | Python 3.11, discord.py (cogs + slash commands), FastAPI (health, webhooks, métricas), SQLAlchemy async + Alembic |
| Processo | Um único processo (`python -m oraculo`) sobe bot, API e jobs conforme `ORACULO_RUN_BOT`/`ORACULO_RUN_API` (`__main__.py`) |
| Hospedagem | Railway (serviço `Athena-Oracle-Bot` + Postgres próprio). Esteve sem deploy de 18/10 a 31/10/2026; religado em 31/10, com a sincronização do Firebase pendente da credencial `ORACULO_FIREBASE_CREDENTIALS_JSON` |
| Banco próprio | Postgres (SQLite em dev): espelho de membros, agenda, comunicados, auditoria, `webhook_events` |
| Interface | Só Discord. Não existe tela no site |
| Escrita na plataforma | Nenhuma (RN-021, ADR-002). A conta de serviço do Firestore deve ser `roles/datastore.viewer` |

Diferente do que se supunha, a Atena **já tem rotinas próprias**: publicador de comunicados
programados (a cada 60 s), sincronização de membros com o Firebase (no start e a cada 6 h), backup
diário e, se ligada, sincronização com o Google Agenda. Ela não tem nenhuma rotina sobre projetos
ou tasks.

## 2. Como recebe mensagens

- Só **slash commands** (`intents.message_content = False` em `bot/client.py`). A Atena não lê
  mensagens livres nem menções; tudo entra por comando.
- Cogs carregados (`bot/client.py:COGS`): `ajuda`, `perfil`, `ranking`, `agenda`, `admin`,
  `pergunta`, `comunicados`, `boas_vindas`.
- Comandos: `/ajuda`, `/perfil`, `/ranking`, `/hierarquia`, `/sincronizar-papeis`,
  `/verificar-cargos`, `/auditoria`, `/criar-reuniao`, `/criar-evento`, `/agenda`,
  `/cancelar-agendamento`, `/comunicar`, `/agendar-comunicado`, `/comunicados`,
  `/cancelar-comunicado`, `/perguntar` (16 sincronizados no servidor).
- Todo comando passa por `@requer(Acao.X)` (`bot/permissions.py`), que: confirma a interação
  (`defer`) antes de qualquer I/O, resolve o autor, checa a política e aplica um teto de tempo
  (`ORACULO_COMANDO_TIMEOUT_SEGUNDOS`, 45 s).
- Erros de domínio viram embed amigável no handler global (`OraculoBot._on_app_command_error`).

## 3. Como identifica o usuário

Cadeia: **ID do Discord → espelho local (`membros`) → documento `users/{uid}` do Firestore**.

1. `AcessoService.membro_cadastrado` (`services/acesso_service.py`) procura o `discord_id` no espelho.
2. Se não achar, faz **uma** consulta pontual ao Firestore (`users where discordId == id`), espelha
   quem for elegível e guarda recusas em cache negativo por 60 s.
3. Elegível (RN-020): conta de Clube ativa, não suspensa, não `merchant`, com `discordId` numérico.
   Quem não for é recusado e nunca registrado.
4. O espelho guarda patente, XP, `conselheiro` e `admin` (mapa em `integrations/plataforma.py`,
   `MAPA_PADRAO_FIREBASE`), atualizado pela sincronização periódica (`tasks/sincronizacao.py`).

O que o espelho **não** guarda: `countryCode` (reino), `dominatium` (Rex), `duxVecturium`,
Guarda Pretoriana, vínculo com projetos, `clickupUserId`/`clickupEmail`.

## 4. Como carrega os `.md`

- `integrations/regras_corpus.py` lê todos os `.md` de `ORACULO_REGRAS_DIR` (padrão
  `docs/regras-tyto/`), em ordem alfabética estável, uma vez no start, e monta um bloco único.
- O bloco vai no prompt com `cache_control` (prefixo compartilhado por todas as perguntas).
- **No repositório essa pasta só tem o `README.md`** (o resto é ignorado pelo `.gitignore`). Se
  ninguém copiar os arquivos para o container, o `/perguntar` responde sem regulamento. Foi o que
  aconteceu em produção até 31/10. Os regulamentos vivos estão em `TYTO.club/docs/*.md`.

## 5. Como chama a API do Claude

- `integrations/llm.py`: SDK oficial `anthropic`, uma chamada sem streaming, modelo
  `ORACULO_LLM_MODEL` (padrão `claude-haiku-4-5`), `max_tokens` 1500, timeout 30 s.
- Prompt em três partes: instruções (estáveis), regulamento (estável, em cache), contexto do
  usuário + pergunta (volátil).
- Freio de custo: `ORACULO_PERGUNTA_LIMITE_HORA` (10 perguntas por pessoa por hora, contador no
  cache). Não há cache de respostas a perguntas repetidas nem limite diário.
- Só o `/perguntar` chama o modelo. Nenhuma outra parte do código usa LLM.

## 6. Como aplica a hierarquia

Dois eixos, ambos espelhados da plataforma (`domain/hierarchy.py`, `domain/permissions.py`):

- **Patente** (19 patamares, irrevogável) e **cargos institucionais** (Conselheiro, Administrador).
- A política `_POLITICA` mapeia cada `Acao` para uma patente mínima ou um cargo. Administrador
  satisfaz tudo; Conselheiro satisfaz requisitos de patente; patente nunca satisfaz cargo.

No `/perguntar` a hierarquia de **informação** é outra (RN-017, `services/pergunta_service.py`):

1. **Autorizar**: lê no Firestore, na hora, em que projetos a pessoa está.
2. **Recuperar**: carrega só esses projetos de um Postgres externo somente leitura
   (`ORACULO_PROJETOS_DATABASE_URL`, tabelas `projetos` e `projeto_decisoes`, contrato em
   `docs/projetos-schema.sql`).
3. **Gerar**: só então chama o modelo. O modelo nunca decide permissão; dado alheio nem é carregado.
   Resposta sempre efêmera.

**Divergência encontrada:** a Atena procura os projetos da pessoa na subcoleção
`users/{uid}/projetos` ou num campo `projetos` do documento. No site, o vínculo real vive em
`project_stats/{id}.members` (`{ uid: 'leader' | 'partner' | 'contributor' | 'seller' }`), que é o
que a `TYTO.club-API` e as regras do Firestore usam. Na prática o `/perguntar` não encontra projeto
nenhum. E o Postgres externo de projetos é uma base à parte, que não é alimentada pelo site.

## 7. O que já existe e serve ao "gerente"

| Peça | Onde | Serve para |
|---|---|---|
| Camada de envio com canais (`NotificacaoService` + `CanalDiscord` por DM + `CanalEmail`) | `services/notificacao_service.py`, `bot/notificador.py` | Base da "camada de envio abstrata" (M2–M4, M7, M9) |
| Endpoint `/webhooks/clickup` com HMAC e deduplicação | `api/routers/webhooks.py` | Só grava o evento; usa um segredo global. **Redundante**: o webhook real do ClickUp é registrado pela `TYTO.club-API` por projeto (ver §8) |
| Jobs em laço dentro do processo | `tasks/` | Padrão para jobs diários (reconciliação, alertas, resumo) |
| Auditoria append-only | `repositories/auditoria.py` | Log estruturado de cada ação |
| Política central de permissão | `domain/permissions.py` | Hoje é por comando (patente/cargo), não por recurso. O `can_view(viewer, recurso)` do gerente é novo |

## 8. O que vive fora da Atena e importa para o gerente

Na `TYTO.club-API` (Node/TypeScript, Firestore):

- **ClickUp já integrado por projeto**: o líder conecta o projeto (token pessoal ou OAuth), a API
  guarda token e segredo do webhook **cifrados** (`project_integrations`, `clickup_webhooks`),
  registra um webhook filtrado pela lista do projeto (`taskStatusUpdated`, `taskDeleted`) e paga
  Dracmas/XP na conclusão de tasks vinculadas a missões (`docs/CLICKUP_MISSOES.md`). Tasks fora de
  missões são descartadas no webhook. Não há cópia das tasks nem dos prazos.
- **Identidade ClickUp → site**: `users.clickupUserId` (só a API grava, no primeiro match confiável)
  e `users.clickupEmail` (declarado pelo membro; só vale se for único entre os membros do projeto).
- **Projetos**: `project_stats/{id}` com `members`, `leader`, `status`, `tier`.
- **Reino**: `users.countryCode`; o reino do projeto é o do líder técnico (`EMPRESAS.md` Art. 7º,
  já usado em `ProjectLeaderChangeService`).
- **Cargos**: `users.admin`, `users.conselheiro`, `users.dominatium` (Rex do reino),
  `users.duxVecturium`, Guarda Pretoriana em `guarda_pretoriana_members`.
- **Missões**: `missions/{id}` (`status`, `scope`, `createdAt`, `rewardDracmas`, `rewardXp`);
  contratos em `user_missions`.
- **Rota serviço-a-serviço** já usada pela Atena: `/api/internal/*` com `requireServiceKey`.

Não existe hoje: campo de férias/pausa declarada, campo de fuso horário do membro, endpoint que
liste tasks/prazos por pessoa, painel de gestão.

## 9. Endpoints do site: disponíveis e faltando

| Precisa | Existe? |
|---|---|
| Quem é a pessoa (cargo, reino, admin, Rex) | Sim, mas só lendo `users/{uid}` no Firestore. Sem endpoint interno |
| Vínculos e papel no projeto | Sim em `project_stats.members`; `GET /api/projects/:id/members` exige token do usuário |
| Credencial ClickUp do projeto | Só dentro da API (cifrada). Não deve sair de lá |
| Tasks, prazos, responsáveis, última atividade | **Falta** (nada guarda isso hoje) |
| Missões abertas sem ninguém | Dá para derivar de `missions` + `user_missions`; **falta** o endpoint |
| Saída para o painel, filtrada por cargo | **Falta** |
| Pausa declarada, fuso do membro | **Falta** (campo inexistente) |
