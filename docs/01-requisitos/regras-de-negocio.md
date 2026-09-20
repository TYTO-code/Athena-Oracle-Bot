# Catálogo de Regras de Negócio — Atena v1.0

| ID | Nome | Descrição | Prioridade | Rastreabilidade |
|----|------|-----------|------------|-----------------|
| RN-001 | Cargo único | Cada membro poderá possuir apenas um cargo de hierarquia ativo. | Crítica | RF-005, RF-006, UC-003, TD-005 |
| RN-002 | Progressão por XP | A progressão ocorre automaticamente conforme o XP acumulado. | Alta | RF-005, UC-003 |
| RN-003 | Promoção automática | Ao promover, o sistema remove o cargo anterior, concede o novo e registra a promoção em log. | Crítica | RF-005, RF-006, RF-012, UC-003, TD-005 |
| RN-004 | Controle de XP | Somente usuários autorizados (Conselheiros+) podem adicionar ou remover XP. | Crítica | RF-003, UC-001 |
| RN-005 | Auditoria de XP | Toda alteração de XP deve registrar: autor, membro, quantidade, motivo e data/hora. | Crítica | RF-003, RF-012, UC-001, TD-006 |
| RN-006 | Criação de reuniões | Somente cargos superiores à Cavalaria podem criar reuniões. | Alta | RF-007, UC-004 |
| RN-007 | Criação de eventos oficiais | Somente Lordes ou superiores podem criar eventos oficiais. | Alta | RF-008, UC-005 |
| RN-008 | Controle de permissões | Todo acesso a comandos deve ser validado conforme o cargo do membro. | Crítica | RF-* privilegiados |
| RN-009 | Integração Google Agenda | Integração obrigatória com Google Agenda para reuniões e eventos. | Alta | RF-011, UC-004, UC-005 |
| RN-010 | Histórico imutável | Nenhuma movimentação crítica poderá ser excluída fisicamente. | Crítica | RF-012 |
| RN-011 | Camada Comunidade separada de cargo | Um Aldeão (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 2º) não tem cargo de hierarquia nem XP deste bot — é um eixo à parte, sem relação com `hierarchy.py`. | Crítica | RF-013, RF-014 |
| RN-012 | Movimentação de Dracmas exige motivo e origem | Toda movimentação de Dracmas registra tipo, valor, saldo antes/depois, motivo e data (`Institucional/DRACMAS.md` §2/§3). | Crítica | RF-013, RF-014 |
| RN-013 | Ledger de Dracmas imutável | Nenhuma movimentação de Dracmas (`dracmas_ledger`) poderá ser excluída ou editada fisicamente — mesmo princípio de RN-010, aplicado à carteira da Comunidade. | Crítica | RF-013, RF-014 |
| RN-014 | Suspensão automática por saldo negativo | Uma conta de Aldeão com saldo negativo é suspensa automaticamente; reversão é sempre manual (`Institucional/DRACMAS.md` §4). | Crítica | RF-014 |
| RN-015 | Ingresso na Comunidade custa Dracmas | O primeiro crédito de Dracmas a um `discord_id` sem conta cria o Aldeão e cobra 30.000 Dracmas de ingresso na mesma operação, salvo dispensa nomeada (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 3º §1º/§2º/§3º — ver a decisão de implementação documentada em `services/dracmas_service.py`). | Alta | RF-013, RF-014 |
| RN-016 | Prova de posse para autovínculo Discord↔plataforma | A importação (RF-001) só liga `Membro.discord_id` quando o Firestore já traz `discordId`; quando não traz, ninguém pode reivindicar um registro alheio só citando e-mail/ID — precisa provar que controla o e-mail já cadastrado (código de verificação de uso único, TTL curto, tentativas limitadas). A resposta ao pedido de vínculo nunca revela se o identificador existe, está vinculado a outra conta, ou tem outra verificação em andamento — mesma resposta silenciosa nos três casos (evita enumeração e invalidação por terceiros). Nunca aplica cargo/XP nem mescla com um `Membro` que já exista para o mesmo `discord_id` (ver `services/vinculo_service.py`). | Crítica | RF-001 |
| RN-017 | Autorização de leitura de projeto na recuperação, não no prompt | `/perguntar` responde sobre o regulamento (público a todos os membros) e sobre projetos — mas **só os projetos em que a pessoa participa**, conforme o registro no Firebase, lido no momento da pergunta. A filtragem acontece **antes** de qualquer chamada ao modelo: dado de projeto alheio nunca é carregado, então nenhuma instrução de prompt (nem uma injeção escrita dentro do banco) consegue extraí-lo. Sem vínculo Discord↔plataforma (RN-016) não há `id_externo`, logo não há projeto algum — falha fechada. Falha ao *verificar* acesso nega a resposta como indisponibilidade, nunca como "sem acesso". Resposta sempre efêmera: conteúdo restrito não pode ser publicado no canal. | Crítica | RF-001, RN-016 |

## Notas de implementação

- **RN-001 / RN-003:** ao atribuir cargo, remover **todos** os cargos TYTO anteriores antes da nova atribuição (ver TD-005).
- **RN-005:** persistir em tabela de auditoria (ex.: `xp_audit`); o legado não registra autor/motivo (TD-006).
- **RN-010:** preferir soft-delete e append-only em logs/auditoria.
- **RN-011 a RN-015:** implementam só a camada Comunidade (`Aldeao`) — `Membro.dracmas` (US-405)
  segue sem nenhum comando, fica para uma fase seguinte junto com a migração de saldo na
  filiação ao Clube (`Institucional/COMUNIDADE_E_CLUBE.md` Art. 4º §1º-A).
