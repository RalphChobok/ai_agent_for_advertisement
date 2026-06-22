CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY,
    name TEXT,
    brand TEXT,
    tone TEXT,
    voice_description TEXT,
    market_stage TEXT,
    core_emotion TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
