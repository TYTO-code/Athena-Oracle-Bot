# CLAUDE.md

Orientações para o Claude Code neste repositório.

## O que é

**Atena** (pacote `oraculo`, "Bot Oráculo"): o bot Discord do Clube TYTO. Python 3.11+, discord.py,
FastAPI (health + webhooks), SQLAlchemy async + Alembic, Postgres/SQLite. **O bot só espelha** a
plataforma TYTO.club: não concede XP, Dracmas nem cargos (RN-021) — lê `users` do Firestore e reage.

O regulamento institucional vence o código (`.claude/rules/institucional-is-law.md`): onde divergirem,
o código muda, nunca o regulamento.

## Comandos

```bash
make setup       # venv + dependências de desenvolvimento (.env a partir do .env.example)
make test        # suíte pytest completa
make check       # lint + testes (antes de abrir PR)
make lint        # ruff check src tests
make typecheck   # mypy
make migrate     # alembic upgrade head
make migration m="descrição"   # nova migração (autogenerate)
```

O CI (`.github/workflows/ci.yml`) roda a suíte a cada push/PR. O hook `.claude/hooks/gate-testes.sh`
barra `git commit`/`git push` se `make test` falhar (e libera com aviso se não houver `.venv`).

## Arquitetura

Camadas de dentro para fora; `domain/` não importa discord.py, FastAPI nem HTTP:

```
domain/          hierarchy.py (patentes, cargos), permissions.py, errors.py — regras puras
services/        orquestram casos de uso (promoção, ranking, importação, comunicados…)
repositories/    acesso a dados
db/              models.py (SQLAlchemy) + base
bot/             client, cogs (comandos), role_sync (papéis do Discord), permissions
api/             FastAPI: health, webhooks, painel de métricas
tasks/           rotinas agendadas
```

Rastreabilidade: `Visão → RN/RF/RNF → Casos de Uso → Dívida Técnica → ADR → Backlog → Código`,
em `docs/` (catálogo de regras em `docs/01-requisitos/regras-de-negocio.md`). Mudou uma regra? Atualize
`docs/06-implementacao/rastreabilidade-codigo.md` na mesma mudança.

## Regras que mais importam

- **Patente** vem só do XP, é irrevogável e segue a escala única de 19 patamares (Escudeiro 400 XP,
  cada um 4× o anterior): ver `.claude/rules/escala-de-patentes.md` e `hierarquia-td-007.md`.
  Cargos institucionais (Conselheiro, Administrador) são eixo à parte, concedidos na plataforma.
- **Migrações** Alembic têm uma única cabeça; uma migração não importa código da aplicação (cópia
  congelada dos valores). Teste a migração de dados (ver `tests/test_migracao_kyrios.py`).
- **Segredos** só por variável de ambiente (TD-001). O hook `bloquear-segredos.py` barra commit com
  segredo ou e-mail pessoal; o repositório é público.
- Testes de patente derivam limiares das constantes (`ESCUDEIRO.xp_minimo`); não cole números.

## Harness (`.claude/`)

`rules/` (instruções por caminho), `agents/domain-reviewer.md` (revisor de domínio — use depois de mexer
em `domain/`, `services/` ou `docs/`), `skills/add-cog` (novo comando), `commands/test.md` (`/test`),
`hooks/` (gates). Ao criar uma Skill, o frontmatter precisa de `author:` (hook `require-skill-author`).
