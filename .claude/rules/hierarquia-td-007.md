---
description: hierarchy.py implementa Institucional/XP.md (TD-007 fechada) — patente irrevogável, cargos institucionais à parte
paths:
  - "src/oraculo/domain/hierarchy.py"
  - "src/oraculo/domain/permissions.py"
---

Você está mexendo na hierarquia do bot. TD-007 foi **fechada**: o Clube TYTO decidiu unificar com
`Institucional/XP.md`, e o código modela os eixos da Carta Art. VIII:

- **Patente** — os 19 patamares de `XP.md` Art. 2º (Neófito→Omni; o nível divino é Kyrios,
  Invictus, Dominus, Renovek, Omni). Os limiares **não são números soltos**: vêm da regra única
  `xp_minimo(n) = XP_BASE × XP_MULTIPLICADOR^(n−2)` (Escudeiro em 400 XP, cada patamar 4× o
  anterior), a mesma de `src/constants/tiers.ts` na plataforma e no backend. Para mudar a curva,
  mude só `XP_BASE`/`XP_MULTIPLICADOR` e `docs/XP.md` — e as outras duas cópias (ver
  `escala-de-patentes`). Vem **só** do XP e é irrevogável (Art. 1º §3º): não
  adicione caminho que rebaixe patente nem que desconte XP (Art. 1º §1º) — por isso não existe
  `/remover-xp`.
- **Cargo institucional** — `Conselheiro` e `Administrador`, flags independentes da patente,
  concedidos **na plataforma TYTO.club** e apenas espelhados pelo bot (RN-021, `conselheiro`/`admin`
  do documento do membro) — o bot não tem comando que os conceda ou revogue; mudanças geram
  auditoria `importacao.cargo_espelhado`.

O mapa de privilégios em `permissions.py` (reunião Veterano+, evento/comunicado Oficial+,
auditoria/`@everyone` Conselheiro, sistema Administrador) foi aprovado pelo Clube TYTO — mudar
um requisito é decisão do Clube, não ajuste de engenharia. Mudar um limiar de patente exige mudar
também a plataforma, para as duas nunca discordarem.
