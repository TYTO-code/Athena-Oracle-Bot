# ADR-002 — Bot somente leitura e restrito a membros cadastrados

**Status:** aceita · **Regras:** RN-020, RN-021 · **Substitui parcialmente:** RN-004, RN-011 a RN-016, RN-019

## Contexto

Até aqui o bot tinha poder de escrita sobre o que é do Clube: concedia XP, nomeava Conselheiros e
Administradores, confirmava patentes, migrava saldos de Dracmas e criava um `Membro` para qualquer
pessoa que rodasse um comando. Isso tornava qualquer falha de permissão do bot — ou da conta de
serviço do Firebase — uma forma de alterar dados do Clube a partir do Discord, onde basta estar no
servidor para disparar um comando.

## Decisão

1. **Só consulta (RN-021).** O bot lê o Firestore e espelha em seu banco local. Foram removidos os
   comandos `/conceder-xp`, `/historico-xp`, `/cargo-institucional`, `/confirmar-patente`,
   `/migrar-para-clube`, `/reconciliar-conta`, `/vincular-conta`, `/confirmar-vinculo`, `/saldo`,
   `/extrato-dracmas` e `/doar-dracmas`, os serviços por trás deles (XP, cargos, Dracmas, filiação,
   vínculo, bootstrap de Administrador) e o cliente da API de economia da plataforma. Permanecem as
   ações próprias do Discord: comunicados, agenda/Google Agenda, RSVP e aplicação dos papéis.
2. **Só cadastrados (RN-020).** Todo comando passa por `requer`, que resolve o autor com
   `obter_cadastrado_por_discord` — nunca cria. É cadastrado quem tem, na TYTO.club, conta de Clube
   ativa (não suspensa, não `merchant`) com o ID numérico do Discord no perfil.
3. **Cargos e patente vêm da plataforma.** `conselheiro` e `admin` são espelhados; patente e XP só
   sobem (XP.md Art. 1º). O primeiro Administrador é marcado na plataforma, não no bot.
4. **Consulta pontual no primeiro acesso.** Para não obrigar quem acabou de se cadastrar a esperar o
   ciclo de 6 h, `AcessoService` consulta a plataforma por `discordId` quando o membro não está no
   espelho. Recusas ficam em cache por 60 s (limite de 2000 entradas) para que repetir o comando não
   gere leituras. Falha na consulta nega o acesso.
5. **Sincronização desativa.** Quem não é mais elegível ou sumiu da plataforma é desativado
   (soft-delete). Uma leitura que não devolve ninguém não desativa ninguém.

## Consequências

- **Positivas:** o pior que um comando malicioso faz é consultar; a conta de serviço pode (e deve) ser
  `roles/datastore.viewer`, de modo que mesmo um bot comprometido não consegue gravar no Firebase.
- **Custo:** o acesso de quem foi suspenso pode durar até um ciclo de sincronização (6 h) no espelho.
- **Risco herdado:** sem o teto e a confirmação manual de patente, uma patente/`admin` adulterados na
  plataforma chegam ao bot. A proteção disso é das regras do Firestore da TYTO.club (campos `tier`,
  `xp`, `admin`, `conselheiro` só alteráveis pelo backend) — fora deste repositório.
- Tabelas `aldeoes`, `dracmas_ledger` e `vinculos_pendentes` ficam no schema como histórico; nenhuma
  migração destrutiva foi feita.
