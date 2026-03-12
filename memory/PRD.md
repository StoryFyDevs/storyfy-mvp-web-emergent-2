# StoryFy - Product Requirements Document

## Original Problem Statement
StoryFy is a full-stack audio storytelling platform for creators. It features a multi-provider voice engine (ElevenLabs and Gemini), character-centric voice generation, an audition system, dual credit management, and an admin panel.

## Core Architecture
- **Frontend:** React, TailwindCSS, Shadcn/UI
- **Backend:** FastAPI, Nhost PostgreSQL (via Hasura GraphQL), Pydantic
- **Storage:** Nhost Storage (audio files, voice samples, script clips)
- **Database:** Nhost PostgreSQL (accessed via Hasura GraphQL)
- **Voice Providers:** Gemini 2.5 Pro TTS (multi-speaker), ElevenLabs (switchable via admin)
- **Auth:** Nhost Auth (email/password, Google OAuth planned)

## Database Schema (PostgreSQL)
All tables managed via Hasura GraphQL:
- `user_profiles` — {id, user_id, auth_id, email, name, role, generation_credits, audition_credits, ...}
- `stories` — {id, story_id, created_by, title, genre, status, ...}
- `episodes` — {id, episode_id, story_id, status, script_content (structured JSON), final_audio_url, project_state, ...}
- `characters` — {id, character_id, story_id, name, voice_id, voice_settings, ...}
- `voice_settings` — {id, setting_id, active_provider}
- `audition_cache` — {id, voice_id, text_hash, audio_url, duration_seconds}
- `voice_samples` — {id, voice_id, display_name, storage_path, audio_url, duration_seconds, status}
- `audio_cache` — {id, cache_key (SHA-256), voice_id, dialogue_text, director_notes, audio_url, duration_seconds}
- `script_generation_jobs` — {id, job_id, episode_id, user_id, status, total_dialogues, completed_dialogues, batches_total, batches_completed, result_data (JSONB), error_message}
- `system_settings` — {id, setting_key, setting_value (JSONB)} — stores generation_limits including batch_size
- `generation_logs`, `limit_transactions`, `admin_logs`, `usage_alerts`, etc.

## What's Been Implemented

### Phase 1-7: (See previous phases in CHANGELOG.md)

### Phase 8: Script Compiler - Speaker-Pair Batched Audio Generation (Updated Mar 6, 2026)
**Architecture: Speaker-pair batching + Deepgram diarization + per-dialogue fallback**

1. **Script Editor Workflow** - COMPLETE
   - Structured dialogue blocks (character selector, dialogue text, director notes)
   - Add/remove/reorder dialogue blocks
   - Each dialogue linked to character and assigned voice

2. **Speaker-Pair Batching** - COMPLETE (Architecture v3)
   - Groups dialogues by unique 2-speaker pairs (Gemini max 2 speakers)
   - Example: 8 dialogues (4 chars) → 2 batches → 2 Gemini calls (instead of 8)
   - Merges non-consecutive batches with same speaker pair
   - Single-speaker batches or single dialogues → per-dialogue fallback

3. **Multi-Speaker TTS** - COMPLETE
   - Uses Gemini `multiSpeakerVoiceConfig` with `speakerVoiceConfigs`
   - Director notes included per-line only when provided
   - Returns single combined audio per batch

4. **Deepgram Diarization** - COMPLETE
   - Sends combined audio to Deepgram (nova-3 model, diarize+utterances)
   - Returns speaker-labeled timestamps per utterance
   - `_reconcile_utterances` with 3-strategy approach:
     - Exact match → pass-through
     - Too many → merge adjacent same-speaker + aggressive merge
     - Too few → time-gap-based splitting of longest segments

5. **Clip Extraction** - COMPLETE
   - Frame-accurate slicing at Deepgram timestamps
   - Each clip validated (size >1KB, RIFF/WAVE header, duration >0.3s)
   - Clips mapped back to dialogue_index for script-order preservation

