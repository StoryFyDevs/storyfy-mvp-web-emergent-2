from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
import asyncio

logger = logging.getLogger("storyfy")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("StoryFy starting up (Supabase backend)")

    # Auto-generate voice samples if needed
    try:
        from routers.creator import GEMINI_VOICES_MASTER, generate_all_voice_samples
        import supabase_db as ndb
        ready_count = await ndb.count_rows("voice_samples", {"status": "ready"})
        if ready_count < len(GEMINI_VOICES_MASTER):
            asyncio.create_task(generate_all_voice_samples())
            logger.info(f"Auto-triggered voice sample generation ({ready_count}/{len(GEMINI_VOICES_MASTER)} ready)")
        else:
            logger.info(f"All {ready_count} voice samples ready")
    except Exception as e:
        logger.warning(f"Voice sample check skipped: {e}")

    # Tables already created via Supabase SQL migration — just verify connectivity
    try:
        import supabase_db as ndb
        count = await ndb.count_rows("generation_metrics")
        logger.info(f"Generation analytics table ready ({count} rows)")
    except Exception as e:
        logger.warning(f"Analytics table check skipped: {e}")

    # Ensure Supabase storage buckets exist
    try:
        import supabase_storage as _st
        _st._ensure_buckets()
        logger.info("Storage buckets verified/created")
    except Exception as e:
        logger.warning(f"Storage bucket check skipped: {e}")

    # Start daily storage cleanup background task
    try:
        from storage_cleanup import _daily_cleanup_loop
        asyncio.create_task(_daily_cleanup_loop())
        logger.info("Storage cleanup scheduler started")
    except Exception as e:
        logger.warning(f"Storage cleanup scheduler skipped: {e}")

    # Start global generation queue worker
    try:
        import queue_worker as qw
        await qw.start_worker()
        logger.info("Global generation queue worker started")
    except Exception as e:
        logger.warning(f"Queue worker start failed: {e}")

    yield

    logger.info("StoryFy shutting down")


app = FastAPI(title="StoryFy API", lifespan=lifespan)

cors_origins_env = os.environ.get("CORS_ORIGINS", "")
if cors_origins_env:
    origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
else:
    origins = []

if origins:
    # Specific origins — use exact list with credentials
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # No specific origins — use regex to reflect any origin (allows credentials)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Import and register routers
from routers.auth import auth_router
from routers.creator import creator_router
from routers.admin import admin_router

app.include_router(auth_router)
app.include_router(creator_router)
app.include_router(admin_router)

from routers.mobile import mobile_v1_router
app.include_router(mobile_v1_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "backend": "supabase"}
