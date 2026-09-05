# Glossário — Domínio Clube TYTO / Bot Oráculo

| Termo | Definição |
|-------|-----------|
| Atena v1.0 | Linha de requisitos / versão do sistema especificada neste pacote |
| Bot Oráculo | Sistema de gestão operacional do Clube TYTO via Discord e WhatsApp — implementação do **bot Atena** regido normativamente por `Institucional/SERVIDOR_DISCORD.md` |
| Cargo de hierarquia (Bot Oráculo) | Papel operacional Membro/Cavalaria/Lorde/Conselheiro/Administrador, definido pelo "Documento Único de Especificação do Bot Oráculo" (fonte externa a este repositório); apenas um ativo por membro (RN-001). **Não é o mesmo eixo** que a escala de patentes de `Institucional/XP.md` Art. 2º (Neófito→Omni, 17 patamares) nem os cargos institucionais de `Institucional/CARTA_INSTITUCIONAL.md` (Conselheiro, Tribuno, Dux Vecturium, Rex) — a relação entre os dois vocabulários ainda não foi reconciliada, ver nota em [fase-2.md](05-roadmap/fase-2.md) |
| Cavalaria+ | Cargos iguais ou superiores à Cavalaria; podem criar reuniões (RN-006) |
| Conselheiro+ | Cargos iguais ou superiores a Conselheiro (hierarquia deste bot); podem gerir XP (RN-004) — não confundir com o cargo eletivo "Conselheiro" (Conselho Régio) de `Institucional/CARTA_INSTITUCIONAL.md` Art. II, que é institucional, não operacional |
| Dracmas | Moeda interna da TYTO, **já regulamentada** em `Institucional/DRACMAS.md` — saldo único por pessoa, movimentado por taxa mensal, missões, ingresso em Comunidade/Clube, bônus de venda do Mercador, entre outras origens listadas em `DRACMAS.md` §2. A regra já é vigente independente da implementação; a Fase 2 deste bot ([fase-2.md](05-roadmap/fase-2.md)) é só quando o Bot Oráculo passa a materializá-la — hoje esse saldo não existe em código nenhum |
| Aldeão / Comunidade | Camada intermediária de acesso entre Visitante e Clube (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 1º) — registro feito integralmente pelo Atena, com saldo de Dracmas e histórico de Crédito de Mérito, sem conta na plataforma nem "cargo de hierarquia" deste bot |
| Clube | Filiação plena — o "membro" de toda a Carta Institucional (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 1º §3º); é o universo a que este bot hoje chama de "Membro" e a hierarquia Cavalaria→Administrador se aplica |
| Crédito de Mérito | Registro provisório de mérito para quem ainda não é membro (`Institucional/CREDITO_DE_MERITO.md`), convertido em XP na filiação — fora do escopo atual deste bot, ver Fase 2 |
| Mercador | Único papel institucional aberto a quem não é membro do Clube (`Institucional/MERCADOR.md`) — não usa a hierarquia de cargos deste bot; recebe comissão em dinheiro real e, desde `MERCADOR.md` Art. 4º §13º–§14º, também um bônus em Dracmas creditado à própria conta de Comunidade, que o Atena deveria gerenciar |
| Lorde+ | Cargos iguais ou superiores a Lorde; podem criar eventos oficiais (RN-007) |
| Movimentação crítica | Alteração de XP, promoção, cargo ou evento sensível; não pode ser apagada fisicamente (RN-010) |
| RSVP | Confirmação de presença (confirmar / recusar / pendente) |
| Soft-delete | Exclusão lógica preservando histórico |
| TYTO | Clube / organização dona das regras de hierarquia |
| XP | Pontos de experiência usados para progressão e ranking neste bot — distinto, mas com o mesmo nome, do XP de patente de `Institucional/XP.md` |
| Bot-XP-Discord | Repositório legado analisado; fonte da dívida técnica TD-* |
