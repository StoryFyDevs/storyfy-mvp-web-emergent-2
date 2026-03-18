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
- **Decoupled playhead from React state** — uses `requestAnimationFrame` + direct DOM manipulation via refs (`playheadRef`, `playheadLabelRef`, `transportTimeRef`) during playback. Zero React re-renders during playback.
- **GPU-accelerated clip positioning** — replaced CSS `left` with `transform: translateX()` on all clips. Added `will-change: transform` during drag.
- **Deterministic waveform visualization** — replaced `Math.random()` with seeded `Math.sin()` + `clip.id.charCodeAt()` hash. Waveforms are now stable across re-renders.
- **Optimized drag handler** — uses direct DOM manipulation via `dragClipRef` during drag. `updateClip` called once on mouseup (single re-render). Previous: `updateClip` called ~60 times/sec.
- **Viewport-based clip virtualization** — only renders clips visible in the viewport (±300px buffer). Off-screen clips skip DOM rendering entirely.
- **Throttled scroll handler** — scroll events throttled via `requestAnimationFrame`. Max one `setScrollLeft` state update per frame.
- **Auto-scroll moved to rAF loop** — removed React `useEffect` dependency on `playheadPosition`. Auto-scroll now runs inside the playback `requestAnimationFrame` loop.
- **Fixed `audioBufferCache.current` bug** — undefined variable reference in clip replacement detector. Replaced with proper cleanup.
- **Added `will-change` hints** — `will-change: transform` on playhead, `will-change: scroll-position` on timeline viewport.

## Credentials
- Admin: admin@admin.com / admin12345
- Creator: testuser@test.com / password123
- Story ID: story_45f8bef2c25c

## Test Results
- Backend: All endpoints working (health, auth, episodes, characters, project state)
- Frontend: Login, dashboard, studio navigation, Audio Studio all working
- Audio Studio: 18 clips across 7 tracks rendering correctly with all performance optimizations
- Performance: All 8 optimization categories verified by testing agent (iteration_35)
- Previous "Loading your studio..." stuck issue from iteration_34: RESOLVED

## Next Action Items
- Clip regeneration system verification (seed test data for testuser)
- Add zoom-to-fit button for Audio Studio
- Performance testing with 50+ synthetic clips

## Future / Backlog (P1-P2)
- Deepgram + ElevenLabs integration (keys not provided yet)
- Google OAuth configuration
- PWA for listener experience
- Canvas-based waveform rendering (optional high-impact)
- Fix ESLint `react-hooks/exhaustive-deps` warnings across codebase
- Virtual clip rendering for extremely large timelines (1000+ clips)
- Zoom level presets UI
- Audio engine separation (Web Audio on separate thread via AudioWorklet)
