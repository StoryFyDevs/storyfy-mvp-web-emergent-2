from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException, Header, Cookie, Depends
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
import os
import logging
import uuid
import jwt
import bcrypt
import requests
import base64

from elevenlabs import ElevenLabs
from supabase import create_client, Client

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ElevenLabs
eleven_client = ElevenLabs(api_key=os.environ['ELEVENLABS_API_KEY'])

# Supabase
supabase_url = os.environ['SUPABASE_URL']
supabase_anon_key = os.environ['SUPABASE_ANON_KEY']
supabase_service_key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
supabase: Client = create_client(supabase_url, supabase_anon_key)
supabase_admin: Client = create_client(supabase_url, supabase_service_key)

AUDIO_BUCKET_NAME = os.environ.get('SUPABASE_AUDIO_BUCKET', 'storyfy-audio')
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')
ADMIN_SECRET_PATH = os.environ.get('ADMIN_SECRET_PATH', 'admin-9821')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============ JWT HELPERS ============

def create_jwt_token(user_id: str, email: str, role: str = "creator") -> str:
    payload = {
        'user_id': user_id,
        'email': email,
        'role': role,
        'exp': datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============ AUTH DEPENDENCIES ============

async def get_current_user(authorization: Optional[str] = Header(None), session_token: Optional[str] = Cookie(None)) -> str:
    token = None
    if session_token:
        token = session_token
    elif authorization:
        if authorization.startswith('Bearer '):
            token = authorization.split(' ')[1]
        else:
            token = authorization

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if session:
        expires_at = session["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
        return session["user_id"]

    try:
        payload = verify_jwt_token(token)
        return payload['user_id']
    except:
        raise HTTPException(status_code=401, detail="Invalid authentication")

async def get_current_user_with_role(authorization: Optional[str] = Header(None), session_token: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    user_id = await get_current_user(authorization, session_token)
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    return user_doc

async def require_admin(authorization: Optional[str] = Header(None), session_token: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    user = await get_current_user_with_role(authorization, session_token)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ============ LOGGING HELPERS ============

async def log_admin_action(admin_id: str, action_type: str, target_type: str, target_id: str, details: Dict[str, Any]):
    action_doc = {
        "action_id": f"action_{uuid.uuid4().hex[:12]}",
        "admin_id": admin_id,
        "action_type": action_type,
        "target_type": target_type,
        "target_id": target_id,
        "details": details,
        "created_at": datetime.now(timezone.utc)
    }
    await db.admin_actions.insert_one(action_doc)
    return action_doc

async def log_limit_transaction(user_id: str, amount: int, balance_after: int, transaction_type: str, description: str, reference_id: str = None, admin_id: str = None):
    transaction_doc = {
        "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "amount": amount,
        "balance_after": balance_after,
        "transaction_type": transaction_type,
        "description": description,
        "reference_id": reference_id,
        "admin_id": admin_id,
        "created_at": datetime.now(timezone.utc)
    }
    await db.limit_transactions.insert_one(transaction_doc)
    return transaction_doc

async def log_generation(user_id: str, generation_type: str, duration_seconds: float, limits_used: int, data_size_bytes: int, status: str, model_used: str, story_id: str = None, episode_id: str = None, error_message: str = None):
    generation_doc = {
        "generation_id": f"gen_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "story_id": story_id,
        "episode_id": episode_id,
        "generation_type": generation_type,
        "duration_seconds": duration_seconds,
        "limits_used": limits_used,
        "data_size_bytes": data_size_bytes,
        "status": status,
        "error_message": error_message,
        "model_used": model_used,
        "created_at": datetime.now(timezone.utc)
    }
    await db.generation_logs.insert_one(generation_doc)
    return generation_doc

# ============ USAGE TRACKING ============

def estimate_audio_duration(audio_data_bytes: bytes, output_format: str = "mp3_44100_128") -> float:
    size = len(audio_data_bytes)
    if size == 0:
        return 0.0
    if output_format.startswith("pcm"):
        sample_rate = int(output_format.split("_")[1])
        return size / (sample_rate * 2)
    elif output_format.startswith("mp3"):
        parts = output_format.split("_")
        bitrate = int(parts[2]) * 1000 if len(parts) >= 3 else 128000
        return (size * 8) / bitrate
    return size / 16000

async def track_generation_usage(user_id: str, gen_type: str, text_length: int, duration_seconds: float, file_size: int, status: str, model_used: str, voice_id: str = None, project_id: str = None, error_message: str = None):
    credits_used = text_length

    log_doc = {
        "log_id": f"gul_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "project_id": project_id,
        "type": gen_type,
        "text_length": text_length,
        "duration_seconds": round(duration_seconds, 2),
        "credits_used": credits_used,
        "file_size": file_size,
        "voice_id": voice_id,
        "status": status,
        "model_used": model_used,
        "error_message": error_message,
        "created_at": datetime.now(timezone.utc)
    }
    await db.generation_usage_logs.insert_one(log_doc)
    log_doc.pop("_id", None)

    if status == "success":
        await db.user_usage_summary.update_one(
            {"user_id": user_id},
            {
                "$inc": {
                    "total_credits_used": credits_used,
                    "total_audio_seconds": round(duration_seconds, 2),
                    "total_generations": 1,
                },
                "$set": {"last_updated": datetime.now(timezone.utc)},
                "$setOnInsert": {"total_storage_used": 0, "total_failed_generations": 0}
            },
            upsert=True
        )
        await db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"limits_remaining": -credits_used}}
        )
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "limits_remaining": 1})
        await log_limit_transaction(
            user_id=user_id, amount=-credits_used,
            balance_after=user.get("limits_remaining", 0),
            transaction_type="generation",
            description=f"{gen_type} generation ({text_length} chars, {round(duration_seconds, 1)}s)",
            reference_id=log_doc["log_id"]
        )
        await check_usage_alerts(user_id, credits_used)
    else:
        await db.user_usage_summary.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_failed_generations": 1},
                "$set": {"last_updated": datetime.now(timezone.utc)},
                "$setOnInsert": {"total_credits_used": 0, "total_audio_seconds": 0, "total_generations": 0, "total_storage_used": 0}
            },
            upsert=True
        )
    return log_doc

