CREATE TABLE IF NOT EXISTS proof_bank (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    type TEXT,
    value TEXT,
    source TEXT,
    is_verified BOOLEAN DEFAULT TRUE
);
