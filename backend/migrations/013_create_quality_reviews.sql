CREATE TABLE IF NOT EXISTS quality_reviews (
    id UUID PRIMARY KEY,
    script_id UUID REFERENCES scripts(id),
    passed BOOLEAN,
    score INT,
    feedback JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
