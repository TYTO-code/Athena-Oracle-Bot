---
description: hierarchy.py carrega uma divergência conhecida (TD-007) com Institucional/XP.md — não resolver sozinho
paths:
  - "src/oraculo/domain/hierarchy.py"
---

Você está mexendo em `hierarchy.py`. Esta hierarquia (`Membro → Cavalaria → Lorde → Conselheiro →
Administrador`) vem de um "Documento Único de Especificação do Bot Oráculo" externo a este vault —
**não** corresponde à escala de patente de `Institucional/XP.md` Art. 2º (Neófito→Omni, 17
patamares) nem aos cargos institucionais de `Institucional/CARTA_INSTITUCIONAL.md` (Conselheiro do
Conselho Régio, Tribuno, Rex, Dux Vecturium).

Essa divergência está registrada como **TD-007** em `docs/03-analise/divida-tecnica.md` — aberta,
aguardando decisão do Clube TYTO sobre unificar as duas hierarquias ou mantê-las como eixos
deliberadamente independentes. Além disso, os limiares de XP (500/1.500/3.500) já são
autodocumentados no arquivo como "premissa a validar com o Clube TYTO", não valores oficiais.

Se a tarefa não é resolver TD-007 explicitamente, não renomeie cargos nem mude limiares aqui —
sinalize a divergência se for relevante à tarefa, não a resolva de passagem.