async def track_storage_usage(user_id: str, file_size_bytes: int):
    file_size_mb = file_size_bytes / (1024 * 1024)
    await db.user_usage_summary.update_one(
        {"user_id": user_id},
        {
            "$inc": {"total_storage_used": file_size_bytes},
            "$set": {"last_updated": datetime.now(timezone.utc)},
            "$setOnInsert": {"total_credits_used": 0, "total_audio_seconds": 0, "total_generations": 0, "total_failed_generations": 0}
        },
        upsert=True
    )
    await db.users.update_one(
        {"user_id": user_id},
        {"$inc": {"storage_used_mb": file_size_mb}}
    )

async def check_usage_alerts(user_id: str, credits_just_used: int):
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "limits_remaining": 1, "email": 1})
    if not user:
        return
    limits_remaining = user.get("limits_remaining", 0)
    email = user.get("email", user_id)

    if limits_remaining <= 0:
        await db.usage_alerts.insert_one({
            "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
            "alert_type": "limit_exceeded",
            "severity": "critical",
            "user_id": user_id,
            "message": f"User {email} has exhausted their credit limit",
            "details": {"limits_remaining": limits_remaining, "email": email},
            "resolved": False,
            "created_at": datetime.now(timezone.utc)
        })
    elif limits_remaining < 100:
        await db.usage_alerts.insert_one({
            "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
            "alert_type": "low_credits",
            "severity": "warning",
            "user_id": user_id,
            "message": f"User {email} has low credits ({limits_remaining} remaining)",
            "details": {"limits_remaining": limits_remaining, "email": email},
            "resolved": False,
            "created_at": datetime.now(timezone.utc)
        })

    if credits_just_used > 500:
        await db.usage_alerts.insert_one({
            "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
            "alert_type": "usage_spike",
            "severity": "warning",
            "user_id": user_id,
            "message": f"Large generation by {email}: {credits_just_used} credits",
            "details": {"credits_used": credits_just_used, "email": email},
            "resolved": False,
            "created_at": datetime.now(timezone.utc)
        })

async def validate_elevenlabs_usage():
    try:
        pipeline = [{"$match": {"status": "success"}}, {"$group": {"_id": None, "total": {"$sum": "$credits_used"}}}]
        local_result = await db.generation_usage_logs.aggregate(pipeline).to_list(1)
        local_total = local_result[0]["total"] if local_result else 0

        api_key = os.environ.get('ELEVENLABS_API_KEY', '')
        headers = {"xi-api-key": api_key}
        resp = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers=headers, timeout=10)

        el_total = 0
        el_limit = 0
        if resp.status_code == 200:
            sub_data = resp.json()
            el_total = sub_data.get("character_count", 0)
            el_limit = sub_data.get("character_limit", 0)

        discrepancy = abs(local_total - el_total)
        discrepancy_pct = (discrepancy / max(el_total, 1)) * 100

        sync_status = "ok" if discrepancy_pct <= 10 else "mismatch"

        sync_doc = {
            "sync_id": f"sync_{uuid.uuid4().hex[:12]}",
            "local_total_characters": local_total,
            "elevenlabs_total_characters": el_total,
            "elevenlabs_character_limit": el_limit,
            "discrepancy": discrepancy,
            "discrepancy_percent": round(discrepancy_pct, 2),
            "status": sync_status,
            "created_at": datetime.now(timezone.utc)
        }
        await db.elevenlabs_sync_logs.insert_one(sync_doc)

        if sync_status == "mismatch":
            await db.usage_alerts.insert_one({
                "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
                "alert_type": "api_mismatch",
                "severity": "critical",
                "user_id": None,
                "message": f"ElevenLabs usage mismatch: local={local_total} vs API={el_total} ({discrepancy_pct:.1f}% diff)",
                "details": {"local": local_total, "elevenlabs": el_total, "limit": el_limit},
                "resolved": False,
                "created_at": datetime.now(timezone.utc)
            })

        logger.info(f"ElevenLabs validation: local={local_total}, API={el_total}, status={sync_status}")
        sync_doc.pop("_id", None)
        return sync_doc
    except Exception as e:
        logger.error(f"ElevenLabs validation error: {e}")
        error_doc = {
            "sync_id": f"sync_{uuid.uuid4().hex[:12]}",
            "local_total_characters": 0, "elevenlabs_total_characters": 0,
            "elevenlabs_character_limit": 0, "discrepancy": 0,
            "discrepancy_percent": 0, "status": "error",
            "error_message": str(e),
            "created_at": datetime.now(timezone.utc)
        }
        await db.elevenlabs_sync_logs.insert_one(error_doc)
        error_doc.pop("_id", None)
        return error_doc
