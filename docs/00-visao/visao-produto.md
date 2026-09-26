# Visão do Produto — Bot Oráculo

| Campo | Valor |
|-------|-------|
| Produto | Bot Oráculo |
| Linha / versão de requisitos | Atena v1.0 |
| Organização | Clube TYTO |
| Status | Especificado |
| Canais | Discord, WhatsApp |

## Problema

A gestão operacional do Clube TYTO (hierarquia, XP, promoções, reuniões, eventos e auditoria) está fragmentada e sujeita a inconsistências quando executada manualmente ou por bots sem regras de domínio formadas.

## Solução

Centralizar a gestão operacional do Clube TYTO em um bot multi-canal que automatiza processos administrativos e garante o cumprimento das regras hierárquicas da organização via Discord e WhatsApp.

## Objetivos

1. Garantir **cargo único** de hierarquia por membro (RN-001).
2. Automatizar **progressão por XP** com promoção, remoção do cargo anterior e registro em log.
3. Controlar e auditar toda movimentação de XP (autor, membro, quantidade, motivo, data/hora).
4. Restringir criação de reuniões e eventos oficiais por cargo.
5. Integrar agendas com Google Agenda e preservar histórico crítico (sem exclusão física).

## Fora de escopo (Atena v1.0)

Itens da Fase 2: loja de Dracmas, missões, conquistas, painel web administrativo, torneios e gestão
de times, ledger de Dracmas, camadas de Comunidade/Clube, Crédito de Mérito e integração com o
Mercador. Ver [fase-2.md](../05-roadmap/fase-2.md) — os quatro últimos já são regra institucional
vigente (`Institucional/DRACMAS.md`, `COMUNIDADE_E_CLUBE.md`, `CREDITO_DE_MERITO.md`,
`MERCADOR.md`), só a implementação é que fica para depois.

## Relação com `Institucional/SERVIDOR_DISCORD.md`

Este produto **é** o bot Atena regido por `Institucional/SERVIDOR_DISCORD.md` — identidade única
por pessoa (Art. 1º), canais por função (Art. 3º) e as ferramentas de consulta de saldo/extrato/
ranking (Art. 4º) descritas ali valem para este sistema. Onde este pacote de requisitos e aquele
Regulamento divergirem, o Regulamento vence (`Institucional/` é a lei institucional vigente,
independente do estado da implementação).

## Stakeholders

| Papel | Interesse |
|-------|-----------|
| Membros (qualquer patente) | Consultar perfil, ranking, presença em eventos |
| Patente Veterano+ | Criar e gerir reuniões |
| Patente Oficial+ | Criar e gerir eventos oficiais e comunicados |
| Conselheiros (cargo institucional) | Conceder XP, auditar histórico, `@everyone` |
| Administradores (cargo institucional) | Segurança, logs, backup, cargos institucionais |

## Critérios de sucesso (alto nível)

- Nenhuma movimentação crítica sem auditoria.
- Promoções sempre removem cargos TYTO anteriores antes de atribuir o novo.
- Permissões de comando validadas pelo cargo.
- Integração Google Agenda operacional para reuniões e eventos.
