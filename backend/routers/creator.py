from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import asyncio
import uuid
import base64
import time
import os
import shutil
import hashlib
import logging
import io
import wave

import requests as req_lib

import supabase_db as ndb
import supabase_storage as storage
import generation_queue as gq
from auth_service import resolve_user_from_token
from models import (
    StoryCreate, Story, EpisodeCreate, Episode,
    CharacterCreate, Character, TTSRequest, TTSResponse,
    DialogueRequest, DialogueResponse, AudioAsset
)

logger = logging.getLogger("creator")

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY', '')

# ElevenLabs client (lazy init)
_eleven_client = None
def _get_eleven_client():
    global _eleven_client
    if _eleven_client is None:
        try:
            from elevenlabs import ElevenLabs
            _eleven_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        except Exception:
            pass
    return _eleven_client


# ============ AUTH HELPER ============

async def _auth(authorization: Optional[str]) -> dict:
    """Verify token and return user profile."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return await resolve_user_from_token(token)


# ============ GEMINI VOICE SYSTEM ============

GEMINI_VOICES_MASTER = [
    {"voice_id": "Achernar", "gender": "Female", "tone": "Soft", "category": "narrator"},
    {"voice_id": "Achird", "gender": "Male", "tone": "Friendly", "category": "narrator"},
    {"voice_id": "Algenib", "gender": "Male", "tone": "Gravelly", "category": "deep_voice"},
    {"voice_id": "Algieba", "gender": "Male", "tone": "Smooth", "category": "calm"},
    {"voice_id": "Alnilam", "gender": "Male", "tone": "Firm", "category": "dramatic"},
    {"voice_id": "Aoede", "gender": "Female", "tone": "Breezy", "category": "calm"},
    {"voice_id": "Autonoe", "gender": "Female", "tone": "Bright", "category": "energetic"},
    {"voice_id": "Callirrhoe", "gender": "Female", "tone": "Easy-going", "category": "calm"},
    {"voice_id": "Charon", "gender": "Male", "tone": "Informative", "category": "narrator"},
    {"voice_id": "Despina", "gender": "Female", "tone": "Smooth", "category": "calm"},
    {"voice_id": "Enceladus", "gender": "Male", "tone": "Breathy", "category": "dramatic"},
    {"voice_id": "Erinome", "gender": "Female", "tone": "Clear", "category": "narrator"},
    {"voice_id": "Fenrir", "gender": "Male", "tone": "Excitable", "category": "energetic"},
    {"voice_id": "Gacrux", "gender": "Female", "tone": "Mature", "category": "deep_voice"},
    {"voice_id": "Iapetus", "gender": "Male", "tone": "Clear", "category": "narrator"},
    {"voice_id": "Kore", "gender": "Female", "tone": "Firm", "category": "dramatic"},
    {"voice_id": "Laomedeia", "gender": "Female", "tone": "Upbeat", "category": "energetic"},
    {"voice_id": "Leda", "gender": "Female", "tone": "Youthful", "category": "energetic"},
    {"voice_id": "Orus", "gender": "Male", "tone": "Firm", "category": "dramatic"},
    {"voice_id": "Puck", "gender": "Male", "tone": "Upbeat", "category": "energetic"},
    {"voice_id": "Pulcherrima", "gender": "Female", "tone": "Forward", "category": "dramatic"},
    {"voice_id": "Rasalgethi", "gender": "Male", "tone": "Informative", "category": "narrator"},
    {"voice_id": "Sadachbia", "gender": "Male", "tone": "Neutral", "category": "narrator"},
    {"voice_id": "Sadaltager", "gender": "Male", "tone": "Neutral", "category": "calm"},
    {"voice_id": "Schedar", "gender": "Male", "tone": "Even", "category": "calm"},
    {"voice_id": "Sulafat", "gender": "Female", "tone": "Warm", "category": "narrator"},
    {"voice_id": "Umbriel", "gender": "Male", "tone": "Authoritative", "category": "deep_voice"},
    {"voice_id": "Vindemiatrix", "gender": "Female", "tone": "Gentle", "category": "calm"},
    {"voice_id": "Zephyr", "gender": "Female", "tone": "Energetic", "category": "energetic"},
    {"voice_id": "Zubenelgenubi", "gender": "Male", "tone": "Deep", "category": "deep_voice"},
]

VOICE_DISPLAY_MAP = {
    "Achernar": {"display_name": "Aarohi", "tone_label": "Soft Storyteller"},
    "Achird": {"display_name": "Arjun", "tone_label": "Friendly Narrator"},
    "Algenib": {"display_name": "Kabir", "tone_label": "Gravelly & Bold"},
    "Algieba": {"display_name": "Vihaan", "tone_label": "Smooth & Calm"},
    "Alnilam": {"display_name": "Dev", "tone_label": "Firm & Commanding"},
    "Aoede": {"display_name": "Meher", "tone_label": "Breezy & Relaxed"},
    "Autonoe": {"display_name": "Tara", "tone_label": "Bright & Lively"},
    "Callirrhoe": {"display_name": "Naina", "tone_label": "Easy-going"},
    "Charon": {"display_name": "Samar", "tone_label": "Informative Narrator"},
    "Despina": {"display_name": "Rhea", "tone_label": "Smooth & Soothing"},
    "Enceladus": {"display_name": "Raghav", "tone_label": "Breathy & Dramatic"},
    "Erinome": {"display_name": "Ira", "tone_label": "Clear & Crisp"},
    "Fenrir": {"display_name": "Aryan", "tone_label": "Excitable & Fun"},
    "Gacrux": {"display_name": "Shobha", "tone_label": "Mature & Rich"},
    "Iapetus": {"display_name": "Neel", "tone_label": "Clear & Neutral"},
    "Kore": {"display_name": "Kavya", "tone_label": "Firm & Expressive"},
    "Laomedeia": {"display_name": "Myra", "tone_label": "Upbeat & Cheerful"},
    "Leda": {"display_name": "Kiara", "tone_label": "Youthful & Fresh"},
    "Orus": {"display_name": "Veer", "tone_label": "Firm & Strong"},
    "Puck": {"display_name": "Yash", "tone_label": "Upbeat & Energetic"},
    "Pulcherrima": {"display_name": "Ritika", "tone_label": "Forward & Bold"},
    "Rasalgethi": {"display_name": "Aditya", "tone_label": "Informative & Warm"},
    "Sadachbia": {"display_name": "Karan", "tone_label": "Neutral & Steady"},
    "Sadaltager": {"display_name": "Manav", "tone_label": "Neutral & Calm"},
    "Schedar": {"display_name": "Rahul", "tone_label": "Even & Balanced"},
    "Sulafat": {"display_name": "Aisha", "tone_label": "Warm & Confident"},
    "Umbriel": {"display_name": "Rudra", "tone_label": "Authoritative"},
    "Vindemiatrix": {"display_name": "Suman", "tone_label": "Gentle & Mature"},
    "Zephyr": {"display_name": "Zoya", "tone_label": "Energetic & Bright"},
    "Zubenelgenubi": {"display_name": "Aman", "tone_label": "Deep & Resonant"},
}

VOICE_CATEGORIES = {
    "narrator": "Narrator",
    "deep_voice": "Deep Voice",
    "energetic": "Energetic",
    "calm": "Calm",
    "dramatic": "Dramatic",
}

STYLE_PRESETS = {
    "storytelling": "Speak in a storytelling tone with natural pauses and engaging delivery.",
    "emotional": "Speak with deep emotional expressiveness and varied intonation.",
    "dramatic": "Speak in a dramatic tone with emphasis and theatrical delivery.",
    "calm": "Speak in a calm, soothing tone with gentle pacing.",
    "horror": "Speak in a dark, suspenseful tone with eerie pauses.",
    "casual": "Speak in a casual, conversational tone with natural rhythm.",
}


def _build_creator_voices():
    voices = []
    for v in GEMINI_VOICES_MASTER:
        mapping = VOICE_DISPLAY_MAP.get(v["voice_id"], {})
        voices.append({
            "voice_id": v["voice_id"],
            "name": mapping.get("display_name", v["voice_id"]),
            "tone": mapping.get("tone_label", v["tone"]),
            "gender": v["gender"],
            "category": v["category"],
            "category_label": VOICE_CATEGORIES.get(v["category"], v["category"]),
        })
    return voices


def _build_admin_voices():
    voices = []
    for v in GEMINI_VOICES_MASTER:
        mapping = VOICE_DISPLAY_MAP.get(v["voice_id"], {})
        voices.append({
            "voice_id": v["voice_id"],
            "display_name": mapping.get("display_name", v["voice_id"]),
            "tone": v["tone"], "gender": v["gender"], "category": v["category"],
            "model": "gemini-2.5-flash-preview-tts", "provider": "gemini",
        })
    return voices


async def _get_active_provider() -> str:
    settings = await ndb.find_one("voice_settings", {"setting_id": "default"})
    if settings:
        return settings.get("active_provider", "gemini")
    return "gemini"


def _pcm_to_wav(pcm_bytes, sample_rate=24000, channels=1, sample_width=2):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _estimate_audio_duration(audio_data, fmt):
    if "mp3" in fmt:
        bitrate = 128000
        if "192" in fmt: bitrate = 192000
        elif "64" in fmt: bitrate = 64000
        elif "32" in fmt: bitrate = 32000
        return len(audio_data) * 8 / bitrate
    if "pcm" in fmt:
        sample_rate = 44100
        for sr in [16000, 22050, 24000, 44100]:
            if str(sr) in fmt:
                sample_rate = sr
                break
        return len(audio_data) / (sample_rate * 2)
    return len(audio_data) / (44100 * 2)


async def _gemini_generate_speech(text, voice_name="Kore", style_preset=None, style_instructions=None, language_code=None):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Voice engine not configured")

    # Acquire global rate-limit slot before calling Gemini
    import queue_worker as qw
    if not await qw.acquire_gemini_slot(estimated_tokens=max(len(text), 100), timeout=60):
        raise HTTPException(status_code=429, detail="Audio generation is currently busy. Your request has been rate-limited. Please try again shortly.")

    prompt_parts = []
    if style_preset and style_preset in STYLE_PRESETS:
        prompt_parts.append(STYLE_PRESETS[style_preset])
    if style_instructions:
        prompt_parts.append(style_instructions)
    if language_code:
        prompt_parts.append(f"Speak in {language_code} language.")

    full_text = " ".join(prompt_parts) + "\n\n" + text if prompt_parts else text

    payload = {
        "contents": [{"parts": [{"text": full_text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}}
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}"
    try:
        resp = req_lib.post(url, json=payload, timeout=60)
    except Exception as e:
        await qw.release_gemini_slot(0)
        raise HTTPException(status_code=503, detail="Voice service is temporarily unavailable. Please try again shortly.")

    # Record the call in the global rate limiter
    await qw.release_gemini_slot(max(len(text), 100))

    if resp.status_code != 200:
        logger.error(f"Gemini TTS error: {resp.status_code} {resp.text[:300]}")
        
        # Map Gemini API errors to user-friendly messages
        if resp.status_code == 429:
            raise HTTPException(status_code=429, detail="Voice service is busy. Please try again in a moment.")
        elif resp.status_code == 401 or resp.status_code == 403:
            raise HTTPException(status_code=502, detail="Voice service configuration error. Please contact support.")
        elif resp.status_code >= 500:
            raise HTTPException(status_code=503, detail="Voice service is temporarily unavailable. Please try again shortly.")
        else:
            raise HTTPException(status_code=502, detail="Voice generation failed. Please try again.")

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise HTTPException(status_code=502, detail="No audio generated")

    inline_data = candidates[0].get("content", {}).get("parts", [{}])[0].get("inlineData", {})
    audio_b64 = inline_data.get("data", "")
    if not audio_b64:
        raise HTTPException(status_code=502, detail="No audio data in response")

    pcm_bytes = base64.b64decode(audio_b64)
    wav_bytes = _pcm_to_wav(pcm_bytes, sample_rate=24000)
    wav_b64 = base64.b64encode(wav_bytes).decode()
    duration = len(pcm_bytes) / (24000 * 2)

    return {
        "audio_url": f"data:audio/wav;base64,{wav_b64}",
        "duration_seconds": round(duration, 2),
        "text": text, "voice_id": voice_name,
        "settings_used": {"engine": "alternate", "voice": voice_name, "style_preset": style_preset}
    }


async def _track_generation(user_id, gen_type, text_length, duration, file_size, status, model, voice_id="", error=""):
    try:
        await ndb.insert_one("generation_logs", {
            "user_id": user_id, "gen_type": gen_type, "voice_id": voice_id or "",
            "text_length": text_length, "duration_seconds": duration or 0,
            "status": status, "provider": model or "", "error": (error or "")[:200],
            "character_name": "", "details": "{}",
        })
        if status == "success" and text_length > 0:
            await ndb.increment_field("user_profiles", {"user_id": user_id}, "generation_credits", -text_length)
            await ndb.increment_field("user_profiles", {"user_id": user_id}, "limits_remaining", -text_length)
    except Exception as e:
        logger.warning(f"Track generation error: {e}")


# ============ RESPONSE MAPPERS ============

def _to_story(row):
    if not row: return None
    return {
        "story_id": row.get("story_id", ""),
        "user_id": row.get("created_by", ""),
        "title": row.get("title", ""),
        "genre": row.get("genre", ""),
        "subGenre": row.get("sub_genre", ""),
        "language": row.get("language", "hi"),
        "status": row.get("status", "draft"),
        "description": row.get("description", ""),
        "coverImageUrl": row.get("cover_image_url", ""),
        "cover_art_url": row.get("cover_art_url", ""),
        "tags": row.get("tags", []),
        "publishedAt": row.get("published_at"),
        "play_count": row.get("play_count", 0),
        "story_type": row.get("story_type", "story"),
        "created_at": str(row.get("created_at", "")),
        "updated_at": str(row.get("updated_at", "")),
    }

def _to_episode(row):
    if not row: return None
    return {
        "episode_id": row.get("episode_id", ""),
        "story_id": row.get("story_id", ""),
        "title": row.get("title", ""),
        "order": row.get("order_index", 0),
        "status": row.get("status", "draft"),
        "script": row.get("script", ""),
        "audio_url": row.get("audio_url"),
        "duration": row.get("duration", 0),
        "project_state": row.get("project_state", {}),
        "isPublished": row.get("is_published", False),
        "publishedAt": row.get("published_at"),
        "finalAudioUrl": row.get("final_audio_url", ""),
        "play_count": row.get("play_count", 0),
        "created_at": str(row.get("created_at", "")),
        "updated_at": str(row.get("updated_at", "")),
    }

def _to_character(row):
    if not row: return None
    return {
        "character_id": row.get("character_id", ""),
        "story_id": row.get("story_id", ""),
        "name": row.get("name", ""),
        "voice_id": row.get("voice_id", ""),
        "display_name": row.get("display_name", ""),
        "tone": row.get("tone", ""),
        "category": row.get("category", ""),
        "created_at": str(row.get("created_at", "")),
    }


creator_router = APIRouter(prefix="/api", tags=["creator"])


# ============ STORY CRUD ============

@creator_router.post("/stories")
async def create_story(story_data: StoryCreate, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    user_id = profile["user_id"]

    story_id = f"story_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    row = await ndb.insert_one("stories", {
        "story_id": story_id,
        "created_by": user_id,
        "title": story_data.title,
        "genre": story_data.genre,
        "sub_genre": getattr(story_data, 'subGenre', '') or '',
        "language": getattr(story_data, 'language', 'hi') or 'hi',
        "description": getattr(story_data, 'description', '') or '',
        "story_type": getattr(story_data, 'story_type', 'story') or 'story',
        "status": "draft",
        "play_count": 0,
        "cover_image_url": "",
        "cover_art_url": "",
        "tags": [],
    })
    return _to_story(row)


@creator_router.get("/stories")
async def get_stories(authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    rows = await ndb.find_many("stories", {"created_by": profile["user_id"]}, order_by={"created_at": "desc"})
    return [_to_story(r) for r in rows]


@creator_router.get("/stories/{story_id}")
async def get_story(story_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    row = await ndb.find_one("stories", {"story_id": story_id, "created_by": profile["user_id"]})
    if not row:
        raise HTTPException(status_code=404, detail="Story not found")
    return _to_story(row)


@creator_router.put("/stories/{story_id}")
async def update_story(story_id: str, story_data: StoryCreate, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    result = await ndb.update_rows("stories", {"story_id": story_id, "created_by": profile["user_id"]}, {
        "title": story_data.title,
        "genre": story_data.genre,
        "sub_genre": getattr(story_data, 'subGenre', '') or '',
        "language": getattr(story_data, 'language', 'hi') or 'hi',
        "description": getattr(story_data, 'description', '') or '',
        "updated_at": "now()",
    })
    if result.get("affected_rows", 0) == 0:
        raise HTTPException(status_code=404, detail="Story not found")
    row = await ndb.find_one("stories", {"story_id": story_id})
    return _to_story(row)


@creator_router.delete("/stories/{story_id}")
async def delete_story(story_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    count = await ndb.delete_rows("stories", {"story_id": story_id, "created_by": profile["user_id"]})
    if count == 0:
        raise HTTPException(status_code=404, detail="Story not found")
    import storage_cleanup as sc
    asyncio.create_task(sc.cleanup_story_clips(story_id))
    return {"message": "Story deleted"}


# ============ PUBLISHING ============

@creator_router.post("/creator/stories/{story_id}/publish")
async def publish_story(story_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    story = await ndb.find_one("stories", {"story_id": story_id, "created_by": profile["user_id"]})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.get("status") == "published":
        return {"message": "Story is already published", "story_id": story_id, "status": "published"}

    now = datetime.now(timezone.utc).isoformat()
    await ndb.update_rows("stories", {"story_id": story_id}, {"status": "published", "published_at": now, "updated_at": now})
    return {"message": "Story published successfully", "story_id": story_id, "status": "published", "publishedAt": now}


@creator_router.post("/creator/stories/{story_id}/unpublish")
async def unpublish_story(story_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    story = await ndb.find_one("stories", {"story_id": story_id, "created_by": profile["user_id"]})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if story.get("status") == "draft":
        return {"message": "Story is already a draft", "story_id": story_id, "status": "draft"}

    now = datetime.now(timezone.utc).isoformat()
    await ndb.update_rows("stories", {"story_id": story_id}, {"status": "draft", "updated_at": now})
    await ndb.update_rows("episodes", {"story_id": story_id}, {"is_published": False, "updated_at": now})
    return {"message": "Story unpublished", "story_id": story_id, "status": "draft"}


@creator_router.post("/creator/episodes/{episode_id}/publish")
async def publish_episode(episode_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    story = await ndb.find_one("stories", {"story_id": ep["story_id"], "created_by": profile["user_id"]})
    if not story:
        raise HTTPException(status_code=403, detail="Not authorized")
    if ep.get("is_published"):
        return {"message": "Episode already published", "episode_id": episode_id, "isPublished": True}
    if not ep.get("final_audio_url"):
        raise HTTPException(status_code=422, detail="Cannot publish: no rendered audio")
    if (ep.get("duration") or 0) <= 0:
        raise HTTPException(status_code=422, detail="Cannot publish: duration must be > 0")

    now = datetime.now(timezone.utc).isoformat()
    await ndb.update_rows("episodes", {"episode_id": episode_id}, {"is_published": True, "published_at": now, "updated_at": now})
    return {"message": "Episode published", "episode_id": episode_id, "isPublished": True, "publishedAt": now}


@creator_router.post("/creator/episodes/{episode_id}/unpublish")
async def unpublish_episode(episode_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    story = await ndb.find_one("stories", {"story_id": ep["story_id"], "created_by": profile["user_id"]})
    if not story:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not ep.get("is_published"):
        return {"message": "Episode already unpublished", "episode_id": episode_id, "isPublished": False}

    now = datetime.now(timezone.utc).isoformat()
    await ndb.update_rows("episodes", {"episode_id": episode_id}, {"is_published": False, "updated_at": now})
    return {"message": "Episode unpublished", "episode_id": episode_id, "isPublished": False}


# ============ EPISODE CRUD ============

@creator_router.post("/episodes")
async def create_episode(episode_data: EpisodeCreate, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    story = await ndb.find_one("stories", {"story_id": episode_data.story_id, "created_by": profile["user_id"]})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    episode_id = f"ep_{uuid.uuid4().hex[:12]}"
    existing = await ndb.find_many("episodes", {"story_id": episode_data.story_id})
    next_order = len(existing)

    row = await ndb.insert_one("episodes", {
        "episode_id": episode_id,
        "story_id": episode_data.story_id,
        "created_by": profile["user_id"],
        "title": episode_data.title,
        "status": "draft",
        "order_index": next_order,
        "is_published": False,
        "play_count": 0,
        "duration": 0,
        "script": "",
        "audio_url": "",
        "final_audio_url": "",
        "script_content": "",
        "project_state": "{}",
        "storage_files": "[]",
        "duration_seconds": 0,
    })
    return _to_episode(row)


@creator_router.get("/episodes/story/{story_id}")
async def get_episodes(story_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    story = await ndb.find_one("stories", {"story_id": story_id, "created_by": profile["user_id"]})
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    rows = await ndb.find_many("episodes", {"story_id": story_id}, order_by={"order_index": "asc"})
    return [_to_episode(r) for r in rows]


@creator_router.get("/episodes/{episode_id}")
async def get_episode(episode_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    row = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not row:
        raise HTTPException(status_code=404, detail="Episode not found")
    return _to_episode(row)


@creator_router.put("/episodes/{episode_id}")
async def update_episode(episode_id: str, script: str = Form(None), status: str = Form(None), audio_url: str = Form(None), authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if script is not None:
        update_data["script"] = script
    if status is not None:
        update_data["status"] = status
    if audio_url is not None:
        update_data["audio_url"] = audio_url

    result = await ndb.update_rows("episodes", {"episode_id": episode_id}, update_data)
    if result.get("affected_rows", 0) == 0:
        raise HTTPException(status_code=404, detail="Episode not found")
    row = await ndb.find_one("episodes", {"episode_id": episode_id})
    return _to_episode(row)


@creator_router.delete("/episodes/{episode_id}")
async def delete_episode(episode_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    count = await ndb.delete_rows("episodes", {"episode_id": episode_id})
    if count == 0:
        raise HTTPException(status_code=404, detail="Episode not found")
    import storage_cleanup as sc
    asyncio.create_task(sc.cleanup_episode_clips(episode_id, skip_if_published=False))
    return {"message": "Episode deleted"}


# ============ PROJECT STATE ============

@creator_router.post("/episodes/{episode_id}/save-project")
async def save_project_state(episode_id: str, project_data: Dict[str, Any], authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if ep.get("is_published"):
        raise HTTPException(status_code=423, detail="Episode is published and locked.")

    import json
    await ndb.update_rows("episodes", {"episode_id": episode_id}, {
        "project_state": json.dumps(project_data),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": "Project saved successfully", "saved_at": datetime.now(timezone.utc).isoformat()}


@creator_router.get("/episodes/{episode_id}/project-state")
async def get_project_state(episode_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    ps = ep.get("project_state")
    if isinstance(ps, str):
        import json
        try:
            return json.loads(ps)
        except Exception:
            return {}
    return ps or {}


# ============ EPISODE CLIPS (Source-of-Truth for Audio Studio) ============

@creator_router.get("/episodes/{episode_id}/clips")
async def get_episode_clips(episode_id: str, authorization: Optional[str] = Header(None)):
    """Return all active audio clips for an episode, sorted by dialogue_index.
    This is the single source of truth for Audio Studio clip loading."""
    profile = await _auth(authorization)

    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Fetch all active clips sorted by dialogue_index
    clips = await ndb.find_many(
        "audio_clips",
        {"episode_id": episode_id, "is_active": True},
        order_by={"dialogue_index": "asc"},
        limit=500,
    )

    if not clips:
        return {"clips": [], "episode_id": episode_id}

    # Enrich with duration from audio_cache
    cache_keys = list(set(c.get("cache_key", "") for c in clips if c.get("cache_key")))
    cache_map = {}
    if cache_keys:
        for ck in cache_keys:
            entry = await ndb.find_one("audio_cache", {"cache_key": ck})
            if entry:
                cache_map[ck] = entry

    # Fetch characters from story for name mapping
    story_id = ep.get("story_id", "")
    characters = []
    if story_id:
        characters = await ndb.find_many("characters", {"story_id": story_id}, limit=100)
    voice_to_char = {c.get("voice_id", ""): c.get("name", "") for c in characters}

    result_clips = []
    for clip in clips:
        ck = clip.get("cache_key", "")
        cache_entry = cache_map.get(ck, {})
        voice_id = clip.get("voice_id", "")
        char_name = voice_to_char.get(voice_id, "")

        # Add cache-busting: use created_at or cache_key as version marker
        audio_url = clip.get("audio_url", "")
        created_ts = str(clip.get("created_at", ""))

        result_clips.append({
            "clip_id": clip.get("file_id", ""),
            "dialogue_index": clip.get("dialogue_index", 0),
            "audio_url": audio_url,
            "voice_id": voice_id,
            "version_hash": ck,
            "duration_seconds": cache_entry.get("duration_seconds", 0),
            "character_name": char_name,
            "dialogue_text": cache_entry.get("dialogue_text", ""),
            "created_at": created_ts,
        })

    logger.info(f"CLIPS_LOADED episode={episode_id} count={len(result_clips)}")
    return {"clips": result_clips, "episode_id": episode_id}


# ============ CHARACTERS ============

@creator_router.post("/characters")
async def create_character(char_data: CharacterCreate, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    character_id = f"char_{uuid.uuid4().hex[:12]}"
    row = await ndb.insert_one("characters", {
        "character_id": character_id,
        "story_id": char_data.story_id,
        "created_by": profile["user_id"],
        "name": char_data.name,
        "voice_id": char_data.voice_id,
        "display_name": "",
        "tone": "",
        "category": "",
        "voice_settings": "{}",
    })
    return _to_character(row)


@creator_router.get("/characters/story/{story_id}")
async def get_characters(story_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    rows = await ndb.find_many("characters", {"story_id": story_id})
    return [_to_character(r) for r in rows]


@creator_router.put("/characters/{character_id}")
async def update_character(character_id: str, char_data: CharacterCreate, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    result = await ndb.update_rows("characters", {"character_id": character_id}, {
        "name": char_data.name,
        "voice_id": char_data.voice_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    if result.get("affected_rows", 0) == 0:
        raise HTTPException(status_code=404, detail="Character not found")
    row = await ndb.find_one("characters", {"character_id": character_id})
    return _to_character(row)


@creator_router.delete("/characters/{character_id}")
async def delete_character(character_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    count = await ndb.delete_rows("characters", {"character_id": character_id})
    if count == 0:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"message": "Character deleted"}


# ============ TTS SETTINGS & VOICES ============

@creator_router.get("/tts/settings")
async def get_tts_settings(authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    active = await _get_active_provider()
    if active == "gemini":
        return {
            "engineType": "alternate",
            "controls": ["stylePreset", "customInstructions", "language"],
            "voices": _build_creator_voices(),
            "stylePresets": list(STYLE_PRESETS.keys()),
            "voiceCategories": VOICE_CATEGORIES,
            "audioTagsSupported": True,
        }
    return {
        "engineType": "default",
        "controls": ["stability", "similarity", "style", "speed", "speakerBoost", "format", "language"],
        "voices": None, "stylePresets": None, "voiceCategories": None, "audioTagsSupported": True,
    }


@creator_router.get("/voices")
async def get_voices(authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    active = await _get_active_provider()
    if active == "gemini":
        return {"voices": _build_creator_voices()}
    eleven = _get_eleven_client()
    if eleven:
        try:
            voices_response = eleven.voices.get_all()
            return {"voices": [{"voice_id": v.voice_id, "name": v.name, "category": getattr(v, 'category', 'general')} for v in voices_response.voices]}
        except Exception as e:
            logger.error(f"ElevenLabs error: {e}")
    return {"voices": []}


# ============ CREDITS ============

@creator_router.get("/credits")
async def get_credits(authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    return {
        "generation_credits": profile.get("generation_credits", 0),
        "audition_credits": profile.get("audition_credits", 0),
        "generation_status": profile.get("generation_status", "inactive"),
    }


@creator_router.get("/generation/status")
async def get_generation_status(authorization: Optional[str] = Header(None)):
    """Get generation availability and limits for the current user."""
    profile = await _auth(authorization)
    user_id = profile["user_id"]
    
    # Get limits and usage
    creator_limits = await gq.get_creator_limits(user_id)
    usage_today = await gq.get_creator_usage_today(user_id)
    
    # Calculate remaining
    if creator_limits.get("allowed"):
        daily_limit = creator_limits.get("daily_limit", 10)
        generations_remaining = max(0, daily_limit - usage_today.get("generation_count", 0))
        gen_credits = profile.get("generation_credits", 0)
        
        return {
            "can_generate": generations_remaining > 0 and gen_credits > 0,
            "generations_remaining": generations_remaining,
            "daily_limit": daily_limit,
            "generations_today": usage_today.get("generation_count", 0),
            "generation_credits": gen_credits,
            "audition_credits": profile.get("audition_credits", 0),
            "generation_status": profile.get("generation_status", "inactive"),
            "status": "active"
        }
    else:
        return {
            "can_generate": False,
            "generations_remaining": 0,
            "daily_limit": 0,
            "generations_today": 0,
            "generation_credits": profile.get("generation_credits", 0),
            "audition_credits": profile.get("audition_credits", 0),
            "generation_status": profile.get("generation_status", "inactive"),
            "status": creator_limits.get("status", "inactive"),
            "message": creator_limits.get("reason", "audio_access_disabled")
        }


# ============ AUDITION ============

@creator_router.post("/tts/audition")
async def audition_voice(body: Dict[str, Any], authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    user_id = profile["user_id"]

    # Master switch: check generation_status
    gen_status = profile.get("generation_status", "inactive")
    if gen_status != "active":
        raise HTTPException(status_code=403, detail="audio_access_disabled")

    voice_id = body.get("voice_id", "")
    text = body.get("text", "").strip()
    if not voice_id or not text:
        raise HTTPException(status_code=400, detail="voice_id and text are required")

    text_hash = hashlib.sha256(f"{voice_id}:{text}".encode()).hexdigest()
    cached = await ndb.find_one("audition_cache", {"voice_id": voice_id, "text_hash": text_hash})
    if cached:
        return {"audio_url": cached["audio_url"], "duration_seconds": cached.get("duration_seconds", 0), "cached": True}

    credits = profile.get("audition_credits", 0)
    if credits <= 0:
        raise HTTPException(status_code=402, detail="insufficient_audition_credits")

    # Check rate limits
    rate_check = await gq.check_rate_limits(user_id, len(text))
    if not rate_check.get("allowed"):
        raise HTTPException(status_code=429, detail=rate_check.get("reason", "Audio generation is currently unavailable."))

    active = await _get_active_provider()
    try:
        if active == "gemini":
            result = await _gemini_generate_speech(text=text, voice_name=voice_id, style_instructions="Speak naturally in Hindi with expressive delivery.", language_code="hi")
        else:
            from elevenlabs import VoiceSettings
            eleven = _get_eleven_client()
            voice_settings = VoiceSettings(stability=0.5, similarity_boost=0.75, style=0.0, use_speaker_boost=True)
            audio_gen = eleven.text_to_speech.convert(text=text, voice_id=voice_id, model_id="eleven_v3", voice_settings=voice_settings, output_format="mp3_44100_128", language_code="hi")
            audio_data = b"".join(audio_gen)
            audio_b64 = base64.b64encode(audio_data).decode()
            duration = _estimate_audio_duration(audio_data, "mp3_44100_128")
            result = {"audio_url": f"data:audio/mpeg;base64,{audio_b64}", "duration_seconds": round(duration, 2)}

        # Record successful generation
        await gq.record_generation(user_id, success=True, tokens_used=len(text))

        # Cache
        try:
            await ndb.insert_one("audition_cache", {"voice_id": voice_id, "text_hash": text_hash, "audio_url": result["audio_url"], "duration_seconds": result.get("duration_seconds", 0)})
        except Exception:
            pass  # unique constraint

        # Deduct credit
        await ndb.increment_field("user_profiles", {"user_id": user_id}, "audition_credits", -1)

        return {"audio_url": result["audio_url"], "duration_seconds": result.get("duration_seconds", 0), "cached": False}
    except HTTPException:
        # Record failed generation
        await gq.record_generation(user_id, success=False, tokens_used=0)
        raise
    except Exception as e:
        error_str = str(e).lower()
        logger.error(f"Audition error: {e}")
        
        # Record failed generation
        await gq.record_generation(user_id, success=False, tokens_used=0)
        
        # Map technical errors to user-friendly messages
        if "429" in str(e) or "quota" in error_str or "rate" in error_str:
            raise HTTPException(status_code=429, detail="Audio generation is currently busy. Please wait a moment and try again.")
        elif "401" in str(e) or "unauthorized" in error_str or "api key" in error_str:
            raise HTTPException(status_code=502, detail="Voice service configuration error. Please contact support.")
        elif "timeout" in error_str or "connection" in error_str:
            raise HTTPException(status_code=503, detail="Voice service is temporarily unavailable. Please try again shortly.")
        else:
            raise HTTPException(status_code=500, detail="Voice generation failed. Please try again.")


# ============ VOICE PREVIEW SAMPLES ============

async def generate_all_voice_samples():
    import asyncio as _asyncio
    logger.info("Starting voice sample generation...")
    generated = 0
    for v in GEMINI_VOICES_MASTER:
        voice_id = v["voice_id"]
        display_name = VOICE_DISPLAY_MAP.get(voice_id, {}).get("display_name", voice_id)

        existing = await ndb.find_one("voice_samples", {"voice_id": voice_id, "status": "ready"})
        if existing:
            continue

        text = f"{display_name} की आवाज़ सुनने में कुछ ऐसी लगती है"
        try:
            try:
                await ndb.insert_one("voice_samples", {"voice_id": voice_id, "display_name": display_name, "status": "generating", "text_content": text, "audio_url": "", "storage_path": "", "storage_file_id": "", "duration_seconds": 0, "error": ""})
            except Exception:
                await ndb.update_rows("voice_samples", {"voice_id": voice_id}, {"status": "generating"})

            result = await _gemini_generate_speech(text=text, voice_name=voice_id, language_code="hi")

            # Upload to Supabase Storage
            storage_file_id = ""
            try:
                audio_b64_data = result["audio_url"].split(",")[1]
                audio_bytes = base64.b64decode(audio_b64_data)
                file_meta = await storage.upload_file(f"{voice_id}.wav", audio_bytes, "audio/wav")
                storage_file_id = file_meta.get("id", "")
            except Exception as ue:
                logger.warning(f"Storage upload failed for {voice_id}: {ue}")

            await ndb.update_rows("voice_samples", {"voice_id": voice_id}, {
                "display_name": display_name, "audio_url": result["audio_url"],
                "duration_seconds": result["duration_seconds"], "status": "ready",
                "storage_file_id": storage_file_id, "text_content": text,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            generated += 1
            logger.info(f"Voice sample {generated}: {display_name} ({voice_id})")
        except Exception as e:
            logger.error(f"Voice sample failed {voice_id}: {e}")
            try:
                await ndb.update_rows("voice_samples", {"voice_id": voice_id}, {"status": "failed", "error": str(e)[:200]})
            except Exception:
                pass
        await _asyncio.sleep(2)
    logger.info(f"Voice sample generation done: {generated} new")


@creator_router.get("/voices/samples")
async def get_voice_samples_status(authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    rows = await ndb.find_many("voice_samples", {"status": "ready"}, fields=["voice_id"])
    return {"samples": {r["voice_id"]: True for r in rows}, "total_available": len(rows), "total_voices": len(GEMINI_VOICES_MASTER)}


@creator_router.get("/voices/preview/{voice_id}")
async def get_voice_preview(voice_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    sample = await ndb.find_one("voice_samples", {"voice_id": voice_id, "status": "ready"})
    if not sample:
        raise HTTPException(status_code=404, detail="Voice sample not available yet")
    return {"audio_url": sample["audio_url"], "duration_seconds": sample.get("duration_seconds", 0), "voice_id": voice_id, "display_name": sample.get("display_name", voice_id)}


# ============ TTS GENERATE ============

@creator_router.post("/tts/generate")
async def generate_tts(request: TTSRequest, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    user_id = profile["user_id"]

    # Master switch check
    if profile.get("generation_status", "inactive") != "active":
        raise HTTPException(status_code=403, detail="audio_access_disabled")

    text_length = len(request.text)
    credits_needed = text_length

    gen_credits = profile.get("generation_credits", 0)
    if gen_credits < credits_needed:
        await _track_generation(user_id, "voice", text_length, 0, 0, "failed", "internal", request.voice_id, "Insufficient credits")
        raise HTTPException(status_code=402, detail="insufficient_generation_credits")

    # Check rate limits
    rate_check = await gq.check_rate_limits(user_id, text_length)
    if not rate_check.get("allowed"):
        raise HTTPException(status_code=429, detail=rate_check.get("reason", "Audio generation is currently unavailable."))

    active = await _get_active_provider()

    if active == "gemini":
        try:
            result = await _gemini_generate_speech(text=request.text, voice_name=request.voice_id, style_preset=request.style_preset, style_instructions=request.style_instructions, language_code=request.language_code)
            file_size = len(base64.b64decode(result["audio_url"].split(",")[1])) if "," in result["audio_url"] else 0
            await _track_generation(user_id, "voice", text_length, result["duration_seconds"], file_size, "success", "internal", request.voice_id)
            
            # Record successful generation for rate limiting
            await gq.record_generation(user_id, success=True, tokens_used=text_length)
            
            return TTSResponse(audio_url=result["audio_url"], text=request.text, voice_id=request.voice_id, duration_seconds=result["duration_seconds"], settings_used=result["settings_used"])
        except HTTPException:
            await gq.record_generation(user_id, success=False, tokens_used=0)
            raise
        except Exception as e:
            error_str = str(e).lower()
            await _track_generation(user_id, "voice", text_length, 0, 0, "failed", "internal", request.voice_id, str(e))
            await gq.record_generation(user_id, success=False, tokens_used=0)
            
            # Map technical errors to user-friendly messages
            if "429" in str(e) or "quota" in error_str or "rate" in error_str:
                raise HTTPException(status_code=429, detail="Audio generation is currently busy. Please wait a moment and try again.")
            elif "401" in str(e) or "unauthorized" in error_str or "api key" in error_str:
                raise HTTPException(status_code=502, detail="Voice service configuration error. Please contact support.")
            elif "timeout" in error_str or "connection" in error_str:
                raise HTTPException(status_code=503, detail="Voice service is temporarily unavailable. Please try again shortly.")
            else:
                raise HTTPException(status_code=500, detail="Voice generation failed. Please try again.")

    # ElevenLabs fallback
    try:
        from elevenlabs import VoiceSettings
        eleven = _get_eleven_client()
        voice_settings = VoiceSettings(stability=request.validated_stability, similarity_boost=request.similarity_boost, style=request.style, use_speaker_boost=request.use_speaker_boost, speed=request.speed)
        convert_params = {"text": request.text, "voice_id": request.voice_id, "model_id": "eleven_v3", "voice_settings": voice_settings, "output_format": request.output_format}
        if request.language_code:
            convert_params["language_code"] = request.language_code
        audio_gen = eleven.text_to_speech.convert(**convert_params)
        audio_data = b"".join(audio_gen)
        audio_b64 = base64.b64encode(audio_data).decode()
        mime_type = "audio/mpeg" if not request.output_format.startswith("pcm") else "audio/wav"
        duration = _estimate_audio_duration(audio_data, request.output_format)
        settings_used = {"stability": request.validated_stability, "similarity_boost": request.similarity_boost, "style": request.style, "speed": request.speed, "use_speaker_boost": request.use_speaker_boost, "output_format": request.output_format, "model": "eleven_v3"}
        await _track_generation(user_id, "voice", text_length, round(duration, 2), len(audio_data), "success", "eleven_v3", request.voice_id)
        await gq.record_generation(user_id, success=True, tokens_used=text_length)
        return TTSResponse(audio_url=f"data:{mime_type};base64,{audio_b64}", text=request.text, voice_id=request.voice_id, duration_seconds=round(duration, 2), settings_used=settings_used)
    except HTTPException:
        await gq.record_generation(user_id, success=False, tokens_used=0)
        raise
    except Exception as e:
        await _track_generation(user_id, "voice", text_length, 0, 0, "failed", "eleven_v3", request.voice_id, str(e))
        await gq.record_generation(user_id, success=False, tokens_used=0)
        raise HTTPException(status_code=500, detail="Voice generation failed. Please try again.")


@creator_router.post("/tts/dialogue")
async def generate_dialogue(request: DialogueRequest, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    user_id = profile["user_id"]

    if profile.get("generation_status", "inactive") != "active":
        raise HTTPException(status_code=403, detail="audio_access_disabled")

    total_text_length = sum(len(s.text) for s in request.inputs)
    gen_credits = profile.get("generation_credits", 0)
    if gen_credits < total_text_length:
        raise HTTPException(status_code=402, detail="insufficient_generation_credits")
    try:
        eleven = _get_eleven_client()
        dialogue_inputs = [{"text": s.text, "voice_id": s.voice_id} for s in request.inputs]
        audio_gen = eleven.text_to_dialogue.convert(inputs=dialogue_inputs, model_id="eleven_v3")
        audio_data = b"".join(audio_gen)
        audio_b64 = base64.b64encode(audio_data).decode()
        duration = _estimate_audio_duration(audio_data, "mp3_44100_128")
        await _track_generation(user_id, "dialogue", total_text_length, round(duration, 2), len(audio_data), "success", "eleven_v3")
        return DialogueResponse(audio_url=f"data:audio/mpeg;base64,{audio_b64}", speakers_count=len(set(s.voice_id for s in request.inputs)), total_turns=len(request.inputs))
    except Exception as e:
        await _track_generation(user_id, "dialogue", total_text_length, 0, 0, "failed", "eleven_v3", error=str(e))
        raise HTTPException(status_code=500, detail=f"Dialogue generation failed: {e}")


@creator_router.post("/tts/isolate")
async def isolate_audio(authorization: Optional[str] = Header(None), audio_data: Dict[str, Any] = None):
    profile = await _auth(authorization)
    if not audio_data or "audio_base64" not in audio_data:
        raise HTTPException(status_code=400, detail="audio_base64 is required")
    try:
        audio_b64 = audio_data["audio_base64"]
        if "," in audio_b64:
            audio_b64 = audio_b64.split(",", 1)[1]
        raw_audio = base64.b64decode(audio_b64)
        headers = {"xi-api-key": ELEVENLABS_API_KEY}
        resp = req_lib.post("https://api.elevenlabs.io/v1/audio-isolation/convert", headers=headers, files={"file": ("audio.mp3", raw_audio, "audio/mpeg")}, data={"format": "other"}, timeout=60)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Audio isolation failed")
        cleaned = resp.content
        cleaned_b64 = base64.b64encode(cleaned).decode()
        return {"audio_url": f"data:audio/mpeg;base64,{cleaned_b64}", "file_size": len(cleaned), "duration_seconds": round(_estimate_audio_duration(cleaned, "mp3_44100_128"), 2)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio isolation failed: {e}")


@creator_router.get("/tts/models")
async def get_tts_models(authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    return {
        "models": [
            {"model_id": "eleven_v3", "name": "Eleven v3", "description": "Most expressive", "languages": 70, "features": ["audio_tags"], "max_characters": 5000},
        ],
        "audio_tags": {"emotions": ["cheerfully", "sad", "excited", "angry", "whispering"], "usage": "Wrap in square brackets"},
        "output_formats": [
            {"id": "mp3_44100_128", "description": "MP3 Standard"},
            {"id": "mp3_44100_192", "description": "MP3 High quality"},
        ],
    }


# ============ AUDIO STORAGE ============

@creator_router.post("/audio/upload")
async def upload_audio(file: UploadFile = File(...), story_id: str = Form(...), episode_id: str = Form(None), asset_type: str = Form("voice"), name: str = Form(...), authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    user_id = profile["user_id"]
    try:
        file_content = await file.read()
        timestamp = int(time.time())
        safe_filename = file.filename.replace(" ", "_")
        storage_filename = f"{user_id}_{story_id}_{timestamp}_{safe_filename}"

        file_meta = await storage.upload_file(storage_filename, file_content, file.content_type or "audio/wav")
        storage_file_id = file_meta.get("id", "")

        asset_id = f"asset_{uuid.uuid4().hex[:12]}"
        row = await ndb.insert_one("audio_assets", {
            "asset_id": asset_id, "story_id": story_id, "episode_id": episode_id or "",
            "created_by": user_id, "name": name, "asset_type": asset_type,
            "file_path": storage_filename, "storage_file_id": storage_file_id,
            "duration_seconds": 0, "file_size": len(file_content), "mime_type": file.content_type or "audio/wav",
        })
        return {"asset_id": asset_id, "user_id": user_id, "story_id": story_id, "episode_id": episode_id, "asset_type": asset_type, "name": name, "file_path": storage_filename, "duration": None, "metadata": {}, "created_at": str(row.get("created_at", ""))}
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@creator_router.get("/audio/assets/{story_id}")
async def get_audio_assets(story_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    rows = await ndb.find_many("audio_assets", {"story_id": story_id, "created_by": profile["user_id"]})
    return [{"asset_id": r["asset_id"], "user_id": r["created_by"], "story_id": r["story_id"], "episode_id": r.get("episode_id", ""), "asset_type": r.get("asset_type", "voice"), "name": r.get("name", ""), "file_path": r.get("file_path", ""), "duration": r.get("duration_seconds"), "metadata": {}, "created_at": str(r.get("created_at", ""))} for r in rows]


@creator_router.get("/audio/download/{asset_id}")
async def download_audio(asset_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    asset = await ndb.find_one("audio_assets", {"asset_id": asset_id, "created_by": profile["user_id"]})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        file_content = await storage.download_file(asset["storage_file_id"])
        return StreamingResponse(iter([file_content]), media_type=asset.get("mime_type", "audio/mpeg"), headers={"Content-Disposition": f"attachment; filename={asset.get('name', 'audio')}"})
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise HTTPException(status_code=500, detail="Download failed")


@creator_router.delete("/audio/assets/{asset_id}")
async def delete_audio_asset(asset_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    asset = await ndb.find_one("audio_assets", {"asset_id": asset_id, "created_by": profile["user_id"]})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        if asset.get("storage_file_id"):
            await storage.delete_file(asset["storage_file_id"])
        await ndb.delete_rows("audio_assets", {"asset_id": asset_id})
        return {"message": "Asset deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")


@creator_router.get("/audio/stream-file/{file_id:path}")
async def stream_audio_file(file_id: str):
    """Stream an audio file from Supabase Storage by file ID.
    This is the stable endpoint for audio playback — presigned URLs expire,
    but this endpoint always works because it authenticates server-side."""
    try:
        file_content = await storage.download_file(file_id)
        return StreamingResponse(
            iter([file_content]),
            media_type="audio/wav",
            headers={
                "Content-Type": "audio/wav",
                "Cache-Control": "no-cache, must-revalidate",
                "Accept-Ranges": "bytes",
            },
        )
    except Exception as e:
        logger.error(f"Stream file error for {file_id}: {e}")
        raise HTTPException(status_code=404, detail="Audio file not found")


# ============ USAGE ============

@creator_router.get("/usage/me")
async def get_my_usage(authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    return {
        "user_id": profile["user_id"],
        "limits_remaining": profile.get("generation_credits", 0),
        "storage_used_mb": 0,
        "storage_limit_mb": 500,
        "total_credits_used": 0,
        "total_audio_seconds": 0,
        "total_generations": 0,
    }


# ============ RENDER (CHUNKED UPLOAD) ============

RENDER_TEMP_DIR = "/tmp/storyfy_renders"

@creator_router.post("/episodes/{episode_id}/render/chunk")
async def upload_render_chunk(episode_id: str, chunk: UploadFile = File(...), chunk_index: int = Form(...), total_chunks: int = Form(...), authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    story = await ndb.find_one("stories", {"story_id": ep["story_id"], "created_by": profile["user_id"]})
    if not story:
        raise HTTPException(status_code=403, detail="Not authorized")

    chunk_dir = os.path.join(RENDER_TEMP_DIR, episode_id)
    os.makedirs(chunk_dir, exist_ok=True)
    chunk_data = await chunk.read()
    with open(os.path.join(chunk_dir, f"chunk_{chunk_index:05d}"), "wb") as f:
        f.write(chunk_data)
    return {"message": f"Chunk {chunk_index + 1}/{total_chunks} received", "chunk_index": chunk_index}


@creator_router.post("/episodes/{episode_id}/render/finalize")
async def finalize_render(episode_id: str, body: Dict[str, Any] = None, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    story = await ndb.find_one("stories", {"story_id": ep["story_id"], "created_by": profile["user_id"]})
    if not story:
        raise HTTPException(status_code=403, detail="Not authorized")

    duration = (body or {}).get("duration", 0)
    chunk_dir = os.path.join(RENDER_TEMP_DIR, episode_id)
    if not os.path.isdir(chunk_dir):
        raise HTTPException(status_code=400, detail="No render chunks found")

    chunk_files = sorted([f for f in os.listdir(chunk_dir) if f.startswith("chunk_")])
    if not chunk_files:
        raise HTTPException(status_code=400, detail="No render chunks found")

    assembled_path = os.path.join(chunk_dir, "final.wav")
    with open(assembled_path, "wb") as out_f:
        for cf in chunk_files:
            with open(os.path.join(chunk_dir, cf), "rb") as in_f:
                out_f.write(in_f.read())

    file_size = os.path.getsize(assembled_path)

    # Upload to Supabase Storage
    storage_filename = f"{profile['user_id']}_{ep['story_id']}_{episode_id}_final.wav"
    try:
        with open(assembled_path, "rb") as f:
            file_content = f.read()
        file_meta = await storage.upload_file(storage_filename, file_content, "audio/wav")
        storage_file_id = file_meta.get("id", "")
    except Exception as e:
        shutil.rmtree(chunk_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    shutil.rmtree(chunk_dir, ignore_errors=True)

    now = datetime.now(timezone.utc).isoformat()
    await ndb.update_rows("episodes", {"episode_id": episode_id}, {
        "final_audio_url": storage_file_id,
        "duration": round(duration, 2),
        "updated_at": now,
    })

    return {"message": "Audio rendered and saved", "episode_id": episode_id, "finalAudioUrl": storage_file_id, "duration": round(duration, 2), "file_size": file_size}


@creator_router.get("/episodes/{episode_id}/render/stream")
async def stream_rendered_audio(episode_id: str, authorization: Optional[str] = Header(None)):
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep or not ep.get("final_audio_url"):
        raise HTTPException(status_code=404, detail="No rendered audio found")
    try:
        file_content = await storage.download_file(ep["final_audio_url"])
        return StreamingResponse(iter([file_content]), media_type="audio/wav", headers={"Content-Disposition": f"inline; filename={episode_id}_final.wav"})
    except Exception as e:
        logger.error(f"Stream error: {e}")
        raise HTTPException(status_code=500, detail="Failed to stream audio")


# ============ SCRIPT COMPILER ============

import script_compiler as sc
from pydantic import BaseModel as _BaseModel

class ScriptDialogue(_BaseModel):
    index: int
    character_id: str
    character_name: str
    voice_id: str
    text: str
    director_notes: Optional[str] = ""
    generated_voice_id: Optional[str] = ""

class ScriptSaveRequest(_BaseModel):
    dialogues: List[ScriptDialogue]

class ScriptGenerateRequest(_BaseModel):
    dialogues: List[ScriptDialogue]

class RegenDialogueRequest(_BaseModel):
    dialogue_index: int
    character_id: str
    character_name: str
    voice_id: str
    text: str
    director_notes: Optional[str] = ""


@creator_router.post("/script/{episode_id}/dialogues")
async def save_script_dialogues(episode_id: str, body: ScriptSaveRequest, authorization: Optional[str] = Header(None)):
    """Save structured dialogue data for an episode."""
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    import json as _json
    script_data = [d.dict() for d in body.dialogues]
    await ndb.update_rows("episodes", {"episode_id": episode_id}, {
        "script_content": _json.dumps(script_data),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": "Script saved", "dialogue_count": len(script_data)}


@creator_router.get("/script/{episode_id}/dialogues")
async def get_script_dialogues(episode_id: str, authorization: Optional[str] = Header(None)):
    """Get structured dialogue data for an episode."""
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    import json as _json
    raw = ep.get("script_content", "")
    if isinstance(raw, str) and raw:
        try:
            dialogues = _json.loads(raw)
            if isinstance(dialogues, list):
                return {"dialogues": dialogues}
        except _json.JSONDecodeError:
            pass
    return {"dialogues": []}


@creator_router.post("/script/{episode_id}/generate")
async def generate_script_audio(episode_id: str, body: ScriptGenerateRequest, authorization: Optional[str] = Header(None)):
    """Trigger batch audio generation for a script.

    Compares current dialogues against previously saved script to detect
    deletions for smart regeneration. Returns a job_id that can be polled.
    """
    profile = await _auth(authorization)
    user_id = profile["user_id"]

    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if ep.get("is_published"):
        raise HTTPException(status_code=423, detail="Episode is published and locked.")

    if not body.dialogues:
        raise HTTPException(status_code=400, detail="No dialogues to generate")

    # Check generation access
    creator_limits = await gq.get_creator_limits(user_id)
    if not creator_limits.get("allowed"):
        raise HTTPException(status_code=403, detail=creator_limits.get("reason", "audio_access_disabled"))
    # Detect deleted dialogues by comparing with previously saved script
    import json as _json
    previous_raw = ep.get("script_content", "")
    previous_dialogues = []
    if isinstance(previous_raw, str) and previous_raw:
        try:
            previous_dialogues = _json.loads(previous_raw)
        except _json.JSONDecodeError:
            pass

    # Find clip names that should be removed (dialogues present before but absent now)
    current_keys = set()
    for d in body.dialogues:
        key = sc.compute_cache_key(d.text, d.voice_id, d.director_notes or "")
        current_keys.add(key)

    removed_clips = []
    for prev in previous_dialogues:
        prev_key = sc.compute_cache_key(
            prev.get("text", ""),
            prev.get("voice_id", ""),
            prev.get("director_notes", "")
        )
        if prev_key not in current_keys:
            char_name = prev.get("character_name", "Unknown").replace(" ", "_")
            idx = prev.get("index", 0)
            removed_clips.append(f"{char_name}_{idx + 1:02d}")

    # Build voice map from dialogues
    voice_map = {}
    dialogues_data = []
    for d in body.dialogues:
        voice_map[d.character_name] = d.voice_id
        dialogues_data.append({
            "index": d.index,
            "dialogue_index": d.index,
            "character_id": d.character_id,
            "character_name": d.character_name,
            "text": d.text,
            "director_notes": d.director_notes or "",
        })

    # Create job
    job_id = f"scrjob_{uuid.uuid4().hex[:12]}"
    await ndb.insert_one("script_generation_jobs", {
        "job_id": job_id,
        "episode_id": episode_id,
        "user_id": user_id,
        "status": "pending",
        "total_dialogues": len(dialogues_data),
        "completed_dialogues": 0,
        "batches_total": 0,
        "batches_completed": 0,
        "result_data": "{}",
        "error_message": "",
    })

    # Start background generation
    story_id = ep.get("story_id", "")
    asyncio.create_task(sc.run_generation_job(job_id, episode_id, user_id, dialogues_data, voice_map, story_id=story_id))

    return {
        "job_id": job_id,
        "status": "pending",
        "total_dialogues": len(dialogues_data),
        "removed_clips": removed_clips,
    }


@creator_router.post("/script/{episode_id}/dialogue/{dialogue_index}/regenerate")
async def regenerate_dialogue_clip(
    episode_id: str,
    dialogue_index: int,
    body: RegenDialogueRequest,
    authorization: Optional[str] = Header(None),
):
    """Queue audio regeneration for a single dialogue. Returns job_id for polling."""
    profile = await _auth(authorization)
    user_id = profile["user_id"]

    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if ep.get("is_published"):
        raise HTTPException(status_code=423, detail="Episode is published and locked.")

    creator_limits = await gq.get_creator_limits(user_id)
    if not creator_limits.get("allowed"):
        raise HTTPException(status_code=403, detail=creator_limits.get("reason", "audio_access_disabled"))
    story_id = ep.get("story_id", "")

    import queue_worker as qw
    job_id = await qw.submit_job(user_id, "regenerate", {
        "episode_id": episode_id,
        "story_id": story_id,
        "dialogue_index": dialogue_index,
        "character_id": body.character_id,
        "character_name": body.character_name,
        "voice_id": body.voice_id,
        "text": body.text,
        "director_notes": body.director_notes or "",
    })

    return {
        "status": "queued",
        "job_id": job_id,
        "dialogue_index": dialogue_index,
    }


@creator_router.get("/script/job/{job_id}/status")
async def get_script_job_status(job_id: str, authorization: Optional[str] = Header(None)):
    """Poll the status of a script generation job."""
    profile = await _auth(authorization)

    job = await ndb.find_one("script_generation_jobs", {"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    import json as _json
    result_data = job.get("result_data", "{}")
    if isinstance(result_data, str):
        try:
            result_data = _json.loads(result_data)
        except _json.JSONDecodeError:
            result_data = {}

    return {
        "job_id": job.get("job_id"),
        "status": job.get("status", "unknown"),
        "total_dialogues": job.get("total_dialogues", 0),
        "completed_dialogues": job.get("completed_dialogues", 0),
        "error_message": job.get("error_message", ""),
        "results": result_data if job.get("status") in ("completed", "completed_with_errors") else {},
    }


@creator_router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, authorization: Optional[str] = Header(None)):
    """Poll the status of a queued generation job (regeneration etc)."""
    profile = await _auth(authorization)

    import queue_worker as qw
    status = await qw.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    return status



# ============ PLATFORM SETTINGS (PUBLIC) ============

@creator_router.get("/settings/dialogue-mode")
async def get_dialogue_mode_public(authorization: Optional[str] = Header(None)):
    """Check if dialogue mode is enabled (public endpoint for creators)."""
    await _auth(authorization)
    setting = await ndb.find_one("voice_settings", {"setting_id": "dialogue_mode"})
    enabled = setting.get("active_provider", "false") == "true" if setting else False
    return {"enabled": enabled}


# ============ SCRIPT DATA (MODE-AWARE) ============

@creator_router.post("/script/{episode_id}/script-data")
async def save_script_data(episode_id: str, body: Dict[str, Any], authorization: Optional[str] = Header(None)):
    """Save script data in either narration or dialogue format."""
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    import json as _json
    await ndb.update_rows("episodes", {"episode_id": episode_id}, {
        "script_content": _json.dumps(body),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"message": "Script data saved", "mode": body.get("mode", "dialogue")}


@creator_router.get("/script/{episode_id}/script-data")
async def get_script_data(episode_id: str, authorization: Optional[str] = Header(None)):
    """Get script data with mode detection."""
    profile = await _auth(authorization)
    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    import json as _json
    raw = ep.get("script_content", "")
    if isinstance(raw, str) and raw.strip():
        try:
            data = _json.loads(raw)
            # New format: has explicit mode key
            if isinstance(data, dict) and "mode" in data:
                return data
            # Legacy format: plain array of dialogues
            if isinstance(data, list) and len(data) > 0:
                return {"mode": "dialogue", "dialogues": data, "parts": [], "voice_id": ""}
            # Empty dict or unknown
            if isinstance(data, dict):
                return {"mode": "narration", "parts": [{"part_number": 1, "text": "", "director_notes": ""}], "dialogues": [], "voice_id": ""}
        except _json.JSONDecodeError:
            pass
    # Default: empty narration
    return {"mode": "narration", "parts": [{"part_number": 1, "text": "", "director_notes": ""}], "dialogues": [], "voice_id": ""}


# ============ NARRATION GENERATION ============

class NarrationPart(_BaseModel):
    part_number: int
    text: str
    director_notes: Optional[str] = ""

class NarrationGenerateRequest(_BaseModel):
    voice_id: str
    parts: List[NarrationPart]

NARRATION_CHAR_LIMIT = 15000

@creator_router.post("/script/{episode_id}/narration/generate")
async def generate_narration_audio(episode_id: str, body: NarrationGenerateRequest, authorization: Optional[str] = Header(None)):
    """Generate audio for narration mode parts. Each part = 1 Gemini TTS call."""
    profile = await _auth(authorization)
    user_id = profile["user_id"]

    ep = await ndb.find_one("episodes", {"episode_id": episode_id})
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if ep.get("is_published"):
        raise HTTPException(status_code=423, detail="Episode is published and locked.")

    if not body.parts:
        raise HTTPException(status_code=400, detail="No parts to generate")
    if not body.voice_id:
        raise HTTPException(status_code=400, detail="voice_id is required")

    # Validate character limits per part
    for part in body.parts:
        total_chars = len(part.text) + len(part.director_notes or "")
        if total_chars > NARRATION_CHAR_LIMIT:
            raise HTTPException(status_code=422, detail="content_too_long")
        if not part.text.strip():
            raise HTTPException(status_code=400, detail=f"Part {part.part_number} has no text")

    # Check generation access
    creator_limits = await gq.get_creator_limits(user_id)
    if not creator_limits.get("allowed"):
        raise HTTPException(status_code=403, detail=creator_limits.get("reason", "audio_access_disabled"))

    # Convert narration parts to dialogue format for the existing pipeline
    voice_map = {"Narrator": body.voice_id}
    dialogues_data = []
    for part in body.parts:
        dialogues_data.append({
            "index": part.part_number - 1,
            "dialogue_index": part.part_number - 1,
            "character_id": "",
            "character_name": "Narrator",
            "text": part.text,
            "director_notes": part.director_notes or "",
        })

    # Create job
    job_id = f"narjob_{uuid.uuid4().hex[:12]}"
    await ndb.insert_one("script_generation_jobs", {
        "job_id": job_id,
        "episode_id": episode_id,
        "user_id": user_id,
        "status": "pending",
        "total_dialogues": len(dialogues_data),
        "completed_dialogues": 0,
        "batches_total": 0,
        "batches_completed": 0,
        "result_data": "{}",
        "error_message": "",
    })

    # Start background generation
    story_id = ep.get("story_id", "")
    asyncio.create_task(sc.run_generation_job(job_id, episode_id, user_id, dialogues_data, voice_map, story_id=story_id))

    return {
        "job_id": job_id,
        "status": "pending",
        "total_parts": len(body.parts),
        "total_dialogues": len(dialogues_data),
    }