6. **Fallback System** - COMPLETE (Hardened Mar 7, 2026)
   - If Deepgram fails, segment count mismatches, or speaker mapping unreliable → per-dialogue generation
   - Single-speaker batches always use per-dialogue
   - Individual clip failures within a batch → per-dialogue for that clip only
   - Gemini retry (1 attempt) before triggering fallback
   - Pre-flight batch validation (2 speakers, valid voice IDs, non-empty dialogues)

7. **Audio Caching** - COMPLETE
   - SHA-256 hash of (dialogue_text + voice_id + director_notes)
   - Cache checked before batching — only uncached dialogues are generated

8. **Voice Snapshot System** - COMPLETE
   - `generated_voice_id` stored per dialogue after generation
   - On script load, detects voice changes (generated_voice_id ≠ character.voice_id)
   - Amber banner per dialogue + top-level count of affected dialogues

9. **Smart Regeneration** - COMPLETE
   - Cache key changes when text/voice/notes change → automatic invalidation
   - Deleted dialogues → removed_clips
   - Voice change detection → needs_regeneration indicator

### Phase 10: Pipeline Audit & Hardening (Updated Mar 7, 2026) — SUPERSEDED by Phase 12
Previously implemented speaker-pair batching + Deepgram diarization. This was replaced by the character-based pipeline in Phase 12.

### Phase 11: Pipeline Diarization & Batching Fix (Feb 2026) — SUPERSEDED by Phase 12
Previously added conversation-block batching and break tags. This was replaced by the character-based pipeline in Phase 12.

### Phase 12: Character-Based Batch Pipeline (Feb 2026) — COMPLETE
Complete pipeline rewrite replacing speaker-pair batching + diarization with character-based batching + transcription-aligned segmentation.

**Architecture:**
1. **Character Batching** — `group_dialogues_by_character()` groups all dialogues by character name. Each character gets exactly 1 Gemini call (4 characters = 4 calls). Eliminates speaker-pair complexity entirely.
2. **Single-Speaker TTS** — `_build_character_batch_payload()` builds Gemini payload with single `voiceConfig` (not multiSpeaker). Dialogues concatenated with `<break time="700ms"/>` tags and punctuation enforcement via `_ensure_punctuation()`.
3. **Deepgram Transcription** — `_call_deepgram_transcription()` sends generated audio to Deepgram for word-level timestamps (replaces diarization/utterance detection).
4. **Text Alignment** — `_align_transcription_with_dialogues()` uses sequential fuzzy matching to map each dialogue's text to Deepgram word ranges. Segment boundaries use gap midpoints between adjacent dialogues for clean cuts.
5. **Clip Extraction** — Clips extracted at aligned boundaries. Each clip contains only its dialogue's audio.
6. **Per-Dialogue Fallback** — If batch pipeline or alignment fails for any dialogue, falls back to individual Gemini calls.
7. **Cache System** — `compute_cache_key(text + voice_id + notes)`. Cached clips reused across regenerations.

**Removed functions:** `group_dialogues_by_speaker_pairs`, `_build_multi_speaker_payload`, `_generate_batch`, `_reconcile_utterances`, `_map_speakers_to_characters`, `_validate_batch`
**New functions:** `group_dialogues_by_character`, `_build_character_batch_payload`, `_call_deepgram_transcription`, `_align_transcription_with_dialogues`, `_normalize_to_tokens`, `_normalize_word`, `_words_similar`, `_generate_character_batch`, `_get_wav_duration`

### Phase 9: Generation Analytics & Debug Panel (Completed Mar 7, 2026)
1. **Database Schema** - COMPLETE
   - `generation_metrics` table: tracks dialogue_count, gemini_calls_used/saved, cache_hits/misses, deepgram_minutes, estimated_cost, fallback_triggered, generation_time_seconds per run
   - `generation_debug_logs` table: stores event_type + message + metadata per pipeline step
   - Tables auto-created on server startup via `execute_sql`

