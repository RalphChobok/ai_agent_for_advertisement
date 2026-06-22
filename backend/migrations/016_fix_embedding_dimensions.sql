-- Alter ideas.embedding and scripts.embedding from vector(768) to vector(1536)
-- to support OpenAI text-embedding-3-small (1536 dimensions).
-- Safe to re-run: the DO block checks the current dimension before altering.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_type t ON a.atttypid = t.oid
        WHERE c.relname = 'ideas' AND a.attname = 'embedding'
          AND t.typname = 'vector' AND a.atttypmod = 768
    ) THEN
        ALTER TABLE ideas DROP COLUMN embedding;
        ALTER TABLE ideas ADD COLUMN embedding vector(1536);
        RAISE NOTICE 'ideas.embedding altered to vector(1536)';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_type t ON a.atttypid = t.oid
        WHERE c.relname = 'scripts' AND a.attname = 'embedding'
          AND t.typname = 'vector' AND a.atttypmod = 768
    ) THEN
        ALTER TABLE scripts DROP COLUMN embedding;
        ALTER TABLE scripts ADD COLUMN embedding vector(1536);
        RAISE NOTICE 'scripts.embedding altered to vector(1536)';
    END IF;
END $$;
