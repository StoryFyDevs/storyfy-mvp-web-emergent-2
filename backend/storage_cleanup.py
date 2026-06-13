"""
Storage Lifecycle Management for StoryFy.

Tracks all generated audio clips, soft-deletes them after a 7-day grace period,
and permanently removes files only after confirming no references remain.

SAFETY RULE: A clip is NEVER permanently deleted while it is "in use":
  1. is_active=True  → still the live clip for its script dialogue
  2. Referenced in an episode's project_state JSON → Audio Studio timeline
  3. Belongs to a published episode → is_published=True
"""

import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import supabase_db as ndb
import supabase_storage as nst

logger = logging.getLogger("storage_cleanup")

SOFT_DELETE_GRACE_DAYS = 7
STALE_CACHE_DAYS = 30


def _extract_file_id(audio_url: str) -> str:
    """Extract the storage file_id from an audio URL.

    Handles:
      - 'bucket/path'            — canonical Supabase format, returned as-is
      - 'nhost-file:bucket/path' — legacy prefix, stripped and returned
      - 'data:audio/...'         — embedded data, returns ''
      - 'http...'                — external URL, returns ''
    """
    if not audio_url:
        return ""
    if audio_url.startswith("nhost-file:"):
        return audio_url[len("nhost-file:"):]
    if audio_url.startswith("data:") or audio_url.startswith("http"):
        return ""
    return audio_url


# ──────────────────────────────────────────────
#  SAFETY GATE
# ──────────────────────────────────────────────

async def _is_clip_in_use(clip: dict) -> tuple[bool, str]:
    """Return (True, reason) if the clip must NOT be deleted, else (False, '')."""
    audio_url = clip.get("audio_url", "")
    episode_id = clip.get("episode_id", "")

    # 1. Still the active script-dialogue clip
    if clip.get("is_active"):
        return True, "is_active=True (script dialogue in use)"

    if episode_id:
        try:
            ep = await ndb.find_one(
                "episodes",
                {"episode_id": episode_id},
                fields=["episode_id", "is_published", "project_state"],
            )
        except Exception:
            ep = None

        if ep:
            # 2. Published episode — never touch
            if ep.get("is_published"):
                return True, "published episode"

            # 3. Clip URL appears in the Audio Studio project_state JSON
            ps = ep.get("project_state")
            if ps:
                try:
                    ps_str = ps if isinstance(ps, str) else json.dumps(ps)
                    if audio_url and audio_url in ps_str:
                        return True, "referenced in Audio Studio timeline"
                except Exception:
                    pass

    return False, ""


# ──────────────────────────────────────────────
#  SOFT DELETE (stage 1)
# ──────────────────────────────────────────────

async def _soft_delete_clips(clips: list) -> dict:
    """Mark clips as pending_deletion=True if not in use.
    Returns {'scanned', 'soft_deleted', 'skipped_in_use'}."""
    soft_deleted = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for clip in clips:
        file_id = clip.get("file_id", "")
        if not file_id:
            continue

        in_use, reason = await _is_clip_in_use(clip)
        if in_use:
            logger.info(f"Clip {file_id} skipped (in use: {reason})")
            skipped += 1
            continue

        try:
            await ndb.update_rows(
                "audio_clips",
                {"file_id": file_id},
                {"pending_deletion": True, "pending_deletion_at": now},
            )
            soft_deleted += 1
            logger.info(f"Soft-deleted clip file_id={file_id}")
        except Exception as e:
            logger.warning(f"soft_delete failed for {file_id}: {e}")

    return {
        "scanned": len(clips),
        "soft_deleted": soft_deleted,
        "skipped_in_use": skipped,
    }


# ──────────────────────────────────────────────
#  HARD DELETE (stage 2, after grace period)
# ──────────────────────────────────────────────

