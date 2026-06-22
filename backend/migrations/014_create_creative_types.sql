CREATE TABLE IF NOT EXISTS creative_types (
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    PRIMARY KEY (client_id, name)
);

-- Seed the five default types for every client that exists at migration time.
-- New clients should have rows inserted when their reference pack is processed.
INSERT INTO creative_types (client_id, name)
SELECT id, unnest(ARRAY['talking-head', 'UGC', 'listicle', 'story', 'demo'])
FROM clients
ON CONFLICT DO NOTHING;
