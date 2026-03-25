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
- **Narration Mode** (default in Script Editor):
  - Narrator voice selector from 30 available voices
  - 15,000 character limit per part (text + notes combined)
  - Live character counter (X / 15,000)
  - Director's Notes (optional) per part
  - "+ Add Next Part" chunking (Part 1, Part 2, etc.)
  - Friendly warning messages when nearing/exceeding limit
  - Single Gemini TTS call per part
- **Dialogue Mode** (advanced, behind admin toggle):
  - Multi-character dialogue system preserved
  - Gated by `dialogue_mode_enabled` admin setting
  - "Coming Soon" dialog when disabled (visible but blocked)
  - Credit usage warning when enabled
- **Backend Endpoints**:
  - `GET/POST /api/script/{episode_id}/script-data` - Mode-aware save/load
  - `POST /api/script/{episode_id}/narration/generate` - Narration audio gen
  - `GET /api/settings/dialogue-mode` - Public dialogue mode check
  - `GET/POST /api/admin-9821/settings/dialogue-mode` - Admin toggle

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
- `PATCH /api/admin-9821/users/{user_id}/audio-access` - Master toggle
- `GET/POST /api/admin-9821/settings/dialogue-mode` - Dialogue mode setting

## Key DB Tables
- `audio_clips`: clip_id, dialogue_id, episode_id, dialogue_index, version_hash, audio_url, is_active
- `user_profiles`: user_id, generation_credits, audition_credits, generation_status
- `script_generation_jobs`: job_id, user_id, episode_id, status
- `voice_settings`: setting_id, active_provider (used for dialogue_mode too)

## Test Credentials
- Creator: `testuser@test.com` / `password123`
- Admin: `admin@admin.com` / `admin12345`
