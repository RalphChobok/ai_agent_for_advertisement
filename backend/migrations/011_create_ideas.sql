CREATE TABLE IF NOT EXISTS idea_batches (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ideas (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),
    hook TEXT,
    angle_id UUID REFERENCES angles(id),
    description TEXT,
    score_impact INT,
    score_confidence INT,
    score_ease INT,
    score_reasoning TEXT,
    status TEXT DEFAULT 'pending',
    creative_type TEXT,
    lead_type TEXT,
    target_avatar_id UUID REFERENCES avatars(id),
    pain_point_id UUID REFERENCES pain_points(id),
    proof_point_ids UUID[],
    batch_id UUID REFERENCES idea_batches(id),
    embedding vector(768),
    created_at TIMESTAMP DEFAULT NOW()
);
