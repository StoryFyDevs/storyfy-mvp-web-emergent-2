"""
Supabase Auth Module
Handles user authentication via Supabase Auth API.
"""
import os
import uuid
import logging
from pathlib import Path
from dotenv import load_dotenv
from fastapi import HTTPException
from supabase import create_client, Client

load_dotenv(Path(__file__).parent / '.env')

logger = logging.getLogger("supabase_auth")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

_auth_client: Client = None


def _get_client() -> Client:
    global _auth_client
    if _auth_client is None:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        _auth_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _auth_client


async def register_supabase_user(email: str, password: str, display_name: str = "", role: str = "creator"):
    """Register a new user via Supabase Auth."""
    client = _get_client()
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "display_name": display_name or email.split("@")[0],
                    "role": role,
                }
            }
        })
        return response
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "already registered" in msg.lower() or "already been registered" in msg.lower():
            raise HTTPException(status_code=400, detail="Email already registered")
        if "429" in msg or "rate" in msg.lower():
            raise HTTPException(status_code=429, detail="Too many signup attempts. Please wait a minute and try again.")
        logger.error(f"Supabase signup error: {e}")
        raise HTTPException(status_code=400, detail=msg)


async def login_supabase_user(email: str, password: str):
    """Login via Supabase Auth."""
    client = _get_client()
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        if not response.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return response
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate" in msg.lower():
            raise HTTPException(status_code=429, detail="Too many login attempts. Please wait a moment and try again.")
        logger.error(f"Supabase login error: {e}")
        raise HTTPException(status_code=401, detail="Invalid email or password")


async def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase JWT and return user data."""
    client = _get_client()
    try:
        response = client.auth.get_user(token)
        if not response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = response.user
        return {
            "id": user.id,
            "email": user.email or "",
            "display_name": (user.user_metadata or {}).get("display_name", ""),
            "role": (user.user_metadata or {}).get("role", "creator"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_or_create_profile(auth_id: str, email: str = "", display_name: str = "", metadata: dict = None):
    """Get user profile by auth_id, create if not exists."""
    import supabase_db as db

    profile = await db.find_one("user_profiles", {"auth_id": auth_id})
    if profile:
        return profile

    role = "creator"
    if metadata and metadata.get("role"):
        role = metadata["role"]

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    new_profile = {
        "auth_id": auth_id,
        "user_id": user_id,
        "email": email or "",
        "name": display_name or (email.split("@")[0] if email else ""),
        "role": role,
        "generation_credits": 1000,
        "audition_credits": 500,
        "limits_remaining": 1000,
        "is_active": True,
    }
    profile = await db.insert_one("user_profiles", new_profile)
    logger.info(f"Created profile for {email}: {user_id} (role={role})")
    return profile


async def resolve_user_from_token(token: str) -> dict:
    """Full flow: verify token -> get/create profile -> return profile."""
    user_data = await verify_supabase_token(token)
    auth_id = user_data["id"]

    profile = await get_or_create_profile(
        auth_id=auth_id,
        email=user_data.get("email", ""),
        display_name=user_data.get("display_name", ""),
        metadata={"role": user_data.get("role", "creator")},
    )

    if not profile.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account disabled")

    return profile


async def require_admin_from_token(token: str) -> dict:
    """Verify token and ensure user is admin."""
    profile = await resolve_user_from_token(token)
    if profile.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return profile
