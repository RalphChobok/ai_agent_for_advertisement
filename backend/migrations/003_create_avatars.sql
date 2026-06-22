CREATE TABLE IF NOT EXISTS avatars (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    description TEXT,
    age_range TEXT,
    awareness_level TEXT,
    dominant_belief TEXT,
    key_phrase TEXT
);
