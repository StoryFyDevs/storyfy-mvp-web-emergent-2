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

## What's Been Implemented (Imported from GitHub)
- Full authentication system (Supabase Auth - signup, login, admin login)
- Creator dashboard with story/episode management
- Script editor with structured dialogue blocks
- Character management with voice assignment
- Voice generator with Gemini TTS (30 voice samples)
- Audio studio for clip arrangement
- Character-based batch pipeline (Gemini TTS → Deepgram → alignment → clips)
- Audio caching (SHA-256 based)
- Admin panel (creator management, usage analytics, voice settings, storage management)
- Mobile API (listener signup/login, browse stories, playback, progress tracking, library)
- Generation queue with rate limiting
- Storage cleanup scheduler

## Credentials
- Admin: admin@admin.com / admin12345
- Creator: testuser@test.com / password123

## Environment Setup (Jan 2026)
- Backend .env configured with Supabase URL, keys, Gemini API key
- Frontend .env configured with backend URL and Supabase client keys
- Both services running on Emergent platform (backend:8001, frontend:3000)

## Test Results
- Backend: Health, auth login (creator + admin), /me endpoint all passing
- Frontend: Login page, routing, auth redirects, signup page all passing
- Minor: Supabase rejects @test.com during new signup (built-in email validation)

## Changes Applied (Jan 2026)
- Confirmed all existing Supabase Auth users with emails via admin API
- Rewrote `register_supabase_user` to use Supabase Admin API (`admin.create_user` with `email_confirm: True`) so new signups are auto-confirmed — no email verification needed
- Both web signup and mobile listener signup benefit from the change

## Next Action Items
- None requested yet - awaiting user feedback

## Future / Backlog (P1-P2)
- Deepgram + ElevenLabs integration (keys not provided yet)
- Google OAuth configuration
- PWA for listener experience
- Waveform visualization for audio clips
- Admin Portal: Storage Tracking, Rule Engine, System Health dashboard
