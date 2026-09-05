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
| F2-006 | Ledger de Dracmas | Saldo único por pessoa e as movimentações oficiais de `Institucional/DRACMAS.md` §2 (taxa mensal, missão, doação, ingresso de camada, bônus de venda do Mercador etc.); suspensão automática por saldo negativo (`DRACMAS.md` §4) | Schema base, F2-001 depende deste |
| F2-007 | Camadas Comunidade/Clube | Registro de Aldeão (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 2º) — hoje inteiramente ausente: este bot só conhece "Membro" (= Clube), sem a camada intermediária de Comunidade nem o ingresso pago em Dracmas (30.000/70.000) | F2-006 |
| F2-008 | Crédito de Mérito | Registro provisório de mérito para não-membro (`Institucional/CREDITO_DE_MERITO.md`), convertido em XP na filiação ao Clube | F2-007 |
| F2-009 | Integração com o Mercador | Conta de Comunidade do Mercador para o bônus de venda em Dracmas (`Institucional/MERCADOR.md` Art. 4º §13º–§14º), criada automaticamente no primeiro bônus se não existir | F2-006, F2-007 |

## Regra de entrada

Nenhum item F2-* inicia desenvolvimento com dívida crítica (TD-001–TD-006) aberta ou com Atena v1.0 incompleta.

## Nota sobre a hierarquia de cargos deste bot

Registrada formalmente como **TD-007** em
[divida-tecnica.md](../03-analise/divida-tecnica.md#dívida-técnica-pós-baseline-não-é-do-legado-bot-xp-discord):
a hierarquia Membro/Cavalaria/Lorde/Conselheiro/Administrador vem do "Documento Único de
Especificação do Bot Oráculo", fonte externa a este repositório — não corresponde à escala de
patentes de `Institucional/XP.md` Art. 2º (Neófito→Omni) nem aos cargos institucionais de
`Institucional/CARTA_INSTITUCIONAL.md` (Conselheiro, Tribuno, Dux Vecturium, Rex). Nenhum item deste
backlog resolve essa divergência sozinho — TD-007 fica aberta até decisão explícita do Clube TYTO, e
bloqueia especificamente F2-007 e F2-008 abaixo até lá.
