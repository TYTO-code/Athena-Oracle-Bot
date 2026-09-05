---
description: Roda a suíte de testes de Athena-Oracle-Bot e resume o resultado
---

Rode `make test` neste repositório (146 testes, pytest). Se passar, diga em uma frase que está
tudo verde. Se falhar, mostre só o(s) teste(s) que falharam e a asserção — não cole a saída
completa do pytest. Se o erro for de ambiente (venv ausente, dependência faltando), diga isso
claramente e sugira `make setup` em vez de tentar diagnosticar o teste em si.