async def _hard_delete_pending_clips() -> dict:
    """Permanently delete clips that have been pending_deletion for >SOFT_DELETE_GRACE_DAYS days
    and still pass all safety checks."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SOFT_DELETE_GRACE_DAYS)).isoformat()
    deleted = 0
    reinstated = 0

    try:
        clips = await ndb.find_many(
            "audio_clips",
            {
                "pending_deletion": {"_eq": True},
                "pending_deletion_at": {"_lt": cutoff},
            },
            limit=500,
        )
    except Exception as e:
        logger.error(f"_hard_delete_pending_clips query failed: {e}")
        return {"scanned": 0, "deleted": 0, "reinstated": 0, "error": str(e)}

    for clip in clips:
        file_id = clip.get("file_id", "")
        if not file_id:
            continue

        # Final safety re-check before permanent deletion
        in_use, reason = await _is_clip_in_use(clip)
        if in_use:
            logger.warning(f"Clip {file_id} reinstated — now in use ({reason})")
            try:
                await ndb.update_rows(
                    "audio_clips",
                    {"file_id": file_id},
                    {"pending_deletion": False, "pending_deletion_at": None},
                )
            except Exception:
                pass
            reinstated += 1
            continue

        try:
            ok = await nst.delete_file(file_id)
            if ok:
                await ndb.delete_rows("audio_clips", {"file_id": file_id})
                deleted += 1
                logger.info(f"Hard-deleted clip file_id={file_id}")
            else:
                logger.warning(f"Storage delete returned false for file_id={file_id}")
        except Exception as e:
            logger.warning(f"Hard delete failed for file_id={file_id}: {e}")

    logger.info(
        f"_hard_delete_pending_clips: {deleted} deleted, {reinstated} reinstated from {len(clips)} pending"
    )
    return {"scanned": len(clips), "deleted": deleted, "reinstated": reinstated}


# ──────────────────────────────────────────────
#  PUBLIC LIFECYCLE API
# ──────────────────────────────────────────────

async def register_clip(
    audio_url: str,
    episode_id: str,
    story_id: str,
    dialogue_index: int,
    voice_id: str,
    cache_key: str = "",
    is_cached: bool = False,
) -> None:
    """Register a freshly uploaded clip. Marks any previous clips for the same
    episode + dialogue_index as inactive (they were regenerated) and queues
    them for soft deletion."""
    file_id = _extract_file_id(audio_url)
    if not file_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        # Mark older clips for this episode/dialogue as inactive
        if episode_id and dialogue_index is not None:
            try:
                old_clips = await ndb.find_many(
                    "audio_clips",
                    {
                        "episode_id": {"_eq": episode_id},
                        "dialogue_index": {"_eq": dialogue_index},
                        "is_active": {"_eq": True},
                        "file_id": {"_neq": file_id},
                    },
                    limit=50,
                )
                if old_clips:
                    for old in old_clips:
                        await ndb.update_rows(
                            "audio_clips",
                            {"file_id": old["file_id"]},
                            {
                                "is_active": False,
                                "pending_deletion": True,
                                "pending_deletion_at": now,
                            },
                        )
            except Exception:
                pass

        await ndb.insert_one("audio_clips", {
            "file_id": file_id,
            "audio_url": audio_url,
            "episode_id": episode_id,
            "story_id": story_id,
            "dialogue_index": dialogue_index,
            "voice_id": voice_id,
            "cache_key": cache_key or "",
            "is_cached": is_cached,
            "is_active": True,
            "pending_deletion": False,
            "last_used_at": now,
            "created_at": now,
        })
    except Exception as e:
        logger.warning(f"register_clip failed for {file_id}: {e}")


async def touch_clip(audio_url: str) -> None:
    """Update last_used_at and clear any pending_deletion flag when a clip is reused."""
    file_id = _extract_file_id(audio_url)
    if not file_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        await ndb.update_rows(
            "audio_clips",
            {"file_id": file_id},
            {"last_used_at": now, "pending_deletion": False, "pending_deletion_at": None},
        )
    except Exception as e:
        logger.warning(f"touch_clip failed for {file_id}: {e}")


async def mark_clip_inactive(audio_url: str) -> None:
    """Mark a clip as inactive and queue for soft deletion."""
    file_id = _extract_file_id(audio_url)
    if not file_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        await ndb.update_rows(
            "audio_clips",
            {"file_id": file_id},
            {"is_active": False, "pending_deletion": True, "pending_deletion_at": now},
        )
    except Exception as e:
        logger.warning(f"mark_clip_inactive failed for {file_id}: {e}")


# ──────────────────────────────────────────────
#  SCHEDULED CLEANUP PASSES
# ──────────────────────────────────────────────

async def cleanup_unused_cached_clips(max_age_days: int = STALE_CACHE_DAYS) -> dict:
    """Soft-delete cached clips not reused in the last max_age_days days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    try:
        clips = await ndb.find_many(
            "audio_clips",
            {
                "is_cached": {"_eq": True},
                "is_active": {"_eq": False},
                "pending_deletion": {"_eq": False},
                "last_used_at": {"_lt": cutoff},
            },
            limit=500,
        )
        result = await _soft_delete_clips(clips)
        logger.info(f"cleanup_unused_cached_clips: {result}")
        return result
    except Exception as e:
        logger.error(f"cleanup_unused_cached_clips error: {e}")
        return {"scanned": 0, "soft_deleted": 0, "skipped_in_use": 0, "error": str(e)}


async def cleanup_inactive_clips() -> dict:
    """Soft-delete unselected version clips older than 30 days.
    
    IMPORTANT: Inactive clips are now 'unselected versions' in the review workflow.
    They should NOT be immediately deleted — only after 30 days of being unselected.
    """
    VERSION_RETENTION_DAYS = 30
    cutoff = (datetime.now(timezone.utc) - timedelta(days=VERSION_RETENTION_DAYS)).isoformat()
    try:
        clips = await ndb.find_many(
            "audio_clips",
            {
                "is_active": {"_eq": False},
                "pending_deletion": {"_eq": False},
                "created_at": {"_lt": cutoff},
            },
            limit=500,
        )
        result = await _soft_delete_clips(clips)
        logger.info(f"cleanup_inactive_clips (30-day retention): {result}")
        return result
    except Exception as e:
        logger.error(f"cleanup_inactive_clips error: {e}")
        return {"scanned": 0, "soft_deleted": 0, "skipped_in_use": 0, "error": str(e)}


