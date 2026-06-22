CREATE TABLE IF NOT EXISTS pain_points (
    id UUID PRIMARY KEY,
    avatar_id UUID REFERENCES avatars(id),
    pain TEXT,
    embedding vector
);
