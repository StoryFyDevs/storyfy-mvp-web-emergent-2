"""
Generation Queue Manager - Handles rate limiting, quota management, and queue-based processing
for voice generation requests.
"""
import asyncio
import os
import uuid
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional, Dict, Any, Callable
from collections import deque
import json

import supabase_db as ndb

logger = logging.getLogger("generation_queue")

# Default system limits (can be overridden by admin)
DEFAULT_LIMITS = {
    "rpd": 50,       # Requests Per Day (global)
    "rpm": 5,        # Requests Per Minute (global)
    "tpm": 10000,    # Tokens Per Minute (global)
    "auto_distribute": True,  # Auto-distribute limits among active creators
    "default_creator_rpd": 10,  # Default per-creator daily limit
    "default_creator_rpm": 2,   # Default per-creator per-minute limit
}

# In-memory rate tracking
_minute_requests = deque()  # Track timestamps of requests in current minute
_minute_tokens = 0
_last_minute_reset = datetime.now(timezone.utc)

# Queue processing
_queue_lock = asyncio.Lock()
_processing = False


async def get_system_limits() -> Dict[str, Any]:
    """Get current system limits from database or defaults."""
    try:
        setting = await ndb.find_one("system_settings", {"setting_key": "generation_limits"})
        if setting:
            setting_value = setting.get("setting_value", {})
            # Parse JSON string if needed
            if isinstance(setting_value, str):
                try:
                    setting_value = json.loads(setting_value)
                except json.JSONDecodeError:
                    setting_value = {}
            return {**DEFAULT_LIMITS, **setting_value}
    except Exception as e:
        logger.error(f"Error getting system limits: {e}")
    return DEFAULT_LIMITS


async def update_system_limits(limits: Dict[str, Any], admin_id: str = None) -> Dict[str, Any]:
    """Update system limits in database."""
    try:
        existing = await ndb.find_one("system_settings", {"setting_key": "generation_limits"})
        now = datetime.now(timezone.utc).isoformat()
        
        # Merge with existing limits to preserve unspecified values
        current_limits = {}
        if existing:
            setting_value = existing.get("setting_value", {})
            if isinstance(setting_value, str):
                try:
                    current_limits = json.loads(setting_value)
                except json.JSONDecodeError:
                    current_limits = {}
            else:
                current_limits = setting_value or {}
        
        # Merge new limits with current limits
        merged_limits = {**DEFAULT_LIMITS, **current_limits, **limits}
        
        if existing:
            await ndb.update_rows(
                "system_settings",
                {"setting_key": "generation_limits"},
                {"setting_value": json.dumps(merged_limits), "updated_at": now, "updated_by": admin_id}
            )
        else:
            await ndb.insert_one("system_settings", {
                "setting_key": "generation_limits",
                "setting_value": json.dumps(merged_limits),
                "updated_by": admin_id
            })
        
        return merged_limits
    except Exception as e:
        logger.error(f"Error updating system limits: {e}")
        raise


async def get_active_creator_count() -> int:
    """Get count of creators with generation_status = 'active'."""
    try:
        count = await ndb.count_rows("user_profiles", {
            "generation_status": "active",
            "role": {"_neq": "admin"}
        })
        return max(count, 1)  # At least 1 to avoid division by zero
    except Exception as e:
        logger.error(f"Error counting active creators: {e}")
        return 1


