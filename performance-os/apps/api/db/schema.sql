-- =====================================================================
-- Performance OS — Database Schema (Step 2)
-- PostgreSQL 15+
-- Extensions: pgcrypto (uuid), pgvector (RAG embeddings on text notes only)
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================================
-- 1. IDENTITY
-- =====================================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_user_id   TEXT NOT NULL UNIQUE,          -- Clerk is source of truth for auth
    email           TEXT NOT NULL,
    display_name    TEXT,
    timezone        TEXT NOT NULL DEFAULT 'UTC',
    units           TEXT NOT NULL DEFAULT 'metric' CHECK (units IN ('metric', 'imperial')),
    date_of_birth   DATE,
    sex             TEXT CHECK (sex IN ('male', 'female', 'other', 'prefer_not_to_say')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_settings (
    user_id                 UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    weekly_summary_enabled  BOOLEAN NOT NULL DEFAULT true,
    ai_coach_tone           TEXT NOT NULL DEFAULT 'direct' CHECK (ai_coach_tone IN ('direct', 'encouraging', 'clinical')),
    notification_prefs      JSONB NOT NULL DEFAULT '{}',
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 2. PROVIDER LAYER
-- Every external data source (Garmin, Apple Health, Polar, Strava...)
-- implements the same shape here. Adding a provider = adding a row type,
-- not a migration.
-- =====================================================================

CREATE TABLE provider_connections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_type       TEXT NOT NULL CHECK (provider_type IN ('garmin', 'apple_health', 'polar', 'strava', 'manual')),
    access_token        TEXT,                       -- encrypted at rest via app-layer encryption
    refresh_token       TEXT,
    token_expires_at    TIMESTAMPTZ,
    external_account_id TEXT,                        -- provider's user/account identifier
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'revoked', 'error')),
    last_synced_at      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, provider_type, external_account_id)
);

CREATE INDEX idx_provider_connections_user ON provider_connections(user_id);

CREATE TABLE provider_sync_logs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_connection_id  UUID NOT NULL REFERENCES provider_connections(id) ON DELETE CASCADE,
    sync_started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    sync_completed_at       TIMESTAMPTZ,
    status                  TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
    records_synced          INT DEFAULT 0,
    error_message           TEXT
    -- Deliberately no raw payload storage here — debug payloads go to object
    -- storage (S3/R2) with a reference URL if ever needed, not into Postgres.
);

CREATE INDEX idx_sync_logs_connection ON provider_sync_logs(provider_connection_id, sync_started_at DESC);

-- =====================================================================
-- 3. NORMALIZATION LAYER
-- Provider-agnostic facts. Every table here carries external_id + a
-- unique constraint against its provider connection for idempotent sync.
-- =====================================================================

CREATE TABLE activities (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_connection_id  UUID REFERENCES provider_connections(id) ON DELETE SET NULL,
    external_id             TEXT,                     -- null for manually logged activities
    activity_type           TEXT NOT NULL,             -- 'run', 'ride', 'strength', 'crossfit', 'swim', etc.
    source                  TEXT NOT NULL DEFAULT 'provider' CHECK (source IN ('provider', 'manual')),
    started_at              TIMESTAMPTZ NOT NULL,
    duration_seconds        INT NOT NULL,
    distance_meters         NUMERIC(10,2),
    calories                INT,
    avg_heart_rate          INT,
    max_heart_rate          INT,
    elevation_gain_meters   NUMERIC(8,2),
    perceived_effort        SMALLINT CHECK (perceived_effort BETWEEN 1 AND 10),
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider_connection_id, external_id)
);

CREATE INDEX idx_activities_user_date ON activities(user_id, started_at DESC);
CREATE INDEX idx_activities_type ON activities(user_id, activity_type, started_at DESC);

CREATE TABLE activity_laps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id     UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    lap_index       INT NOT NULL,
    distance_meters NUMERIC(10,2),
    duration_seconds INT,
    avg_pace_sec_per_km NUMERIC(6,2),
    avg_heart_rate  INT
);

CREATE INDEX idx_laps_activity ON activity_laps(activity_id, lap_index);

-- High-frequency append-only data. Kept separate from `activities` because
-- of the very different write/read pattern. Candidate for monthly
-- partitioning once volume grows — not needed at launch.
CREATE TABLE heart_rate_samples (
    id              BIGSERIAL PRIMARY KEY,
    activity_id     UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    recorded_at     TIMESTAMPTZ NOT NULL,
    bpm             SMALLINT NOT NULL
);

CREATE INDEX idx_hr_samples_activity ON heart_rate_samples(activity_id, recorded_at);

CREATE TABLE running_metrics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id         UUID NOT NULL UNIQUE REFERENCES activities(id) ON DELETE CASCADE,
    vo2max_estimate     NUMERIC(4,1),
    avg_cadence_spm     SMALLINT,
    avg_ground_contact_ms NUMERIC(5,1),
    avg_vertical_oscillation_mm NUMERIC(5,1),
    running_power_watts SMALLINT,
    pace_zones          JSONB              -- flexible: {"zone1": {"sec_per_km": 360}, ...}
);

