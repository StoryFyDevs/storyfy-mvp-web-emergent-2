from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional
from datetime import datetime, timezone
import uuid
import bcrypt
import jwt

from db import db, create_jwt_token, JWT_SECRET, JWT_ALGORITHM, logger, supabase_admin, AUDIO_BUCKET_NAME
from models import ListenerSignup, ListenerLogin, ProgressSave, PlayEventCreate, LibrarySave

mobile_v1_router = APIRouter(prefix="/api/v1/mobile", tags=["mobile_v1"])

# ============ MOBILE AUTH HELPERS ============

def _get_signed_audio_url(storage_path: str) -> str:
    """Generate a signed URL for audio streaming (valid 2 hours)."""
    if not storage_path:
        return None
    try:
        result = supabase_admin.storage.from_(AUDIO_BUCKET_NAME).create_signed_url(storage_path, 7200)
        return result.get("signedURL") or result.get("signedUrl") or None
    except Exception as e:
        logger.error(f"Signed URL error for {storage_path}: {e}")
        return None

async def get_optional_listener(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if not authorization:
        return None
    try:
        token = authorization.split(' ')[1] if authorization.startswith('Bearer ') else authorization
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") == "listener":
            return payload["user_id"]
    except Exception:
        pass
    return None


async def require_listener(authorization: Optional[str] = Header(None)) -> str:
    lid = await get_optional_listener(authorization)
    if not lid:
        raise HTTPException(status_code=401, detail="Listener authentication required")
    return lid


# ============ AUTH ============

@mobile_v1_router.post("/auth/signup")
async def listener_signup(req: ListenerSignup):
    existing = await db.listeners.find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    listener_id = f"listener_{uuid.uuid4().hex[:12]}"
    doc = {
        "listener_id": listener_id, "email": req.email,
        "name": req.name or req.email.split("@")[0],
        "password": hashed, "created_at": datetime.now(timezone.utc)
    }
    await db.listeners.insert_one(doc)
    token = create_jwt_token(listener_id, req.email, role="listener")
    return {"token": token, "listener_id": listener_id, "email": req.email, "name": doc["name"]}


@mobile_v1_router.post("/auth/login")
async def listener_login(req: ListenerLogin):
    listener = await db.listeners.find_one({"email": req.email})
    if not listener or not bcrypt.checkpw(req.password.encode(), listener["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_jwt_token(listener["listener_id"], listener["email"], role="listener")
    return {"token": token, "listener_id": listener["listener_id"], "email": listener["email"], "name": listener.get("name", "")}


# ============ HELPER: enrich story for mobile ============

async def _enrich_story(story_doc: dict) -> dict:
    """Add episode count, total duration, creator name to a story dict."""
    ep_stats = await db.episodes.aggregate([
        {"$match": {"story_id": story_doc["story_id"], "isPublished": True}},
        {"$group": {"_id": None, "count": {"$sum": 1}, "total_duration": {"$sum": {"$ifNull": ["$duration", 0]}}}}
    ]).to_list(1)
    stats = ep_stats[0] if ep_stats else {"count": 0, "total_duration": 0}

    user_id = story_doc.get("user_id", "")
    creator = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1})

    return {
        "story_id": story_doc["story_id"],
        "title": story_doc.get("title", ""),
        "description": story_doc.get("description", ""),
        "genre": story_doc.get("genre", ""),
        "language": story_doc.get("language", ""),
        "cover_art_url": story_doc.get("cover_art_url"),
        "story_type": story_doc.get("story_type", "story"),
        "play_count": story_doc.get("play_count", 0),
        "total_episodes": stats["count"],
        "total_duration_seconds": round(stats["total_duration"], 2),
        "creator_name": creator.get("name", "Unknown") if creator else "Unknown",
        "publishedAt": story_doc.get("publishedAt"),
    }


# ============ HOME FEED ============

@mobile_v1_router.get("/home")
async def mobile_home(authorization: Optional[str] = Header(None)):
    listener_id = await get_optional_listener(authorization)
    sections = []

    # Section 1: Continue Listening (only for logged-in users)
    if listener_id:
        progress_list = await db.listening_progress.find(
            {"listener_id": listener_id}, {"_id": 0}
        ).sort("updated_at", -1).limit(12).to_list(12)

        continue_items = []
        for p in progress_list:
            ep = await db.episodes.find_one(
                {"episode_id": p["episode_id"], "isPublished": True},
                {"_id": 0, "episode_id": 1, "title": 1, "story_id": 1, "duration": 1, "order": 1, "audio_url": 1}
            )
            if not ep:
                continue
            story = await db.stories.find_one(
                {"story_id": ep["story_id"], "status": "published"},
                {"_id": 0, "title": 1, "cover_art_url": 1}
            )
            if not story:
                continue
            continue_items.append({
                "episode_id": ep["episode_id"], "episode_title": ep["title"],
                "episode_number": ep.get("order", 1),
                "story_id": ep["story_id"], "story_title": story["title"],
                "cover_art_url": story.get("cover_art_url"),
                "current_time": p["current_time"],
                "duration": ep.get("duration", 0),
                "progress_percent": round((p["current_time"] / ep["duration"]) * 100, 1) if ep.get("duration") else 0
            })

        if continue_items:
            sections.append({
                "id": "continue_listening",
                "title": "Continue Listening",
                "type": "continue_listening",
                "items": continue_items
            })

    # Section 2: Trending Stories (most plays)
    trending_raw = await db.stories.find(
        {"status": "published"},
        {"_id": 0, "story_id": 1, "title": 1, "description": 1, "genre": 1, "language": 1, "cover_art_url": 1, "story_type": 1, "play_count": 1, "user_id": 1, "publishedAt": 1}
    ).sort("play_count", -1).limit(12).to_list(12)

    trending_items = []
    for s in trending_raw:
        trending_items.append(await _enrich_story(s))

    sections.append({
        "id": "trending",
        "title": "Trending Stories",
        "type": "story_list",
        "items": trending_items
    })

    # Section 3: New Releases (latest published)
    new_raw = await db.stories.find(
        {"status": "published"},
        {"_id": 0, "story_id": 1, "title": 1, "description": 1, "genre": 1, "language": 1, "cover_art_url": 1, "story_type": 1, "play_count": 1, "user_id": 1, "publishedAt": 1}
    ).sort("publishedAt", -1).limit(12).to_list(12)

    new_items = []
    for s in new_raw:
        new_items.append(await _enrich_story(s))

    sections.append({
        "id": "new_releases",
        "title": "New Releases",
        "type": "story_list",
        "items": new_items
    })

    return {"sections": sections}


# ============ BROWSE / DISCOVER ============

@mobile_v1_router.get("/stories")
async def mobile_browse_stories(genre: Optional[str] = None, language: Optional[str] = None, sort: str = "latest", page: int = 1, limit: int = 12):
    query = {"status": "published"}
    if genre:
        query["genre"] = {"$regex": genre, "$options": "i"}
    if language:
        query["language"] = {"$regex": language, "$options": "i"}

    sort_field = {"latest": ("publishedAt", -1), "popular": ("play_count", -1), "title": ("title", 1)}.get(sort, ("publishedAt", -1))
    total = await db.stories.count_documents(query)
    skip = (page - 1) * limit

    stories_raw = await db.stories.find(
        query,
        {"_id": 0, "story_id": 1, "title": 1, "description": 1, "genre": 1, "language": 1, "cover_art_url": 1, "story_type": 1, "play_count": 1, "user_id": 1, "publishedAt": 1}
    ).sort(*sort_field).skip(skip).limit(limit).to_list(limit)

    items = []
    for s in stories_raw:
        items.append(await _enrich_story(s))

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "hasNext": (skip + limit) < total
    }


