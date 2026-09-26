# Fase 2 — Product Backlog (pós Atena v1.0)

Funcionalidades **fora do escopo** do roadmap de 60 dias. Só entram após conclusão das Sprints 1–4.

**Nota sobre F2-006 a F2-009:** diferente dos itens F2-001 a F2-005 (recursos ainda em ideação),
estes quatro já são regra institucional vigente e detalhada em `Institucional/` — o que falta é só
a implementação, não a definição. Ver [[institutional_docs_are_binding]]: o Regulamento vale a
partir da ratificação, independente de este bot já cobrir ou não a regra.

| ID | Feature | Descrição | Dependências prováveis |
|----|---------|-----------|------------------------|
| F2-001 | Loja interna (Dracmas) | Troca de Dracmas por itens e benefícios | US-405 (schema base) |
| F2-002 | Missões e desafios | Atribuição de tarefas com correção automática | XP, auditoria, permissões |
| F2-003 | Conquistas (Achievements) | Medalhas por marcos | Perfil, notificações |
| F2-004 | Painel web administrativo | Gestão web para Conselheiros | API FastAPI, autenticação |
| F2-005 | Torneios e gestão de times | Criação de chaves e guildas | Cargos, ranking, eventos |
| F2-006 | Ledger de Dracmas | **Parcialmente em pé** — `dracmas_ledger` cobre a camada Comunidade (`Aldeao`): doação, ingresso, prêmio de torneio, bônus de venda do Mercador, suspensão automática (`DRACMAS.md` §4). Falta o lado Clube: taxa mensal de manutenção, migração de saldo na filiação, e ligar `Membro.dracmas` (US-405) a este mesmo ledger em vez de ficar solto | F2-001 ainda depende da parte que falta |
| F2-007 | Camadas Comunidade/Clube | **Parcialmente em pé** — registro de Aldeão (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 2º) existe, com ingresso pago em 30.000 Dracmas (Art. 3º §1º). Falta o ingresso no Clube (70.000, Art. 4º §1º) e a migração de saldo Aldeão→Membro (Art. 4º §1º-A) | F2-006 (parte que falta) |
| F2-008 | Crédito de Mérito | Registro provisório de mérito para não-membro (`Institucional/CREDITO_DE_MERITO.md`), convertido em XP na filiação ao Clube | F2-007 |
| F2-009 | Integração com o Mercador | Conta de Comunidade do Mercador para o bônus de venda em Dracmas (`Institucional/MERCADOR.md` Art. 4º §13º–§14º), criada automaticamente no primeiro bônus se não existir | F2-006, F2-007 |

## Regra de entrada

Nenhum item F2-* inicia desenvolvimento com dívida crítica (TD-001–TD-006) aberta ou com Atena v1.0 incompleta.

## Nota sobre a hierarquia deste bot

A divergência registrada como **TD-007** em
[divida-tecnica.md](../03-analise/divida-tecnica.md#dívida-técnica-pós-baseline-não-é-do-legado-bot-xp-discord)
foi fechada: o Clube TYTO decidiu **unificar** a hierarquia do bot com `Institucional/XP.md`. A
patente agora é a escala oficial de 17 patamares (Neófito→Omni), e Conselheiro/Administrador são
cargos institucionais independentes da patente (`CARTA_INSTITUCIONAL.md` Art. VIII). `Membro` é a
filiação ao Clube, o que desbloqueia F2-007 e F2-008.
