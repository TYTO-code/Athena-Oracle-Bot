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

1. Crie os cargos com **exatamente** estes nomes: `Membro`, `Cavalaria`, `Lorde`, `Conselheiro`, `Administrador`.
2. Posicione o cargo do bot **acima** deles na lista de cargos (senão o Discord recusa a atribuição).
3. Habilite o intent **Server Members** no portal do desenvolvedor.
4. Rode `/verificar-cargos` no servidor para confirmar.

## Comandos do bot

| Comando | Função | Cargo mínimo |
|---------|--------|--------------|
| `/ajuda` | Lista os comandos e o que seu cargo libera | Membro |
| `/perfil` | Cargo, XP, próximo cargo e posição (RF-002) | Membro |
| `/ranking` | Ranking geral ou por período (RF-004) | Membro |
| `/agenda` | Próximas reuniões e eventos | Membro |
| `/hierarquia` | Cargos e limiares de XP | Membro |
| `/criar-reuniao` | Cria reunião e sincroniza agenda (RF-007) | Cavalaria |
| `/cancelar-agendamento` | Cancelamento lógico (RN-010) | Cavalaria / organizador |
| `/criar-evento` | Cria evento oficial (RF-008) | Lorde |
| `/conceder-xp`, `/remover-xp` | Movimenta XP com motivo obrigatório (RF-003) | Conselheiro |
| `/historico-xp` | Trilha auditável de um membro (RF-012) | Conselheiro |
| `/auditoria` | Últimos registros do log | Conselheiro |
| `/definir-cargo` | Atribuição manual de cargo | Administrador |
| `/verificar-cargos` | Diagnóstico dos cargos do servidor | Administrador |

RSVP (UC-006) é feito pelos botões do anúncio — eles continuam funcionando após reiniciar o bot.

## API

| Rota | Uso |
|------|-----|
| `GET /health` | Liveness (US-403) |
| `GET /health/ready` | Readiness: banco e cache |
| `POST /webhooks/clickup` | Webhook assinado com HMAC-SHA256 no header `X-Signature` |

A API **não** expõe operações de domínio: XP, cargos e agenda passam pelo bot, onde a identidade do autor é conhecida e a política de permissões (RN-008) é aplicada.

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
`/conceder-xp` e `/remover-xp` são recusados com mensagem explicativa, porque a
próxima sincronização sobrescreveria o saldo. O cargo é derivado do XP pelas
regras da hierarquia (RN-002) — um campo `cargo` ausente nunca rebaixa ninguém.

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
├── bot/               Cliente Discord, cogs, sincronização de cargos (TD-005)
├── api/               FastAPI: health e webhooks (TD-003)
└── tasks/             Backup diário (RNF-005) e sincronização com a plataforma
```

O domínio não conhece Discord nem HTTP: as regras valem igualmente para comandos, webhooks e rotinas.

## Testes

```bash
make test        # 146 testes
make check       # lint + testes
```

A suíte cobre as regras críticas: cargo único e não acúmulo de cargos (RN-001/TD-005), motivo obrigatório e trilha de XP (RN-005/TD-006), permissões por cargo (RN-004/006/007/008), promoção automática (RN-002/003), cancelamento lógico (RN-010) e rejeição de webhook sem assinatura válida (TD-003).

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
