-- PostgreSQL schema for recently viewed properties feature.

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS properties (
    id UUID PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS recently_viewed_properties (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_recent_views_user_property UNIQUE (user_id, property_id)
);

CREATE INDEX IF NOT EXISTS ix_recent_views_user_viewed_at_desc
    ON recently_viewed_properties (user_id, viewed_at DESC);
