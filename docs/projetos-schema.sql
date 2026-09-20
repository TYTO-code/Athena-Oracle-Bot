-- Base externa de projetos do Clube TYTO — contrato lido pelo /perguntar (RN-017)
--
-- Rode este script no PostgreSQL de projetos (o do Railway), que é SEPARADO do
-- banco do bot. O bot nunca cria nem migra nada aqui: ele só lê, e só o que o
-- autor da pergunta tem direito de ver.
--
-- Uso: psql "$PROJETOS_DATABASE_URL" -f docs/projetos-schema.sql

-- ---------------------------------------------------------------------------
-- 1. Tabelas
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projetos (
    -- Precisa casar com o id do projeto no Firebase (o id do documento na
    -- subcoleção `membros/{id}/projetos`). É por este campo que a autorização
    -- liga uma pessoa a um projeto — se os dois lados divergirem, ninguém vê nada.
    id            text PRIMARY KEY,
    nome          text NOT NULL,
    descricao     text,
    status        text,
    atualizado_em timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS projeto_decisoes (
    id          bigserial PRIMARY KEY,
    projeto_id  text NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
    titulo      text,
    conteudo    text NOT NULL,
    decidido_em timestamptz DEFAULT now()
);

-- O bot lê as decisões mais recentes de cada projeto autorizado.
CREATE INDEX IF NOT EXISTS ix_projeto_decisoes_recentes
    ON projeto_decisoes (projeto_id, decidido_em DESC);

-- ---------------------------------------------------------------------------
-- 2. Usuário somente leitura para o bot
-- ---------------------------------------------------------------------------
-- Defesa em profundidade: mesmo que algo dê errado no código, o banco recusa
-- escrita. Troque a senha antes de rodar e use essa credencial na
-- ORACULO_PROJETOS_DATABASE_URL (nunca a credencial de dono do banco).

-- CREATE ROLE oraculo_leitura LOGIN PASSWORD 'troque-esta-senha';
-- GRANT CONNECT ON DATABASE <nome_do_banco> TO oraculo_leitura;
-- GRANT USAGE ON SCHEMA public TO oraculo_leitura;
-- GRANT SELECT ON projetos, projeto_decisoes TO oraculo_leitura;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO oraculo_leitura;

-- ---------------------------------------------------------------------------
-- 3. Se o banco real já tiver outro schema
-- ---------------------------------------------------------------------------
-- Os nomes acima são fixos no código de propósito: identificador de SQL não é
-- parametrizável, então torná-los configuráveis por variável de ambiente abriria
-- uma via de injeção. Para adaptar um schema existente, exponha VIEWs:
--
--   CREATE VIEW projetos AS
--       SELECT slug AS id, titulo AS nome, resumo AS descricao,
--              situacao AS status, modificado_em AS atualizado_em
--       FROM meus_projetos;
--
--   CREATE VIEW projeto_decisoes AS
--       SELECT id, projeto_slug AS projeto_id, assunto AS titulo,
--              texto AS conteudo, criada_em AS decidido_em
--       FROM minhas_decisoes;

-- ---------------------------------------------------------------------------
-- 4. Dados de exemplo (opcional — remova em produção)
-- ---------------------------------------------------------------------------
-- INSERT INTO projetos (id, nome, descricao, status) VALUES
--     ('atena', 'Atena — Bot Oráculo', 'Bot de gestão do Clube no Discord.', 'ativo')
-- ON CONFLICT (id) DO NOTHING;
--
-- INSERT INTO projeto_decisoes (projeto_id, titulo, conteudo) VALUES
--     ('atena', 'Banco de dados', 'Adotado PostgreSQL no Railway (ADR-001).');
