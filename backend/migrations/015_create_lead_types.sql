CREATE TABLE IF NOT EXISTS lead_types (
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    PRIMARY KEY (client_id, name)
);
