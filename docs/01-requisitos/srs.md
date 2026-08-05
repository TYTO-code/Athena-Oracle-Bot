# Software Requirements Specification (SRS) — Atena v1.0

Documento adaptado da estrutura **IEEE 830**, derivado do Documento Único de Especificação do Bot Oráculo (Clube TYTO).

| Campo | Valor |
|-------|-------|
| Sistema | Bot Oráculo |
| Versão | Atena v1.0 |
| Organização | Clube TYTO |
| Status | Baseline de especificação |

## 1. Introdução

### 1.1 Propósito

Definir os requisitos do sistema Bot Oráculo para desenvolvimento, validação e rastreabilidade com regras de negócio, casos de uso e backlog.

### 1.2 Escopo

O sistema centraliza a gestão operacional do Clube TYTO, automatizando processos administrativos e garantindo o cumprimento das regras hierárquicas via Discord e WhatsApp.

**Inclui:** autenticação multi-canal, perfil/XP/ranking, promoções e cargos, reuniões/eventos, RSVP, notificações, Google Agenda, logs e auditoria.

**Exclui (Fase 2):** loja de Dracmas, missões, conquistas, painel web, torneios.

### 1.3 Definições

Ver [glossario.md](../glossario.md).

### 1.4 Referências

- Catálogo de regras de negócio: [regras-de-negocio.md](regras-de-negocio.md)
- Catálogo RF: [requisitos-funcionais.md](requisitos-funcionais.md)
- Catálogo RNF: [requisitos-nao-funcionais.md](requisitos-nao-funcionais.md)
- Casos de uso: [../02-casos-de-uso/casos-de-uso.md](../02-casos-de-uso/casos-de-uso.md)
- Dívida técnica (legado Bot-XP-Discord): [../03-analise/divida-tecnica.md](../03-analise/divida-tecnica.md)
- ADR de stack: [../04-arquitetura/adr-001-stack-tecnica.md](../04-arquitetura/adr-001-stack-tecnica.md)

### 1.5 Visão geral do documento

Seção 2 descreve o produto; seção 3 aponta os requisitos detalhados nos catálogos; seção 4 cobre restrições e premissas.

## 2. Descrição geral

### 2.1 Perspectiva do produto

Bot de gestão operacional integrado a Discord e WhatsApp, com API/webhooks (ex.: ClickUp), persistência relacional, cache e Google Agenda.

### 2.2 Funções do produto (resumo)

| Área | Funções |
|------|---------|
| Identidade | Autenticar usuários Discord/WhatsApp |
| XP e hierarquia | Perfil, ranking, concessão/remoção de XP, promoção automática, cargo único |
| Agenda | Reuniões, eventos, RSVP, sync Google Agenda |
| Comunicação | Notificações Discord e e-mail |
| Governança | Logs, auditoria, backup, permissões por cargo |

### 2.3 Características dos usuários

Membros, Cavalaria+, Lordes+, Conselheiros+ e Administradores (ver visão do produto).

### 2.4 Restrições

- Credenciais e segredos apenas via variáveis de ambiente.
- Nenhuma movimentação crítica com exclusão física (soft-delete / histórico imutável).
- Validação de assinatura HMAC em webhooks externos.
- Hierarquia real TYTO (não níveis arbitrários do legado).

### 2.5 Premissas e dependências

- Servidor(es) Discord do Clube TYTO e papéis (roles) alinhados à hierarquia.
- Conta Google com API Calendar e OAuth2.
- Infraestrutura Docker-compatible (Render / Railway ou equivalente).
- Correção da dívida técnica do repositório legado **Bot-XP-Discord** antes de novas features (Sprint 1).

## 3. Requisitos específicos

Requisitos detalhados e versionados nos catálogos:

| Tipo | Documento |
|------|-----------|
| Regras de negócio | [regras-de-negocio.md](regras-de-negocio.md) |
| Funcionais | [requisitos-funcionais.md](requisitos-funcionais.md) |
| Não funcionais | [requisitos-nao-funcionais.md](requisitos-nao-funcionais.md) |
| Casos de uso | [../02-casos-de-uso/casos-de-uso.md](../02-casos-de-uso/casos-de-uso.md) |

### 3.1 Matriz de rastreabilidade (resumo)

| RN | RF / UC relacionados |
|----|----------------------|
| RN-001 | RF-005, RF-006, UC-003 |
| RN-002, RN-003 | RF-005, RF-006, UC-003 |
| RN-004, RN-005 | RF-003, RF-012, UC-001 |
| RN-006, RN-007 | RF-007, RF-008, UC-004, UC-005 |
| RN-008 | Todos os comandos privilegiados |
| RN-009 | RF-011 |
| RN-010 | RF-012 |

## 4. Apêndices

- Roadmap: [../05-roadmap/backlog-sprints.md](../05-roadmap/backlog-sprints.md)
- Fase 2: [../05-roadmap/fase-2.md](../05-roadmap/fase-2.md)
