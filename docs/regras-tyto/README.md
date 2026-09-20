# Regulamento TYTO — base de conhecimento do `/perguntar` (RN-017)

Coloque aqui os `.md` do regulamento do Clube TYTO (`CARTA_INSTITUCIONAL.md`,
`XP.md`, `DRACMAS.md`, `COMUNIDADE_E_CLUBE.md`, `MERCADOR.md`,
`CREDITO_DE_MERITO.md`, `SERVIDOR_DISCORD.md`…). É deste diretório que o bot
carrega o material que usa para responder perguntas sobre as regras.

`ORACULO_REGRAS_DIR` já aponta para cá por padrão — largar os arquivos aqui
basta, sem configurar nada.

## Como o conteúdo é usado

Todos os `.md` (inclusive em subpastas) são lidos **uma vez, no start do bot**,
concatenados em ordem alfabética estável e enviados como prefixo do prompt.
Esse prefixo fica em cache e é compartilhado por todas as perguntas de todos os
membros — é o que mantém o custo baixo mesmo com o regulamento inteiro em
contexto. Trocar um arquivo exige reiniciar o bot para recarregar.

Ordem alfabética não é estética: o cache só é reaproveitado enquanto o prefixo
for byte a byte o mesmo.

## O que **não** colocar aqui

- Qualquer coisa restrita a um subconjunto de membros. Tudo neste diretório é
  tratado como **público a todos os membros** — não existe filtro por cargo ou
  por projeto aqui. Dado restrito de projeto vive no banco externo, que tem
  autorização por membro (ver README principal, RN-017).
- Segredos, credenciais, dados pessoais.
- Dumps grandes: arquivos acima de 512 KB são ignorados no carregamento.

## Relação com o vault `Institucional/`

O vault do Clube é a fonte normativa (ver `.claude/rules/institucional-is-law.md`);
o que está aqui é uma **cópia operacional** para o bot conseguir ler em runtime.
Quando o vault mudar, atualize os arquivos daqui — senão o bot responde com
regra velha, e nesse caso o Regulamento continua valendo, não a resposta do bot.
