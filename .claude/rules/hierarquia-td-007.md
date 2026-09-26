---
description: hierarchy.py implementa Institucional/XP.md (TD-007 fechada) — patente irrevogável, cargos institucionais à parte
paths:
  - "src/oraculo/domain/hierarchy.py"
  - "src/oraculo/domain/permissions.py"
---

Você está mexendo na hierarquia do bot. TD-007 foi **fechada**: o Clube TYTO decidiu unificar com
`Institucional/XP.md`, e o código modela os eixos da Carta Art. VIII:

- **Patente** — os 17 patamares de `XP.md` Art. 2º (Neófito→Omni), com os valores exatos de
  `CLAN_TIERS` da plataforma TYTO.club. Vem **só** do XP e é irrevogável (Art. 1º §3º): não
  adicione caminho que rebaixe patente nem que desconte XP (Art. 1º §1º) — por isso não existe
  `/remover-xp`.
- **Cargo institucional** — `Conselheiro` e `Administrador`, flags independentes da patente,
  concedidos só por Administrador (`/cargo-institucional`), sempre auditados.

O mapa de privilégios em `permissions.py` (reunião Veterano+, evento/comunicado Oficial+,
XP/auditoria/`@everyone` Conselheiro, sistema Administrador) foi aprovado pelo Clube TYTO — mudar
um requisito é decisão do Clube, não ajuste de engenharia. Mudar um limiar de patente exige mudar
também a plataforma, para as duas nunca discordarem.