CREATE TABLE sleep_sessions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_connection_id  UUID REFERENCES provider_connections(id) ON DELETE SET NULL,
    external_id             TEXT,
    sleep_date              DATE NOT NULL,           -- the night this sleep "belongs" to
    started_at              TIMESTAMPTZ NOT NULL,
    ended_at                TIMESTAMPTZ NOT NULL,
    total_sleep_seconds     INT,
    light_sleep_seconds     INT,
    deep_sleep_seconds      INT,
    rem_sleep_seconds       INT,
    awake_seconds           INT,
    sleep_score             SMALLINT CHECK (sleep_score BETWEEN 0 AND 100),
    UNIQUE (provider_connection_id, external_id)
);

CREATE INDEX idx_sleep_user_date ON sleep_sessions(user_id, sleep_date DESC);

CREATE TABLE hrv_readings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_connection_id  UUID REFERENCES provider_connections(id) ON DELETE SET NULL,
    external_id             TEXT,
    reading_date            DATE NOT NULL,
    rmssd_ms                NUMERIC(5,1) NOT NULL,   -- raw HRV measurement
    provider_baseline_low   NUMERIC(5,1),             -- provider's own baseline band, kept for reference
    provider_baseline_high  NUMERIC(5,1),
    recorded_at             TIMESTAMPTZ NOT NULL,
    UNIQUE (provider_connection_id, external_id)
);

CREATE INDEX idx_hrv_user_date ON hrv_readings(user_id, reading_date DESC);

CREATE TABLE body_battery_readings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_connection_id  UUID REFERENCES provider_connections(id) ON DELETE SET NULL,
    recorded_at             TIMESTAMPTZ NOT NULL,
    level                   SMALLINT NOT NULL CHECK (level BETWEEN 0 AND 100),
    event_type              TEXT CHECK (event_type IN ('charge', 'drain', 'activity', 'stress'))
);

CREATE INDEX idx_body_battery_user_date ON body_battery_readings(user_id, recorded_at DESC);

CREATE TABLE stress_readings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_connection_id  UUID REFERENCES provider_connections(id) ON DELETE SET NULL,
    recorded_at             TIMESTAMPTZ NOT NULL,
    stress_level            SMALLINT CHECK (stress_level BETWEEN 0 AND 100)
);

CREATE INDEX idx_stress_user_date ON stress_readings(user_id, recorded_at DESC);

CREATE TABLE training_readiness_scores (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_connection_id  UUID REFERENCES provider_connections(id) ON DELETE SET NULL,
    score_date              DATE NOT NULL,
    score                   SMALLINT CHECK (score BETWEEN 0 AND 100),
    contributing_factors    JSONB,                    -- provider's own breakdown, if given
    UNIQUE (user_id, score_date, provider_connection_id)
);

CREATE INDEX idx_readiness_user_date ON training_readiness_scores(user_id, score_date DESC);

-- =====================================================================
-- 4. STRENGTH & CROSSFIT (manually logged, no provider equivalent yet)
-- =====================================================================

CREATE TABLE strength_workouts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_id     UUID REFERENCES activities(id) ON DELETE SET NULL, -- optional link if also logged as an activity
    performed_at    TIMESTAMPTZ NOT NULL,
    notes           TEXT
);

CREATE INDEX idx_strength_workouts_user ON strength_workouts(user_id, performed_at DESC);

CREATE TABLE strength_sets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strength_workout_id UUID NOT NULL REFERENCES strength_workouts(id) ON DELETE CASCADE,
    exercise_name       TEXT NOT NULL,
    set_index           INT NOT NULL,
    reps                SMALLINT,
    weight_kg           NUMERIC(6,2),
    rpe                 NUMERIC(3,1) CHECK (rpe BETWEEN 0 AND 10)
);

CREATE INDEX idx_strength_sets_workout ON strength_sets(strength_workout_id, set_index);

CREATE TABLE crossfit_workouts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_id     UUID REFERENCES activities(id) ON DELETE SET NULL,
    wod_name        TEXT,                             -- e.g. "Fran", "Murph", or custom
    score_type      TEXT NOT NULL CHECK (score_type IN ('time', 'reps', 'load', 'rounds_reps')),
    result_value    NUMERIC(10,2) NOT NULL,            -- interpretation depends on score_type
    rx              BOOLEAN NOT NULL DEFAULT true,     -- Rx'd vs scaled
    performed_at    TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_crossfit_user ON crossfit_workouts(user_id, performed_at DESC);
CREATE INDEX idx_crossfit_wod_name ON crossfit_workouts(user_id, wod_name);

-- =====================================================================
-- 5. GOALS, RECORDS, ACHIEVEMENTS
-- =====================================================================

