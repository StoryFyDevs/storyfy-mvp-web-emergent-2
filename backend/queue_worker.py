"""
Global Generation Queue Worker - Processes all audio generation jobs
with fair round-robin scheduling, rate limiting, and retry logic.

Architecture:
  Frontend → submit_job() → DB + in-memory scheduler
  Worker loop: pick_next_fair() → check rate limits → process → update DB
  Frontend polls: get_job_status() → returns status + queue position
"""
import asyncio
import uuid
import logging
import json
import time
from datetime import datetime, timezone
from collections import deque, defaultdict
from typing import Dict, Optional, Any

import supabase_db as ndb

logger = logging.getLogger("queue_worker")

# ──────────────────────────────────────────────
#  RATE LIMITS (Gemini API)
# ──────────────────────────────────────────────
RPM_LIMIT = 10       # Requests per minute
RPD_LIMIT = 50       # Requests per day
TPM_LIMIT = 10000    # Tokens per minute

# ──────────────────────────────────────────────
#  RETRY CONFIG
# ──────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAYS = [5, 10, 20]  # seconds (exponential backoff)


class RateLimiter:
    """Global rate limiter for Gemini API calls.
    Shared by both the queue worker and batch generation in script_compiler.
    """

    def __init__(self):
        self._minute_requests: deque = deque()
        self._minute_tokens: int = 0
        self._last_minute_reset: float = time.time()
        self._daily_count: int = 0
        self._daily_date: Optional[str] = None
        self._lock = asyncio.Lock()

    async def can_proceed(self, estimated_tokens: int = 500) -> bool:
        async with self._lock:
            self._cleanup_minute_window()
            today = datetime.now(timezone.utc).date().isoformat()
            if self._daily_date != today:
                self._daily_count = 0
                self._daily_date = today

            if len(self._minute_requests) >= RPM_LIMIT:
                return False
            if self._minute_tokens + estimated_tokens > TPM_LIMIT:
                return False
            if self._daily_count >= RPD_LIMIT:
                return False
            return True

    async def record(self, tokens_used: int = 0):
        async with self._lock:
            self._minute_requests.append(time.time())
            self._minute_tokens += tokens_used
            self._daily_count += 1

    async def seconds_until_available(self) -> float:
        async with self._lock:
            self._cleanup_minute_window()
            if len(self._minute_requests) >= RPM_LIMIT and self._minute_requests:
                oldest = self._minute_requests[0]
                return max(1.0, 60.0 - (time.time() - oldest))
            return 0.0

    def _cleanup_minute_window(self):
        now = time.time()
        cutoff = now - 60
        while self._minute_requests and self._minute_requests[0] < cutoff:
            self._minute_requests.popleft()
        if now - self._last_minute_reset >= 60:
            self._minute_tokens = 0
            self._last_minute_reset = now


class FairScheduler:
    """Round-robin per-user job scheduler.

    Ensures no single user monopolizes the queue:
      User A → 1 job → User B → 1 job → User C → 1 job → repeat
    """

    def __init__(self):
        self._user_queues: Dict[str, deque] = defaultdict(deque)
        self._user_order: deque = deque()
        self._jobs: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def add_job(self, job: Dict):
        async with self._lock:
            job_id = job["job_id"]
            user_id = job["user_id"]
            self._jobs[job_id] = job
            self._user_queues[user_id].append(job_id)
            if user_id not in self._user_order:
                self._user_order.append(user_id)

    async def pick_next(self) -> Optional[Dict]:
        async with self._lock:
            if not self._user_order:
                return None

            tried = 0
            while tried < len(self._user_order):
                user_id = self._user_order[0]
                self._user_order.rotate(-1)
                tried += 1

                if self._user_queues[user_id]:
                    job_id = self._user_queues[user_id].popleft()
                    if not self._user_queues[user_id]:
                        try:
                            self._user_order.remove(user_id)
                        except ValueError:
                            pass
                        del self._user_queues[user_id]

                    job = self._jobs.pop(job_id, None)
                    if job:
                        return job

            return None

    async def get_position(self, job_id: str) -> int:
        """Get 0-based position of a job in the queue. Returns -1 if not found."""
        async with self._lock:
            position = 0
            seen_users = list(self._user_order)
            for uid in seen_users:
                for jid in self._user_queues.get(uid, []):
                    if jid == job_id:
                        return position
                    position += 1
            return -1

    async def queue_size(self) -> int:
        async with self._lock:
            return sum(len(q) for q in self._user_queues.values())

    async def requeue_job(self, job: Dict):
        """Put a job back at the front of its user's queue (for rate-limit waits)."""
        async with self._lock:
            job_id = job["job_id"]
            user_id = job["user_id"]
            self._jobs[job_id] = job
            self._user_queues[user_id].appendleft(job_id)
            if user_id not in self._user_order:
                self._user_order.appendleft(user_id)