async def get_creator_limits(user_id: str) -> Dict[str, Any]:
    """Get generation limits for a specific creator."""
    try:
        user = await ndb.find_one("user_profiles", {"user_id": user_id})
        if not user:
            return {"allowed": False, "reason": "User not found"}
        
        # Check generation status
        status = user.get("generation_status", "inactive")
        if status != "active":
            return {
                "allowed": False,
                "reason": "audio_access_disabled",
                "status": status
            }
        
        limits = await get_system_limits()
        
        # Calculate per-creator limits
        daily_limit = user.get("daily_generation_limit")
        per_minute_limit = user.get("per_minute_limit")
        
        # If auto-distribute is enabled and no manual override
        if limits.get("auto_distribute", True):
            active_count = await get_active_creator_count()
            auto_daily = limits.get("rpd", 50) // active_count
            
            if daily_limit is None:
                daily_limit = auto_daily
            if per_minute_limit is None:
                per_minute_limit = max(1, limits.get("rpm", 5) // active_count)
        else:
            if daily_limit is None:
                daily_limit = limits.get("default_creator_rpd", 10)
            if per_minute_limit is None:
                per_minute_limit = limits.get("default_creator_rpm", 2)
        
        return {
            "allowed": True,
            "daily_limit": daily_limit,
            "per_minute_limit": per_minute_limit,
            "status": status
        }
    except Exception as e:
        logger.error(f"Error getting creator limits: {e}")
        return {"allowed": False, "reason": "Unable to verify generation access"}


async def get_creator_usage_today(user_id: str) -> Dict[str, int]:
    """Get today's usage for a creator."""
    today = date.today().isoformat()
    try:
        usage = await ndb.find_one("generation_usage", {
            "user_id": user_id,
            "generation_date": today
        })
        if usage:
            return {
                "generation_count": usage.get("generation_count", 0),
                "token_count": usage.get("token_count", 0),
                "failed_count": usage.get("failed_count", 0)
            }
    except Exception as e:
        logger.error(f"Error getting creator usage: {e}")
    
    return {"generation_count": 0, "token_count": 0, "failed_count": 0}


async def get_global_usage_today() -> Dict[str, int]:
    """Get total system usage for today."""
    today = date.today().isoformat()
    try:
        # Sum all users' usage for today
        usages = await ndb.find_many("generation_usage", {"generation_date": today})
        total_gen = sum(u.get("generation_count", 0) for u in usages)
        total_tokens = sum(u.get("token_count", 0) for u in usages)
        total_failed = sum(u.get("failed_count", 0) for u in usages)
        
        return {
            "total_generations": total_gen,
            "total_tokens": total_tokens,
            "total_failed": total_failed
        }
    except Exception as e:
        logger.error(f"Error getting global usage: {e}")
    
    return {"total_generations": 0, "total_tokens": 0, "total_failed": 0}


async def check_rate_limits(user_id: str, estimated_tokens: int = 500) -> Dict[str, Any]:
    """Check if a generation request can proceed based on all rate limits."""
    global _minute_requests, _minute_tokens, _last_minute_reset
    
    # Get limits
    creator_limits = await get_creator_limits(user_id)
    if not creator_limits.get("allowed"):
        return creator_limits
    
    system_limits = await get_system_limits()
    
    # Reset minute tracking if needed
    now = datetime.now(timezone.utc)
    if (now - _last_minute_reset).total_seconds() >= 60:
        _minute_requests.clear()
        _minute_tokens = 0
        _last_minute_reset = now
    
    # Clean old requests from deque
    one_minute_ago = now - timedelta(minutes=1)
    while _minute_requests and _minute_requests[0] < one_minute_ago:
        _minute_requests.popleft()
    
    # Check global RPM
    if len(_minute_requests) >= system_limits.get("rpm", 5):
        return {
            "allowed": False,
            "reason": "Audio generation is currently busy. Please wait a moment and try again.",
            "retry_after": 60
        }
    
    # Check global TPM
    if _minute_tokens + estimated_tokens > system_limits.get("tpm", 10000):
        return {
            "allowed": False,
            "reason": "Audio generation is currently busy. Please wait a moment and try again.",
            "retry_after": 60
        }
    
    # Check global RPD
    global_usage = await get_global_usage_today()
    if global_usage["total_generations"] >= system_limits.get("rpd", 50):
        return {
            "allowed": False,
            "reason": "System generation capacity reached for today. Please try again tomorrow.",
            "retry_after": 3600
        }
    
    # Check per-creator daily limit
    creator_usage = await get_creator_usage_today(user_id)
    if creator_usage["generation_count"] >= creator_limits["daily_limit"]:
        return {
            "allowed": False,
            "reason": "You've reached today's generation limit. You can generate more audio tomorrow.",
            "retry_after": 3600,
            "daily_limit_reached": True
        }
    
    return {
        "allowed": True,
        "generations_remaining": creator_limits["daily_limit"] - creator_usage["generation_count"],
        "daily_limit": creator_limits["daily_limit"]
    }


async def record_generation(user_id: str, success: bool, tokens_used: int = 0):
    """Record a generation attempt for rate limiting and analytics."""
    global _minute_requests, _minute_tokens
    
    now = datetime.now(timezone.utc)
    today = date.today().isoformat()
    
    # Update in-memory tracking
    _minute_requests.append(now)
    if success:
        _minute_tokens += tokens_used
    
    # Update database usage tracking
    try:
        existing = await ndb.find_one("generation_usage", {
            "user_id": user_id,
            "generation_date": today
        })
        
        if existing:
            update_data = {"last_generation_at": now.isoformat()}
            if success:
                update_data["generation_count"] = existing.get("generation_count", 0) + 1
                update_data["token_count"] = existing.get("token_count", 0) + tokens_used
            else:
                update_data["failed_count"] = existing.get("failed_count", 0) + 1
            
            await ndb.update_rows("generation_usage", {
                "user_id": user_id,
                "generation_date": today
            }, update_data)
        else:
            await ndb.insert_one("generation_usage", {
                "user_id": user_id,
                "generation_date": today,
                "generation_count": 1 if success else 0,
                "token_count": tokens_used if success else 0,
                "failed_count": 0 if success else 1,
                "last_generation_at": now.isoformat()
            })
        
        # Update user's last generation timestamp
        await ndb.update_rows("user_profiles", {"user_id": user_id}, {
            "last_generation_at": now.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error recording generation: {e}")


async def get_queue_status() -> Dict[str, Any]:
    """Get current queue status for admin dashboard."""
    try:
        pending = await ndb.count_rows("generation_queue", {"status": "pending"})
        processing = await ndb.count_rows("generation_queue", {"status": "processing"})
        
        return {
            "pending": pending,
            "processing": processing,
            "total_in_queue": pending + processing
        }
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        return {"pending": 0, "processing": 0, "total_in_queue": 0}


async def add_to_queue(user_id: str, request_type: str, request_data: Dict) -> str:
    """Add a generation request to the queue."""
    queue_id = f"gen_{uuid.uuid4().hex[:12]}"
    
    try:
        await ndb.insert_one("generation_queue", {
            "queue_id": queue_id,
            "user_id": user_id,
            "request_type": request_type,
            "request_data": json.dumps(request_data),
            "status": "pending"
        })
        return queue_id
    except Exception as e:
        logger.error(f"Error adding to queue: {e}")
        raise


async def update_queue_item(queue_id: str, status: str, result_data: Dict = None, error: str = None):
    """Update a queue item's status."""
    now = datetime.now(timezone.utc).isoformat()
    update_data = {"status": status}
    
    if status == "processing":
        update_data["started_at"] = now
    elif status in ("completed", "failed"):
        update_data["completed_at"] = now
    
    if result_data:
        update_data["result_data"] = json.dumps(result_data)
    if error:
        update_data["error_message"] = error
    
    try:
        await ndb.update_rows("generation_queue", {"queue_id": queue_id}, update_data)
    except Exception as e:
        logger.error(f"Error updating queue item: {e}")


async def get_queue_item_status(queue_id: str) -> Optional[Dict]:
    """Get status of a queue item."""
    try:
        item = await ndb.find_one("generation_queue", {"queue_id": queue_id})
        if item:
            result_data = item.get("result_data")
            if result_data and isinstance(result_data, str):
                try:
                    result_data = json.loads(result_data)
                except:
                    pass
            return {
                "queue_id": item.get("queue_id"),
                "status": item.get("status"),
                "result_data": result_data,
                "error_message": item.get("error_message"),
                "created_at": item.get("created_at"),
                "completed_at": item.get("completed_at")
            }
    except Exception as e:
        logger.error(f"Error getting queue item: {e}")
    return None


# ============ ADMIN FUNCTIONS ============

async def get_all_creator_stats() -> list:
    """Get generation stats for all creators (admin view)."""
    today = date.today().isoformat()
    try:
        # Get all non-admin users
        users = await ndb.find_many("user_profiles", {"role": {"_neq": "admin"}}, limit=500)
        
        stats = []
        for user in users:
            user_id = user.get("user_id", "")
            usage = await get_creator_usage_today(user_id)
            limits = await get_creator_limits(user_id)
            
            stats.append({
                "user_id": user_id,
                "email": user.get("email", ""),
                "name": user.get("name", ""),
                "generation_status": user.get("generation_status", "active"),
                "daily_limit": limits.get("daily_limit", 0) if limits.get("allowed") else 0,
                "per_minute_limit": limits.get("per_minute_limit", 0) if limits.get("allowed") else 0,
                "generations_today": usage.get("generation_count", 0),
                "tokens_today": usage.get("token_count", 0),
                "failed_today": usage.get("failed_count", 0),
                "generations_remaining": max(0, limits.get("daily_limit", 0) - usage.get("generation_count", 0)) if limits.get("allowed") else 0,
                "last_generation_at": user.get("last_generation_at"),
                "generation_credits": user.get("generation_credits", 0),
                "audition_credits": user.get("audition_credits", 0)
            })
        
        return stats
    except Exception as e:
        logger.error(f"Error getting creator stats: {e}")
        return []


async def update_creator_generation_status(user_id: str, status: str, admin_id: str = None):
    """Enable or disable generation access for a creator."""
    if status not in ("active", "inactive"):
        raise ValueError("Status must be 'active' or 'inactive'")
    
    try:
        await ndb.update_rows("user_profiles", {"user_id": user_id}, {
            "generation_status": status
        })
        
        # Log admin action
        await ndb.insert_one("admin_logs", {
            "admin_id": admin_id,
            "action": f"set_generation_status_{status}",
            "target_type": "user",
            "target_id": user_id,
            "details": json.dumps({"new_status": status})
        })
    except Exception as e:
        logger.error(f"Error updating creator status: {e}")
        raise


async def update_creator_limits(user_id: str, daily_limit: int = None, per_minute_limit: int = None, admin_id: str = None):
    """Set individual limits for a creator."""
    update_data = {}
    if daily_limit is not None:
        update_data["daily_generation_limit"] = daily_limit
    if per_minute_limit is not None:
        update_data["per_minute_limit"] = per_minute_limit
    
    if not update_data:
        return
    
    try:
        await ndb.update_rows("user_profiles", {"user_id": user_id}, update_data)
        
        # Log admin action
        await ndb.insert_one("admin_logs", {
            "admin_id": admin_id,
            "action": "update_creator_limits",
            "target_type": "user",
            "target_id": user_id,
            "details": json.dumps(update_data)
        })
    except Exception as e:
        logger.error(f"Error updating creator limits: {e}")
        raise


async def get_generation_analytics() -> Dict[str, Any]:
    """Get comprehensive generation analytics for admin dashboard."""
    today = date.today().isoformat()
    limits = await get_system_limits()
    global_usage = await get_global_usage_today()
    queue_status = await get_queue_status()
    active_count = await get_active_creator_count()
    
    return {
        "system_limits": {
            "rpd": limits.get("rpd", 50),
            "rpm": limits.get("rpm", 5),
            "tpm": limits.get("tpm", 10000),
            "auto_distribute": limits.get("auto_distribute", True)
        },
        "usage_today": {
            "total_generations": global_usage.get("total_generations", 0),
            "total_tokens": global_usage.get("total_tokens", 0),
            "total_failed": global_usage.get("total_failed", 0),
            "generations_remaining": max(0, limits.get("rpd", 50) - global_usage.get("total_generations", 0))
        },
        "queue_status": queue_status,
        "creators": {
            "active_count": active_count,
            "per_creator_daily_limit": limits.get("rpd", 50) // active_count if limits.get("auto_distribute") else limits.get("default_creator_rpd", 10)
        },
        "current_minute": {
            "requests": len(_minute_requests),
            "tokens": _minute_tokens
        }
    }
