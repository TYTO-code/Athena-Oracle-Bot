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

Itens da Fase 2: loja de Dracmas, missões, conquistas, painel web administrativo, torneios e gestão de times. Ver [fase-2.md](../05-roadmap/fase-2.md).

## Stakeholders

| Papel | Interesse |
|-------|-----------|
| Membros | Consultar perfil, ranking, presença em eventos |
| Cavalaria+ | Criar e gerir reuniões |
| Lordes+ | Criar e gerir eventos oficiais |
| Conselheiros+ | Conceder/remover XP e auditar histórico |
| Administradores | Segurança, logs, backup, conformidade hierárquica |

## Critérios de sucesso (alto nível)

- Nenhuma movimentação crítica sem auditoria.
- Promoções sempre removem cargos TYTO anteriores antes de atribuir o novo.
- Permissões de comando validadas pelo cargo.
- Integração Google Agenda operacional para reuniões e eventos.