# ──────────────────────────────────────────────
#  GLOBAL SINGLETONS
# ──────────────────────────────────────────────
_rate_limiter = RateLimiter()
_scheduler = FairScheduler()
_worker_task: Optional[asyncio.Task] = None


# ──────────────────────────────────────────────
#  PUBLIC API
# ──────────────────────────────────────────────

async def submit_job(user_id: str, job_type: str, payload: Dict) -> str:
    """Submit a generation job to the global queue. Returns job_id."""
    job_id = f"qj_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    job = {
        "job_id": job_id,
        "user_id": user_id,
        "type": job_type,
        "payload": payload,
        "status": "queued",
        "retry_count": 0,
        "created_at": now,
    }

    await ndb.insert_one("generation_queue", {
        "queue_id": job_id,
        "user_id": user_id,
        "request_type": job_type,
        "request_data": json.dumps(payload),
        "status": "queued",
    })

    await _scheduler.add_job(job)
    queue_size = await _scheduler.queue_size()
    logger.info(f"Job {job_id} queued: type={job_type}, user={user_id}, queue_size={queue_size}")
    return job_id


async def get_job_status(job_id: str) -> Optional[Dict]:
    """Get job status including queue position."""
    item = await ndb.find_one("generation_queue", {"queue_id": job_id})
    if not item:
        return None

    status = item.get("status", "unknown")
    position = -1
    queue_size = 0

    if status == "queued":
        position = await _scheduler.get_position(job_id)
        queue_size = await _scheduler.queue_size()

    result_data = item.get("result_data")
    if result_data and isinstance(result_data, str):
        try:
            result_data = json.loads(result_data)
        except (json.JSONDecodeError, TypeError):
            result_data = None

    return {
        "job_id": job_id,
        "status": status,
        "position_in_queue": max(0, position) if status == "queued" else 0,
        "queue_size": queue_size,
        "result": result_data if status == "completed" else None,
        "error": item.get("error_message", ""),
        "created_at": str(item.get("created_at", "")),
    }


async def get_queue_info() -> Dict:
    """Get overall queue status for admin monitoring."""
    queue_size = await _scheduler.queue_size()
    try:
        processing = await ndb.count_rows("generation_queue", {"status": "processing"})
    except Exception:
        processing = 0
    return {
        "queued": queue_size,
        "processing": processing,
        "total_in_queue": queue_size + processing,
    }


# ──────────────────────────────────────────────
#  SHARED RATE LIMITER (used by script_compiler)
# ──────────────────────────────────────────────

