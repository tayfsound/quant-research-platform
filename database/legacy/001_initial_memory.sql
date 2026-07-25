CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Observations (hypertable) — composite primary key
CREATE TABLE IF NOT EXISTS observations (
    id UUID,
    cycle_id UUID,
    symbol TEXT NOT NULL,
    observation_type TEXT,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
);
SELECT create_hypertable('observations', 'created_at', if_not_exists => TRUE);

-- Episodes (hypertable) — composite primary key
CREATE TABLE IF NOT EXISTS episodes (
    id UUID,
    cycle_id UUID,
    symbol TEXT NOT NULL,
    observation JSONB,
    binding_expression TEXT,
    decision TEXT,
    outcome JSONB,
    lesson TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
);
SELECT create_hypertable('episodes', 'created_at', if_not_exists => TRUE);

-- Beliefs (regular table)
CREATE TABLE IF NOT EXISTS beliefs (
    id UUID PRIMARY KEY,
    expression TEXT UNIQUE,
    confidence DOUBLE PRECISION DEFAULT 0.0,
    evidence_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Experiments (regular table)
CREATE TABLE IF NOT EXISTS experiments (
    id UUID PRIMARY KEY,
    curiosity_id UUID,
    hypothesis TEXT,
    test_expression TEXT,
    estimated_value DOUBLE PRECISION DEFAULT 0.0,
    status TEXT DEFAULT 'proposed',
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Lessons (regular table)
CREATE TABLE IF NOT EXISTS lessons (
    id UUID PRIMARY KEY,
    episode_id UUID,
    lesson_text TEXT,
    category TEXT DEFAULT 'general',
    severity TEXT DEFAULT 'info',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
