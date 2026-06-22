CREATE TABLE IF NOT EXISTS hooks (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    type TEXT,
    content TEXT
);
