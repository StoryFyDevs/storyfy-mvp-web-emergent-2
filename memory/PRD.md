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

## What's Been Implemented

### Session 1: GitHub Import (Jan 2026)
- Full app imported and configured
- Backend + frontend .env files created with Supabase and Gemini credentials
- Both services running on Emergent platform

### Session 2: Email Validation Fix
- Confirmed all existing Supabase Auth users via admin API
- Rewrote `register_supabase_user` to use Admin API with `email_confirm: True` — no email verification needed
- Both web and mobile signup paths auto-confirm

### Session 3: CORS & Login Fixes
- Fixed REACT_APP_BACKEND_URL for Emergent (empty for relative URLs via ingress)
- Fixed CORS: `allow_origin_regex=".*"` for proper origin reflection with credentials
- Removed `credentials: 'include'` from ALL frontend fetch calls (Bearer token auth doesn't need cookies)
- Added `API_BASE` import to Login.js, Signup.js, AuthCallback.js, App.js
- Created `.npmrc` with `legacy-peer-deps=true` for Vercel deployment
- Removed `package-lock.json` (project uses yarn)
- Fixed Vercel build: `CI=false craco build` to treat warnings as warnings
- Removed `emergentintegrations` and other unused packages from requirements.txt
- Created `vercel.json` for backend Vercel deployment

### Session 4: Dynamic DAW Timeline (Audio Studio Upgrade)
- **Removed fixed 60s timeline** — replaced `useState(60)` with `useMemo` computed from all clips
- **Dynamic timeline duration**: `max(clip.start + clip.duration) + 5s buffer`, minimum 30s
- **Added constants**: `TIMELINE_BUFFER = 5`, `MIN_TIMELINE_DURATION = 30`
- **Removed drag clamping** — clips can be dragged infinitely past timeline end
- **Auto-scroll during drag** — viewport scrolls when cursor near edges (±80px threshold)
- **Auto-expand** — timeline grows as clips are moved/added (via useMemo recalculation)
- **Timeline markers** adapt dynamically to computed duration
- **Playhead** syncs with full computed duration
- **Episode-scoped** — switching episodes recalculates timeline from that episode's clips
- **Zoom controls** — `1.00x` multiplier for pixelsPerSecond (configurable)

## Credentials
- Admin: admin@admin.com / admin12345
- Creator: testuser@test.com / password123
- Story ID: story_45f8bef2c25c

## Test Results
- Backend: All endpoints working (health, auth, episodes, characters, project state)
- Frontend: Login, dashboard, studio navigation, Audio Studio all working
- Audio Studio: Dynamic timeline, markers, transport bar, zoom, tracks all rendering correctly
- CORS: Fixed for both Emergent (relative URLs) and Vercel (specific origins)

## Next Action Items
- Test with actual audio clips to verify timeline expansion > 60s
- Test clip dragging and auto-scroll behavior with real content

## Future / Backlog (P1-P2)
- Deepgram + ElevenLabs integration (keys not provided yet)
- Google OAuth configuration
- PWA for listener experience
- Waveform visualization for audio clips
- Virtual clip rendering for performance (large timelines)
- Zoom level presets UI
