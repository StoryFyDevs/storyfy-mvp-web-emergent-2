# StoryFy Mobile API Documentation

**Base URL:** `https://<your-backend-domain>/api/mobile`

> All endpoints are prefixed with `/api/mobile`. Do **not** use `/api/stories`, `/api/creator/*`, or any other path — those are for the creator web app only.

---

## Authentication

Listeners can browse ALL content **without authentication**. Auth is required only for saving progress and getting personalized data (continue listening).

Listener auth (`/api/mobile/auth/*`) is **completely separate** from creator auth (`/api/auth/*`). Creator accounts cannot log in via the mobile endpoints, and listener accounts cannot log in via the creator web app.

### Signup
```
POST /api/mobile/auth/signup
Content-Type: application/json

Body: { "email": "user@email.com", "password": "pass123", "name": "John" }
Response: { "token": "jwt...", "listener_id": "listener_xxx", "email": "...", "name": "..." }

Errors:
  409 — Email already registered
```

### Login
```
POST /api/mobile/auth/login
Content-Type: application/json

Body: { "email": "user@email.com", "password": "pass123" }
Response: { "token": "jwt...", "listener_id": "listener_xxx", "email": "...", "name": "..." }

Errors:
  401 — Invalid email or password
  403 — Not a listener account (creator accounts are rejected here)
```

**Auth Header for authenticated endpoints:** `Authorization: Bearer <token>`

---

## Public Endpoints (No Auth Required)

### 1. Home Feed
```
GET /api/mobile/home
Optional Header: Authorization: Bearer <token>  (enables continue_listening)

Response:
{
  "trending": [{ "story_id", "title", "description", "genre", "cover_art_url", "total_episodes", "total_duration_seconds", "play_count", "creator_name" }],
  "latest": [same shape],
  "continue_listening": [{ "episode_id", "episode_title", "story_id", "story_title", "cover_art_url", "current_time", "duration", "progress_percent" }]
}
```

### 2. Browse Stories
```
GET /api/mobile/stories?genre=fiction&language=English&sort=popular&page=1&limit=20

sort options: "latest" (default), "popular", "title"

Response:
{
  "stories": [{ "story_id", "title", "description", "genre", "language", "cover_art_url", "total_episodes", "total_duration_seconds", "play_count", "creator_name" }],
  "total": 8, "page": 1, "limit": 20, "total_pages": 1
}
```

### 3. Story Details
```
GET /api/mobile/stories/{story_id}
Optional Header: Authorization: Bearer <token>  (for episode progress)

Response:
{
  "story_id", "title", "description", "genre", "language", "cover_art_url", "story_type",
  "creator_name", "total_episodes", "total_duration_seconds", "play_count",
  "episodes": [{
    "episode_id", "title", "episode_number", "duration",
    "audio_url": "https://...",  // direct Supabase Storage public URL — play directly
    "has_audio": true,
    "progress_seconds": 45.5    // only present if authenticated
  }]
}
```

### 4. Episode Playback
```
GET /api/mobile/episodes/{episode_id}
Optional Header: Authorization: Bearer <token>  (for resume_at)

Response:
{
  "episode_id", "title", "episode_number",
  "story_id", "story_title", "cover_art_url",
  "audio_url": "https://xyz.supabase.co/storage/v1/object/public/...",
  "duration": 120,
  "resume_at": 45.5,           // seconds (0 if no auth/progress)
  "next_episode_id": "ep_xxx", // null if last
  "prev_episode_id": "ep_xxx"  // null if first
}
```

> **Audio URLs** are direct Supabase Storage public HTTPS URLs. Pass them straight to your audio player — no authentication header needed, no proxying required.

**Note:** Each call increments play_count.

### 5. Search
```
GET /api/mobile/search?q=keyword&page=1&limit=20

Response:
{
  "results": [{ "story_id", "title", "description", "genre", "total_episodes", "creator_name", "play_count" }],
  "total": 5, "query": "keyword", "page": 1, "total_pages": 1
}
```

### 6. Genres & Languages (for filter UI)
```
GET /api/mobile/genres      → ["fiction", "thriller", ...]
GET /api/mobile/languages   → ["English", "Hindi", ...]
```

---

## Authenticated Endpoints (Token Required)

### 7. Save Progress
```
POST /api/mobile/progress
Authorization: Bearer <token>
Content-Type: application/json

Body: { "episode_id": "ep_xxx", "current_time": 45.5, "duration": 120 }
Response: { "message": "Progress saved", "episode_id": "ep_xxx", "current_time": 45.5 }
```

### 8. Get All Progress
```
GET /api/mobile/progress
Authorization: Bearer <token>

Response: [{
  "episode_id", "current_time", "duration",
  "episode_title", "episode_number",
  "story_id", "story_title", "cover_art_url",
  "progress_percent": 37.9,
  "updated_at": "2026-02-23T..."
}]
```

### 9. Track Analytics
```
POST /api/mobile/analytics/play
Optional Header: Authorization: Bearer <token>
Content-Type: application/json

Body: { "episode_id": "ep_xxx", "event_type": "play|pause|complete|drop_off", "position_seconds": 0 }
Response: { "message": "Event tracked" }
```

---

## Auth Separation Summary

| App | Login Endpoint | Role |
|-----|---------------|------|
| Expo mobile app | `POST /api/mobile/auth/login` | `listener` only |
| Creator web app | `POST /api/auth/login` | `creator` or `admin` only |

- A **creator** account trying to log in at `/api/mobile/auth/login` gets `403 Not a listener account`
- A **listener** account trying to log in at `/api/auth/login` gets `401 Listener accounts must use the mobile app`

---

## Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Listener | listener@test.com | listen123 |
| Creator | admin@admin.com | admin12345 |

---

## Error Codes
- `401` — Invalid credentials or missing token
- `403` — Wrong account type for this login endpoint; or account suspended
- `404` — Story/Episode not found
- `409` — Email already registered (signup)
- `429` — Too many attempts, wait a moment

## Notes
- All timestamps are UTC ISO format
- Pagination: `page` starts at 1, default `limit` is 20
- `audio_url` is always an absolute `https://` URL or `null` — never a relative path
- Only content with `status: "published"` is returned — draft content is never exposed
