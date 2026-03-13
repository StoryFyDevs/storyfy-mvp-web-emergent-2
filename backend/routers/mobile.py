from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging
import math

import supabase_db as ndb
import auth_service

from models import ListenerSignup, ListenerLogin, ProgressSave, PlayEventCreate, LibrarySave

logger = logging.getLogger("mobile")

mobile_v1_router = APIRouter(prefix="/api/mobile", tags=["mobile"])


async def _get_optional_listener(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    if not authorization:
        return None
    try:
        token = authorization.split(" ")[1] if authorization.startswith("Bearer ") else authorization
        user_data = await auth_service.verify_supabase_token(token)
        profile = await auth_service.get_or_create_profile(
            auth_id=user_data["id"],
            email=user_data.get("email", ""),
            display_name=user_data.get("display_name", ""),
            metadata={"role": user_data.get("role", "listener")},
        )
        if profile and profile.get("role") == "listener":
            return profile
    except Exception:
        pass
    return None


async def _require_listener(authorization: Optional[str] = Header(None)) -> dict:
    profile = await _get_optional_listener(authorization)
    if not profile:
        raise HTTPException(status_code=401, detail="Listener authentication required")
    if not profile.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")
    return profile


def _resolve_audio_url(raw_url: str) -> Optional[str]:
    if not raw_url:
        return None
    if raw_url.startswith("nhost-file:"):
        file_id = raw_url[len("nhost-file:"):]
        if "/" in file_id:
            return f"/api/audio/stream-file/{file_id}"
        return None
    if raw_url.startswith("data:audio/"):
        return raw_url
    if raw_url.startswith("http"):
        return raw_url
    return None


async def _enrich_story(story: dict) -> dict:
    story_id = story.get("story_id", "")
    user_id = story.get("created_by", "")

    episodes = await ndb.find_many(
        "episodes",
        {"story_id": story_id, "is_published": True},
        fields=["id", "duration"],
        limit=200,
    )
    total_eps = len(episodes)
    total_dur = sum(e.get("duration", 0) or 0 for e in episodes)

    creator = await ndb.find_one("user_profiles", {"user_id": user_id}, fields=["name"])
    creator_name = creator.get("name", "Unknown") if creator else "Unknown"

    return {
        "story_id": story_id,
        "title": story.get("title", ""),
        "description": story.get("description", ""),
        "genre": story.get("genre", ""),
        "language": story.get("language", ""),
        "cover_art_url": story.get("cover_art_url", ""),
        "story_type": story.get("story_type", "story"),
        "play_count": story.get("play_count", 0),
        "total_episodes": total_eps,
        "total_duration_seconds": round(total_dur, 2),
        "creator_name": creator_name,
        "publishedAt": str(story.get("published_at", "")),
    }


@mobile_v1_router.post("/auth/signup")
async def listener_signup(req: ListenerSignup):
    existing = await ndb.find_one("user_profiles", {"email": req.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    result = await auth_service.register_supabase_user(
        email=req.email,
        password=req.password,
        display_name=req.name or req.email.split("@")[0],
        role="listener",
    )

    user = result.user
    session = result.session
    access_token = session.access_token if session else ""

    profile = await auth_service.get_or_create_profile(
        auth_id=user.id,
        email=req.email,
        display_name=req.name or req.email.split("@")[0],
        metadata={"role": "listener"},
    )

    if profile.get("role") != "listener":
        await ndb.update_rows("user_profiles", {"user_id": profile["user_id"]}, {"role": "listener"})

    resp = {
        "token": access_token,
        "listener_id": profile["user_id"],
        "email": profile.get("email", req.email),
        "name": profile.get("name", ""),
    }

    if not access_token:
        resp["message"] = "Account created. Please confirm your email to log in."

    return resp


@mobile_v1_router.post("/auth/login")
async def listener_login(req: ListenerLogin):
    result = await auth_service.login_supabase_user(email=req.email, password=req.password)
    user = result.user
    session = result.session
    if not session or not session.access_token:
        raise HTTPException(status_code=401, detail="Login failed — no session returned")
    access_token = session.access_token

    profile = await auth_service.get_or_create_profile(
        auth_id=user.id,
        email=req.email,
        display_name=(user.user_metadata or {}).get("display_name", ""),
        metadata={"role": "listener"},
    )

    if profile.get("role") not in ("listener",):
        raise HTTPException(status_code=403, detail="Not a listener account")

    return {
        "token": access_token,
        "listener_id": profile["user_id"],
        "email": profile.get("email", req.email),
        "name": profile.get("name", ""),
    }


@mobile_v1_router.get("/home")
async def mobile_home(authorization: Optional[str] = Header(None)):
    listener = await _get_optional_listener(authorization)

    trending = []
    latest = []
    continue_listening = []

    published_stories = await ndb.find_many(
        "stories",
        {"status": "published"},
        order_by={"play_count": "desc"},
        limit=12,
    )
    for s in published_stories:
        trending.append(await _enrich_story(s))

    latest_stories = await ndb.find_many(
        "stories",
        {"status": "published"},
        order_by={"published_at": "desc"},
        limit=12,
    )
    for s in latest_stories:
        latest.append(await _enrich_story(s))

    if listener:
        listener_id = listener["user_id"]
        progress_rows = await ndb.find_many(
            "listening_progress",
            {"listener_id": listener_id},
            order_by={"updated_at": "desc"},
            limit=12,
        )
        for p in progress_rows:
            ep = await ndb.find_one("episodes", {"episode_id": p["episode_id"], "is_published": True})
            if not ep:
                continue
            story = await ndb.find_one("stories", {"story_id": ep["story_id"], "status": "published"})
            if not story:
                continue
            dur = ep.get("duration", 0) or 0
            ct = p.get("current_time", 0) or 0
            continue_listening.append({
                "episode_id": ep["episode_id"],
                "episode_title": ep.get("title", ""),
                "episode_number": ep.get("order_index", 0),
                "story_id": ep["story_id"],
                "story_title": story.get("title", ""),
                "cover_art_url": story.get("cover_art_url", ""),
                "current_time": ct,
                "duration": dur,
                "progress_percent": round((ct / dur) * 100, 1) if dur > 0 else 0,
            })

    return {
        "trending": trending,
        "latest": latest,
        "continue_listening": continue_listening,
    }


@mobile_v1_router.get("/stories")
async def mobile_browse_stories(
    genre: Optional[str] = None,
    language: Optional[str] = None,
    sort: str = "latest",
    page: int = 1,
    limit: int = 20,
):
    where = {"status": "published"}
    if genre:
        where["genre"] = {"_ilike": f"%{genre}%"}
    if language:
        where["language"] = {"_ilike": f"%{language}%"}

    sort_map = {
        "latest": {"published_at": "desc"},
        "popular": {"play_count": "desc"},
        "title": {"title": "asc"},
    }
    order = sort_map.get(sort, {"published_at": "desc"})

    all_stories = await ndb.find_many("stories", where, order_by=order, limit=500)
    total = len(all_stories)
    start = (page - 1) * limit
    end = start + limit
    page_stories = all_stories[start:end]

    stories = []
    for s in page_stories:
        stories.append(await _enrich_story(s))

    return {
        "stories": stories,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
    }


@mobile_v1_router.get("/stories/{story_id}")
async def mobile_story_detail(story_id: str, authorization: Optional[str] = Header(None)):
    story = await ndb.find_one("stories", {"story_id": story_id, "status": "published"})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    creator = await ndb.find_one("user_profiles", {"user_id": story.get("created_by", "")}, fields=["name"])
    episodes = await ndb.find_many(
        "episodes",
        {"story_id": story_id, "is_published": True},
        order_by={"order_index": "asc"},
        limit=200,
    )

    listener = await _get_optional_listener(authorization)
    progress_map = {}
    in_library = False
    if listener:
        listener_id = listener["user_id"]
        ep_ids = [e["episode_id"] for e in episodes]
        if ep_ids:
            prog_rows = await ndb.find_many(
                "listening_progress",
                {"listener_id": listener_id},
                limit=200,
            )
            progress_map = {
                p["episode_id"]: p.get("current_time", 0)
                for p in prog_rows
                if p["episode_id"] in ep_ids
            }
        lib_entry = await ndb.find_one("listener_library", {"listener_id": listener_id, "story_id": story_id})
        in_library = lib_entry is not None

    episode_list = []
    for ep in episodes:
        raw_url = ep.get("final_audio_url", "") or ep.get("audio_url", "")
        episode_list.append({
            "episode_id": ep["episode_id"],
            "title": ep.get("title", ""),
            "episode_number": ep.get("order_index", 0),
            "duration": ep.get("duration", 0) or 0,
            "audio_url": _resolve_audio_url(raw_url),
            "has_audio": bool(raw_url),
            "progress_seconds": progress_map.get(ep["episode_id"], 0),
        })

    total_dur = sum(e["duration"] for e in episode_list)

    return {
        "story_id": story["story_id"],
        "title": story.get("title", ""),
        "description": story.get("description", ""),
        "genre": story.get("genre", ""),
        "language": story.get("language", ""),
        "cover_art_url": story.get("cover_art_url", ""),
        "story_type": story.get("story_type", "story"),
        "creator_name": creator.get("name", "Unknown") if creator else "Unknown",
        "total_episodes": len(episode_list),
        "total_duration_seconds": round(total_dur, 2),
        "play_count": story.get("play_count", 0),
        "in_library": in_library,
        "episodes": episode_list,
    }


@mobile_v1_router.get("/episodes/{episode_id}")
async def mobile_episode_playback(episode_id: str, authorization: Optional[str] = Header(None)):
    episode = await ndb.find_one("episodes", {"episode_id": episode_id, "is_published": True})
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    story = await ndb.find_one("stories", {"story_id": episode["story_id"]})

    try:
        await ndb.increment_field("episodes", {"episode_id": episode_id}, "play_count", 1)
        await ndb.increment_field("stories", {"story_id": episode["story_id"]}, "play_count", 1)
    except Exception as e:
        logger.warning(f"Play count increment failed: {e}")

    listener = await _get_optional_listener(authorization)
    resume_at = 0
    if listener:
        prog = await ndb.find_one("listening_progress", {
            "listener_id": listener["user_id"],
            "episode_id": episode_id,
        })
        if prog:
            resume_at = prog.get("current_time", 0)

    all_eps = await ndb.find_many(
        "episodes",
        {"story_id": episode["story_id"], "is_published": True},
        order_by={"order_index": "asc"},
        limit=200,
    )
    ep_ids = [e["episode_id"] for e in all_eps]
    current_idx = ep_ids.index(episode_id) if episode_id in ep_ids else -1
    next_episode_id = ep_ids[current_idx + 1] if 0 <= current_idx < len(ep_ids) - 1 else None
    prev_episode_id = ep_ids[current_idx - 1] if current_idx > 0 else None

    raw_url = episode.get("final_audio_url", "") or episode.get("audio_url", "")

    return {
        "episode_id": episode["episode_id"],
        "title": episode.get("title", ""),
        "episode_number": episode.get("order_index", 0),
        "story_id": episode["story_id"],
        "story_title": story.get("title", "") if story else "",
        "cover_art_url": story.get("cover_art_url", "") if story else "",
        "audio_url": _resolve_audio_url(raw_url),
        "duration": episode.get("duration", 0) or 0,
        "resume_at": resume_at,
        "next_episode_id": next_episode_id,
        "prev_episode_id": prev_episode_id,
    }


@mobile_v1_router.get("/search")
async def mobile_search(q: str = "", page: int = 1, limit: int = 20):
    if not q or len(q.strip()) < 2:
        return {"results": [], "total": 0, "query": q, "page": page, "total_pages": 1}

    all_published = await ndb.find_many(
        "stories",
        {"status": "published"},
        order_by={"play_count": "desc"},
        limit=500,
    )

    q_lower = q.strip().lower()
    matched = [
        s for s in all_published
        if q_lower in (s.get("title", "") or "").lower()
        or q_lower in (s.get("description", "") or "").lower()
        or q_lower in (s.get("genre", "") or "").lower()
    ]

    total = len(matched)
    start = (page - 1) * limit
    page_stories = matched[start : start + limit]

    results = []
    for s in page_stories:
        enriched = await _enrich_story(s)
        results.append({
            "story_id": enriched["story_id"],
            "title": enriched["title"],
            "description": enriched["description"],
            "genre": enriched["genre"],
            "total_episodes": enriched["total_episodes"],
            "creator_name": enriched["creator_name"],
            "play_count": enriched["play_count"],
        })

    return {
        "results": results,
        "total": total,
        "query": q,
        "page": page,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
    }


@mobile_v1_router.get("/genres")
async def mobile_genres():
    stories = await ndb.find_many("stories", {"status": "published"}, fields=["genre"], limit=500)
    genres = sorted(set(s.get("genre", "") for s in stories if s.get("genre")))
    return genres


@mobile_v1_router.get("/languages")
async def mobile_languages():
    stories = await ndb.find_many("stories", {"status": "published"}, fields=["language"], limit=500)
    langs = sorted(set(s.get("language", "") for s in stories if s.get("language")))
    return langs


@mobile_v1_router.post("/progress")
async def save_listening_progress(req: ProgressSave, authorization: Optional[str] = Header(None)):
    listener = await _require_listener(authorization)
    listener_id = listener["user_id"]

    ep = await ndb.find_one("episodes", {"episode_id": req.episode_id, "is_published": True})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    duration = req.duration or ep.get("duration", 0) or 0
    now = datetime.now(timezone.utc).isoformat()

    existing = await ndb.find_one("listening_progress", {
        "listener_id": listener_id,
        "episode_id": req.episode_id,
    })

    if existing:
        await ndb.update_rows(
            "listening_progress",
            {"id": {"_eq": existing["id"]}},
            {"current_time": req.current_time, "duration": duration, "updated_at": now},
        )
    else:
        await ndb.insert_one("listening_progress", {
            "progress_id": f"prog_{uuid.uuid4().hex[:12]}",
            "listener_id": listener_id,
            "episode_id": req.episode_id,
            "current_time": req.current_time,
            "duration": duration,
        })

    return {"message": "Progress saved", "episode_id": req.episode_id, "current_time": req.current_time}


@mobile_v1_router.get("/progress")
async def get_listening_progress(authorization: Optional[str] = Header(None)):
    listener = await _require_listener(authorization)
    listener_id = listener["user_id"]

    progress_rows = await ndb.find_many(
        "listening_progress",
        {"listener_id": listener_id},
        order_by={"updated_at": "desc"},
        limit=50,
    )

    enriched = []
    for p in progress_rows:
        ep = await ndb.find_one("episodes", {"episode_id": p["episode_id"]})
        if not ep:
            continue
        story = await ndb.find_one("stories", {"story_id": ep["story_id"]})
        dur = p.get("duration", 0) or ep.get("duration", 0) or 0
        ct = p.get("current_time", 0)
        enriched.append({
            "episode_id": p["episode_id"],
            "current_time": ct,
            "duration": dur,
            "episode_title": ep.get("title", ""),
            "episode_number": ep.get("order_index", 0),
            "story_id": ep.get("story_id", ""),
            "story_title": story.get("title", "") if story else "",
            "cover_art_url": story.get("cover_art_url", "") if story else "",
            "progress_percent": round((ct / dur) * 100, 1) if dur > 0 else 0,
            "updated_at": str(p.get("updated_at", "")),
        })

    return enriched


@mobile_v1_router.post("/analytics/play")
async def track_play_event(req: PlayEventCreate, authorization: Optional[str] = Header(None)):
    listener = await _get_optional_listener(authorization)
    listener_id = listener["user_id"] if listener else None

    ep = await ndb.find_one("episodes", {"episode_id": req.episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    await ndb.insert_one("play_events", {
        "event_id": f"pe_{uuid.uuid4().hex[:12]}",
        "listener_id": listener_id or "",
        "episode_id": req.episode_id,
        "story_id": ep.get("story_id", ""),
        "event_type": req.event_type,
        "position_seconds": req.position_seconds or 0,
    })

    return {"message": "Event tracked"}


@mobile_v1_router.post("/me/library")
async def add_to_library(req: LibrarySave, authorization: Optional[str] = Header(None)):
    listener = await _require_listener(authorization)
    listener_id = listener["user_id"]

    story = await ndb.find_one("stories", {"story_id": req.story_id, "status": "published"})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    existing = await ndb.find_one("listener_library", {"listener_id": listener_id, "story_id": req.story_id})
    if existing:
        return {"message": "Already in library", "story_id": req.story_id}

    await ndb.insert_one("listener_library", {
        "entry_id": f"lib_{uuid.uuid4().hex[:12]}",
        "listener_id": listener_id,
        "story_id": req.story_id,
    })

    return {"message": "Added to library", "story_id": req.story_id}


@mobile_v1_router.get("/me/library")
async def get_library(page: int = 1, limit: int = 20, authorization: Optional[str] = Header(None)):
    listener = await _require_listener(authorization)
    listener_id = listener["user_id"]

    lib_items = await ndb.find_many(
        "listener_library",
        {"listener_id": listener_id},
        order_by={"created_at": "desc"},
        limit=500,
    )
    total = len(lib_items)
    start = (page - 1) * limit
    page_items = lib_items[start : start + limit]

    items = []
    for item in page_items:
        story = await ndb.find_one("stories", {"story_id": item["story_id"], "status": "published"})
        if story:
            enriched = await _enrich_story(story)
            enriched["added_at"] = str(item.get("created_at", ""))
            items.append(enriched)

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total / limit) if total > 0 else 1,
    }


@mobile_v1_router.delete("/me/library/{story_id}")
async def remove_from_library(story_id: str, authorization: Optional[str] = Header(None)):
    listener = await _require_listener(authorization)
    listener_id = listener["user_id"]

    count = await ndb.delete_rows("listener_library", {"listener_id": listener_id, "story_id": story_id})
    if count == 0:
        raise HTTPException(status_code=404, detail="Not in library")
    return {"message": "Removed from library", "story_id": story_id}
