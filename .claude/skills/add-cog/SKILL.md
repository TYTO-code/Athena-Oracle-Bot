---
name: add-cog
description: Use quando for adicionar um novo comando/cog ao bot Oráculo (Athena-Oracle-Bot), seguindo a camada domain/services/repositories/bot já existente e a cadeia de rastreabilidade RN/RF/UC/TD.
author: Dayvid Santana
created: 2026-09-05
---

# Adicionar um novo comando (cog) ao Bot Oráculo

Siga a mesma ordem de dentro para fora do resto do projeto — nunca comece pelo cog do Discord.

1. **Regra de negócio primeiro** — se o comando implementa uma regra nova, ela precisa de uma
   entrada em `docs/01-requisitos/regras-de-negocio.md` (RN-xxx) antes do código. Se a regra já
   existe implicitamente em `Institucional/` mas ainda não tem RN correspondente aqui, pare e
   confirme com o usuário antes de inventar uma numeração — a numeração RN/RF/UC é uma cadeia de
   rastreabilidade formal, não um rótulo solto.
2. **`domain/`** — qualquer invariante que não precise de banco/Discord (ex.: regra de hierarquia,
   validação de transição de estado) vai aqui, sem import de `discord.py` nem `fastapi`. Este
   pacote é testado sem subir bot nem API.
3. **`services/`** — orquestração e qualquer regra que precise de dado externo (repositório,
   integração). É aqui que vive a lógica de caso de uso de verdade (ver `PromocaoService`,
   `XpService` como exemplo).
4. **`repositories/`** — acesso a dado via SQLAlchemy async; nunca query direta dentro de
   `services/`.
5. **`bot/cogs/`** — o comando Discord em si (`/nome-do-comando`) só desempacota a interação,
   valida permissão por cargo (`bot/permissions.py`, `requer(...)`) e chama o serviço. Toda ação
   privilegiada nova entra em `Acao` **e** em `_POLITICA` (RN-008) — sem política, o código falha
   explicitamente, não silenciosamente.
6. **Notificação, se o comando gera evento relevante** — use `NotificacaoService` +
   `Notificacao` (ver `services/notificacao_service.py`); adicione uma fábrica de mensagem nova se
   nenhuma existente encaixa. Lembre que hoje **nenhuma fábrica preenche `destinatario_email`** —
   se este comando precisa notificar por e-mail de verdade, isso é trabalho adicional (ver
   `CanalEmail`), não algo que já funciona.
7. **Teste** — siga o padrão de `tests/test_*.py` existente: teste de domínio isolado, teste de
   serviço com repositório fake/em memória, teste de comando via fixture do bot se aplicável.
8. **Atualize a rastreabilidade** — `docs/06-implementacao/rastreabilidade-codigo.md` (RN → onde é
   aplicada → teste) e a tabela de comandos do `README.md` raiz.

Rode `make test` (ou `/test`) antes de considerar terminado — o gate de commit deste repositório já
bloqueia se a suíte não estiver verde (e exige `make setup` rodado antes, se ainda não rodou).
