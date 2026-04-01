# StoryFy PRD - Production Requirements

## Original Problem Statement
StoryFy is an AI-powered audio storytelling platform where creators write scripts (narration or dialogue), assign character voices, and generate professional-quality audio using Gemini TTS.

## Architecture
- **Frontend**: React + TailwindCSS + Shadcn UI
- **Backend**: FastAPI + Supabase (PostgreSQL + Object Storage)
- **TTS Engine**: Google Gemini 2.5 Pro TTS via Vertex AI (`us-central1`)
- **Auth**: Supabase Auth with Bearer token
- **Queue**: In-memory FairScheduler + Supabase `generation_queue` table

## Core Features (Implemented)
- [x] User auth (login/signup/Google OAuth)
- [x] Story & episode management (CRUD)
- [x] Character management with voice assignments
- [x] Narration-first Script Editor (15k char limit, chunking, director's notes)
- [x] Dialogue Mode (admin-toggle gated)
- [x] Audio generation via Gemini TTS (Vertex AI us-central1 endpoint)
- [x] Audio Studio with timeline, playback, Web Audio API
- [x] Voice Generator (voice auditions)
- [x] Admin panel (generation limits, credits, analytics, user management)
- [x] **Global Generation Queue System** (Feb 2026)
  - Centralized FIFO queue with FairScheduler (round-robin per-user)
  - Rate limiter reading admin-configurable RPM/RPD/TPM
  - Batch job types: narration_batch, dialogue_batch, regenerate
  - Persistent floating status widget across all studio tabs
  - Admin live queue monitor with real-time rate limiter stats
  - Auto-retry with exponential backoff (3 attempts)
  - Job recovery on server restart

## Key Endpoints
- `POST /api/script/{episode_id}/generate` → submits dialogue batch to queue
- `POST /api/script/{episode_id}/narration/generate` → submits narration batch to queue
- `GET /api/jobs/active` → returns user's active/recent jobs with positions
- `GET /api/jobs/{job_id}` → single job status
- `GET /api/admin-9821/generation/queue` → live queue stats
- `GET /api/admin-9821/generation/limits` → RPM/RPD/TPM config
- `POST /api/admin-9821/generation/limits` → update limits

## Key Files
- `/app/backend/queue_worker.py` — Global queue with FairScheduler + RateLimiter
- `/app/backend/script_compiler.py` — Core TTS generation logic
- `/app/backend/vertex_auth.py` — Vertex AI Bearer token authentication
- `/app/backend/routers/creator.py` — Creator endpoints
- `/app/backend/routers/admin.py` — Admin panel endpoints
- `/app/frontend/src/contexts/GenerationStatusContext.js` — Global job tracking
- `/app/frontend/src/components/GenerationStatusWidget.js` — Persistent status widget
- `/app/frontend/src/pages/ScriptEditor.js` — Script editor (Narration + Dialogue modes)
- `/app/frontend/src/pages/AudioStudio.js` — Audio timeline + playback
- `/app/frontend/src/pages/StudioLayout.js` — Studio wrapper with GenerationStatusProvider

## DB Schema (Key Tables)
- `audio_clips`: clip_id, dialogue_id, episode_id, dialogue_index, version_hash, audio_url, is_active
- `user_profiles`: user_id, generation_credits, audition_credits, generation_status
- `generation_queue`: queue_id, user_id, request_type, request_data, status, error_message, result_data
- `script_generation_jobs`: job_id, episode_id, user_id, status, total_dialogues, completed_dialogues

## Pending Issues
- P2: ESLint react-hooks/exhaustive-deps warnings (4+ recurrences)
- P3: Legacy /app/backend/db.py cleanup (MongoDB remnant)

## Upcoming Tasks
- P1: Zoom System for Audio Studio (pixelsPerSecond controls)
- P1: Zoom-to-Fit button for Audio Studio
- P2: Admin Dashboard analytics routes fix (ERR_ABORTED on /api/admin-9821/stats)

## Future / Backlog
- P3: Performance Monitor Overlay (developer FPS view)
- P3: Deepgram + ElevenLabs integration
- P3: PWA implementation
