# StoryFy Mobile API Documentation

**Base URL:** `/api/mobile`

---

## Authentication

Listeners can browse ALL content **without authentication**. Auth is required only for saving progress and getting personalized data (continue listening).

### Signup
```
POST /api/mobile/auth/signup
Content-Type: application/json

Body: { "email": "user@email.com", "password": "pass123", "name": "John" }
Response: { "token": "jwt...", "listener_id": "listener_xxx", "email": "...", "name": "..." }
```

### Login
```
POST /api/mobile/auth/login
Content-Type: application/json

Body: { "email": "user@email.com", "password": "pass123" }
Response: { "token": "jwt...", "listener_id": "listener_xxx", "email": "...", "name": "..." }
```

**Auth Header:** `Authorization: Bearer <token>`

---

## Public Endpoints (No Auth Required)

### 1. Home Feed
```
GET /api/mobile/home
Optional Header: Authorization: Bearer <token>  (for continue_listening)

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
    "episode_id", "title", "episode_number", "duration", "audio_url", "has_audio",
    "progress_seconds": 45.5   // only if authenticated
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
  "audio_url": "https://...",  // streaming URL
  "duration": 120,
  "resume_at": 45.5,           // seconds (0 if no auth/progress)
  "next_episode_id": "ep_xxx", // null if last
  "prev_episode_id": "ep_xxx"  // null if first
}
```
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

## Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Listener | listener@test.com | listen123 |
| Creator (admin panel) | admin@admin.com | admin123 |

## Error Codes
- `401` — Authentication required (for progress endpoints)
- `404` — Story/Episode not found
- `409` — Email already registered (signup)

## Notes
- All timestamps are UTC ISO format
- Pagination: `page` starts at 1, default `limit` is 20
- Audio URLs may be base64 data URIs or external URLs depending on how creators uploaded
- Only content with `status: "published"` is returned — draft content is never exposed
