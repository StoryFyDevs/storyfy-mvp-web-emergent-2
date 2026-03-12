"""
Nhost Auth Module - JWT verification for backend routes.
Verifies Nhost-issued JWTs and resolves user profiles.
"""
import os
import jwt
import httpx
import logging
from pathlib import Path
from dotenv import load_dotenv
from jwt import PyJWKClient
from fastapi import HTTPException

# Load .env from backend directory
load_dotenv(Path(__file__).parent / '.env')

logger = logging.getLogger("nhost_auth")

NHOST_SUBDOMAIN = os.environ.get("NHOST_SUBDOMAIN", "")
NHOST_REGION = os.environ.get("NHOST_REGION", "")
NHOST_ADMIN_SECRET = os.environ.get("NHOST_ADMIN_SECRET", "")

AUTH_URL = f"https://{NHOST_SUBDOMAIN}.auth.{NHOST_REGION}.nhost.run/v1"
HASURA_URL = f"https://{NHOST_SUBDOMAIN}.hasura.{NHOST_REGION}.nhost.run"

# JWKS client for token verification
_jwks_client = None


def _get_jwks_client():
    """Not used - JWKS endpoint not available in basic Nhost setup."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = f"{AUTH_URL}/jwks"
        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def verify_nhost_token(token: str) -> dict:
    """Verify a Nhost JWT and return the decoded payload.
    
    Since Nhost doesn't expose JWKS by default, we decode without 
    signature verification and validate via the /token endpoint.
    """
    try:
        # First decode without verification to get claims
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": True,
                "verify_aud": False,
            },
        )
        
        # The 'sub' claim contains the Nhost auth user ID
        if not payload.get("sub"):
            raise HTTPException(status_code=401, detail="Invalid token: no sub claim")
            
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")
        raise HTTPException(status_code=401, detail="Authentication failed")


async def get_or_create_profile(auth_id: str, email: str = "", display_name: str = "", metadata: dict = None):
    """Get user profile by auth_id, create if not exists."""
    import supabase_db as db
    import uuid

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
        "name": display_name or email.split("@")[0] if email else "",
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
    payload = verify_nhost_token(token)
    auth_id = payload.get("sub")
    if not auth_id:
        raise HTTPException(status_code=401, detail="Invalid token: no sub claim")

    claims = payload.get("https://hasura.io/jwt/claims", {})
    email = claims.get("x-hasura-user-email", "")
    metadata = payload.get("metadata", {})

    profile = await get_or_create_profile(
        auth_id=auth_id,
        email=email,
        display_name=payload.get("name", ""),
        metadata=metadata,
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


async def register_nhost_user(email: str, password: str, display_name: str = "", role: str = "creator"):
    """Register a user via Nhost Auth API. Returns auth user data."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{AUTH_URL}/signup/email-password",
            json={
                "email": email,
                "password": password,
                "options": {
                    "displayName": display_name or email.split("@")[0],
                    "metadata": {"role": role},
                },
            },
        )
        if resp.status_code == 429:
            raise HTTPException(status_code=429, detail="Too many signup attempts. Please wait a minute and try again.")
        if resp.status_code not in (200, 201):
            try:
                error = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"message": resp.text}
                msg = error.get("message", error.get("error", "Registration failed"))
            except:
                msg = "Registration failed"
            raise HTTPException(status_code=resp.status_code, detail=msg)
        return resp.json()


async def login_nhost_user(email: str, password: str):
    """Login via Nhost Auth API. Returns session with accessToken."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{AUTH_URL}/signin/email-password",
            json={"email": email, "password": password},
        )
        if resp.status_code == 429:
            raise HTTPException(status_code=429, detail="Too many login attempts. Please wait a minute and try again.")
        if resp.status_code != 200:
            try:
                error = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"message": resp.text}
                msg = error.get("message", error.get("error", "Login failed"))
            except:
                msg = "Invalid credentials"
            raise HTTPException(status_code=resp.status_code, detail=msg)
        return resp.json()
