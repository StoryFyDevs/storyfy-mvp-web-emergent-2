-- ============================================================
-- StoryFy → Supabase Migration Schema
-- Run this ONCE in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- ============ USER PROFILES ============
CREATE TABLE IF NOT EXISTS user_profiles (
    id BIGSERIAL PRIMARY KEY,
    auth_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL UNIQUE,
    email TEXT DEFAULT '',
    name TEXT DEFAULT '',
    role TEXT DEFAULT 'creator',
    generation_credits INT DEFAULT 1000,
    audition_credits INT DEFAULT 500,
    limits_remaining INT DEFAULT 1000,
    is_active BOOLEAN DEFAULT TRUE,
    avatar_url TEXT DEFAULT '',
    password_hash TEXT DEFAULT '',
    generation_status TEXT DEFAULT 'idle',
    daily_generation_limit INT DEFAULT 50,
    per_minute_limit INT DEFAULT 10,
    last_generation_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ STORIES ============
CREATE TABLE IF NOT EXISTS stories (
    id BIGSERIAL PRIMARY KEY,
    story_id TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    title TEXT DEFAULT '',
    genre TEXT DEFAULT '',
    sub_genre TEXT DEFAULT '',
    language TEXT DEFAULT 'English',
    status TEXT DEFAULT 'draft',
    description TEXT DEFAULT '',
    cover_image_url TEXT DEFAULT '',
    cover_art_url TEXT DEFAULT '',
    tags TEXT[] DEFAULT '{}',
    published_at TIMESTAMPTZ NULL,
    play_count INT DEFAULT 0,
    story_type TEXT DEFAULT 'scripted',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ EPISODES ============
CREATE TABLE IF NOT EXISTS episodes (
    id BIGSERIAL PRIMARY KEY,
    episode_id TEXT NOT NULL UNIQUE,
    story_id TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    title TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    script_content TEXT DEFAULT '',
    script TEXT DEFAULT '',
    final_audio_url TEXT DEFAULT '',
    audio_url TEXT DEFAULT '',
    project_state JSONB NULL,
    duration_seconds FLOAT DEFAULT 0,
    duration FLOAT DEFAULT 0,
    order_index INT DEFAULT 0,
    is_published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMPTZ NULL,
    play_count INT DEFAULT 0,
    storage_files JSONB NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ CHARACTERS ============
CREATE TABLE IF NOT EXISTS characters (
    id BIGSERIAL PRIMARY KEY,
    character_id TEXT NOT NULL UNIQUE,
    story_id TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    name TEXT DEFAULT '',
    voice_id TEXT DEFAULT '',
    display_name TEXT DEFAULT '',
    tone TEXT DEFAULT '',
    category TEXT DEFAULT '',
    voice_settings JSONB NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ VOICE SAMPLES ============
CREATE TABLE IF NOT EXISTS voice_samples (
    id BIGSERIAL PRIMARY KEY,
    voice_id TEXT NOT NULL UNIQUE,
    display_name TEXT DEFAULT '',
    storage_path TEXT DEFAULT '',
    storage_file_id TEXT DEFAULT '',
    audio_url TEXT DEFAULT '',
    duration_seconds FLOAT DEFAULT 0,
    status TEXT DEFAULT 'active',
    text_content TEXT DEFAULT '',
    error TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ AUDITION CACHE ============
CREATE TABLE IF NOT EXISTS audition_cache (
    id BIGSERIAL PRIMARY KEY,
    voice_id TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    audio_url TEXT DEFAULT '',
    duration_seconds FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(voice_id, text_hash)
);

-- ============ AUDIO CACHE ============
CREATE TABLE IF NOT EXISTS audio_cache (
    id BIGSERIAL PRIMARY KEY,
    cache_key TEXT NOT NULL UNIQUE,
    voice_id TEXT DEFAULT '',
    dialogue_text TEXT DEFAULT '',
    director_notes TEXT DEFAULT '',
    audio_url TEXT DEFAULT '',
    duration_seconds FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ AUDIO CLIPS (storage lifecycle) ============
CREATE TABLE IF NOT EXISTS audio_clips (
    id BIGSERIAL PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,
    audio_url TEXT NOT NULL,
    episode_id TEXT DEFAULT '',
    story_id TEXT DEFAULT '',
    dialogue_index INT DEFAULT 0,
    voice_id TEXT DEFAULT '',
    cache_key TEXT DEFAULT '',
    is_cached BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    pending_deletion BOOLEAN DEFAULT FALSE,
    pending_deletion_at TIMESTAMPTZ NULL,
    last_used_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ AUDIO ASSETS ============
CREATE TABLE IF NOT EXISTS audio_assets (
    id BIGSERIAL PRIMARY KEY,
    asset_id TEXT NOT NULL UNIQUE,
    story_id TEXT DEFAULT '',
    episode_id TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    name TEXT DEFAULT '',
    asset_type TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    storage_file_id TEXT DEFAULT '',
    duration_seconds FLOAT DEFAULT 0,
    file_size BIGINT DEFAULT 0,
    mime_type TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ GENERATION LOGS ============
CREATE TABLE IF NOT EXISTS generation_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT DEFAULT '',
    gen_type TEXT DEFAULT '',
    character_name TEXT DEFAULT '',
    voice_id TEXT DEFAULT '',
    text_length INT DEFAULT 0,
    duration_seconds FLOAT DEFAULT 0,
    status TEXT DEFAULT '',
    provider TEXT DEFAULT '',
    error TEXT DEFAULT '',
    details JSONB NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ GENERATION USAGE ============
CREATE TABLE IF NOT EXISTS generation_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    generation_date DATE DEFAULT CURRENT_DATE,
    generation_count INT DEFAULT 0,
    token_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,
    last_generation_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, generation_date)
);

-- ============ GENERATION QUEUE ============
CREATE TABLE IF NOT EXISTS generation_queue (
    id BIGSERIAL PRIMARY KEY,
    queue_id TEXT NOT NULL UNIQUE,
    user_id TEXT DEFAULT '',
    request_type TEXT DEFAULT '',
    request_data TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    result_data TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ SCRIPT GENERATION JOBS ============
CREATE TABLE IF NOT EXISTS script_generation_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE,
    episode_id TEXT DEFAULT '',
    user_id TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    total_dialogues INT DEFAULT 0,
    completed_dialogues INT DEFAULT 0,
    batches_total INT DEFAULT 0,
    batches_completed INT DEFAULT 0,
    result_data TEXT DEFAULT '{}',
    error_message TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ GENERATION METRICS ============
CREATE TABLE IF NOT EXISTS generation_metrics (
    id BIGSERIAL PRIMARY KEY,
    generation_id TEXT NOT NULL UNIQUE,
    episode_id TEXT DEFAULT '',
    user_id TEXT DEFAULT '',
    dialogue_count INT DEFAULT 0,
    speaker_pair_count INT DEFAULT 0,
    batch_count INT DEFAULT 0,
    gemini_calls_used INT DEFAULT 0,
    gemini_calls_saved INT DEFAULT 0,
    cache_hits INT DEFAULT 0,
    cache_misses INT DEFAULT 0,
    deepgram_audio_minutes FLOAT DEFAULT 0,
    segmentation_success_rate FLOAT DEFAULT 0,
    fallback_triggered BOOLEAN DEFAULT FALSE,
    generation_time_seconds FLOAT DEFAULT 0,
    estimated_cost FLOAT DEFAULT 0,
    empty_gemini_responses INT DEFAULT 0,
    gemini_retries INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ GENERATION DEBUG LOGS ============
CREATE TABLE IF NOT EXISTS generation_debug_logs (
    id BIGSERIAL PRIMARY KEY,
    log_id TEXT NOT NULL UNIQUE,
    generation_id TEXT DEFAULT '',
    episode_id TEXT DEFAULT '',
    user_id TEXT DEFAULT '',
    event_type TEXT DEFAULT '',
    message TEXT DEFAULT '',
    metadata JSONB NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ SYSTEM SETTINGS ============
CREATE TABLE IF NOT EXISTS system_settings (
    id BIGSERIAL PRIMARY KEY,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT DEFAULT '',
    updated_by TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ USAGE LOGS ============
CREATE TABLE IF NOT EXISTS usage_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT DEFAULT '',
    action TEXT DEFAULT '',
    resource_type TEXT DEFAULT '',
    resource_id TEXT DEFAULT '',
    details JSONB NULL,
    credits_used INT DEFAULT 0,
    credit_type TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ LIMIT TRANSACTIONS ============
CREATE TABLE IF NOT EXISTS limit_transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT DEFAULT '',
    admin_id TEXT DEFAULT '',
    credit_type TEXT DEFAULT '',
    previous_value INT DEFAULT 0,
    new_value INT DEFAULT 0,
    change_amount INT DEFAULT 0,
    reason TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ USAGE ALERTS ============
CREATE TABLE IF NOT EXISTS usage_alerts (
    id BIGSERIAL PRIMARY KEY,
    alert_id TEXT NOT NULL UNIQUE,
    user_id TEXT DEFAULT '',
    alert_type TEXT DEFAULT '',
    message TEXT DEFAULT '',
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============ VOICE SETTINGS ============
CREATE TABLE IF NOT EXISTS voice_settings (
    id BIGSERIAL PRIMARY KEY,
    setting_id TEXT NOT NULL UNIQUE,
    active_provider TEXT DEFAULT 'gemini',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============ LISTENING PROGRESS (mobile) ============
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

-- ============ LISTENER LIBRARY (mobile) ============
CREATE TABLE IF NOT EXISTS listener_library (
    id BIGSERIAL PRIMARY KEY,
    entry_id TEXT NOT NULL UNIQUE,
    listener_id TEXT NOT NULL,
    story_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(listener_id, story_id)
);

-- ============ PLAY EVENTS (mobile) ============
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
CREATE INDEX IF NOT EXISTS idx_stories_created_by ON stories(created_by);
CREATE INDEX IF NOT EXISTS idx_episodes_story_id ON episodes(story_id);
CREATE INDEX IF NOT EXISTS idx_characters_story_id ON characters(story_id);
CREATE INDEX IF NOT EXISTS idx_audio_cache_key ON audio_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_audio_clips_episode ON audio_clips(episode_id);
CREATE INDEX IF NOT EXISTS idx_audio_clips_story ON audio_clips(story_id);
CREATE INDEX IF NOT EXISTS idx_audio_clips_pending ON audio_clips(pending_deletion);
CREATE INDEX IF NOT EXISTS idx_script_jobs_episode ON script_generation_jobs(episode_id);
CREATE INDEX IF NOT EXISTS idx_gen_usage_user ON generation_usage(user_id, generation_date);
CREATE INDEX IF NOT EXISTS idx_gen_debug_gen_id ON generation_debug_logs(generation_id);
CREATE INDEX IF NOT EXISTS idx_gen_metrics_episode ON generation_metrics(episode_id);
CREATE INDEX IF NOT EXISTS idx_listening_progress_listener ON listening_progress(listener_id);
CREATE INDEX IF NOT EXISTS idx_listening_progress_episode ON listening_progress(episode_id);
CREATE INDEX IF NOT EXISTS idx_listener_library_listener ON listener_library(listener_id);
CREATE INDEX IF NOT EXISTS idx_play_events_episode ON play_events(episode_id);
CREATE INDEX IF NOT EXISTS idx_play_events_story ON play_events(story_id);
CREATE INDEX IF NOT EXISTS idx_stories_published ON stories(status) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_episodes_published ON episodes(is_published) WHERE is_published = true;

-- ============ STORAGE BUCKETS (run separately if needed) ============
-- INSERT INTO storage.buckets (id, name, public) VALUES ('storyfy-audio', 'storyfy-audio', true) ON CONFLICT DO NOTHING;
-- INSERT INTO storage.buckets (id, name, public) VALUES ('storyfy-cache', 'storyfy-cache', true) ON CONFLICT DO NOTHING;
-- INSERT INTO storage.buckets (id, name, public) VALUES ('storyfy-exports', 'storyfy-exports', true) ON CONFLICT DO NOTHING;

-- ============ RLS: Disable for service-role access ============
-- All tables: service role bypasses RLS automatically in Supabase.
-- No RLS policies needed for backend-only access.

SELECT 'Schema migration complete. Tables created successfully.' AS status;
