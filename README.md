# Bot Oráculo — Clube TYTO

Sistema de gestão operacional do **Clube TYTO** (produto **Atena v1.0**): hierarquia, XP, promoções, reuniões, eventos, RSVP e auditoria via Discord, com API de webhooks e integração com o Google Agenda.

Este repositório contém **a documentação de engenharia** e **a implementação** da baseline definida no [ADR-001](docs/04-arquitetura/adr-001-stack-tecnica.md).

Este é o bot **Atena** regido normativamente por `Institucional/SERVIDOR_DISCORD.md` (fora deste
repositório, no vault do Clube). Onde a documentação daqui divergir daquele Regulamento, ele vence —
ver a nota em [docs/00-visao/visao-produto.md](docs/00-visao/visao-produto.md#relação-com-institucionalservidor_discordmd).
Dracmas, camadas de Comunidade/Clube, Crédito de Mérito e a integração com o Mercador já são regra
vigente lá, mesmo fora do escopo de código desta v1.0 — ver [docs/05-roadmap/fase-2.md](docs/05-roadmap/fase-2.md).

## Stack

`discord.py` (cogs) · `FastAPI` · `SQLAlchemy 2 async` + `Alembic` · PostgreSQL (SQLite em dev) · Redis (opcional) · Google Calendar API · Docker

## Começando

```bash
make setup                 # venv, dependências e .env a partir do .env.example
$EDITOR .env               # preencha ORACULO_DISCORD_TOKEN e demais segredos
make migrate               # aplica o schema
make run                   # sobe bot + API
```

Sem `make`:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pip install -e .
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m oraculo
```

Em produção (ou onde a plataforma detecta `requirements.txt` sozinha, como Render e Railway), basta `pip install -r requirements.txt`. O [pyproject.toml](pyproject.toml) segue como fonte de verdade das dependências; os `requirements*.txt` fixam as versões exatas com que a suíte passa — ao mudar uma, atualize os dois e rode `make check`.

Ambiente completo com PostgreSQL e Redis:

```bash
cp .env.example .env
docker compose up --build
```

### Comandos úteis

| Comando | O que faz |
|---------|-----------|
| `make run` / `bot` / `api` | Sobe tudo, só o bot ou só a API |
| `make migrate` | Aplica migrações (`alembic upgrade head`) |
| `make migration m="..."` | Gera migração a partir dos modelos |
| `make verificar` | Valida a configuração para produção (RNF-003) |
| `make backup` | Executa um backup imediato (RNF-005) |
| `make check` | Lint + testes |

## Configuração

Todos os segredos vêm de variáveis de ambiente com o prefixo `ORACULO_` — **nada de credencial em código** (TD-001 / RNF-003). O catálogo completo está em [.env.example](.env.example); o mínimo para subir é:

| Variável | Para quê |
|----------|----------|
| `ORACULO_DISCORD_TOKEN` | Token do bot |
| `ORACULO_DATABASE_URL` | `postgresql+asyncpg://...` em produção |
| `ORACULO_CLICKUP_WEBHOOK_SECRET` | Segredo HMAC do webhook (TD-003) |

`make verificar` recusa uma configuração de produção incompleta antes do deploy.

### Antes do primeiro uso no servidor Discord

1. Crie os papéis com **exatamente** estes nomes: as 17 patentes de `XP.md` (`Neófito`, `Escudeiro`,
   `Armeiro`, `Veterano`, `Mestre de Armas`, `Desafiante Legionário`, `Oficial`, `Centurião`,
   `Comandante`, `Dom`, `Lorde`, `Senhor da Guerra`, `Suserano`, `Monarca`, `Dominador`, `Renovek`,
   `Omni`) e os cargos institucionais `Conselheiro` e `Administrador`.
2. Posicione o papel do bot **acima** deles na lista de cargos (senão o Discord recusa a atribuição).
3. Habilite o intent **Server Members** no portal do desenvolvedor.
4. Rode `/verificar-cargos` no servidor para confirmar.
5. `/cargo-institucional` exige Administrador — e ninguém começa com esse cargo. Quebre o ciclo uma vez, por
   qualquer um destes dois caminhos (recusam sozinhos se já existir um Administrador ativo):
   - com acesso a rodar comandos no servidor: `python -m oraculo promover-admin --discord-id <seu id>`;
   - só com acesso ao painel de variáveis do deploy (ex.: Railway, sem CLI/espaço local): defina
     `ORACULO_BOOTSTRAP_ADMIN_DISCORD_ID=<seu id>` e reinicie o serviço — o bot se autopromove sozinho
     no próximo start.

   Depois, rode `/sincronizar-papeis` em você mesmo para aplicar o papel no servidor, e use
   `/cargo-institucional` normalmente para nomear Conselheiros e outros Administradores.

## Comandos do bot

| Comando | Função | Quem pode |
|---------|--------|--------------|
| `/ajuda` | Lista os comandos e o que sua patente/cargo libera | Qualquer membro |
| `/perguntar` | Pergunta sobre o regulamento TYTO e sobre **seus** projetos (RN-017) | Qualquer membro |
| `/perfil` | Patente, cargos, XP, próxima patente e posição (RF-002) | Qualquer membro |
| `/ranking` | Ranking geral ou por período (RF-004) | Qualquer membro |
| `/saldo` | Saldo de Dracmas na Comunidade (RF-013) | Nenhuma — Aldeão não usa cargo |
| `/extrato-dracmas` | Histórico de movimentações de Dracmas (RF-013) | Nenhuma — Aldeão não usa cargo |
| `/doar-dracmas` | Doa Dracmas do próprio saldo a outra pessoa (RF-014) | Nenhuma — Aldeão não usa cargo |
| `/agenda` | Próximas reuniões e eventos | Qualquer membro |
| `/hierarquia` | Escala de patentes e cargos institucionais | Qualquer membro |
| `/criar-reuniao` | Cria reunião e sincroniza agenda (RF-007) | Veterano+ |
| `/cancelar-agendamento` | Cancelamento lógico (RN-010) | Veterano+ / organizador |
| `/criar-evento` | Cria evento oficial (RF-008) | Oficial+ |
| `/comunicar` | Publica um comunicado oficial num canal (RF-015) | Oficial+ |
| `/agendar-comunicado` | Programa um comunicado para depois (RF-015) | Oficial+ |
| `/comunicados` | Fila de comunicados: programados, publicados, falhados | Oficial+ |
| `/cancelar-comunicado` | Cancela um comunicado ainda não publicado (RN-010) | Oficial+ / autor |
| `/conceder-xp` | Concede XP com motivo obrigatório (RF-003) — XP nunca é removido (`XP.md` Art. 1º) | Conselheiro |
| `/historico-xp` | Trilha auditável de um membro (RF-012) | Conselheiro |
| `/auditoria` | Últimos registros do log | Conselheiro |
| `/cargo-institucional` | Concede ou revoga Conselheiro/Administrador | Administrador |
| `/confirmar-patente` | Libera a patente que o XP determina, retida pela importação | Administrador |
| `/sincronizar-papeis` | Reaplica no Discord a patente e os cargos do banco | Administrador |
| `/migrar-para-clube` | Na filiação, leva o saldo inteiro da Comunidade para a conta do Clube na plataforma (RN-019) | Administrador |
| `/verificar-cargos` | Diagnóstico dos papéis do servidor | Administrador |

RSVP (UC-006) é feito pelos botões do anúncio — eles continuam funcionando após reiniciar o bot.

## API

| Rota | Uso |
|------|-----|
| `GET /health` | Liveness (US-403) |
| `GET /health/ready` | Readiness: banco e cache |
| `GET /metrics` | Métricas no formato Prometheus (membros por patente e cargo, XP, promoções, agenda, comunicados, Comunidade, último backup/importação) — exige `ORACULO_METRICAS_TOKEN` |
| `GET /painel` | As mesmas métricas numa página HTML (`?token=` ou `Authorization: Bearer`) |
| `POST /webhooks/clickup` | Webhook assinado com HMAC-SHA256 no header `X-Signature` |

A API **não** expõe operações de domínio: XP, cargos e agenda passam pelo bot, onde a identidade do autor é conhecida e a política de permissões (RN-008) é aplicada.

## Comunicados (`/comunicar`, `/agendar-comunicado`) — RN-018

O bot publica avisos oficiais num canal do servidor — tipicamente o `#comunicados` —
na hora ou em data marcada.

```bash
# .env — o canal padrão dos comunicados
ORACULO_DISCORD_COMUNICADOS_CHANNEL_ID=123456789012345678
```

Para pegar o ID: no Discord, **Configurações → Avançado → Modo desenvolvedor**, depois
botão direito no canal → **Copiar ID do canal**. Sem essa variável os comandos seguem
funcionando, mas exigem o canal informado a cada vez.

No Discord:

```
/agendar-comunicado titulo:Assembleia de outubro
                    corpo:Pauta: orçamento e novos Lordes.\nComparecimento recomendado.
                    quando:05/10/2026 19:30
```

`\n` no corpo vira quebra de linha (o campo do slash command não aceita Enter).
O bot confirma em resposta privada e publica na hora marcada. `/comunicados` mostra a
fila; `/cancelar-comunicado` desmarca o que ainda não saiu.

### O que está protegido aqui

- **Publicar é Oficial+; `@here`/`@everyone` é do cargo Conselheiro.** Escrever no canal
  atinge quem for ler; um ping atinge o celular de cada membro — é um degrau a mais.
- **O texto do aviso não consegue forçar um ping.** O corpo vai no *embed*, e menção
  dentro de embed não notifica ninguém: escrever `@everyone` no texto produz as letras
  `@everyone`, nada mais. Quem notifica é o parâmetro `mencao`, que passou pela política
  de permissões.
- **Um comunicado programado sai uma vez, ou nenhuma.** O publicador reserva a linha no
  banco antes de falar com o Discord; se o bot cair no meio do envio, aquele comunicado
  é encerrado como falha e aparece em `/comunicados` — nunca republicado sozinho, porque
  um `@everyone` duplicado é pior que um aviso atrasado.
- **Comunicado atrasado demais não vai ao ar.** Passadas
  `ORACULO_COMUNICADOS_ATRASO_MAXIMO_HORAS` (6h por padrão) da hora marcada, ele expira
  em vez de aparecer fora de hora — útil exatamente quando o bot passou um tempo fora.

O ciclo de publicação roda dentro do processo do próprio bot, a cada
`ORACULO_COMUNICADOS_INTERVALO_SEGUNDOS` (60 por padrão; `0` desliga). Não há agendador
externo — mesma escolha do backup e da sincronização (ADR-001).

## Pergunta ao Oráculo (`/perguntar`) — RN-017

O bot responde sobre o **regulamento TYTO** (os `.md` em
[`docs/regras-tyto/`](docs/regras-tyto/), já apontados por padrão) e sobre os
**projetos em que a pessoa participa**.

A regra de segurança que sustenta isso: **a autorização acontece na recuperação,
nunca no prompt**. O bot descobre no Firebase, no momento da pergunta, em quais
projetos o autor está; só esses são lidos do banco externo; só então o modelo é
chamado. Dado de projeto alheio nunca entra no contexto — então não existe
instrução de prompt (nem texto malicioso salvo no banco) capaz de extraí-lo.
Quem não tem vínculo Discord↔plataforma (RN-016) não tem projeto algum, e a
resposta é sempre efêmera, porque conteúdo restrito não pode ir para o canal.

### Quem pode ver qual projeto (Firebase)

A autorização sai da **subcoleção** `membros/{id_externo}/projetos` no Firestore:
um documento por projeto, cujo **id do documento é o id do projeto**. Um documento
com `ativo: false` (ou `removido: true`) é lido como vínculo encerrado — quem sai
de um projeto normalmente é desativado, não apagado.

Se a subcoleção não existir, o bot ainda tenta um campo `projetos` no próprio
documento do membro (lista, mapa `{id: true}` ou string com vírgulas) — custa uma
leitura e evita um "sem acesso" falso só por diferença de formato.

### Banco externo de projetos

`ORACULO_PROJETOS_DATABASE_URL` aponta para um PostgreSQL **separado** do banco do
bot, com um usuário que tenha **apenas `SELECT`**. O schema pronto para rodar está
em [`docs/projetos-schema.sql`](docs/projetos-schema.sql):

```bash
psql "$PROJETOS_DATABASE_URL" -f docs/projetos-schema.sql
```

`projetos.id` precisa casar com o id do projeto no Firebase — se os dois lados
divergirem, ninguém vê nada. Para adaptar um schema que já exista, exponha `VIEW`s
com esses nomes: eles são fixos no código de propósito, porque identificador de SQL
não é parametrizável e torná-los configuráveis abriria uma via de injeção.

Sem essa variável, `/perguntar` continua funcionando **só** para o regulamento.

### Custo

O padrão é o modelo mais barato da linha atual (`claude-haiku-4-5`, ~$1/$5 por
milhão de tokens), e o regulamento inteiro vai num prefixo de prompt **cacheado e
compartilhado** entre todas as perguntas de todos os membros — a parte cara do
prompt é paga uma vez, não por pessoa. `ORACULO_PERGUNTA_LIMITE_HORA` (padrão 10)
é o freio por pessoa: um LLM aberto ao servidor inteiro sem teto é conta aberta.
Se as respostas ficarem rasas, `ORACULO_LLM_MODEL=claude-sonnet-5` dobra o custo.

## Plataforma de membros (Firebase)

Os membros do clube vivem no **Cloud Firestore**; o bot lê essa coleção e mantém
o cadastro local sincronizado.

```bash
python -m oraculo importar --ensaio   # percorre tudo e relata sem gravar nada
python -m oraculo importar            # aplica
```

Com `ORACULO_FIREBASE_PROJECT_ID` configurado, a sincronização também roda
sozinha dentro do processo do bot: uma vez no start e a cada
`ORACULO_IMPORTACAO_INTERVALO_HORAS`.

| Variável | Para quê |
|----------|----------|
| `ORACULO_FIREBASE_PROJECT_ID` | Projeto do Firebase; vazio desliga a integração |
| `ORACULO_FIREBASE_CREDENTIALS_FILE` | JSON da service account (nunca versionar) |
| `ORACULO_FIREBASE_COLECAO` | Coleção com os membros (padrão: `membros`) |
| `ORACULO_FIREBASE_CAMPOS` | Mapa campo interno → campo do documento, em JSON |
| `ORACULO_IMPORTACAO_POLITICA` | `cadastro`, `carga_inicial` ou `espelho` |

Se os campos do Firestore tiverem outros nomes, ajuste o mapa em vez de mexer no
código — ele aceita caminho aninhado:

```bash
ORACULO_FIREBASE_CAMPOS={"nome":"displayName","discord_id":"discord.id","xp":"pontos"}
```

**Modo `espelho`** (XP vem da plataforma): o bot passa a apenas exibir o XP.
`/conceder-xp` é recusado com mensagem explicativa, porque a próxima
sincronização sobrescreveria o saldo. A patente é derivada do XP (RN-002) e lida
do campo `tier` da plataforma; XP menor na plataforma não é espelhado (XP é
irrevogável — vai para a auditoria) e nada rebaixa uma patente. Acima de
Oficial, a importação só registra a sugestão; um Administrador libera com
`/confirmar-patente`. Cargos institucionais nunca vêm da importação.

Quem sai da plataforma **não** é desativado por padrão; use
`--desativar-ausentes` (soft-delete, RN-010) se quiser esse comportamento.

## Estrutura

```
src/oraculo/
├── config.py          Configuração por ambiente (TD-001)
├── container.py       Composição de serviços e integrações
├── domain/            Hierarquia TYTO, permissões e erros de negócio
├── db/                Modelos e sessão SQLAlchemy async (TD-002)
├── repositories/      Acesso a dados
├── services/          Casos de uso (XP, promoção, ranking, agenda, notificações)
├── integrations/      Cache, Google Agenda, e-mail, Firestore
├── bot/               Cliente Discord, cogs, sincronização de papéis (TD-005)
├── api/               FastAPI: health, webhooks (TD-003) e painel de métricas
└── tasks/             Backup diário com cópia remota (RNF-005), sincronização com a plataforma e Google Agenda → bot
```

O domínio não conhece Discord nem HTTP: as regras valem igualmente para comandos, webhooks e rotinas.

## Testes

```bash
make test        # 337 testes
make check       # lint + testes
```

A suíte cobre as regras críticas: patente única e não acúmulo de papéis (RN-001/TD-005), patente e XP irrevogáveis (`XP.md` Art. 1º), cargos institucionais independentes da patente (TD-007), motivo obrigatório e trilha de XP (RN-005/TD-006), permissões por patente ou cargo (RN-004/006/007/008), promoção automática (RN-002/003), cancelamento lógico (RN-010) e rejeição de webhook sem assinatura válida (TD-003).

## Documentação

| Artefato | Caminho |
|----------|---------|
| Visão do produto | [docs/00-visao/visao-produto.md](docs/00-visao/visao-produto.md) |
| SRS (IEEE 830) | [docs/01-requisitos/srs.md](docs/01-requisitos/srs.md) |
| Regras de negócio | [docs/01-requisitos/regras-de-negocio.md](docs/01-requisitos/regras-de-negocio.md) |
| Requisitos funcionais | [docs/01-requisitos/requisitos-funcionais.md](docs/01-requisitos/requisitos-funcionais.md) |
| Requisitos não funcionais | [docs/01-requisitos/requisitos-nao-funcionais.md](docs/01-requisitos/requisitos-nao-funcionais.md) |
| Casos de uso | [docs/02-casos-de-uso/casos-de-uso.md](docs/02-casos-de-uso/casos-de-uso.md) |
| Dívida técnica | [docs/03-analise/divida-tecnica.md](docs/03-analise/divida-tecnica.md) |
| ADR — Stack | [docs/04-arquitetura/adr-001-stack-tecnica.md](docs/04-arquitetura/adr-001-stack-tecnica.md) |
| Roadmap / sprints | [docs/05-roadmap/backlog-sprints.md](docs/05-roadmap/backlog-sprints.md) |
| Fase 2 | [docs/05-roadmap/fase-2.md](docs/05-roadmap/fase-2.md) |
| **Requisito → código** | [docs/06-implementacao/rastreabilidade-codigo.md](docs/06-implementacao/rastreabilidade-codigo.md) |
| Glossário | [docs/glossario.md](docs/glossario.md) |

Rastreabilidade: `Visão → RN / RF / RNF → Casos de Uso → Dívida Técnica → ADR → Backlog → Código`.
IDs estáveis: `RN-xxx`, `RF-xxx`, `RNF-xxx`, `UC-xxx`, `TD-xxx`, `ADR-xxx`, `US-xxx`.

## Convenções de contribuição

- Commits e PRs que fecham dívida referenciam o ID (`TD-003: valida HMAC no webhook`).
- Toda ação privilegiada nova entra em `Acao` **e** em `_POLITICA` (RN-008) — sem política, o código falha explicitamente.
- Nada de `DELETE` em `xp_audit`, `promocoes` ou `audit_log` (RN-010).
