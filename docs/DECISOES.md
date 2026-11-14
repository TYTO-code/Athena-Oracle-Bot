# Decisões do "gerente dos projetos"

Registro das escolhas feitas ao adaptar o pedido ("Atena como gerente operacional dos projetos") ao
que já existe na plataforma. Regra seguida: **onde o pedido contradiz o código ou uma decisão já
tomada, vale o que existe**, e a divergência fica registrada aqui. Itens marcados **[pendente]**
esperam a palavra do Dayvid; até lá vale a opção conservadora indicada.

## D1. Dados e regras moram na TYTO.club-API; a Atena é o canal

**Pedido:** a Atena recebe webhooks do ClickUp, guarda cache próprio (Postgres) e roda o motor de
regras e a API do painel.

**O que existe:** a `TYTO.club-API` já é dona do ClickUp de cada projeto (token e segredo do webhook
cifrados com `CLICKUP_ENCRYPTION_KEY`, webhook filtrado pela lista, idempotência em
`clickup_events`), de `project_stats.members`, dos cargos e das missões. Decisão de 2026-10 é
"mono-serviço por ora". O Postgres da Atena ficou parado por custo.

**Decisão:** o motor de regras, o cache de tasks, os registros de alerta e os endpoints do painel
ficam na API (TypeScript, `src/domain/gerente/` puro e testado, coleções `gerente_*` no
Firestore). A Atena continua sendo a voz no Discord: entrega as DMs que a API decidir, responde aos
comandos fixos lendo a API e mantém o `/perguntar`.

**Por quê:** uma só cópia do token do ClickUp (nunca sai da API), uma só fonte de verdade de
vínculos e cargos, nenhuma regra duplicada em duas linguagens, nenhum banco novo, e o painel do
site já fala com a API. A Atena continua somente leitura (RN-021).

## D2. "Rex vê tudo": visão global = `admin`

**Pedido:** Rex é a autoridade máxima e vê todos os projetos de todos os reinos.

