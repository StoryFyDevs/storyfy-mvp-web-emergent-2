from fastapi import APIRouter, HTTPException, Header, Response
from typing import Optional
from datetime import datetime, timezone
import logging

import supabase_db as ndb
import auth_service
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
        result = await auth_service.register_supabase_user(
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

    user = result.user
    session = result.session

    if not user or not user.id:
        return {
            "message": "Account created! Please check your email to verify your account.",
            "requires_verification": True,
            "user": None,
            "token": "",
        }

    # Email confirmation required — no session yet
    if not session or not session.access_token:
        return {
            "message": "Account created! Please check your email to confirm your account, then sign in.",
            "requires_verification": True,
            "user": None,
            "token": "",
        }

    access_token = session.access_token

    profile = await auth_service.get_or_create_profile(
        auth_id=user.id,
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
        result = await auth_service.login_supabase_user(
            email=credentials.email,
            password=credentials.password,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = result.user
    session = result.session
    access_token = session.access_token if session else ""

    # Check the authoritative role from Supabase auth metadata BEFORE profile creation.
    # This prevents a listener account from ever being minted as a creator profile here.
    auth_role = (user.user_metadata or {}).get("role", "")
    if auth_role == "listener":
        raise HTTPException(status_code=401, detail="Listener accounts must use the mobile app")

    profile = await auth_service.get_or_create_profile(
        auth_id=user.id,
        email=credentials.email,
        display_name=(user.user_metadata or {}).get("display_name", ""),
    )

    if not profile.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is suspended")

    # Secondary check covers existing profiles whose role may have been set before auth metadata check
    if profile.get("role") == "listener":
        raise HTTPException(status_code=401, detail="Listener accounts must use the mobile app")

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
        profile = await auth_service.resolve_user_from_token(token)
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
        profile = await auth_service.resolve_user_from_token(token)
        return {"user": UserPublic(**_profile_to_user(profile)), "message": "Profile synced"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth sync error: {e}")
        raise HTTPException(status_code=400, detail="Failed to sync profile")


@auth_router.post("/session")
async def process_session():
    """Legacy session endpoint - no longer supported."""
    raise HTTPException(status_code=410, detail="Use email/password or Google OAuth via Supabase")