CREATE TABLE goals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_type       TEXT NOT NULL,                     -- 'race_time', 'body_weight', 'lift_pr', 'consistency', etc.
    description     TEXT NOT NULL,
    target_value    NUMERIC(10,2),
    target_unit     TEXT,
    target_date     DATE,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'achieved', 'abandoned')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_goals_user_status ON goals(user_id, status);

CREATE TABLE personal_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    record_type     TEXT NOT NULL,                     -- '5k_time', 'back_squat_1rm', 'fran_time', etc.
    value           NUMERIC(10,2) NOT NULL,
    unit            TEXT NOT NULL,
    achieved_at     TIMESTAMPTZ NOT NULL,
    activity_id     UUID REFERENCES activities(id) ON DELETE SET NULL,
    UNIQUE (user_id, record_type, achieved_at)
);

CREATE INDEX idx_prs_user_type ON personal_records(user_id, record_type, achieved_at DESC);

CREATE TABLE achievements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    achievement_key TEXT NOT NULL,                     -- 'streak_30_days', 'first_sub_20_5k', etc.
    earned_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, achievement_key)
);

-- =====================================================================
-- 6. FEATURE STORE
-- The single most important table for the AI layer. Analytics Engine
-- writes here; AI Context Builder reads ONLY from here for physiological
-- data — never from raw normalized tables directly.
-- =====================================================================

CREATE TABLE feature_snapshots (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_date           DATE NOT NULL,
    period                  TEXT NOT NULL CHECK (period IN ('daily', 'weekly')),

    -- Well-known, frequently queried metrics get typed columns:
    acute_load              NUMERIC(6,2),              -- 7-day training load
    chronic_load            NUMERIC(6,2),               -- 28-day training load
    acwr                    NUMERIC(4,2),                -- acute:chronic workload ratio
    fatigue_score           NUMERIC(5,2),
    recovery_trend          TEXT CHECK (recovery_trend IN ('improving', 'stable', 'declining')),
    hrv_baseline_deviation  NUMERIC(5,2),                -- % deviation from personal HRV baseline
    consistency_score       NUMERIC(5,2),                -- adherence to planned training
    vo2max_trend            NUMERIC(4,2),                -- rate of change over trailing window

    -- Everything else the Analytics Engine computes, without needing a
    -- migration every time a new metric is added:
    metrics                 JSONB NOT NULL DEFAULT '{}',

    computed_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, snapshot_date, period)
);

CREATE INDEX idx_feature_snapshots_user_date ON feature_snapshots(user_id, snapshot_date DESC);
CREATE INDEX idx_feature_snapshots_metrics_gin ON feature_snapshots USING GIN (metrics);

-- =====================================================================
-- 7. AI LAYER
-- =====================================================================

CREATE TABLE ai_conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_conversations_user ON ai_conversations(user_id, updated_at DESC);

CREATE TABLE ai_messages (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id             UUID NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role                        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content                     TEXT NOT NULL,
    referenced_feature_snapshot_ids UUID[],             -- traceability: what data grounded this answer
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_messages_conversation ON ai_messages(conversation_id, created_at);

CREATE TABLE ai_insights (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature_snapshot_id     UUID REFERENCES feature_snapshots(id) ON DELETE SET NULL,
    category                TEXT NOT NULL,               -- 'recovery', 'training_load', 'sleep', etc.
    title                   TEXT NOT NULL,
    body                    TEXT NOT NULL,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until             TIMESTAMPTZ,                 -- cache invalidation for dashboard cards
    dismissed_at            TIMESTAMPTZ
);

CREATE INDEX idx_ai_insights_user_active ON ai_insights(user_id, generated_at DESC) WHERE dismissed_at IS NULL;

CREATE TABLE ai_predictions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prediction_type         TEXT NOT NULL,               -- 'race_time', 'next_pr', 'injury_risk'
    predicted_value         NUMERIC(10,2),
    predicted_unit          TEXT,
    confidence              NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
    based_on_feature_snapshot_id UUID REFERENCES feature_snapshots(id) ON DELETE SET NULL,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    target_date             DATE
);

CREATE INDEX idx_ai_predictions_user ON ai_predictions(user_id, generated_at DESC);

-- Free-text notes: goals in prose, journal entries, race reports.
-- This is the ONLY place RAG applies — never on physiological time-series.
CREATE TABLE training_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_id     UUID REFERENCES activities(id) ON DELETE SET NULL,
    content         TEXT NOT NULL,
    embedding       vector(1536),                        -- adjust dimension to embedding model used
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_training_notes_user ON training_notes(user_id, created_at DESC);
CREATE INDEX idx_training_notes_embedding ON training_notes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- =====================================================================
-- NOTES FOR FUTURE SCALING (not implemented now, flagged for later):
-- - Partition heart_rate_samples, hrv_readings, body_battery_readings,
--   stress_readings by month once row counts justify it.
-- - Consider TimescaleDB hypertables for the same tables if query
--   patterns lean heavily on time-bucketed aggregation.
-- - access_token / refresh_token should be encrypted at the application
--   layer before insert (e.g. via envelope encryption), not stored plain.
-- =====================================================================