# ============ STORY DETAILS ============

@mobile_v1_router.get("/stories/{story_id}")
async def mobile_story_detail(story_id: str, authorization: Optional[str] = Header(None)):
    story = await db.stories.find_one({"story_id": story_id, "status": "published"}, {"_id": 0})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    creator = await db.users.find_one({"user_id": story.get("user_id", "")}, {"_id": 0, "name": 1})
    episodes = await db.episodes.find(
        {"story_id": story_id, "isPublished": True},
        {"_id": 0, "episode_id": 1, "title": 1, "order": 1, "duration": 1, "finalAudioUrl": 1, "created_at": 1}
    ).sort("order", 1).to_list(100)

    listener_id = await get_optional_listener(authorization)
    progress_map = {}
    if listener_id:
        progress_docs = await db.listening_progress.find(
            {"listener_id": listener_id, "episode_id": {"$in": [e["episode_id"] for e in episodes]}}, {"_id": 0}
        ).to_list(100)
        progress_map = {p["episode_id"]: p["current_time"] for p in progress_docs}

    for ep in episodes:
        ep["episode_number"] = ep.pop("order", 1)
        ep["progress_seconds"] = progress_map.get(ep["episode_id"], 0)
        ep["has_audio"] = bool(ep.get("finalAudioUrl"))
        # Generate signed URL for audio
        raw_path = ep.pop("finalAudioUrl", None)
        ep["audio_url"] = _get_signed_audio_url(raw_path) if raw_path else None

    total_duration = sum(e.get("duration", 0) or 0 for e in episodes)

    # Check if story is in user's library
    in_library = False
    if listener_id:
        lib = await db.listener_library.find_one({"listener_id": listener_id, "story_id": story_id})
        in_library = lib is not None

    return {
        "story_id": story["story_id"], "title": story["title"],
        "description": story.get("description", ""),
        "genre": story.get("genre", ""), "language": story.get("language", ""),
        "cover_art_url": story.get("cover_art_url"),
        "story_type": story.get("story_type", "story"),
        "creator_name": creator.get("name", "Unknown") if creator else "Unknown",
        "total_episodes": len(episodes),
        "total_duration_seconds": round(total_duration, 2),
        "play_count": story.get("play_count", 0),
        "in_library": in_library,
        "episodes": episodes
    }


