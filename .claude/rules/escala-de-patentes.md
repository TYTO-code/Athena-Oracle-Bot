---
description: A escala de patentes (XP) tem uma regra única e quatro cópias — mude todas juntas
paths:
  - "src/oraculo/domain/hierarchy.py"
  - "tests/test_hierarquia.py"
  - "tests/test_promocao.py"
  - "tests/test_importacao.py"
---

Você está mexendo na **escala de patentes**. Ela vive em quatro lugares e **nunca pode divergir**
(já divergiu uma vez: o backend gravava nomes que o site não conhecia):

| Cópia | Onde |
|---|---|
| Documento (fonte da regra) | `TYTO.club/docs/XP.md` Art. 2º |
| Site | `TYTO.club/src/constants/tiers.ts` — `TIER_BASE_XP`, `TIER_MULTIPLIER` |
| Backend | `TYTO.club-API/src/constants/tiers.ts` — as mesmas constantes |
| Bot Atena | `Athena-Oracle-Bot/src/oraculo/domain/hierarchy.py` — `XP_BASE`, `XP_MULTIPLICADOR` |
| Elegibilidade | `Elections-Services/.../MembroDocumentRules.java` — só nomes e ordem (`PATENTES`) |

**A regra:** Neófito começa em 0 XP; Escudeiro exige 400; cada patamar seguinte exige exatamente
4× o anterior — `minXp(n) = 400 × 4^(n−2)`, n ≥ 2. Nunca escreva um limiar como número solto: derive
da constante-base.

| # | Patente | XP mínimo |
|---|---|---:|
| 1 | Neófito | 0 |
| 2 | Escudeiro | 400 |
| 3 | Armeiro | 1.600 |
| 4 | Veterano | 6.400 |
| 5 | Mestre de Armas | 25.600 |
| 6 | Desafiante Legionário | 102.400 |
| 7 | Oficial | 409.600 |
| 8 | Centurião | 1.638.400 |
| 9 | Comandante | 6.553.600 |
| 10 | Dom | 26.214.400 |
| 11 | Lorde | 104.857.600 |
| 12 | Senhor da Guerra | 419.430.400 |
| 13 | Suserano | 1.677.721.600 |
| 14 | Monarca | 6.710.886.400 |
| 15 | Kyrios | 26.843.545.600 |
| 16 | Invictus | 107.374.182.400 |
| 17 | Dominus | 429.496.729.600 |
| 18 | Renovek | 1.717.986.918.400 |
| 19 | Omni | 6.871.947.673.600 |

**Nome oficial** é o da tabela. Apelidos antigos (`Iniciante`→Neófito, `Desafiante`→Desafiante
Legionário, `Comandante de Linha`→Comandante, `Elite`→Dom, `Barão`→Lorde, `Dominador`→Kyrios) só
existem para ler dados antigos; nunca os grave.

**Irrevogável (`XP.md` Art. 1º §3º):** a patente de um membro é a *maior* entre a do XP e a já
registrada. Mudar a escala vale só dali em diante e **nunca rebaixa ninguém** — não crie caminho que
grave uma patente menor que a registrada, nem que desconte XP.

**Neste bot:** o `PromocaoService` só promove (nunca rebaixa) e a patente fica em `membros.patente_slug`.
O slug `dominador` ainda resolve para Kyrios (`_SLUGS_LEGADOS`) até a migração `d4e5f6a7b8c9` rodar.
Os testes derivam os limiares das constantes (`ESCUDEIRO.xp_minimo`…); mantenha assim.

**Para mudar a escala** (nova base, novo título, nova ordem): altere as cópias acima **na mesma
mudança**, atualize `docs/XP.md` e os testes que fixam os valores, e planeje a migração dos dados já
gravados (`TYTO.club-API`: `npm run migrar-patentes`, que simula por padrão). A nova escala também
exige ratificação do Dominatium.