async def acquire_gemini_slot(estimated_tokens: int = 500, timeout: float = 120) -> bool:
    """Wait for a rate-limited slot for a Gemini TTS call.
    Called by script_compiler before each Gemini request.
    Returns True if slot acquired, False if timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        if await _rate_limiter.can_proceed(estimated_tokens):
            return True
        wait = await _rate_limiter.seconds_until_available()
        await asyncio.sleep(min(wait, 5))
    return False


async def release_gemini_slot(tokens_used: int = 0):
    """Record that a Gemini TTS call completed. Must be called after acquire_gemini_slot."""
    await _rate_limiter.record(tokens_used)


# ──────────────────────────────────────────────
#  WORKER LOOP
# ──────────────────────────────────────────────

async def _process_job(job: Dict):
    """Process a single generation job with retry logic."""
    job_id = job["job_id"]
    job_type = job["type"]
    payload = job.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}
    user_id = job["user_id"]
    retry_count = job.get("retry_count", 0)

    now = datetime.now(timezone.utc).isoformat()
    await ndb.update_rows("generation_queue", {"queue_id": job_id}, {
        "status": "processing",
        "started_at": now,
    })

    try:
        if job_type == "regenerate":
            result = await _process_regenerate(payload, user_id)
        else:
            raise ValueError(f"Unknown job type: {job_type}")

        await ndb.update_rows("generation_queue", {"queue_id": job_id}, {
            "status": "completed",
            "result_data": json.dumps(result),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed (attempt {retry_count + 1}/{MAX_RETRIES}): {error_msg}")

        if retry_count < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[min(retry_count, len(RETRY_DELAYS) - 1)]
            job["retry_count"] = retry_count + 1
            job["payload"] = payload
            logger.info(f"Job {job_id}: retrying in {delay}s (attempt {retry_count + 2}/{MAX_RETRIES})")

            await ndb.update_rows("generation_queue", {"queue_id": job_id}, {
                "status": "queued",
                "error_message": f"Retry {retry_count + 1}: {error_msg[:200]}",
            })
            await asyncio.sleep(delay)
            await _scheduler.add_job(job)
        else:
            await ndb.update_rows("generation_queue", {"queue_id": job_id}, {
                "status": "failed",
                "error_message": f"Failed after {MAX_RETRIES} attempts: {error_msg[:300]}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.error(f"Job {job_id} failed permanently")


async def _process_regenerate(payload: Dict, user_id: str) -> Dict:
    """Process a single dialogue regeneration through the Gemini API."""
    import script_compiler as sc

    episode_id = payload["episode_id"]
    story_id = payload.get("story_id", "")
    dialogue = {
        "dialogue_index": payload["dialogue_index"],
        "index": payload["dialogue_index"],
        "character_id": payload.get("character_id", ""),
        "character_name": payload.get("character_name", "Unknown"),
        "text": payload["text"],
        "director_notes": payload.get("director_notes", ""),
    }
    voice_id = payload["voice_id"]

    result = await sc.regenerate_single_dialogue(
        episode_id=episode_id,
        story_id=story_id,
        dialogue=dialogue,
        voice_id=voice_id,
        user_id=user_id,
    )

    return {
        "success": True,
        "dialogue_index": payload["dialogue_index"],
        "audio_url": result["audio_url"],
        "duration_seconds": result["duration_seconds"],
        "filename": result.get("filename", ""),
        "character_name": payload.get("character_name", ""),
        "generated_voice_id": voice_id,
    }


async def _worker_loop():
    """Main worker loop — processes jobs with rate limiting and fair scheduling."""
    logger.info("Global queue worker started")

    while True:
        try:
            job = await _scheduler.pick_next()

            if job is None:
                await asyncio.sleep(1)
                continue

            payload = job.get("payload", {})
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    payload = {}
            estimated_tokens = len(payload.get("text", ""))

            if not await _rate_limiter.can_proceed(estimated_tokens):
                await _scheduler.requeue_job(job)
                wait = await _rate_limiter.seconds_until_available()
                logger.info(f"Rate limit reached, waiting {wait:.0f}s")
                await asyncio.sleep(min(wait, 10))
                continue

            await _process_job(job)
            await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info("Queue worker cancelled")
            break
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(5)


# ──────────────────────────────────────────────
#  STARTUP / RECOVERY
# ──────────────────────────────────────────────

async def start_worker():
    """Start the global queue worker and recover pending jobs from DB."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())
        logger.info("Queue worker task created")

    await _recover_pending_jobs()


async def _recover_pending_jobs():
    """Load queued jobs from DB into in-memory scheduler on startup."""
    try:
        pending = await ndb.find_many(
            "generation_queue",
            {"status": "queued"},
            order_by={"created_at": "asc"},
        )
        for item in pending:
            request_data = item.get("request_data", "{}")
            if isinstance(request_data, str):
                try:
                    request_data = json.loads(request_data)
                except (json.JSONDecodeError, TypeError):
                    request_data = {}

            job = {
                "job_id": item.get("queue_id"),
                "user_id": item.get("user_id", ""),
                "type": item.get("request_type", ""),
                "payload": request_data,
                "status": "queued",
                "retry_count": 0,
            }
            await _scheduler.add_job(job)

        if pending:
            logger.info(f"Recovered {len(pending)} pending jobs from database")
    except Exception as e:
        logger.warning(f"Failed to recover pending jobs: {e}")
