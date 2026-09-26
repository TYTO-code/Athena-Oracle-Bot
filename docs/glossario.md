# Glossário — Domínio Clube TYTO / Bot Oráculo

| Termo | Definição |
|-------|-----------|
| Atena v1.0 | Linha de requisitos / versão do sistema especificada neste pacote |
| Bot Oráculo | Sistema de gestão operacional do Clube TYTO via Discord e WhatsApp — implementação do **bot Atena** regido normativamente por `Institucional/SERVIDOR_DISCORD.md` |
| Patente | Posição na escala oficial de `Institucional/XP.md` Art. 2º (17 patamares, Neófito→Omni), determinada **só** pelo XP e irrevogável (Art. 1º §3º); apenas uma ativa por membro (RN-001). Substituiu a hierarquia Membro/Cavalaria/Lorde/Conselheiro/Administrador ao fechar TD-007 |
| Cargo institucional | Conselheiro (eleito, Carta Art. III/IV) ou Administrador (governança técnica do bot) — eixo independente da patente (Carta Art. VIII), concedido por Administrador via `/cargo-institucional` |
| Veterano+ | Patente Veterano ou superior; pode criar reuniões (RN-006) |
| Conselheiro | Cargo institucional eleito do Conselho Régio (Carta Art. III/IV); no bot, concede XP e audita (RN-004). Não é alcançado por XP |
| Dracmas | Moeda interna da TYTO, **já regulamentada** em `Institucional/DRACMAS.md` — saldo único por pessoa, movimentado por taxa mensal, missões, ingresso em Comunidade/Clube, bônus de venda do Mercador, entre outras origens listadas em `DRACMAS.md` §2. A regra já é vigente independente da implementação; a Fase 2 deste bot ([fase-2.md](05-roadmap/fase-2.md)) é só quando o Bot Oráculo passa a materializá-la — hoje esse saldo não existe em código nenhum |
| Aldeão / Comunidade | Camada intermediária de acesso entre Visitante e Clube (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 1º) — registro feito integralmente pelo Atena, com saldo de Dracmas e histórico de Crédito de Mérito, sem conta na plataforma nem patente deste bot |
| Clube | Filiação plena — o "membro" de toda a Carta Institucional (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 1º §3º); é o que um registro `Membro` deste bot representa; a escala de patentes se aplica a ele |
| Crédito de Mérito | Registro provisório de mérito para quem ainda não é membro (`Institucional/CREDITO_DE_MERITO.md`), convertido em XP na filiação — fora do escopo atual deste bot, ver Fase 2 |
| Mercador | Único papel institucional aberto a quem não é membro do Clube (`Institucional/MERCADOR.md`) — não usa a escala de patentes deste bot; recebe comissão em dinheiro real e, desde `MERCADOR.md` Art. 4º §13º–§14º, também um bônus em Dracmas creditado à própria conta de Comunidade, que o Atena deveria gerenciar |
| Oficial+ | Patente Oficial ou superior; pode criar eventos oficiais e comunicados (RN-007, RN-018) |
| Movimentação crítica | Alteração de XP, promoção, cargo ou evento sensível; não pode ser apagada fisicamente (RN-010) |
| RSVP | Confirmação de presença (confirmar / recusar / pendente) |
| Soft-delete | Exclusão lógica preservando histórico |
| TYTO | Clube / organização dona das regras de hierarquia |
| XP | Pontos de experiência usados para progressão e ranking neste bot — distinto, mas com o mesmo nome, do XP de patente de `Institucional/XP.md` |
| Bot-XP-Discord | Repositório legado analisado; fonte da dívida técnica TD-* |
