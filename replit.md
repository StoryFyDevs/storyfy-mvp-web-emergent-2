# StoryFy

A full-stack audio story creation platform built with React (frontend) and FastAPI (Python backend).

## Architecture

- **Frontend**: React (Create React App + CRACO), runs on port 5000
- **Backend**: FastAPI (Python), runs on port 8000
- **Auth**: Supabase Auth (email/password + Google OAuth)
- **Database**: Supabase PostgreSQL via PostgREST
- **Storage**: Supabase Storage (buckets: storyfy-audio, storyfy-cache, storyfy-exports)

## Project Structure

```
frontend/       React app (CRA + CRACO)
  src/
    pages/      Route-level pages
    components/ Shared components (LoadingScreen, etc.)
    contexts/   StudioContext — shared state for studio tabs (episodes, characters, voices)
    lib/        Supabase client config (supabase.js)
  plugins/      Visual edits + health check plugins
backend/        FastAPI app
  routers/      auth, creator, admin, mobile
  server.py     Main FastAPI app
  auth_service.py     Supabase Auth SDK — register, login, token verify, profile sync
  supabase_db.py      PostgREST CRUD client
  supabase_storage.py Supabase Storage client
  script_compiler.py  Audio generation pipeline
  storage_cleanup.py  Storage lifecycle management
  generation_queue.py Background generation
  requirements.txt
migration_backups/
  nhost_full_backup.json    320+ rows backed up from Nhost
  supabase_schema.sql       Full DDL — run in Supabase SQL Editor
  migrate_to_supabase.py    Data migration script
```

## Environment Variables

### Frontend (.env)
- `PORT=5000` — Dev server port
- `REACT_APP_BACKEND_URL` — URL of the FastAPI backend
- `REACT_APP_NHOST_SUBDOMAIN` — Nhost project subdomain (auth still uses Nhost)
- `REACT_APP_NHOST_REGION` — Nhost project region

### Backend (Replit Secrets)
- `SUPABASE_URL` — Supabase project URL (https://kuophclrijrriufdzbks.supabase.co)
- `SUPABASE_SERVICE_ROLE_KEY` — Supabase service role key (full DB access)
- `SUPABASE_ANON_KEY` — Supabase anon key
- `SUPABASE_DB_PASSWORD` — Supabase DB password
- `SUPABASE_BUCKET_AUDIO` — Audio bucket name (storyfy-audio)
- `SUPABASE_BUCKET_CACHE` — Cache bucket name (storyfy-cache)
- `SUPABASE_BUCKET_EXPORTS` — Exports bucket name (storyfy-exports)
- `NHOST_SUBDOMAIN` — Nhost project subdomain (auth)
- `NHOST_REGION` — Nhost project region (auth)
- `NHOST_ADMIN_SECRET` — Hasura admin secret (auth)
- `GEMINI_API_KEY` — Google Gemini API key
- `DEEPGRAM_API_KEY` — Deepgram API key
- `CORS_ORIGINS` — Allowed CORS origins (default: *)

## Running

- Frontend: `cd frontend && npm start` (port 5000)
- Backend: `cd backend && uvicorn server:app --host 0.0.0.0 --port 8000`

## Supabase Migration Status

### Completed
- [x] Nhost data backed up (320+ rows across 17 tables → nhost_full_backup.json)
- [x] Supabase schema DDL written (supabase_schema.sql)
- [x] supabase_db.py written and wired (PostgREST drop-in for nhost_db.py)
- [x] supabase_storage.py written and wired (Supabase Storage drop-in)
- [x] All imports in server.py, routers/, script_compiler.py, storage_cleanup.py, generation_queue.py updated
- [x] Admin analytics endpoints rewritten to use PostgREST (no raw SQL)
- [x] Server startup DDL replaced with connectivity check
- [x] Data migration script written (migrate_to_supabase.py)
- [x] Backend restarts cleanly with Supabase

### Pending (user action required)
- [ ] Run `migration_backups/supabase_schema.sql` in Supabase SQL Editor
- [ ] Confirm 3 storage buckets exist: storyfy-audio, storyfy-cache, storyfy-exports
- [ ] Run data migration: `cd migration_backups && python migrate_to_supabase.py`
- [ ] End-to-end test of audio generation

## Audio URL Convention

Audio files use `nhost-file:{bucket}/{path}` prefix convention throughout the codebase.
`supabase_storage.resolve_audio_url()` converts this to a public HTTPS URL when needed.

## Notes

- `emergentintegrations` in requirements.txt is not used in code — skip
- Direct Postgres access from Replit is blocked (IPv6/pooler issues) — all DB ops go through PostgREST
- Nhost auth (JWT) is kept — only the database and storage layers migrated to Supabase
