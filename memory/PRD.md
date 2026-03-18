# StoryFy - Product Requirements Document

## Original Problem Statement
Import StoryFy app from GitHub - a full-stack audio storytelling platform for creators featuring multi-provider voice engine (Gemini TTS + ElevenLabs), character-centric voice generation, script editor, audio studio, admin panel, and mobile API.

## Architecture
- **Frontend:** React 19, TailwindCSS, Shadcn/UI, Framer Motion
- **Backend:** FastAPI, Supabase (PostgreSQL + Storage + Auth)
- **Voice Providers:** Gemini 2.5 Flash Preview TTS (primary), ElevenLabs (switchable)
- **Audio Pipeline:** Gemini TTS → Deepgram transcription → text alignment → clip extraction
- **Auth:** Supabase Auth (email/password + Google OAuth)
- **Storage:** Supabase Storage (audio files, voice samples, script clips)
- **Queue System:** Global rate-aware fair queue (queue_worker.py) with round-robin scheduling

## What's Been Implemented

### Session 1: GitHub Import (Jan 2026)
- Full app imported and configured
- Backend + frontend .env files created with Supabase and Gemini credentials
- Both services running on Emergent platform

### Session 2: Email Validation Fix
- Confirmed all existing Supabase Auth users via admin API
- Rewrote `register_supabase_user` to use Admin API with `email_confirm: True`

### Session 3: CORS & Login Fixes
- Fixed REACT_APP_BACKEND_URL for Emergent (empty for relative URLs via ingress)
- Fixed CORS: `allow_origin_regex=".*"` for proper origin reflection with credentials
- Removed `credentials: 'include'` from ALL frontend fetch calls
- Created `.npmrc` with `legacy-peer-deps=true` for Vercel deployment
- Fixed Vercel build: `CI=false craco build`
- Created `vercel.json` for backend Vercel deployment

### Session 4: Dynamic DAW Timeline (Audio Studio Upgrade)
- Removed fixed 60s timeline — replaced with dynamic computed duration
- Dynamic timeline duration: `max(clip.start + clip.duration) + 5s buffer`, minimum 30s
- Auto-scroll during drag, auto-expand, zoom controls

### Session 5: Audio Studio Performance Optimization (Mar 2026)
- Decoupled playhead from React state using requestAnimationFrame + direct DOM manipulation
- GPU-accelerated clip positioning with transform: translateX()
- Deterministic waveform visualization with seeded Math.sin()
- Optimized drag handler using direct DOM manipulation
- Viewport-based clip virtualization
- Throttled scroll handler via requestAnimationFrame

### Session 6: Global Generation Queue System (Mar 2026)
- **Created `/app/backend/queue_worker.py`**: Complete global queue worker with:
  - `RateLimiter` class: Enforces Gemini API limits (RPM=10, RPD=50, TPM=10000)
  - `FairScheduler` class: Round-robin per-user scheduling so no user monopolizes the queue
  - Background worker loop: Continuously processes jobs sequentially
  - Exponential backoff retry: 5s → 10s → 20s, max 3 attempts
  - Startup recovery: Loads pending jobs from DB on server restart
  - `acquire_gemini_slot()` / `release_gemini_slot()`: Shared rate limiter used by both queue worker AND batch generation in script_compiler.py
- **Modified regeneration endpoint** (`POST /api/script/{episode_id}/dialogue/{index}/regenerate`):
  - Now queues a job and returns `{status: "queued", job_id}` immediately (non-blocking)
  - No more 503/timeout errors from synchronous Gemini calls
- **New job status endpoint** (`GET /api/jobs/{job_id}`):
  - Returns status, queue position, queue size, and result when completed
- **Integrated global rate limiter into all Gemini TTS calls**:
  - `script_compiler.py._call_gemini_tts()` now waits for a rate-limit slot before calling Gemini
  - `creator.py._gemini_generate_speech()` (audition/direct TTS) also uses the global rate limiter
- **Updated admin queue endpoint**: Returns live in-memory queue stats + DB stats
- **Frontend ScriptEditor.js**: Regeneration now uses polling:
  - Shows "Your audio is in queue" / "N jobs ahead of you" / "Processing your audio..."
  - Automatically updates timeline when job completes
- **Testing**: 12/12 tests passed (iteration_36.json) - all backend + frontend verified

## Credentials
- Admin: admin@admin.com / admin12345
- Creator: testuser@test.com / password123
- Story ID: story_45f8bef2c25c

## Test Results
- Backend: All endpoints working (health, auth, queue, regeneration, job status)
- Frontend: Login, dashboard, studio navigation, Audio Studio, ScriptEditor all working
- Queue: Jobs processed sequentially, fair scheduling verified, rate limiting active
- Previous tests: Audio Studio performance verified (iteration_35), Queue system verified (iteration_36)

## Next Action Items
- P1: Add Zoom System to Audio Studio
- P2: Add "Zoom-to-Fit" button
- P2: Fix ESLint `react-hooks/exhaustive-deps` warnings

## Future / Backlog (P1-P2)
- Deepgram + ElevenLabs integration (keys not provided yet)
- Google OAuth configuration
- PWA for listener experience
- Canvas-based waveform rendering (optional high-impact)
- Virtual clip rendering for extremely large timelines (1000+ clips)
- Zoom level presets UI
- Audio engine separation (Web Audio on separate thread via AudioWorklet)
- Performance Monitor Overlay (dev FPS/render count)
- Replace localStorage message bus with proper state management (Zustand/Context)
