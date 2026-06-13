# StoryFy PRD - Production Requirements

## Original Problem Statement
StoryFy is an AI-powered audio storytelling platform where creators write scripts (narration or dialogue), assign character voices, and generate professional-quality audio using Gemini TTS.

## Architecture
- **Frontend**: React + TailwindCSS + Shadcn UI
- **Backend**: FastAPI + Supabase (PostgreSQL + Object Storage)
- **TTS Engine**: Google Gemini 2.5 Pro TTS via Vertex AI (`us-central1`)
- **Auth**: Supabase Auth with Bearer token + Password Reset
- **Queue**: In-memory FairScheduler + Supabase `generation_queue` table

## Core Features (Implemented)
- [x] User auth (login/signup/Google OAuth)
- [x] **Password Reset Flow** (Feb 2026) — Forgot password, email reset link, new password form with strength meter
- [x] Story & episode management (CRUD)
- [x] Character management with voice assignments
- [x] Narration-first Script Editor (15k char limit, chunking, director's notes)
- [x] Dialogue Mode (admin-toggle gated)
- [x] Audio generation via Gemini TTS (Vertex AI us-central1 endpoint, Service Account Bearer auth)
- [x] Audio Studio with timeline, playback, Web Audio API
- [x] Voice Generator (voice auditions)
- [x] Admin panel (generation limits, credits, analytics, user management)
- [x] **Global Generation Queue System** (Feb 2026)
  - Centralized FIFO queue with FairScheduler (round-robin per-user)
  - Rate limiter reading admin-configurable RPM/RPD/TPM
  - Batch job types: narration_batch, dialogue_batch, regenerate
  - Persistent floating status widget across all studio tabs
  - Admin live queue monitor with real-time rate limiter stats
- [x] **Generation Version Review Workflow** (Feb 2026)
  - Multiple versions per Part (max 5, enforced)
  - New generations create unselected versions (first auto-selects)
  - Creator review UI with play button, duration, timestamp, labels
  - "Use This Version" to select for episode
  - Audio Studio only loads selected (is_active=true) versions
  - 30-day retention cleanup for unselected old versions
  - Friendly labels: Latest, Selected for Episode, Previous Version
- [x] **Hard Regenerate** (Jun 2026)
  - Per-Part overflow menu (•••) → "Hard Regenerate" advanced action
  - Forces a brand-new version (cache bypass via nonce in cache_key)
  - Confirmation dialog; enters same queue; respects credits/limits/max-5
  - NEVER auto-selects new version; existing selection + Audio Studio unchanged until creator manually selects

## Key Endpoints
- `POST /api/script/{episode_id}/generate` → dialogue batch queue submission
- `POST /api/script/{episode_id}/narration/generate` → narration batch queue submission
- `GET /api/episodes/{episode_id}/versions` → all versions grouped by part
- `POST /api/episodes/{episode_id}/versions/{clip_id}/select` → select version
- `POST /api/episodes/{episode_id}/versions/{clip_id}/deselect` → deselect version
- `GET /api/episodes/{episode_id}/clips` → only selected (is_active=true) clips
- `POST /api/script/{episode_id}/narration/part/{part_number}/hard-regenerate` → force a fresh, unselected version for a single Part (Hard Regenerate)
- `GET /api/jobs/active` → user's active/recent jobs
- `POST /api/auth/forgot-password` → send reset email
- `POST /api/auth/reset-password` → update password
- `GET /api/admin-9821/generation/queue` → live queue stats

## Key Files
- `/app/backend/queue_worker.py` — Global queue with FairScheduler + RateLimiter
- `/app/backend/script_compiler.py` — Core TTS + version management (register_clip)
- `/app/backend/vertex_auth.py` — Vertex AI Bearer token authentication
- `/app/backend/routers/creator.py` — Creator endpoints + version management
- `/app/backend/routers/auth.py` — Auth + password reset
- `/app/backend/routers/admin.py` — Admin panel endpoints
- `/app/backend/storage_cleanup.py` — 30-day version retention cleanup
- `/app/frontend/src/contexts/GenerationStatusContext.js` — Global job tracking
- `/app/frontend/src/components/GenerationStatusWidget.js` — Persistent status widget
- `/app/frontend/src/pages/ScriptEditor.js` — Script editor + version review UI
- `/app/frontend/src/pages/ForgotPassword.js` — Forgot password page
- `/app/frontend/src/pages/ResetPassword.js` — Reset password page
- `/app/frontend/src/pages/AudioStudio.js` — Audio timeline + playback

## DB Schema (Key Tables)
- `audio_clips`: file_id, audio_url, episode_id, dialogue_index, voice_id, cache_key, is_active, pending_deletion, created_at
  - `is_active=true` = selected version (shown in Audio Studio)
  - `is_active=false` = unselected version (only in review UI)
- `generation_queue`: queue_id, user_id, request_type, request_data, status
- `script_generation_jobs`: job_id, episode_id, user_id, status, total_dialogues, completed_dialogues

## Pending Issues
- P2: ESLint react-hooks/exhaustive-deps warnings
- P3: Legacy /app/backend/db.py cleanup

## Upcoming Tasks
- P1: Zoom System for Audio Studio (pixelsPerSecond controls)
- P1: Zoom-to-Fit button for Audio Studio
- P2: Admin Dashboard analytics routes fix

## Future / Backlog
- P3: Performance Monitor Overlay
- P3: Deepgram + ElevenLabs integration
- P3: PWA implementation

## Production Deployment
- Domain: https://www.storyfy.in
- Supabase project: kuophclrijrriufdzbks
- GCP Project: gen-lang-client-0988882713
- Vertex AI Region: us-central1
- Important: Add `https://www.storyfy.in/**` to Supabase Redirect URLs for password reset
