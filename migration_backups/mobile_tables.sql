-- ============================================================
-- StoryFy Mobile Listener Tables
-- Run in Supabase SQL Editor (Dashboard -> SQL Editor)
-- ============================================================

-- ============ LISTENING PROGRESS ============
CREATE TABLE IF NOT EXISTS listening_progress (
    id BIGSERIAL PRIMARY KEY,
    progress_id TEXT NOT NULL UNIQUE,
    listener_id TEXT NOT NULL,
    episode_id TEXT NOT NULL,
    current_time FLOAT DEFAULT 0,
    duration FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(listener_id, episode_id)
);

-- ============ LISTENER LIBRARY ============
CREATE TABLE IF NOT EXISTS listener_library (
    id BIGSERIAL PRIMARY KEY,
    entry_id TEXT NOT NULL UNIQUE,
    listener_id TEXT NOT NULL,
    story_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(listener_id, story_id)
);

-- ============ PLAY EVENTS ============
CREATE TABLE IF NOT EXISTS play_events (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    listener_id TEXT DEFAULT '',
    episode_id TEXT NOT NULL,
    story_id TEXT DEFAULT '',
    event_type TEXT DEFAULT 'play',
    position_seconds FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ INDEXES ============
CREATE INDEX IF NOT EXISTS idx_listening_progress_listener ON listening_progress(listener_id);
CREATE INDEX IF NOT EXISTS idx_listening_progress_episode ON listening_progress(episode_id);
CREATE INDEX IF NOT EXISTS idx_listener_library_listener ON listener_library(listener_id);
CREATE INDEX IF NOT EXISTS idx_play_events_episode ON play_events(episode_id);
CREATE INDEX IF NOT EXISTS idx_play_events_story ON play_events(story_id);
CREATE INDEX IF NOT EXISTS idx_stories_published ON stories(status) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_episodes_published ON episodes(is_published) WHERE is_published = true;

SELECT 'Mobile tables created successfully.' AS status;
