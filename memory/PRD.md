# StoryFy PRD - Product Requirements Document

## Original Problem Statement
Build a full-stack storytelling platform (StoryFy) that enables creators to produce audio stories using AI-powered TTS (Text-to-Speech). The platform supports character creation, script editing, audio generation via Gemini TTS, and an audio studio for editing/arranging clips.

## Current Architecture
- **Frontend**: React + TailwindCSS + Shadcn/UI
- **Backend**: FastAPI + Supabase (PostgreSQL)
- **Auth**: Supabase Auth with JWT tokens
- **TTS Engine**: Gemini 2.5 Flash Preview TTS (primary)
- **Storage**: Supabase Storage for audio files
- **Job Queue**: In-memory async worker with round-robin scheduling

## Key User Flows
1. Creator creates a Story → Episodes → Characters (with voice assignments)
2. Writes script (Narration Mode or Dialogue Mode)
3. Generates audio via Gemini TTS
4. Arranges audio in Audio Studio
5. Renders final audio → Publishes

## What's Been Implemented

### Core Systems (Complete)
- User authentication (signup, login, JWT)
- Story CRUD with publishing
- Episode CRUD with ordering
- Character management with voice assignments
- 30 Gemini TTS voices with display names and categories
- Voice preview/audition system

### Audio Generation Pipeline (Complete)
- Global fair-queue generation system with rate limiting
- Per-dialogue and batch generation with caching
- Audio clip registration in `audio_clips` table
- Generation job tracking with polling

### Credit & Access Control (Complete)
- Generation credits system
- Audition credits system
- Admin master switch for user audio access (`generation_status`)
- Rate limiting (RPM, RPD, TPM)

### Audio Studio (Complete)
- Multi-track timeline editor (Web Audio API)
- Clip arrangement, trimming
- Deterministic clip loading from backend API (`GET /api/episodes/{id}/clips`)
- Version-aware audio buffer caching (prevents stale audio playback)
- Cache-busting on audio URLs (?v=versionHash)
- Chunked render + upload to Supabase Storage
- Project state persistence

### Admin Panel (Complete)
- Creator management (status, credits, limits)
- Generation controls (RPD, RPM, TPM, batch size)
- Voice engine settings
- Usage analytics and logs
- Storage management
- Dialogue mode global toggle

### Narration-first Workflow (Complete - March 25, 2026)
- **Tab Reorder**: Characters → Script Editor → Audio Studio → Voice Generator
- **Narration Mode** (default in Script Editor)
- **Dialogue Mode** (advanced, behind admin toggle)
- Backend endpoints for narration save/load/generate

### Stale Audio Bug Fix (Complete - March 25, 2026)
- **Root Cause**: Race condition between two `register_clip` functions — fire-and-forget OLD one deactivated synchronized NEW one
- **Fix 1**: Removed duplicate `asyncio.create_task(sc_storage.register_clip)` calls from `_generate_single_dialogue` and `_generate_character_batch`
- **Fix 2**: Changed `Cache-Control` from `max-age=86400` to `no-cache, must-revalidate` on `/api/audio/stream-file`
- **Fix 3**: Added version-aware buffer caching in AudioStudio (`bufferKey = clip.id + '_' + clip.versionHash`)
- **Fix 4**: Clear all audio buffers when loading new project
- **Fix 5**: Added `?v=` cache-busting parameter to audio stream URLs

## Pending / Backlog

### P1 - Upcoming
- Zoom System for Audio Studio (pixelsPerSecond controls)
- Zoom-to-Fit button for Audio Studio

### P2 - Future
- Clean up legacy `db.py` (MongoDB remnant)
- Fix ESLint `react-hooks/exhaustive-deps` warnings
- Fix admin panel loading issue (pre-existing)

### P3 - Backlog
- Performance Monitor Overlay
- Deepgram + ElevenLabs integration
- Google OAuth & PWA

## Key API Endpoints
- `GET /api/episodes/{episode_id}/clips` - Audio Studio clip source of truth
- `GET/POST /api/script/{episode_id}/script-data` - Mode-aware script data
- `POST /api/script/{episode_id}/narration/generate` - Narration generation
- `POST /api/script/{episode_id}/generate` - Dialogue generation
- `GET /api/audio/stream-file/{file_id}` - Audio streaming (no-cache)
- `PATCH /api/admin-9821/users/{user_id}/audio-access` - Master toggle
- `GET/POST /api/admin-9821/settings/dialogue-mode` - Dialogue mode setting

## Test Credentials
- Creator: `testuser@test.com` / `password123`
- Admin: `admin@admin.com` / `admin12345`
- Affected user: `harshil.zalavadiya02@gmail.com` / `12345678`
