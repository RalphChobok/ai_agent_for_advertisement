CREATE TABLE IF NOT EXISTS mechanisms (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    name TEXT,
    description TEXT
);
