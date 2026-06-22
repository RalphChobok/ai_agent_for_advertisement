CREATE TABLE IF NOT EXISTS constraints (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    type TEXT,
    rule TEXT
);