async def cleanup_episode_clips(episode_id: str, skip_if_published: bool = True) -> dict:
    """Soft-delete all tracked clips for an episode when it is deleted."""
    try:
        if skip_if_published:
            ep = await ndb.find_one("episodes", {"episode_id": episode_id}, fields=["is_published"])
            if ep and ep.get("is_published"):
                logger.info(f"cleanup_episode_clips: skipping published episode {episode_id}")
                return {"scanned": 0, "soft_deleted": 0, "skipped_in_use": 0, "skipped_published": True}

        clips = await ndb.find_many("audio_clips", {"episode_id": {"_eq": episode_id}}, limit=1000)
        result = await _soft_delete_clips(clips)

        # Also evict related audio_cache entries
        try:
            for clip in clips:
                url = clip.get("audio_url", "")
                if url:
                    await ndb.delete_rows("audio_cache", {"audio_url": {"_eq": url}})
        except Exception:
            pass

        logger.info(f"cleanup_episode_clips({episode_id}): {result}")
        return result
    except Exception as e:
        logger.error(f"cleanup_episode_clips error: {e}")
        return {"scanned": 0, "soft_deleted": 0, "skipped_in_use": 0, "error": str(e)}


async def cleanup_story_clips(story_id: str) -> dict:
    """Soft-delete all tracked clips for a story when it is deleted."""
    try:
        clips = await ndb.find_many("audio_clips", {"story_id": {"_eq": story_id}}, limit=2000)
        result = await _soft_delete_clips(clips)
        logger.info(f"cleanup_story_clips({story_id}): {result}")
        return result
    except Exception as e:
        logger.error(f"cleanup_story_clips error: {e}")
        return {"scanned": 0, "soft_deleted": 0, "skipped_in_use": 0, "error": str(e)}


async def get_storage_stats() -> dict:
    """Return storage stats for admin dashboard."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_CACHE_DAYS)).isoformat()
        grace_cutoff = (datetime.now(timezone.utc) - timedelta(days=SOFT_DELETE_GRACE_DAYS)).isoformat()

        total_clips = await ndb.count_rows("audio_clips")
        active_clips = await ndb.count_rows("audio_clips", {"is_active": {"_eq": True}})
        cached_clips = await ndb.count_rows("audio_clips", {"is_cached": {"_eq": True}})
        inactive_clips = await ndb.count_rows("audio_clips", {"is_active": {"_eq": False}})
        pending_clips = await ndb.count_rows("audio_clips", {"pending_deletion": {"_eq": True}})
        ready_for_hard_delete = await ndb.count_rows(
            "audio_clips",
            {"pending_deletion": {"_eq": True}, "pending_deletion_at": {"_lt": grace_cutoff}},
        )
        stale_cached = await ndb.count_rows(
            "audio_clips",
            {
                "is_cached": {"_eq": True},
                "is_active": {"_eq": False},
                "last_used_at": {"_lt": cutoff},
            },
        )
        return {
            "total_tracked_clips": total_clips,
            "active_clips": active_clips,
            "cached_clips": cached_clips,
            "inactive_clips": inactive_clips,
            "pending_soft_deletion": pending_clips,
            "ready_for_permanent_deletion": ready_for_hard_delete,
            "stale_cached_clips_30d": stale_cached,
            "soft_delete_grace_days": SOFT_DELETE_GRACE_DAYS,
            "stale_threshold_days": STALE_CACHE_DAYS,
        }
    except Exception as e:
        logger.error(f"get_storage_stats error: {e}")
        return {"error": str(e)}


async def run_scheduled_cleanup() -> dict:
    """Full cleanup pass:
      Pass 1 — soft-delete inactive and stale-cached clips (if not in use).
      Pass 2 — permanently delete clips past the 7-day grace period (if still not in use).
    """
    logger.info("Running scheduled storage cleanup...")

    result_inactive = await cleanup_inactive_clips()
    result_cached = await cleanup_unused_cached_clips(max_age_days=STALE_CACHE_DAYS)
    result_hard = await _hard_delete_pending_clips()

    total_soft = result_inactive.get("soft_deleted", 0) + result_cached.get("soft_deleted", 0)
    total_hard = result_hard.get("deleted", 0)

    logger.info(
        f"Scheduled cleanup complete: {total_soft} soft-deleted, {total_hard} permanently deleted"
    )
    return {
        "inactive_cleanup": result_inactive,
        "cached_cleanup": result_cached,
        "hard_delete": result_hard,
        "total_soft_deleted": total_soft,
        "total_permanently_deleted": total_hard,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }


async def _daily_cleanup_loop():
    """Background loop that runs cleanup once per day."""
    await asyncio.sleep(3600)
    while True:
        try:
            await run_scheduled_cleanup()
        except Exception as e:
            logger.error(f"Daily cleanup loop error: {e}")
        await asyncio.sleep(86400)
