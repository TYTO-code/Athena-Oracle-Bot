# Plano: Atena como gerente dos projetos

Objetivo: o Rex/administrador abre o painel ou lê o resumo semanal e, em menos de cinco minutos, sabe
o estado de todos os projetos, quem precisa de atenção e o que exige decisão dele, sem perguntar
nada a ninguém. A Atena **detecta e avisa**; motivar, cobrar e atribuir tasks continuam humanos.

Leia antes: `docs/ESTADO_ATUAL.md` (o que existe) e `docs/DECISOES.md` (onde o plano diverge do
pedido original e por quê). Resumo da arquitetura (D1): **a TYTO.club-API decide, a Atena fala.**

## Princípios

1. Determinístico por padrão: datas, contagens, status e permissões são código comum.
2. LLM só na conversa livre do `/perguntar`. Detecção, alertas, lembretes, painel, resumo e
   onboarding nunca chamam LLM.
3. Comandos fixos antes da IA.
4. Fonte única: site/API para identidade, cargos, vínculos e regras; ClickUp para tasks. O gerente
   guarda só cache e histórico próprio.
5. Texto automático só de template editável.
6. Webhook antes de polling; varredura no máximo diária.
7. Hierarquia aplicada no servidor, antes de qualquer saída. Na dúvida, mostra menos.
8. Somente leitura no ClickUp e nos dados do site (cargos, XP, Dracmas, vínculos).

## Componentes

```
ClickUp ──webhook──▶ TYTO.club-API ──────────────────────────────▶ site (/gerente, painel)
                     ├ domain/gerente/   regras puras + permissão      GET /api/gerente/*
                     ├ gerente_tasks     snapshot das tasks            (filtrado por cargo)
                     ├ jobs diários      reconciliação, alertas, resumo
                     └ gerente_outbox ──rota interna──▶ Atena ──DM──▶ Discord
                                                         └ /meus-prazos, /status… (sem LLM)
                                                         └ /perguntar (LLM, contexto filtrado)
```

## Fases

Cada fase termina com uma parada para revisão do Dayvid. Cada módulo tem interruptor de
configuração (`gerente_config`) para ligar e desligar sem deploy.

### Fase 0: diagnóstico (este PR)

`ESTADO_ATUAL.md`, `DECISOES.md`, este plano.

### Fase 1: dados e permissão (sem enviar nada)

Na API:

1. `src/domain/gerente/config.ts`: limiares padrão, sobrescrita por projeto, dias corridos ou
   úteis, silêncio noturno, interruptores por módulo.
2. `src/domain/gerente/rules.ts`: motor puro. Entra o estado (tasks, membros, missões, agora),
   saem ações (`lembrete`, `alerta_pessoa`, `alerta_projeto`, `destaque_missao`, `marca_painel`),
   com id determinístico para não repetir.
3. `src/domain/gerente/permissions.ts`: `canView(viewer, recurso)` com a matriz da seção 6 do
   pedido, testada célula a célula.
4. Snapshot das tasks: ampliar eventos do webhook (D7), gravar `gerente_tasks`, reconciliação
   diária pela API do ClickUp, relatório de responsáveis sem vínculo.

### Fase 2: modo sombra

Job diário roda o motor e grava `gerente_shadow/{data}` com o que **teria** sido enviado. Só o
administrador vê (painel e DM única com o relatório). Rodar ao menos uma semana para calibrar.

### Fase 3: lembretes e alertas de verdade

`gerente_outbox` + consumidor na Atena (rota interna, DM, silêncio 22h–8h, confirmação de
entrega). Liga M2 (prazos −3/0/+1), M3 (pessoa parada para Rex/Conselheiro) e M4 (projeto parado
para o líder).

### Fase 4: painel no site

Página `/gerente` com visões admin → Conselheiro/Rex do reino → líder → membro. Lê
`GET /api/gerente/*` (filtrado no servidor), mostra a hora da última sincronização, nunca chama
o ClickUp ao carregar.

### Fase 5: resumo semanal e comunidade

M7 (segunda de manhã, texto puro copiável) e M5 (destaque de missões abertas sem ninguém, tom de
convite, num canal do Discord).

### Fase 6: conversa e onboarding

Na Atena: `/meus-prazos`, `/minhas-tasks`, `/status <projeto>`, `/missoes` lendo a API (sem LLM);
correção do vínculo de projetos do `/perguntar` (D4); cache de respostas e limite diário. M9:
boas-vindas por template ao entrar num projeto, com o `.md` do projeto mantido pelo líder.

## Situação em 2026-11-14

Todas as fases estão implementadas em branches, sem merge e sem deploy. Tudo desligado por padrão.

| Fase | Onde | Situação |
|---|---|---|
| 1. Dados e permissão | API `src/domain/gerente/` (config, rules, permissions, clickupTasks) | Pronta, com testes |
| 2. Modo sombra | API `shadow.ts`, `GerenteService`, `gerente_shadow` | Pronta; ligado por padrão quando o gerente liga |
| 3. Lembretes e alertas | API `outbox.ts` + rotas internas; Atena `cogs/gerente.py` (entrega, silêncio 22h–8h) | Pronta |
| 4. Painel no site | Site `/gerente` (`src/pages/Gerente.tsx`), API `GET /api/gerente/painel` | Pronta |
| 5. Resumo e missões | API `summary.ts` (segunda 8h), destaque de missões no canal | Pronta |
| 6. Conversa e onboarding | Atena: comandos fixos, roteador, cache, correção D4; API `onboarding.ts` | Pronta |
| Observabilidade (D15) | `/metrics` nas duas, painel e alertas em `observabilidade/grafana/` | Pronta; falta ligar no Grafana |

Para ligar, na ordem: deploy da API e `GERENTE_ENABLED=true` (sobe em modo sombra), migração e
deploy da Atena com `ORACULO_TYTO_API_URL`/`ORACULO_TYTO_API_SERVICE_KEY`, deploy do site, uma
semana de sombra, e então os módulos em `gerente_config/default` (TYTO.club-API `docs/GERENTE.md`).

## Matriz de permissão (alvo da fase 1)

| Informação | Admin | Conselheiro/Rex | Líder | Membro |
|---|---|---|---|---|
| Números de todos os projetos | Sim | Só do reino | Não | Não |
| Números do próprio projeto | Sim | Sim, se do reino | Sim | Resumo público |
| Carga de tasks de cada membro | Sim | Sim (reino) | Sim (projeto) | Não |
| Quem está parado e há quanto tempo | Sim | Sim (reino) | **Não** | Não |
| Próprias tasks e prazos | Sim | Sim | Sim | Sim |

## Limiares padrão (configuráveis)

| Regra | Condição | Ação |
|---|---|---|
| Pessoa: atenção | 3 dias sem atividade em task atribuída | Marca no painel |
| Pessoa: alerta | 7 dias | DM para admin e Conselheiro/Rex do reino |
| Pessoa: risco | 14 dias | Novo alerta, marcado como risco |
| Prazo | 3 dias antes, no dia, 1 dia depois | DM ao responsável |
| Projeto parado | 7 dias sem task criada, movida ou concluída | DM ao líder, marca no painel |
| Missão abandonada | 14 dias aberta sem ninguém | Entra no destaque |

Quem não tem task atribuída nunca está parado. Missões nunca geram pessoa parada. Cada alerta sai
uma vez por mudança de nível e zera com atividade nova.

## Critérios de aceite

Os da seção 15 do pedido, com "Rex" lido como "admin" para a visão global (D2).