**O que existe:** no site, Rex (`users.dominatium`) é **por reino** ("voz do reino no
Dominatium") e o Conselheiro é a autoridade máxima do reino. Quem vê tudo hoje na API é
`users.admin == true` (`requireAdmin`).

**Decisão conservadora:** visão global só para `admin`. Rex e Conselheiro veem o próprio reino.
**[pendente]** confirmar se Rex de um reino deve ver os outros reinos.

## D3. Reino do projeto = reino do líder técnico

Regra já vigente (`EMPRESAS.md` Art. 7º, usada em `ProjectLeaderChangeService`): o reino do
projeto é o `countryCode` do líder. O reino da pessoa é o `countryCode` dela.

## D4. Vínculo pessoa↔projeto vem de `project_stats.members`

O `/perguntar` hoje procura `users/{uid}/projetos`, que o site não escreve (ver
`ESTADO_ATUAL.md` §6). O gerente usa `project_stats.members`. Corrigir o `/perguntar` entra na
fase 6. Papéis do site: `leader`, `partner`, `contributor`, `seller`. "Líder" no gerente =
`leader`; `partner` (sócio) recebe a visão de líder **[pendente]**, por ora fica com a de membro.

## D5. Identidade ClickUp → site reaproveita o que existe

**Pedido:** tabela `identity_link` com e-mail como chave.

**Decisão:** usar `users.clickupUserId` (gravado só pela API) e, sem ele, `users.clickupEmail`
apenas quando for único entre os membros do projeto, como já faz o pagamento de missões. Nunca por
nome. Responsáveis sem correspondência entram num relatório para o líder. Nenhuma tabela nova de
identidade.

## D6. Quem é o responsável por uma task

**O que existe:** no fluxo de missões, a task não é pré-atribuída; o crédito vai para quem a
concluiu. No ClickUp, porém, toda task tem `assignees`.

**Decisão:** para lembretes e "pessoa parada", o responsável é o `assignee` do ClickUp. Task sem
assignee não gera lembrete nem pessoa parada (conta só para "projeto parado"). Isso não muda nada
no pagamento de missões.

## D7. Mais eventos no webhook da API, sem novo webhook

O webhook atual só assina `taskStatusUpdated` e `taskDeleted` e descarta tasks fora de missões.
O gerente precisa também de `taskCreated`, `taskUpdated`, `taskAssigneeUpdated`,
`taskDueDateUpdated`, `taskCommentPosted` e `taskMoved`. Decisão: ampliar a lista de eventos do
mesmo webhook e gravar um snapshot de **toda** task da lista (`gerente_tasks`), mantendo o
processamento de missões como está. Projetos já conectados precisam re-registrar o webhook (job de
migração na API ou o líder reconectar). A reconciliação diária usa a API do ClickUp com o token já
guardado.

## D8. Webhook do ClickUp na Atena fica inerte

O `/webhooks/clickup` da Atena usa um segredo global e não é chamado por ninguém. Não será usado.
Ele deixa de ser exigido em `validate_for_production` quando a fase 1 entrar.

## D9. Sem banco novo; registros no Firestore com id determinístico

`task_snapshot`, `member_activity`, `project_health`, `alert_log`, `reminder_log` e `config` do
pedido viram coleções `gerente_*` gravadas só pela API (regras do Firestore negam o cliente). Alerta
e lembrete usam id determinístico (`{tipo}_{alvo}_{nível ou marco}`), como a fila `mail`: o mesmo
lembrete não é criado duas vezes.

## D10. Fuso horário do destinatário

Não existe campo de fuso. Decisão conservadora: fuso padrão por reino (`countryCode`), com
`America/Sao_Paulo` quando faltar. **[pendente]** criar um campo de fuso no perfil.

## D11. Pausa declarada (férias, licença)

Não existe no site. Fica como pendência; a regra pura já aceita uma pausa opcional, que entra quando
o campo existir. **[pendente]** onde e por quem a pausa é marcada.

## D12. Entrega das DMs

A API decide o que enviar e grava em `gerente_outbox`; a Atena busca a fila por rota interna
(`requireServiceKey`) a cada poucos minutos, envia por DM (respeitando 22h–8h no fuso do
destinatário) e confirma. O token do bot fica só na Atena. Canal futuro (e-mail) = outro
consumidor da mesma fila; a API já tem a fila de e-mail (`mail/`).

## D13. Taxa mensal

O pedido diz "quem zera é removido". No site, saldo negativo **suspende** a conta
(`negative_balance`). A Atena não mexe nisso; registro só para corrigir o entendimento.

## D14. LLM

O `/perguntar` já usa o modelo mais barato (`claude-haiku-4-5`) com regulamento em cache e limite de
10 por hora. Falta: roteador de comandos fixos na frente, cache de respostas repetidas e limite
diário (fase 6). Nenhum módulo novo chama LLM.

## D15. Observabilidade com Grafana Cloud

Pedido complementar de 2026-11-14 (Grafana na Atena). O que vale:

- **Coleta por `/metrics` (Prometheus), buscado pelo Grafana Cloud**, não OpenTelemetry. A Atena
  já tinha `/metrics` protegido por `ORACULO_METRICAS_TOKEN`; a API ganha o mesmo, com
  `METRICS_TOKEN`. O Grafana Cloud busca o endpoint pela integração "Metrics Endpoint" (sem agente
  no Railway). Por que custa menos: as métricas são contadores em memória, sem biblioteca nova, sem
  exportador rodando em segundo plano e sem conexão aberta; o custo só existe no instante da busca.
  OpenTelemetry pediria o SDK e um exportador (mais memória e uma tarefa periódica empurrando dados)
  para os mesmos números. Intervalo de busca sugerido: 5 minutos (a API pode dormir no Railway, e
  uma busca a cada minuto a manteria acordada).
- **CPU e memória** saem do próprio processo (`process_cpu_seconds_total`,
  `process_resident_memory_bytes`), que é o que o Railway cobra. O painel do Railway segue como
  fonte oficial; puxar a API do Railway exigiria um token de conta guardado em mais um lugar.
- **Custo do Claude**: cada resposta é contada (tokens de entrada, saída e cache) e o custo estimado
  pela tabela pública de preços (`domain/custo_llm.py`; modelo desconhecido = o preço mais alto).
  Fica em contadores e numa tabela agregada por dia e modelo (`uso_llm_diario`, sem pessoa), que
  sobrevive a reinício. **Teto de US$ 0,10 por dia, definido por Dayvid**: chegou nele, o
  `/perguntar` recusa até o dia seguinte (UTC) e indica os comandos fixos. Orçamento de US$ 5 no
  mês recusa da mesma forma; o alerta do mês dispara em US$ 4. Tudo ajustável por variável de
  ambiente (`ORACULO_LLM_TETO_DIARIO_USD`, `ORACULO_LLM_ORCAMENTO_MENSAL_USD`,
  `ORACULO_LLM_ALERTA_MENSAL_USD`), e o `/metrics` publica os tetos, então o alerta do Grafana
  compara com o valor configurado. Se não der para ler o uso do dia, recusa (lado seguro).
- **Nenhuma pessoa nas métricas**: só existem os rótulos `rotina` (o nome do job; `job` é reservado pelo Prometheus para o alvo da busca), `resultado`, `tipo`, `modelo`,
  `motivo`, `projeto`, `destino` e `evento`; valor que pareça ID do Discord ou e-mail vira
  `descartado` (`observabilidade.py`, com teste). O rótulo mais específico é o id do projeto.
- **Alertas** (custo do dia, custo do mês, job que não rodou, erro de webhook acima de 5% na hora)
  vão só para Dayvid, por DM da Atena: o contact point do Grafana chama `POST /webhooks/grafana`
  (Bearer `ORACULO_GRAFANA_WEBHOOK_TOKEN`; sem token, 404), a rota põe um texto curto (nome e
  resumo da regra, sem URL nem valor bruto) numa caixa em memória e o cog `alertas` manda a DM para
  `ORACULO_ALERTAS_DISCORD_ID` a cada 20 s. Discord, e não e-mail, porque é o canal que a Atena já
  usa e o que o pedido indica. As métricas são em memória, então o alerta de job atrasado usa
  `max_over_time(...[2d])` para lembrar o último horário depois de um reinício; backup e rodada
  diária do gerente usam horários gravados no banco. Regras, painel e passo a passo em
  `observabilidade/grafana/`.
- **Acesso ao Grafana**: só Dayvid. A guarda pretoriana não recebe acesso até Dayvid decidir
  (opção conservadora). **[pergunta em aberto]**

## Em aberto (do pedido, seção 16)

- Limiares de projeto parado (7 dias) e missão abandonada (14 dias): ficam como padrão
  configurável, a calibrar no modo sombra.
- Dias corridos ou úteis: padrão corridos, configurável.
- Canal do Discord do destaque de missões e horário do resumo semanal: **[pendente]**.
- Conselheiro recebe também o alerta de projeto parado: padrão **não** (só o líder; o projeto
  aparece marcado no painel do Conselheiro).
- E-mail ou WhatsApp no futuro: a fila (D12) já permite outro consumidor.
- Ações com aprovação humana no futuro: o motor devolve "ações" puras; uma ação nova com aprovação
  entra como outro tipo, sem execução automática.