2. **Backend Instrumentation** - COMPLETE
   - `script_compiler.py` logs debug events (SCRIPT_COMPILE, BATCH_CREATED, GEMINI_CALL, DEEPGRAM_DIARIZE, CLIP_EXTRACT, FALLBACK_TRIGGERED)
   - Aggregated metrics saved to `generation_metrics` after each run

3. **Admin API Endpoints** - COMPLETE
   - `GET /api/admin-9821/analytics/generation/summary` — Global analytics (today's totals, rates, costs)
   - `GET /api/admin-9821/analytics/generation/runs` — Paginated runs list with creator_id/episode_id filters
   - `GET /api/admin-9821/analytics/generation/{id}/debug` — Debug logs for a specific run
   - All endpoints admin-only (401 for unauthenticated, 403 for non-admin)
   - SQL injection protection via input sanitization

4. **Frontend UI** - COMPLETE
   - Collapsible "Generation Analytics" section in AdminDashboard showing: Dialogues Today, Gemini Calls (used/saved), Deepgram Minutes, Avg Cost/Episode, Batch Efficiency, Cache Hit Rate, Segmentation Rate
   - Collapsible "Generation Debug" section with: Creator ID/Episode ID filters, paginated runs table (ID, Episode, Dialogues, Batches, Gemini, Saved, Cache, Cost, Time, Fallback), expandable inline debug logs per run

## Key API Endpoints
- `POST /api/script/{episode_id}/dialogues` — Save structured dialogues
- `GET /api/script/{episode_id}/dialogues` — Load structured dialogues
- `POST /api/script/{episode_id}/generate` — Trigger batch generation (returns job_id + removed_clips)
- `GET /api/script/job/{job_id}/status` — Poll job progress (includes filename, character_name, cached status)
- `GET/POST /api/admin-9821/generation/limits` — System limits including batch_size
- `GET /api/admin-9821/analytics/generation/summary` — Global generation analytics
- `GET /api/admin-9821/analytics/generation/runs` — Generation runs list (filterable)
- `GET /api/admin-9821/analytics/generation/{id}/debug` — Debug logs for a run

## Nhost Configuration
- **Subdomain:** hybvrxpirbjtifwmbeyt
- **Region:** ap-south-1

## Upcoming Tasks (P0)
- Google OAuth configuration in Nhost Dashboard
- Data migration: MongoDB -> PostgreSQL (if needed)

## Future / Backlog (P1-P2)
- Waveform Visualization for audio clips
- PWA for listener experience
- Admin Portal: Storage Tracking, Rule Engine, System Health dashboard
- Refactor shared audio playback into usePlaybackEngine hook
- Cleanup deprecated files (db.py, models.py, old api.js)

## Credentials
- Admin: admin@admin.com / admin12345
- Creator: testuser@test.com / password123

## Technical Notes
- Gemini TTS: `gemini-2.5-flash-preview-tts` with `multiSpeakerVoiceConfig` for 2-speaker batches, single-speaker for fallback
- Deepgram: nova-3 model with diarize+utterances for speaker-labeled timestamps. API key in backend .env
- Speaker-pair batching: scan dialogues in order, start new batch on 3rd speaker, merge same-pair batches
- Clip extraction: frame-accurate WAV slicing at Deepgram timestamps (24kHz, 16-bit mono)
- Audio URLs: `nhost-file:{file_id}` (stable). Served via `GET /api/audio/stream-file/{file_id}`
- Frontend resolveAudioUrl: handles nhost-file:, legacy presigned URLs, and base64 data URLs
- Generation: strictly sequential using async httpx. Batches processed one at a time
- WAV validation: size > 1000 bytes + RIFF/WAVE header check. Retry up to 2 times on failure
- Job deduplication: one active generation job per episode. New job cancels existing
- Voice snapshot: `generated_voice_id` per dialogue, compared with character.voice_id on script load
