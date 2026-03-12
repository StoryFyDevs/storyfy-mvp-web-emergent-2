from fastapi import APIRouter, HTTPException, Header, Response
from typing import Optional
from datetime import datetime, timezone
import logging

import supabase_db as ndb
import nhost_auth
from models import UserSignup, UserLogin, User, UserPublic, AdminLogin

logger = logging.getLogger("auth")
ADMIN_EMAIL = "admin@admin.com"

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


def _profile_to_user(profile: dict) -> dict:
    """Convert DB profile to User-compatible dict."""
    return {
        "user_id": profile.get("user_id", ""),
        "email": profile.get("email", ""),
        "name": profile.get("name", ""),
        "picture": profile.get("avatar_url"),
        "role": profile.get("role", "creator"),
        "status": "active" if profile.get("is_active", True) else "suspended",
        "limits_remaining": profile.get("generation_credits", 1000),
        "audition_credits": profile.get("audition_credits", 500),
        "storage_used_mb": 0.0,
        "storage_limit_mb": 500.0,
        "created_at": profile.get("created_at", datetime.now(timezone.utc).isoformat()),
    }


@auth_router.post("/signup")
async def signup(user_data: UserSignup):
    role = "admin" if user_data.email == ADMIN_EMAIL else "creator"
    try:
        result = await nhost_auth.register_nhost_user(
            email=user_data.email,
            password=user_data.password,
            display_name=user_data.name,
            role=role,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    session = result.get("session", {})
    access_token = session.get("accessToken", "")
    nhost_user = session.get("user", result.get("user", {}))
    
    # If no session/user returned, email verification is required
    if not nhost_user or not nhost_user.get("id"):
        return {
            "message": "Account created! Please check your email to verify your account.",
            "requires_verification": True,
            "user": None,
            "token": "",
        }

    profile = await nhost_auth.get_or_create_profile(
        auth_id=nhost_user.get("id", ""),
        email=user_data.email,
        display_name=user_data.name,
        metadata={"role": role},
    )

    return {
        "user": UserPublic(**_profile_to_user(profile)),
        "token": access_token,
    }


@auth_router.post("/login")
async def login(credentials: UserLogin):
    try:
        result = await nhost_auth.login_nhost_user(
            email=credentials.email,
            password=credentials.password,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session = result.get("session", {})
    access_token = session.get("accessToken", "")
    nhost_user = session.get("user", {})

    profile = await nhost_auth.get_or_create_profile(
        auth_id=nhost_user.get("id", ""),
        email=credentials.email,
        display_name=nhost_user.get("displayName", ""),
    )

    if not profile.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is suspended")

    return {
        "user": UserPublic(**_profile_to_user(profile)),
        "token": access_token,
    }


@auth_router.get("/me")
async def get_me(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    try:
        profile = await nhost_auth.resolve_user_from_token(token)
        return User(**_profile_to_user(profile))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get me error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


@auth_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token", path="/", samesite="none")
    return {"message": "Logged out"}


@auth_router.post("/oauth-sync")
async def oauth_sync(authorization: Optional[str] = Header(None)):
    """Sync OAuth user profile with backend database."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        profile = await nhost_auth.resolve_user_from_token(token)
        return {"user": UserPublic(**_profile_to_user(profile)), "message": "Profile synced"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth sync error: {e}")
        raise HTTPException(status_code=400, detail="Failed to sync profile")


@auth_router.post("/session")
async def process_session():
    """Legacy Emergent OAuth session - no longer supported."""
    raise HTTPException(status_code=410, detail="Use email/password or Google OAuth via Nhost")
