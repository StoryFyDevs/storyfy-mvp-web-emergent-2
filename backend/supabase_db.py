"""
Supabase Database Module - PostgREST client for all DB operations.
"""
import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(Path(__file__).parent / '.env')

logger = logging.getLogger("supabase_db")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_client: Client = None


def _get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client


# ============ FIELD REGISTRY ============

TABLE_FIELDS = {
    "user_profiles": "id,auth_id,user_id,email,name,role,generation_credits,audition_credits,limits_remaining,is_active,avatar_url,password_hash,generation_status,daily_generation_limit,per_minute_limit,last_generation_at,created_at,updated_at",
    "stories": "id,story_id,created_by,title,genre,sub_genre,language,status,description,cover_image_url,cover_art_url,tags,published_at,play_count,story_type,created_at,updated_at",
    "episodes": "id,episode_id,story_id,created_by,title,status,script_content,script,final_audio_url,audio_url,project_state,duration_seconds,duration,order_index,is_published,published_at,play_count,storage_files,created_at,updated_at",
    "characters": "id,character_id,story_id,created_by,name,voice_id,display_name,tone,category,voice_settings,created_at,updated_at",
    "voice_settings": "id,setting_id,active_provider,updated_at",
    "voice_samples": "id,voice_id,display_name,storage_path,storage_file_id,audio_url,duration_seconds,status,text_content,error,created_at,updated_at",
    "generation_queue": "id,queue_id,episode_id,created_by,status,priority,error,started_at,completed_at,created_at,updated_at",
    "generation_metrics": "id,episode_id,created_by,provider,voice_id,character_name,status,duration_seconds,api_calls,total_cost_usd,error,started_at,completed_at,created_at",
    "usage_logs": "id,log_id,user_id,action_type,resource_id,resource_type,credits_used,details,metadata,created_at",
    "audio_assets": "id,asset_id,episode_id,story_id,created_by,asset_type,file_path,storage_file_id,duration_seconds,file_size,status,created_at,updated_at",
    "tts_cache": "id,cache_id,text_hash,voice_id,provider,storage_file_id,duration_seconds,hit_count,created_at,updated_at",
    "pending_deletions": "id,deletion_id,resource_type,resource_id,storage_file_ids,scheduled_for,status,resolved_at,created_at",
}


def _select_fields(table: str, fields: list = None) -> str:
    if fields:
        return ",".join(fields)
    return TABLE_FIELDS.get(table, "*")


def _build_filter(query, where: dict):
    for col, val in where.items():
        if isinstance(val, dict):
            op = list(val.keys())[0]
            v = val[op]
            if op == "_eq":
                query = query.eq(col, v)
            elif op == "_neq":
                query = query.neq(col, v)
            elif op == "_gt":
                query = query.gt(col, v)
            elif op == "_gte":
                query = query.gte(col, v)
            elif op == "_lt":
                query = query.lt(col, v)
            elif op == "_lte":
                query = query.lte(col, v)
            elif op == "_in":
                query = query.in_(col, v)
            elif op == "_like":
                query = query.like(col, v)
            elif op == "_ilike":
                query = query.ilike(col, v)
            elif op == "_is":
                query = query.is_(col, v)
        else:
            query = query.eq(col, val)
    return query


# ============ GENERIC CRUD HELPERS ============

async def find_one(table: str, where: dict = None, fields: list = None, order_by: dict = None):
    """Find a single row. Returns dict or None."""
    try:
        sc = _get_client()
        sel = _select_fields(table, fields)
        q = sc.table(table).select(sel)
        if where:
            q = _build_filter(q, where)
        if order_by:
            for col, direction in order_by.items():
                q = q.order(col, desc=(direction.lower() == "desc"))
        q = q.limit(1)
        r = q.execute()
        return r.data[0] if r.data else None
    except Exception as e:
        logger.error(f"find_one({table}) error: {e}")
        raise


async def find_many(table: str, where: dict = None, fields: list = None,
                    order_by: dict = None, limit: int = 500):
    """Find multiple rows."""
    try:
        sc = _get_client()
        sel = _select_fields(table, fields)
        q = sc.table(table).select(sel)
        if where:
            q = _build_filter(q, where)
        if order_by:
            for col, direction in order_by.items():
                q = q.order(col, desc=(direction.lower() == "desc"))
        q = q.limit(limit)
        r = q.execute()
        return r.data or []
    except Exception as e:
        logger.error(f"find_many({table}) error: {e}")
        raise


async def insert_one(table: str, obj: dict):
    """Insert a single row."""
    try:
        sc = _get_client()
        clean = {k: v for k, v in obj.items() if v is not None or _allow_null(k)}
        r = sc.table(table).insert(clean).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        logger.error(f"insert_one({table}) error: {e}")
        raise


async def update_rows(table: str, where: dict, set_data: dict):
    """Update rows matching where clause."""
    try:
        sc = _get_client()
        q = sc.table(table).update(set_data)
        if where:
            q = _build_filter(q, where)
        r = q.execute()
        return {"affected_rows": len(r.data or []), "returning": r.data or []}
    except Exception as e:
        logger.error(f"update_rows({table}) error: {e}")
        raise


async def delete_rows(table: str, where: dict):
    """Delete rows matching where clause."""
    try:
        sc = _get_client()
        q = sc.table(table).delete()
        if where:
            q = _build_filter(q, where)
        r = q.execute()
        return len(r.data or [])
    except Exception as e:
        logger.error(f"delete_rows({table}) error: {e}")
        raise


async def count_rows(table: str, where: dict = None):
    """Count rows matching where clause."""
    try:
        sc = _get_client()
        q = sc.table(table).select("id", count="exact", head=True)
        if where:
            q = _build_filter(q, where)
        r = q.execute()
        return r.count or 0
    except Exception as e:
        logger.error(f"count_rows({table}) error: {e}")
        return 0


async def upsert_one(table: str, obj: dict, conflict_columns: list, update_columns: list):
    """Insert or update on conflict."""
    try:
        sc = _get_client()
        r = sc.table(table).upsert(obj, on_conflict=",".join(conflict_columns)).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        logger.error(f"upsert_one({table}) error: {e}")
        raise


async def increment_field(table: str, where: dict, field: str, amount: int):
    """Increment a numeric field by reading + updating."""
    try:
        row = await find_one(table, where, fields=[field, "id"])
        if not row:
            return {}
        new_val = (row.get(field) or 0) + amount
        return await update_rows(table, {"id": {"_eq": row["id"]}}, {field: new_val})
    except Exception as e:
        logger.error(f"increment_field({table}.{field}) error: {e}")
        raise


async def execute_sql(sql: str):
    """Execute raw SQL. DDL is run via Supabase SQL Editor — this is a no-op."""
    logger.debug(f"execute_sql (no-op in Supabase mode): {sql[:80]}")
    return {"result": [[]]}


async def graphql(query: str, variables: dict = None):
    """Not available in Supabase mode."""
    raise NotImplementedError("graphql() not available — use find_one/find_many")


async def run_sql(sql: str):
    """Stub: same as execute_sql."""
    return await execute_sql(sql)


def _allow_null(field: str) -> bool:
    NULL_OK = {"pending_deletion_at", "last_generation_at", "published_at", "resolved_at",
               "started_at", "completed_at", "voice_settings", "project_state", "storage_files",
               "details", "metadata"}
    return field in NULL_OK
