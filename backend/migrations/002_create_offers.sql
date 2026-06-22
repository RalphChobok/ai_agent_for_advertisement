CREATE TABLE IF NOT EXISTS offers (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    name TEXT,
    type TEXT,
    price NUMERIC,
    description TEXT
);