# ============ EPISODE PLAYBACK ============

@mobile_v1_router.get("/episodes/{episode_id}")
async def mobile_episode_playback(episode_id: str, authorization: Optional[str] = Header(None)):
    episode = await db.episodes.find_one(
        {"episode_id": episode_id, "isPublished": True},
        {"_id": 0, "episode_id": 1, "story_id": 1, "title": 1, "order": 1, "finalAudioUrl": 1, "duration": 1}
    )
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    story = await db.stories.find_one({"story_id": episode["story_id"]}, {"_id": 0, "title": 1, "cover_art_url": 1})

    # Increment play counts
    await db.episodes.update_one({"episode_id": episode_id}, {"$inc": {"play_count": 1}})
    await db.stories.update_one({"story_id": episode["story_id"]}, {"$inc": {"play_count": 1}})

    listener_id = await get_optional_listener(authorization)
    resume_at = 0
    if listener_id:
        prog = await db.listening_progress.find_one({"listener_id": listener_id, "episode_id": episode_id}, {"_id": 0, "current_time": 1})
        if prog:
            resume_at = prog["current_time"]

    # Next/prev episodes
    all_eps = await db.episodes.find(
        {"story_id": episode["story_id"], "isPublished": True},
        {"_id": 0, "episode_id": 1, "order": 1}
    ).sort("order", 1).to_list(100)
    ep_ids = [e["episode_id"] for e in all_eps]
    current_idx = ep_ids.index(episode_id) if episode_id in ep_ids else -1
    next_episode_id = ep_ids[current_idx + 1] if 0 <= current_idx < len(ep_ids) - 1 else None
    prev_episode_id = ep_ids[current_idx - 1] if current_idx > 0 else None

    # Generate signed audio URL
    audio_url = _get_signed_audio_url(episode.get("finalAudioUrl")) if episode.get("finalAudioUrl") else None

    return {
        "episode_id": episode["episode_id"], "title": episode["title"],
        "episode_number": episode.get("order", 1),
        "story_id": episode["story_id"],
        "story_title": story["title"] if story else "",
        "cover_art_url": story.get("cover_art_url") if story else None,
        "audio_url": audio_url,
        "duration": episode.get("duration", 0),
        "resume_at": resume_at,
        "next_episode_id": next_episode_id,
        "prev_episode_id": prev_episode_id,
    }


# ============ SEARCH ============

@mobile_v1_router.get("/search")
async def mobile_search(q: str, page: int = 1, limit: int = 12):
    if not q or len(q.strip()) < 2:
        return {"items": [], "total": 0, "query": q, "page": page, "limit": limit, "hasNext": False}

    query = {
        "status": "published",
        "$or": [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"genre": {"$regex": q, "$options": "i"}},
        ]
    }
    total = await db.stories.count_documents(query)
    skip = (page - 1) * limit
    stories_raw = await db.stories.find(
        query,
        {"_id": 0, "story_id": 1, "title": 1, "description": 1, "genre": 1, "language": 1, "cover_art_url": 1, "story_type": 1, "play_count": 1, "user_id": 1, "publishedAt": 1}
    ).sort("play_count", -1).skip(skip).limit(limit).to_list(limit)

    items = []
    for s in stories_raw:
        items.append(await _enrich_story(s))

    return {
        "items": items,
        "total": total,
        "query": q,
        "page": page,
        "limit": limit,
        "hasNext": (skip + limit) < total
    }


# ============ PROGRESS ============

