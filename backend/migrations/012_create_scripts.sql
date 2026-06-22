CREATE TABLE IF NOT EXISTS scripts (
    id UUID PRIMARY KEY,
    idea_id UUID REFERENCES ideas(id),
    client_id UUID REFERENCES clients(id),
    content TEXT,
    status TEXT,
    embedding vector(768),
    created_at TIMESTAMP DEFAULT NOW()
);
