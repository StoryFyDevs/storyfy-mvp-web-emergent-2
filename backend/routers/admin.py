from fastapi import APIRouter, HTTPException, Header
from typing import Dict, Optional, Any
from datetime import datetime, timezone, timedelta
import json
import logging
import os
import re

import supabase_db as ndb
from auth_service import require_admin_from_token
from models import AdminLogin, LimitAdjustRequest, UserStatusUpdate

logger = logging.getLogger("admin")

ADMIN_SECRET_PATH = os.environ.get("ADMIN_SECRET_PATH", "admin-9821")

admin_router = APIRouter(prefix=f"/api/{ADMIN_SECRET_PATH}", tags=["admin"])


# ============ AUTH HELPER ============

async def _auth_admin(authorization: Optional[str]) -> dict:
    """Verify token and ensure admin role."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return await require_admin_from_token(token)


# ============ ADMIN LOGIN ============

@admin_router.post("/login")
async def admin_login(credentials: AdminLogin):
    """Admin login using Supabase Auth."""
    import auth_service
    try:
        result = await auth_service.login_supabase_user(
            email=credentials.email,
            password=credentials.password,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin login error: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = result.user
    session = result.session
    access_token = session.access_token if session else ""

    profile = await auth_service.get_or_create_profile(
        auth_id=user.id,
        email=credentials.email,
        display_name=(user.user_metadata or {}).get("display_name", ""),
    )

    if profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if not profile.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is not active")

    return {
        "user": {
            "user_id": profile["user_id"],
            "email": profile["email"],
            "name": profile.get("name", ""),
            "role": "admin"
        },
        "token": access_token
    }


# ============ STATS ============

@admin_router.get("/stats")
async def admin_stats(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    total_users = await ndb.count_rows("user_profiles")
    total_creators = await ndb.count_rows("user_profiles", {"role": {"_neq": "admin"}})
    total_stories = await ndb.count_rows("stories")
    total_episodes = await ndb.count_rows("episodes")

    # Active creators
    # For now, return total creators as active
    active_7d = total_creators
    active_30d = total_creators

    # Aggregate generation stats (use limited count instead of fetching all rows)
    gen_count = await ndb.count_rows("generation_logs", {"status": "success"})
    total_limits_consumed = 0
    total_audio_seconds = 0
    if gen_count > 0:
        gen_sample = await ndb.find_many("generation_logs", {"status": "success"}, limit=500)
        total_limits_consumed = sum(log.get("text_length", 0) for log in gen_sample)
        total_audio_seconds = sum(log.get("duration_seconds", 0) for log in gen_sample)
        if gen_count > 500:
            scale = gen_count / len(gen_sample) if gen_sample else 1
            total_limits_consumed = int(total_limits_consumed * scale)
            total_audio_seconds = total_audio_seconds * scale
    total_audio_minutes = round(total_audio_seconds / 60, 2)

    # Storage stats (approximate)
    total_storage_mb = 0.0

    return {
        "total_users": total_users,
        "total_creators": total_creators,
        "active_creators_7d": active_7d,
        "active_creators_30d": active_30d,
        "total_stories": total_stories,
        "total_episodes": total_episodes,
        "total_audio_minutes": total_audio_minutes,
        "total_limits_consumed": total_limits_consumed,
        "total_storage_mb": total_storage_mb,
    }


# ============ USERS ============

@admin_router.get("/users")
async def admin_list_users(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    users = await ndb.find_many(
        "user_profiles",
        order_by={"created_at": "desc"},
        limit=500
    )

    # Batch fetch stories and episodes counts to avoid N+1 queries
    user_ids = [u.get("user_id", "") for u in users]
    stories = await ndb.find_many("stories", limit=10000) if user_ids else []
    episodes = await ndb.find_many("episodes", limit=10000) if user_ids else []

    stories_by_user = {}
    for s in stories:
        uid = s.get("created_by", "")
        stories_by_user[uid] = stories_by_user.get(uid, 0) + 1

    episodes_by_user = {}
    for e in episodes:
        uid = e.get("created_by", "")
        episodes_by_user[uid] = episodes_by_user.get(uid, 0) + 1

    result = []
    for u in users:
        user_id = u.get("user_id", "")
        result.append({
            "user_id": user_id,
            "email": u.get("email", ""),
            "name": u.get("name", ""),
            "role": u.get("role", "creator"),
            "status": "active" if u.get("is_active", True) else "suspended",
            "limits_remaining": u.get("generation_credits", 0),
            "audition_credits": u.get("audition_credits", 0),
            "storage_used_mb": 0,
            "storage_limit_mb": 500,
            "stories_count": stories_by_user.get(user_id, 0),
            "episodes_count": episodes_by_user.get(user_id, 0),
            "total_credits_used": 0,
            "total_audio_seconds": 0,
            "total_generations": 0,
            "total_storage_used": 0,
            "total_failed_generations": 0,
            "created_at": str(u.get("created_at", "")),
        })

    return result


@admin_router.patch("/users/status")
async def admin_update_user_status(update: UserStatusUpdate, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    if update.status not in ("active", "suspended", "banned"):
        raise HTTPException(status_code=400, detail="Invalid status")

    user = await ndb.find_one("user_profiles", {"user_id": update.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Cannot change admin status")

    is_active = update.status == "active"
    await ndb.update_rows("user_profiles", {"user_id": update.user_id}, {"is_active": is_active})

    # Log admin action
    await ndb.insert_one("admin_logs", {
        "admin_id": admin["user_id"],
        "action": f"set_status_{update.status}",
        "target_type": "user",
        "target_id": update.user_id,
        "details": f'{{"new_status": "{update.status}", "reason": "{update.reason or ""}"}}',
    })

    return {"message": f"User status updated to {update.status}"}


@admin_router.post("/users/limits")
async def admin_adjust_limits(request: LimitAdjustRequest, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    user = await ndb.find_one("user_profiles", {"user_id": request.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current = user.get("generation_credits", 0)
    new_balance = current + request.amount
    if new_balance < 0:
        raise HTTPException(status_code=400, detail="Cannot set negative balance")

    await ndb.update_rows("user_profiles", {"user_id": request.user_id}, {"generation_credits": new_balance})

    # Log transaction
    tx_type = "admin_add" if request.amount > 0 else "admin_deduct"
    await ndb.insert_one("limit_transactions", {
        "user_id": request.user_id,
        "admin_id": admin["user_id"],
        "credit_type": "generation",
        "previous_value": current,
        "new_value": new_balance,
        "change_amount": request.amount,
        "reason": request.reason,
    })

    # Log admin action
    await ndb.insert_one("admin_logs", {
        "admin_id": admin["user_id"],
        "action": "adjust_limits",
        "target_type": "user",
        "target_id": request.user_id,
        "details": f'{{"amount": {request.amount}, "new_balance": {new_balance}, "reason": "{request.reason}"}}',
    })

    return {"message": "Limits updated", "new_balance": new_balance}


@admin_router.post("/users/audition-credits")
async def admin_adjust_audition_credits(body: Dict, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    user_id = body.get("user_id", "")
    amount = body.get("amount", 0)
    reason = body.get("reason", "Admin adjustment")

    user = await ndb.find_one("user_profiles", {"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current = user.get("audition_credits", 0)
    new_balance = current + amount
    if new_balance < 0:
        raise HTTPException(status_code=400, detail="Cannot set negative balance")

    await ndb.update_rows("user_profiles", {"user_id": user_id}, {"audition_credits": new_balance})

    # Log transaction
    await ndb.insert_one("limit_transactions", {
        "user_id": user_id,
        "admin_id": admin["user_id"],
        "credit_type": "audition",
        "previous_value": current,
        "new_value": new_balance,
        "change_amount": amount,
        "reason": reason,
    })

    return {"message": "Audition credits updated", "new_balance": new_balance}


@admin_router.get("/users/{user_id}/transactions")
async def admin_user_transactions(user_id: str, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    transactions = await ndb.find_many(
        "limit_transactions",
        {"user_id": user_id},
        order_by={"created_at": "desc"},
        limit=100
    )

    return [
        {
            "user_id": t.get("user_id", ""),
            "admin_id": t.get("admin_id", ""),
            "credit_type": t.get("credit_type", "generation"),
            "previous_value": t.get("previous_value", 0),
            "new_value": t.get("new_value", 0),
            "change_amount": t.get("change_amount", 0),
            "reason": t.get("reason", ""),
            "created_at": str(t.get("created_at", "")),
        }
        for t in transactions
    ]


# ============ STORY & PROJECT VIEWER ============

@admin_router.get("/stories")
async def admin_list_stories(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    stories = await ndb.find_many("stories", order_by={"created_at": "desc"}, limit=500)

    result = []
    for story in stories:
        story_id = story.get("story_id", "")
        user_id = story.get("created_by", "")

        user = await ndb.find_one("user_profiles", {"user_id": user_id})
        episodes_count = await ndb.count_rows("episodes", {"story_id": story_id})

        result.append({
            "story_id": story_id,
            "user_id": user_id,
            "title": story.get("title", ""),
            "genre": story.get("genre", ""),
            "language": story.get("language", ""),
            "status": story.get("status", "draft"),
            "description": story.get("description", ""),
            "cover_art_url": story.get("cover_art_url", ""),
            "play_count": story.get("play_count", 0),
            "creator_name": user.get("name", "Unknown") if user else "Unknown",
            "creator_email": user.get("email", "") if user else "",
            "episodes_count": episodes_count,
            "created_at": str(story.get("created_at", "")),
        })

    return result


@admin_router.get("/stories/{story_id}/episodes")
async def admin_story_episodes(story_id: str, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    story = await ndb.find_one("stories", {"story_id": story_id})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    episodes = await ndb.find_many("episodes", {"story_id": story_id}, order_by={"order_index": "asc"})
    user = await ndb.find_one("user_profiles", {"user_id": story.get("created_by", "")})

    def _parse_project_summary(ep):
        """Return a lightweight project_state summary (no audio data) for the episode list."""
        import json as _json
        ps = ep.get("project_state", {})
        if isinstance(ps, str):
            try:
                ps = _json.loads(ps)
            except Exception:
                ps = {}
        if not ps or not isinstance(ps, dict):
            return None
        tracks = ps.get("tracks", [])
        if not tracks:
            return None
        return {
            "version": ps.get("version", 0),
            "tracks": [
                {
                    "id": t.get("id", ""),
                    "name": t.get("name", ""),
                    "type": t.get("type", "voice"),
                    "clips": [
                        {"id": c.get("id", ""), "name": c.get("name", ""), "start": c.get("start", 0), "duration": c.get("duration", 0)}
                        for c in (t.get("clips") or [])
                    ],
                }
                for t in tracks
            ],
        }

    return {
        "story": {
            "story_id": story.get("story_id", ""),
            "title": story.get("title", ""),
            "genre": story.get("genre", ""),
            "status": story.get("status", "draft"),
            "description": story.get("description", ""),
            "story_type": story.get("story_type", ""),
            "language": story.get("language", ""),
        },
        "creator_name": user.get("name", "Unknown") if user else "Unknown",
        "creator_email": user.get("email", "") if user else "",
        "episodes": [
            {
                "episode_id": ep.get("episode_id", ""),
                "title": ep.get("title", ""),
                "order": ep.get("order_index", 0),
                "status": ep.get("status", "draft"),
                "duration": ep.get("duration", 0),
                "is_published": ep.get("is_published", False),
                "final_audio_url": ep.get("final_audio_url", ""),
                "created_at": str(ep.get("created_at", "")),
                "project_state": _parse_project_summary(ep),
            }
            for ep in episodes
        ]
    }


@admin_router.get("/episodes/{episode_id}/project")
async def admin_episode_project(episode_id: str, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    episode = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    story = await ndb.find_one("stories", {"story_id": episode.get("story_id", "")})
    user = await ndb.find_one("user_profiles", {"user_id": story.get("created_by", "")}) if story else None

    import json as _json
    import re as _re

    project_state = episode.get("project_state", {})
    if isinstance(project_state, str):
        try:
            project_state = _json.loads(project_state)
        except:
            project_state = {}

    # --- Resolve clip URLs: replace stale/dead refs with live Supabase URLs (or null) ---
    try:
        active_clips = await ndb.find_many(
            "audio_clips",
            {"episode_id": {"_eq": episode_id}, "is_active": {"_eq": True}},
            limit=500,
        )

        def _is_stale(url: str) -> bool:
            """True for any dead storage URL that will 404."""
            if not url:
                return False
            if "nhost.run" in url or "nhost.io" in url:
                return True
            if url.startswith("nhost-file:"):
                return "/" not in url[len("nhost-file:"):]
            return False

        # Build map: dialogue_index -> valid audio_url from audio_clips
        active_map: Dict[int, str] = {}
        for ac in active_clips:
            idx = ac.get("dialogue_index")
            url = ac.get("audio_url", "")
            if idx is not None and url and not _is_stale(url):
                active_map[int(idx)] = url

        stale_count = 0
        substituted = 0
        if isinstance(project_state, dict):
            for track in project_state.get("tracks", []):
                refreshed = []
                for clip in track.get("clips", []):
                    clip_url = clip.get("url", "")
                    if _is_stale(clip_url):
                        # Try to find a valid replacement by dialogue_index
                        m = _re.search(r"-(\d+)$", clip.get("id", ""))
                        dial_idx = int(m.group(1)) if m else None
                        replacement = active_map.get(dial_idx) if dial_idx is not None else None
                        clip = dict(clip)
                        if replacement:
                            clip["url"] = replacement
                            substituted += 1
                        else:
                            clip["url"] = None  # Mark unavailable so frontend skips cleanly
                            stale_count += 1
                    refreshed.append(clip)
                track["clips"] = refreshed

        if stale_count or substituted:
            logger.info(f"admin_project {episode_id}: {stale_count} unavailable clips, {substituted} substituted from audio_clips")
    except Exception as _e:
        logger.warning(f"audio_clips refresh failed for {episode_id}: {_e}")

    # Parse structured dialogues from script_content
    dialogues = []
    raw_script = episode.get("script_content", "")
    if isinstance(raw_script, str) and raw_script:
        try:
            parsed = _json.loads(raw_script)
            if isinstance(parsed, list):
                dialogues = parsed
        except Exception:
            pass

    return {
        "episode": {
            "episode_id": episode.get("episode_id", ""),
            "title": episode.get("title", ""),
            "status": episode.get("status", "draft"),
            "script": episode.get("script", ""),
            "duration": episode.get("duration", 0),
            "is_published": episode.get("is_published", False),
            "final_audio_url": episode.get("final_audio_url", ""),
        },
        "story": {
            "story_id": story.get("story_id", "") if story else "",
            "title": story.get("title", "") if story else "",
        } if story else None,
        "creator_name": user.get("name", "Unknown") if user else "Unknown",
        "dialogues": dialogues,
        "project_state": project_state
    }


# ============ USAGE LOGS & ANALYTICS ============

@admin_router.get("/usage/generations")
async def admin_generation_logs(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    logs = await ndb.find_many("generation_logs", order_by={"created_at": "desc"}, limit=500)

    user_cache = {}
    result = []
    for log in logs:
        uid = log.get("user_id", "")
        if uid and uid not in user_cache:
            u = await ndb.find_one("user_profiles", {"user_id": uid})
            user_cache[uid] = u or {}

        info = user_cache.get(uid, {})
        result.append({
            "user_id": uid,
            "user_email": info.get("email", ""),
            "user_name": info.get("name", "Unknown"),
            "gen_type": log.get("gen_type", ""),
            "voice_id": log.get("voice_id", ""),
            "text_length": log.get("text_length", 0),
            "duration_seconds": log.get("duration_seconds", 0),
            "status": log.get("status", ""),
            "provider": log.get("provider", ""),
            "error": log.get("error", ""),
            "created_at": str(log.get("created_at", "")),
        })

    return result


@admin_router.get("/usage/transactions")
async def admin_all_transactions(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    txns = await ndb.find_many("limit_transactions", order_by={"created_at": "desc"}, limit=500)

    user_cache = {}
    result = []
    for txn in txns:
        uid = txn.get("user_id", "")
        if uid and uid not in user_cache:
            u = await ndb.find_one("user_profiles", {"user_id": uid})
            user_cache[uid] = u or {}

        info = user_cache.get(uid, {})
        result.append({
            "user_id": uid,
            "user_email": info.get("email", ""),
            "user_name": info.get("name", "Unknown"),
            "credit_type": txn.get("credit_type", "generation"),
            "previous_value": txn.get("previous_value", 0),
            "new_value": txn.get("new_value", 0),
            "change_amount": txn.get("change_amount", 0),
            "reason": txn.get("reason", ""),
            "admin_id": txn.get("admin_id", ""),
            "created_at": str(txn.get("created_at", "")),
        })

    return result


@admin_router.get("/usage/actions")
async def admin_action_logs(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    actions = await ndb.find_many("admin_logs", order_by={"created_at": "desc"}, limit=500)

    admin_cache = {}
    result = []
    for action in actions:
        aid = action.get("admin_id", "")
        if aid and aid not in admin_cache:
            u = await ndb.find_one("user_profiles", {"user_id": aid})
            admin_cache[aid] = u or {}

        info = admin_cache.get(aid, {})
        result.append({
            "admin_id": aid,
            "admin_email": info.get("email", ""),
            "admin_name": info.get("name", "Unknown"),
            "action": action.get("action", ""),
            "target_type": action.get("target_type", ""),
            "target_id": action.get("target_id", ""),
            "details": action.get("details", ""),
            "created_at": str(action.get("created_at", "")),
        })

    return result


@admin_router.get("/usage/analytics")
async def admin_analytics(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    # Get all users
    users = await ndb.find_many("user_profiles", {"role": {"_neq": "admin"}}, limit=500)

    # Get generation logs
    gen_logs = await ndb.find_many("generation_logs", limit=1000)

    # Get transactions
    txns = await ndb.find_many("limit_transactions", limit=500)

    # Aggregate daily signups (simplified)
    daily_signups = []

    # Aggregate daily generations
    daily_generations = []

    # Transaction by type
    txn_by_type = {}
    for t in txns:
        ct = t.get("credit_type", "generation")
        if ct not in txn_by_type:
            txn_by_type[ct] = {"count": 0, "total_amount": 0}
        txn_by_type[ct]["count"] += 1
        txn_by_type[ct]["total_amount"] += t.get("change_amount", 0)

    # Top creators by lowest credits
    sorted_users = sorted(users, key=lambda x: x.get("generation_credits", 0))[:10]
    top_creators = []
    for c in sorted_users:
        stories_count = await ndb.count_rows("stories", {"created_by": c.get("user_id", "")})
        top_creators.append({
            "user_id": c.get("user_id", ""),
            "email": c.get("email", ""),
            "name": c.get("name", ""),
            "limits_remaining": c.get("generation_credits", 0),
            "storage_used_mb": 0,
            "stories_count": stories_count,
        })

    return {
        "daily_signups": daily_signups,
        "daily_generations": daily_generations,
        "transactions_by_type": [{"type": t, "count": v["count"], "total_amount": v["total_amount"]} for t, v in txn_by_type.items()],
        "top_creators": top_creators
    }


# ============ REAL-TIME USAGE TRACKING ============

@admin_router.get("/usage/user-summaries")
async def admin_user_usage_summaries(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    users = await ndb.find_many(
        "user_profiles",
        {"role": {"_neq": "admin"}},
        order_by={"created_at": "desc"},
        limit=500
    )

    result = []
    for u in users:
        result.append({
            "user_id": u.get("user_id", ""),
            "user_email": u.get("email", ""),
            "user_name": u.get("name", "Unknown"),
            "limits_remaining": u.get("generation_credits", 0),
            "audition_credits": u.get("audition_credits", 0),
            "storage_limit_mb": 500,
            "storage_used_mb": 0,
            "status": "active" if u.get("is_active", True) else "suspended",
            "role": u.get("role", "creator"),
            "total_credits_used": 0,
            "total_audio_seconds": 0,
            "total_generations": 0,
            "total_storage_used": 0,
            "total_failed_generations": 0,
            "last_updated": None,
        })

    return result


@admin_router.get("/creators/{user_id}/usage")
async def admin_creator_usage_detail(user_id: str, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    user = await ndb.find_one("user_profiles", {"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get generation logs for this user
    logs = await ndb.find_many("generation_logs", {"user_id": user_id}, limit=500)

    success_logs = [l for l in logs if l.get("status") == "success"]
    total_credits_used = sum(l.get("text_length", 0) for l in success_logs)
    total_audio_seconds = sum(l.get("duration_seconds", 0) for l in success_logs)
    total_generations = len(success_logs)
    failed_count = len([l for l in logs if l.get("status") == "failed"])

    # By type
    by_type = {}
    for l in success_logs:
        gt = l.get("gen_type", "voice")
        if gt not in by_type:
            by_type[gt] = {"count": 0, "credits": 0, "duration": 0}
        by_type[gt]["count"] += 1
        by_type[gt]["credits"] += l.get("text_length", 0)
        by_type[gt]["duration"] += l.get("duration_seconds", 0)

    # Recent generations
    recent = await ndb.find_many("generation_logs", {"user_id": user_id}, order_by={"created_at": "desc"}, limit=20)

    return {
        "user_id": user_id,
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "limits_remaining": user.get("generation_credits", 0),
        "audition_credits": user.get("audition_credits", 0),
        "storage_used_mb": 0,
        "storage_limit_mb": 500,
        "status": "active" if user.get("is_active", True) else "suspended",
        "total_credits_used": total_credits_used,
        "total_audio_seconds": round(total_audio_seconds, 2),
        "total_audio_minutes": round(total_audio_seconds / 60, 2),
        "total_generations": total_generations,
        "total_file_size_bytes": 0,
        "total_failed_generations": failed_count,
        "by_type": [{"type": t, "count": v["count"], "credits": v["credits"], "duration": round(v["duration"], 2)} for t, v in by_type.items()],
        "recent_generations": [
            {
                "user_id": r.get("user_id", ""),
                "gen_type": r.get("gen_type", ""),
                "text_length": r.get("text_length", 0),
                "duration_seconds": r.get("duration_seconds", 0),
                "status": r.get("status", ""),
                "created_at": str(r.get("created_at", "")),
            }
            for r in recent
        ],
    }


@admin_router.get("/usage/generation-logs")
async def admin_generation_logs_paginated(
    page: int = 1,
    per_page: int = 50,
    user_id: str = None,
    gen_type: str = None,
    status: str = None,
    authorization: Optional[str] = Header(None)
):
    admin = await _auth_admin(authorization)

    # Build query
    where = {}
    if user_id:
        where["user_id"] = user_id
    if gen_type:
        where["gen_type"] = gen_type
    if status:
        where["status"] = status

    total = await ndb.count_rows("generation_logs", where if where else None)
    logs = await ndb.find_many("generation_logs", where if where else None, order_by={"created_at": "desc"}, limit=per_page)

    user_cache = {}
    result = []
    for log in logs:
        uid = log.get("user_id", "")
        if uid and uid not in user_cache:
            u = await ndb.find_one("user_profiles", {"user_id": uid})
            user_cache[uid] = u or {}

        info = user_cache.get(uid, {})
        result.append({
            "user_id": uid,
            "user_email": info.get("email", ""),
            "user_name": info.get("name", "Unknown"),
            "gen_type": log.get("gen_type", ""),
            "text_length": log.get("text_length", 0),
            "duration_seconds": log.get("duration_seconds", 0),
            "status": log.get("status", ""),
            "provider": log.get("provider", ""),
            "created_at": str(log.get("created_at", "")),
        })

    return {
        "logs": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


@admin_router.get("/usage/alerts")
async def admin_usage_alerts(resolved: bool = None, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    where = {}
    if resolved is not None:
        where["resolved"] = resolved

    alerts = await ndb.find_many("usage_alerts", where if where else None, order_by={"created_at": "desc"}, limit=200)

    return [
        {
            "alert_id": a.get("alert_id", ""),
            "user_id": a.get("user_id", ""),
            "alert_type": a.get("alert_type", ""),
            "message": a.get("message", ""),
            "resolved": a.get("resolved", False),
            "resolved_at": str(a.get("resolved_at", "")) if a.get("resolved_at") else None,
            "created_at": str(a.get("created_at", "")),
        }
        for a in alerts
    ]


@admin_router.patch("/usage/alerts/{alert_id}/resolve")
async def admin_resolve_alert(alert_id: str, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    result = await ndb.update_rows(
        "usage_alerts",
        {"alert_id": alert_id},
        {"resolved": True, "resolved_at": datetime.now(timezone.utc).isoformat()}
    )

    if result.get("affected_rows", 0) == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Alert resolved"}


@admin_router.get("/usage/elevenlabs-sync")
async def admin_elevenlabs_sync_status(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    syncs = await ndb.find_many("elevenlabs_sync_logs", order_by={"created_at": "desc"}, limit=20)

    return [
        {
            "status": s.get("status", ""),
            "voices_count": s.get("voices_count", 0),
            "error": s.get("error", ""),
            "created_at": str(s.get("created_at", "")),
        }
        for s in syncs
    ]


@admin_router.post("/usage/validate-elevenlabs")
async def admin_trigger_elevenlabs_validation(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    # Log the sync attempt
    sync_result = await ndb.insert_one("elevenlabs_sync_logs", {
        "status": "success",
        "voices_count": 0,
        "error": "",
    })

    await ndb.insert_one("admin_logs", {
        "admin_id": admin["user_id"],
        "action": "trigger_elevenlabs_validation",
        "target_type": "system",
        "target_id": "elevenlabs",
        "details": "{}",
    })

    return {"status": "success", "message": "ElevenLabs validation triggered"}


# ============ VOICE ENGINE SETTINGS ============

@admin_router.get("/voice-settings")
async def get_voice_settings(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    settings = await ndb.find_one("voice_settings", {"setting_id": "default"})
    if not settings:
        return {"activeProvider": "gemini", "updatedAt": None}

    return {
        "activeProvider": settings.get("active_provider", "gemini"),
        "updatedAt": str(settings.get("updated_at", "")) if settings.get("updated_at") else None
    }


@admin_router.post("/voice-settings")
async def update_voice_settings(body: Dict, authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    provider = body.get("activeProvider", "gemini")
    if provider not in ("elevenlabs", "gemini"):
        raise HTTPException(status_code=400, detail="Invalid provider. Must be 'elevenlabs' or 'gemini'.")

    now = datetime.now(timezone.utc).isoformat()

    # Try to update existing, if not found, insert
    existing = await ndb.find_one("voice_settings", {"setting_id": "default"})
    if existing:
        await ndb.update_rows("voice_settings", {"setting_id": "default"}, {"active_provider": provider, "updated_at": now})
    else:
        await ndb.insert_one("voice_settings", {"setting_id": "default", "active_provider": provider})

    await ndb.insert_one("admin_logs", {
        "admin_id": admin["user_id"],
        "action": "update_voice_settings",
        "target_type": "system",
        "target_id": "voice_settings",
        "details": f'{{"activeProvider": "{provider}"}}',
    })

    return {"message": f"Voice engine switched to {provider}", "activeProvider": provider, "updatedAt": now}


@admin_router.get("/voice-settings/voices")
async def get_admin_voice_details(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    from routers.creator import _build_admin_voices, GEMINI_VOICES_MASTER
    return {
        "provider": "gemini",
        "model": "gemini-2.5-flash-preview-tts",
        "total_voices": len(GEMINI_VOICES_MASTER),
        "voices": _build_admin_voices(),
    }


@admin_router.post("/generate-voice-samples")
async def admin_generate_voice_samples(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    from routers.creator import generate_all_voice_samples, GEMINI_VOICES_MASTER
    import asyncio

    ready_count = await ndb.count_rows("voice_samples", {"status": "ready"})
    generating_count = await ndb.count_rows("voice_samples", {"status": "generating"})

    if generating_count > 0:
        return {
            "message": "Generation already in progress",
            "ready": ready_count,
            "generating": generating_count,
            "total": len(GEMINI_VOICES_MASTER)
        }

    asyncio.create_task(generate_all_voice_samples())

    await ndb.insert_one("admin_logs", {
        "admin_id": admin["user_id"],
        "action": "generate_voice_samples",
        "target_type": "system",
        "target_id": "voice_samples",
        "details": f'{{"ready_count": {ready_count}}}',
    })

    return {
        "message": "Voice sample generation started",
        "currently_ready": ready_count,
        "total_voices": len(GEMINI_VOICES_MASTER)
    }


@admin_router.get("/voice-samples/status")
async def admin_voice_samples_status(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    from routers.creator import GEMINI_VOICES_MASTER

    samples = await ndb.find_many("voice_samples", limit=100)
    ready = sum(1 for s in samples if s.get("status") == "ready")
    failed = sum(1 for s in samples if s.get("status") == "failed")
    generating = sum(1 for s in samples if s.get("status") == "generating")

    return {
        "total_voices": len(GEMINI_VOICES_MASTER),
        "ready": ready,
        "failed": failed,
        "generating": generating,
        "not_started": len(GEMINI_VOICES_MASTER) - len(samples),
        "samples": [
            {
                "voice_id": s.get("voice_id", ""),
                "display_name": s.get("display_name", ""),
                "status": s.get("status", ""),
                "duration_seconds": s.get("duration_seconds", 0),
                "error": s.get("error", ""),
            }
            for s in samples
        ]
    }


@admin_router.get("/usage/global-stats")
async def admin_global_usage_stats(authorization: Optional[str] = Header(None)):
    admin = await _auth_admin(authorization)

    # Get all successful generation logs
    logs = await ndb.find_many("generation_logs", {"status": "success"}, limit=10000)

    total_credits = sum(l.get("text_length", 0) for l in logs)
    total_duration = sum(l.get("duration_seconds", 0) for l in logs)
    total_count = len(logs)

    failed_count = await ndb.count_rows("generation_logs", {"status": "failed"})
    active_alerts = await ndb.count_rows("usage_alerts", {"resolved": False})

    # By type
    by_type = {}
    for l in logs:
        gt = l.get("gen_type", "voice")
        if gt not in by_type:
            by_type[gt] = {"count": 0, "credits": 0, "duration": 0}
        by_type[gt]["count"] += 1
        by_type[gt]["credits"] += l.get("text_length", 0)
        by_type[gt]["duration"] += l.get("duration_seconds", 0)

    return {
        "total_credits_used": total_credits,
        "total_audio_seconds": round(total_duration, 2),
        "total_audio_minutes": round(total_duration / 60, 2),
        "total_file_size_bytes": 0,
        "total_generations": total_count,
        "total_failed_generations": failed_count,
        "total_storage_bytes": 0,
        "total_storage_mb": 0,
        "active_alerts": active_alerts,
        "by_type": [{"type": t, "count": v["count"], "credits": v["credits"], "duration": round(v["duration"], 2)} for t, v in by_type.items()],
        "elevenlabs_sync": None
    }



# ============ VOICE GENERATION CONTROLS ============

@admin_router.get("/generation/limits")
async def get_generation_limits(authorization: Optional[str] = Header(None)):
    """Get current system generation limits."""
    admin = await _auth_admin(authorization)
    
    import generation_queue as gq
    limits = await gq.get_system_limits()
    
    return {
        "rpd": limits.get("rpd", 50),
        "rpm": limits.get("rpm", 5),
        "tpm": limits.get("tpm", 10000),
        "auto_distribute": limits.get("auto_distribute", True),
        "default_creator_rpd": limits.get("default_creator_rpd", 10),
        "default_creator_rpm": limits.get("default_creator_rpm", 2),
        "batch_size": limits.get("batch_size", 10)
    }


@admin_router.post("/generation/limits")
async def update_generation_limits(body: Dict, authorization: Optional[str] = Header(None)):
    """Update system generation limits."""
    admin = await _auth_admin(authorization)
    
    import generation_queue as gq
    
    # Validate inputs
    limits = {}
    if "rpd" in body:
        limits["rpd"] = max(1, int(body["rpd"]))
    if "rpm" in body:
        limits["rpm"] = max(1, int(body["rpm"]))
    if "tpm" in body:
        limits["tpm"] = max(100, int(body["tpm"]))
    if "auto_distribute" in body:
        limits["auto_distribute"] = bool(body["auto_distribute"])
    if "default_creator_rpd" in body:
        limits["default_creator_rpd"] = max(1, int(body["default_creator_rpd"]))
    if "default_creator_rpm" in body:
        limits["default_creator_rpm"] = max(1, int(body["default_creator_rpm"]))
    if "batch_size" in body:
        limits["batch_size"] = max(2, min(20, int(body["batch_size"])))
    
    updated = await gq.update_system_limits(limits, admin["user_id"])
    
    await ndb.insert_one("admin_logs", {
        "admin_id": admin["user_id"],
        "action": "update_generation_limits",
        "target_type": "system",
        "target_id": "generation_limits",
        "details": str(limits)
    })
    
    return {"message": "Generation limits updated", "limits": updated}


@admin_router.get("/generation/analytics")
async def get_generation_analytics(authorization: Optional[str] = Header(None)):
    """Get comprehensive generation analytics."""
    admin = await _auth_admin(authorization)
    
    import generation_queue as gq
    return await gq.get_generation_analytics()


@admin_router.get("/generation/creators")
async def get_creator_generation_stats(authorization: Optional[str] = Header(None)):
    """Get generation stats for all creators."""
    admin = await _auth_admin(authorization)
    
    import generation_queue as gq
    stats = await gq.get_all_creator_stats()
    
    return {
        "creators": stats,
        "total_active": sum(1 for s in stats if s.get("generation_status") == "active"),
        "total_inactive": sum(1 for s in stats if s.get("generation_status") != "active")
    }


@admin_router.patch("/generation/creators/{user_id}/status")
async def update_creator_generation_status(user_id: str, body: Dict, authorization: Optional[str] = Header(None)):
    """Enable or disable generation access for a creator."""
    admin = await _auth_admin(authorization)
    
    status = body.get("status", "active")
    if status not in ("active", "inactive"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'inactive'")
    
    import generation_queue as gq
    await gq.update_creator_generation_status(user_id, status, admin["user_id"])
    
    return {"message": f"Creator generation status set to {status}"}


@admin_router.patch("/generation/creators/{user_id}/limits")
async def update_creator_generation_limits(user_id: str, body: Dict, authorization: Optional[str] = Header(None)):
    """Set individual generation limits for a creator."""
    admin = await _auth_admin(authorization)
    
    daily_limit = body.get("daily_limit")
    per_minute_limit = body.get("per_minute_limit")
    
    if daily_limit is not None:
        daily_limit = max(0, int(daily_limit))
    if per_minute_limit is not None:
        per_minute_limit = max(0, int(per_minute_limit))
    
    import generation_queue as gq
    await gq.update_creator_limits(user_id, daily_limit, per_minute_limit, admin["user_id"])
    
    return {"message": "Creator limits updated"}


@admin_router.get("/generation/queue")
async def get_generation_queue_status(authorization: Optional[str] = Header(None)):
    """Get current generation queue status including live worker stats."""
    admin = await _auth_admin(authorization)
    
    import queue_worker as qw
    live_info = await qw.get_queue_info()

    import generation_queue as gq
    db_status = await gq.get_queue_status()

    return {
        "live_queue": live_info,
        "db_queue": db_status,
    }



# ──────────────────────────────────────────────
#  GENERATION ANALYTICS & DEBUG ENDPOINTS
# ──────────────────────────────────────────────

_SAFE_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]+$')

def _sanitize_id(value: str) -> str:
    """Validate that an ID contains only safe characters to prevent SQL injection."""
    if not _SAFE_ID_RE.match(value):
        raise HTTPException(status_code=400, detail="Invalid ID format")
    return value

@admin_router.get("/analytics/generation/summary")
async def get_generation_analytics_summary(authorization: Optional[str] = Header(None)):
    """Global generation analytics summary."""
    await _auth_admin(authorization)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        rows = await ndb.find_many(
            "generation_metrics",
            where={"created_at": {"_gte": today_start}},
            limit=10000,
        )
    except Exception as e:
        logger.warning(f"Analytics query failed: {e}")
        rows = []

    def _sum(field): return sum(float(r.get(field) or 0) for r in rows)
    def _avg(field): return (_sum(field) / len(rows)) if rows else 0

    total_hits = _sum("cache_hits")
    total_misses = _sum("cache_misses")
    cache_hit_rate = (total_hits / (total_hits + total_misses) * 100) if (total_hits + total_misses) > 0 else 0

    total_gemini = _sum("gemini_calls_used")
    total_saved = _sum("gemini_calls_saved")
    batch_efficiency = (total_saved / (total_gemini + total_saved) * 100) if (total_gemini + total_saved) > 0 else 0

    total_cost = _sum("estimated_cost")
    gen_count = len(rows)
    fallback_count = sum(1 for r in rows if r.get("fallback_triggered") in (True, "true", "t", "1", 1))

    return {
        "today": {
            "total_dialogues": int(_sum("dialogue_count")),
            "gemini_calls_used": int(total_gemini),
            "gemini_calls_saved": int(total_saved),
            "deepgram_minutes": round(_sum("deepgram_audio_minutes"), 2),
            "avg_cost_per_episode": round(total_cost / gen_count if gen_count else 0, 4),
            "total_cost": round(total_cost, 4),
            "cache_hits": int(total_hits),
            "cache_misses": int(total_misses),
            "cache_hit_rate": round(cache_hit_rate, 1),
            "total_batches": int(_sum("batch_count")),
            "avg_segmentation_rate": round(_avg("segmentation_success_rate"), 1),
            "fallback_count": fallback_count,
            "generation_count": gen_count,
            "avg_generation_time": round(_avg("generation_time_seconds"), 1),
            "batch_efficiency": round(batch_efficiency, 1),
            "empty_gemini_responses": int(_sum("empty_gemini_responses")),
            "gemini_retries": int(_sum("gemini_retries")),
        }
    }


@admin_router.get("/analytics/generation/runs")
async def get_generation_runs(authorization: Optional[str] = Header(None),
                              creator_id: Optional[str] = None,
                              episode_id: Optional[str] = None,
                              limit: int = 50, offset: int = 0):
    """List generation runs with optional filters. Paginated."""
    await _auth_admin(authorization)

    where: Dict[str, Any] = {}
    if creator_id:
        where["user_id"] = {"_eq": _sanitize_id(creator_id)}
    if episode_id:
        where["episode_id"] = {"_eq": _sanitize_id(episode_id)}

    try:
        rows = await ndb.find_many(
            "generation_metrics",
            where=where if where else None,
            order_by={"created_at": "desc"},
            limit=min(limit, 100),
        )
        total = await ndb.count_rows("generation_metrics", where if where else None)
    except Exception as e:
        logger.warning(f"Generation runs query failed: {e}")
        return {"runs": [], "total": 0}

    runs = []
    for r in rows:
        runs.append({
            "generation_id": r.get("generation_id", ""),
            "creator_id": r.get("user_id", ""),
            "episode_id": r.get("episode_id", ""),
            "dialogue_count": int(float(r.get("dialogue_count") or 0)),
            "speaker_pair_count": int(float(r.get("speaker_pair_count") or 0)),
            "batch_count": int(float(r.get("batch_count") or 0)),
            "gemini_calls_used": int(float(r.get("gemini_calls_used") or 0)),
            "gemini_calls_saved": int(float(r.get("gemini_calls_saved") or 0)),
            "cache_hits": int(float(r.get("cache_hits") or 0)),
            "cache_misses": int(float(r.get("cache_misses") or 0)),
            "deepgram_audio_minutes": round(float(r.get("deepgram_audio_minutes") or 0), 3),
            "segmentation_success_rate": round(float(r.get("segmentation_success_rate") or 0), 1),
            "fallback_triggered": r.get("fallback_triggered") in (True, "true", "t", "1", 1),
            "generation_time_seconds": round(float(r.get("generation_time_seconds") or 0), 1),
            "estimated_cost": round(float(r.get("estimated_cost") or 0), 4),
            "created_at": str(r.get("created_at") or ""),
            "empty_gemini_responses": int(float(r.get("empty_gemini_responses") or 0)),
            "gemini_retries": int(float(r.get("gemini_retries") or 0)),
        })

    return {"runs": runs, "total": total}


@admin_router.get("/analytics/generation/{generation_id}/debug")
async def get_generation_debug_logs(generation_id: str, authorization: Optional[str] = Header(None)):
    """Get debug logs for a specific generation run."""
    await _auth_admin(authorization)

    safe_id = _sanitize_id(generation_id)
    try:
        rows = await ndb.find_many(
            "generation_debug_logs",
            where={"generation_id": {"_eq": safe_id}},
            order_by={"created_at": "asc"},
            limit=200,
        )
    except Exception as e:
        logger.warning(f"Debug logs query failed: {e}")
        return {"logs": []}

    logs = []
    for r in rows:
        meta = r.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        logs.append({
            "log_id": r.get("log_id", ""),
            "event_type": r.get("event_type", ""),
            "message": r.get("message", ""),
            "metadata": meta,
            "created_at": str(r.get("created_at") or ""),
        })

    return {"logs": logs}


# ============ STORAGE MANAGEMENT ============

@admin_router.get("/storage/stats")
async def admin_storage_stats(authorization: Optional[str] = Header(None)):
    """Return storage lifecycle stats: total clips, cached, inactive, stale."""
    await _auth_admin(authorization)
    import storage_cleanup as sc
    stats = await sc.get_storage_stats()
    return stats


@admin_router.post("/storage/cleanup")
async def admin_run_cleanup(authorization: Optional[str] = Header(None)):
    """Trigger an immediate storage cleanup pass (inactive + stale cached clips)."""
    await _auth_admin(authorization)
    import storage_cleanup as sc
    result = await sc.run_scheduled_cleanup()
    return result


@admin_router.post("/storage/cleanup/episode/{episode_id}")
async def admin_cleanup_episode(episode_id: str, authorization: Optional[str] = Header(None)):
    """Delete all tracked clips for a specific episode."""
    await _auth_admin(authorization)
    import storage_cleanup as sc
    result = await sc.cleanup_episode_clips(episode_id, skip_if_published=False)
    return result


@admin_router.post("/storage/cleanup/story/{story_id}")
async def admin_cleanup_story(story_id: str, authorization: Optional[str] = Header(None)):
    """Delete all tracked clips for a specific story."""
    await _auth_admin(authorization)
    import storage_cleanup as sc
    result = await sc.cleanup_story_clips(story_id)
    return result


@admin_router.get("/storage/clips")
async def admin_list_clips(
    episode_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_cached: Optional[bool] = None,
    limit: int = 100,
    authorization: Optional[str] = Header(None),
):
    """List tracked audio clips with optional filters."""
    await _auth_admin(authorization)
    where: Dict[str, Any] = {}
    if episode_id:
        where["episode_id"] = {"_eq": episode_id}
    if is_active is not None:
        where["is_active"] = {"_eq": is_active}
    if is_cached is not None:
        where["is_cached"] = {"_eq": is_cached}
    import supabase_db as ndb
    clips = await ndb.find_many("audio_clips", where if where else None, limit=limit,
                                order_by={"created_at": "desc"})
    return {"clips": clips, "count": len(clips)}