@mobile_v1_router.post("/progress")
async def save_listening_progress(req: ProgressSave, listener_id: str = Depends(require_listener)):
    episode = await db.episodes.find_one({"episode_id": req.episode_id, "isPublished": True}, {"_id": 0, "episode_id": 1, "duration": 1})
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    await db.listening_progress.update_one(
        {"listener_id": listener_id, "episode_id": req.episode_id},
        {"$set": {
            "listener_id": listener_id, "episode_id": req.episode_id,
            "current_time": req.current_time,
            "duration": req.duration or episode.get("duration", 0),
            "updated_at": datetime.now(timezone.utc)
        }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    return {"message": "Progress saved", "episode_id": req.episode_id, "current_time": req.current_time}


@mobile_v1_router.get("/me/progress")
async def get_listening_progress(listener_id: str = Depends(require_listener)):
    progress = await db.listening_progress.find(
        {"listener_id": listener_id}, {"_id": 0}
    ).sort("updated_at", -1).to_list(50)

    enriched = []
    for p in progress:
        ep = await db.episodes.find_one({"episode_id": p["episode_id"]}, {"_id": 0, "title": 1, "story_id": 1, "order": 1, "duration": 1})
        if ep:
            story = await db.stories.find_one({"story_id": ep["story_id"]}, {"_id": 0, "title": 1, "cover_art_url": 1})
            enriched.append({
                "episode_id": p["episode_id"], "current_time": p["current_time"],
                "duration": p.get("duration", ep.get("duration", 0)),
                "episode_title": ep["title"], "episode_number": ep.get("order", 1),
                "story_id": ep["story_id"],
                "story_title": story["title"] if story else "",
                "cover_art_url": story.get("cover_art_url") if story else None,
                "progress_percent": round((p["current_time"] / p["duration"]) * 100, 1) if p.get("duration") else 0,
                "updated_at": p.get("updated_at")
            })
    return enriched


# ============ LIBRARY ============

@mobile_v1_router.post("/me/library")
async def add_to_library(req: LibrarySave, listener_id: str = Depends(require_listener)):
    story = await db.stories.find_one({"story_id": req.story_id, "status": "published"}, {"_id": 0, "story_id": 1})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    existing = await db.listener_library.find_one({"listener_id": listener_id, "story_id": req.story_id})
    if existing:
        return {"message": "Already in library", "story_id": req.story_id}

    await db.listener_library.insert_one({
        "listener_id": listener_id,
        "story_id": req.story_id,
        "added_at": datetime.now(timezone.utc)
    })
    return {"message": "Added to library", "story_id": req.story_id}


@mobile_v1_router.get("/me/library")
async def get_library(page: int = 1, limit: int = 12, listener_id: str = Depends(require_listener)):
    total = await db.listener_library.count_documents({"listener_id": listener_id})
    skip = (page - 1) * limit

    lib_items = await db.listener_library.find(
        {"listener_id": listener_id}, {"_id": 0}
    ).sort("added_at", -1).skip(skip).limit(limit).to_list(limit)

    items = []
    for item in lib_items:
        story = await db.stories.find_one(
            {"story_id": item["story_id"], "status": "published"},
            {"_id": 0, "story_id": 1, "title": 1, "description": 1, "genre": 1, "language": 1, "cover_art_url": 1, "story_type": 1, "play_count": 1, "user_id": 1, "publishedAt": 1}
        )
        if story:
            enriched = await _enrich_story(story)
            enriched["added_at"] = item["added_at"]
            items.append(enriched)

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "hasNext": (skip + limit) < total
    }


@mobile_v1_router.delete("/me/library/{story_id}")
async def remove_from_library(story_id: str, listener_id: str = Depends(require_listener)):
    result = await db.listener_library.delete_one({"listener_id": listener_id, "story_id": story_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not in library")
    return {"message": "Removed from library", "story_id": story_id}


# ============ ANALYTICS ============

@mobile_v1_router.post("/analytics/play")
async def track_play_event(req: PlayEventCreate, authorization: Optional[str] = Header(None)):
    listener_id = await get_optional_listener(authorization)
    episode = await db.episodes.find_one({"episode_id": req.episode_id}, {"_id": 0, "story_id": 1})
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    event = {
        "event_id": f"pe_{uuid.uuid4().hex[:12]}",
        "listener_id": listener_id,
        "episode_id": req.episode_id,
        "story_id": episode["story_id"],
        "event_type": req.event_type,
        "position_seconds": req.position_seconds,
        "created_at": datetime.now(timezone.utc)
    }
    await db.play_events.insert_one(event)
    return {"message": "Event tracked"}


# ============ GENRES & LANGUAGES ============

@mobile_v1_router.get("/genres")
async def mobile_genres():
    genres = await db.stories.distinct("genre", {"status": "published"})
    return [g for g in genres if g]


@mobile_v1_router.get("/languages")
async def mobile_languages():
    langs = await db.stories.distinct("language", {"status": "published"})
    return [l for l in langs if l]
