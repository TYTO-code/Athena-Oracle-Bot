# Grafana Cloud: Atena e TYTO.club-API

Como ligar a observabilidade decidida em D15 (`docs/DECISOES.md`). Tudo aqui é feito por Dayvid,
no painel do Grafana Cloud e no Railway; o código já está pronto e fica inerte sem os tokens.

Arquivos desta pasta:

- `dashboard.json`: painel com uma linha por grupo (jobs, webhooks, infraestrutura, custo de IA,
  mensagens, projetos agregados).
- `alertas.yaml`: as regras de alerta, no formato do Prometheus (fonte de verdade das consultas).

Nenhuma métrica tem nome, e-mail, ID do Discord ou outro dado de pessoa. O rótulo mais específico
é o id do projeto.

## 1. Tokens no Railway

Gere três segredos longos e aleatórios (por exemplo `openssl rand -hex 32`) e grave só nas
variáveis do Railway:

| Serviço | Variável | Para quê |
|---|---|---|
| Atena | `ORACULO_METRICAS_TOKEN` | o Grafana lê `/metrics` da Atena |
| TYTO.club-API | `METRICS_TOKEN` | o Grafana lê `/metrics` da API |
| Atena | `ORACULO_GRAFANA_WEBHOOK_TOKEN` | o Grafana chama o webhook de alertas |
| Atena | `ORACULO_ALERTAS_DISCORD_ID` | seu ID do Discord (quem recebe a DM) |

Opcionais (já têm padrão): `ORACULO_LLM_TETO_DIARIO_USD=0.10`,
`ORACULO_LLM_ORCAMENTO_MENSAL_USD=5`, `ORACULO_LLM_ALERTA_MENSAL_USD=4`.

Antes do primeiro deploy da Atena com esta versão, rode `alembic upgrade head` (tabela
`uso_llm_diario`). Sem token, `/metrics` e `/webhooks/grafana` respondem 404.

Confira: `curl -H "Authorization: Bearer <token>" https://<atena>/metrics` devolve texto que
começa com `# HELP`.

## 2. Busca das métricas

No Grafana Cloud: **Connections → Add new connection → Metrics Endpoint**. Crie dois alvos:

| Nome do job (scrape job) | URL | Autenticação | Intervalo |
|---|---|---|---|
| `atena` | `https://<domínio da Atena>/metrics` | Bearer, `ORACULO_METRICAS_TOKEN` | 5 min |
| `tyto-api` | `https://<domínio da API>/metrics` | Bearer, `METRICS_TOKEN` | 5 min |

Use exatamente os nomes `atena` e `tyto-api`: o alerta "Serviço fora do ar" e o painel de
infraestrutura filtram por eles. Cinco minutos basta e evita manter a API acordada no Railway.

## 3. Painel

**Dashboards → New → Import**, envie `dashboard.json` e escolha a fonte Prometheus da sua conta
(normalmente `grafanacloud-<conta>-prom`) no seletor "Fonte".

## 4. Alertas por DM

1. **Alerting → Contact points → New contact point**: nome `Dayvid (Atena DM)`, integração
   **Webhook**, URL `https://<domínio da Atena>/webhooks/grafana`, método POST. Em
   "Optional Webhook settings", **Authorization Header Scheme** `Bearer` e **Credentials** com o
   `ORACULO_GRAFANA_WEBHOOK_TOKEN`. Clique em **Test**: chega uma DM da Atena em até 20 s.
2. **Alerting → Notification policies**: deixe `Dayvid (Atena DM)` como contact point padrão (ou
   crie uma política para a pasta das regras abaixo).
3. **Alerting → Alert rules → New alert rule**, uma por regra de `alertas.yaml`:
   - consulta: cole a `expr`, com a fonte Prometheus;
   - condição: **IS ABOVE 0** (a consulta só devolve valor quando há problema);
   - pending period: o `for` da regra;
   - resumo (annotation `summary`): o texto da regra, que vira a DM;
   - "Configure no data and error handling": nas regras **Job atrasado**, *No data* = **Alerting**;
     nas outras, *No data* = **OK**.

Apague a regra de um job que você deixou desligado de propósito (por exemplo, backup sem
`ORACULO_BACKUP_ENABLED=true`), senão ela avisa.

## 5. Testes de aceite

**Alerta de custo com teto baixo.** No Railway da Atena, ponha `ORACULO_LLM_TETO_DIARIO_USD=0.0001`
e faça uma pergunta aberta no `/perguntar` (uma que vá para a IA, não "meus prazos"). Na próxima
busca (até 5 min), "Custo de IA do dia" dispara e chega a DM; um segundo `/perguntar` já é recusado.
Volte o teto para `0.10`: o alerta resolve e chega a DM "✅ Resolvido".

**Alerta de job parado.** Ponha `ORACULO_COMUNICADOS_INTERVALO_SEGUNDOS=0` na Atena e reinicie. Em
cerca de 10 a 15 minutos, "Job atrasado — Atena comunicados" dispara. Volte o valor para `60`.

**Erro de webhook.** Opcional: mande alguns POSTs sem assinatura para o webhook do ClickUp da API;
com 5 ou mais na hora e mais de 5% rejeitados, o alerta dispara.

**Peso no Railway.** Compare CPU e memória no painel do Railway uma semana antes e depois. As
métricas são contadores em memória, sem biblioteca nem tarefa extra; a busca a cada 5 min custa
alguns milissegundos.

## Acesso

Só Dayvid. A guarda pretoriana pode ganhar acesso de leitura (papel *Viewer*) quando Dayvid
decidir; o painel não mostra pessoa, então dar leitura não expõe ninguém.
