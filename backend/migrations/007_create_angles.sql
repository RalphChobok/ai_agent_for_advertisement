CREATE TABLE IF NOT EXISTS angles (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    name TEXT,
    description TEXT,
    embedding vector
);
