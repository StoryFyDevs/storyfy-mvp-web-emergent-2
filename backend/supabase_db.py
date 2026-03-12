"""
Supabase Database Module - PostgREST client for all DB operations.
Drop-in replacement for nhost_db.py using the Supabase REST API.

FALLBACK: If a table is not found in Supabase (schema not yet applied),
operations automatically fall back to the legacy nhost_db module.
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
# Track which tables have been confirmed missing from Supabase schema
_missing_tables: set = set()


def _get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client


def _is_table_missing_error(e) -> bool:
    """Return True if the error means the table doesn't exist in Supabase yet."""
    msg = str(e)
    if "PGRST205" in msg or "schema cache" in msg or "Could not find the table" in msg:
        return True
    # APIError dict format: {'code': 404, 'message': 'JSON could not be generated'}
    if isinstance(e, dict) and e.get("code") == 404:
        return True
    if hasattr(e, "code") and e.code == 404:
        return True
    if "'code': 404" in msg or '"code": 404' in msg:
        return True
    return False


async def _nhost_fallback(fn_name: str, *args, **kwargs):
    """Call the equivalent function on nhost_db as a fallback."""
    try:
        import nhost_db as _ndb
        fn = getattr(_ndb, fn_name)
        return await fn(*args, **kwargs)
    except Exception as fe:
        logger.error(f"nhost_db fallback for {fn_name} also failed: {fe}")
        raise


# ============ FIELD REGISTRY ============

TABLE_FIELDS = {
    "user_profiles": "id,auth_id,user_id,email,name,role,generation_credits,audition_credits,limits_remaining,is_active,avatar_url,password_hash,generation_status,daily_generation_limit,per_minute_limit,last_generation_at,created_at,updated_at",
    "stories": "id,story_id,created_by,title,genre,sub_genre,language,status,description,cover_image_url,cover_art_url,tags,published_at,play_count,story_type,created_at,updated_at",
    "episodes": "id,episode_id,story_id,created_by,title,status,script_content,script,final_audio_url,audio_url,project_state,duration_seconds,duration,order_index,is_published,published_at,play_count,storage_files,created_at,updated_at",
    "characters": "id,character_id,story_id,created_by,name,voice_id,display_name,tone,category,voice_settings,created_at,updated_at",
    "voice_settings": "id,setting_id,active_provider,updated_at",
    "voice_samples": "id,voice_id,display_name,storage_path,storage_file_id,audio_url,duration_seconds,status,text_content,error,created_at,updated_at",
    "audition_cache": "id,voice_id,text_hash,audio_url,duration_seconds,created_at",
    "usage_logs": "id,user_id,action,resource_type,resource_id,details,credits_used,credit_type,created_at",
    "audio_assets": "id,asset_id,story_id,episode_id,created_by,name,asset_type,file_path,storage_file_id,duration_seconds,file_size,mime_type,created_at",
    "generation_logs": "id,user_id,gen_type,character_name,voice_id,text_length,duration_seconds,status,provider,error,details,created_at",
    "limit_transactions": "id,user_id,admin_id,credit_type,previous_value,new_value,change_amount,reason,created_at",
    "usage_alerts": "id,alert_id,user_id,alert_type,message,resolved,resolved_at,created_at",
    "system_settings": "id,setting_key,setting_value,updated_by,updated_at",
    "generation_usage": "id,user_id,generation_date,generation_count,token_count,failed_count,last_generation_at,created_at,updated_at",
    "generation_queue": "id,queue_id,user_id,request_type,request_data,status,result_data,error_message,started_at,completed_at,created_at,updated_at",
    "audio_cache": "id,cache_key,voice_id,dialogue_text,director_notes,audio_url,duration_seconds,created_at",
    "audio_clips": "id,file_id,audio_url,episode_id,story_id,dialogue_index,voice_id,cache_key,is_cached,is_active,pending_deletion,pending_deletion_at,last_used_at,created_at",
    "script_generation_jobs": "id,job_id,episode_id,user_id,status,total_dialogues,completed_dialogues,batches_total,batches_completed,result_data,error_message,created_at,updated_at",
    "generation_metrics": "id,generation_id,episode_id,user_id,dialogue_count,speaker_pair_count,batch_count,gemini_calls_used,gemini_calls_saved,cache_hits,cache_misses,deepgram_audio_minutes,segmentation_success_rate,fallback_triggered,generation_time_seconds,estimated_cost,empty_gemini_responses,gemini_retries,created_at",
    "generation_debug_logs": "id,log_id,generation_id,episode_id,user_id,event_type,message,metadata,created_at",
}


def _select_fields(table: str, fields: list = None) -> str:
    if fields:
        return ",".join(fields)
    return TABLE_FIELDS.get(table, "*")


def _build_filter(query, where: dict):
    """Apply where-clause filters to a PostgREST query builder."""
    for col, val in where.items():
        if isinstance(val, dict):
            for op, v in val.items():
                if op == "_eq":
                    query = query.eq(col, v)
                elif op == "_neq":
                    query = query.neq(col, v)
                elif op == "_lt":
                    query = query.lt(col, v)
                elif op == "_lte":
                    query = query.lte(col, v)
                elif op == "_gt":
                    query = query.gt(col, v)
                elif op == "_gte":
                    query = query.gte(col, v)
                elif op == "_in":
                    query = query.in_(col, v)
                elif op == "_is":
                    query = query.is_(col, v)
                elif op == "_like":
                    query = query.like(col, v)
                else:
                    query = query.eq(col, v)
        else:
            query = query.eq(col, val)
    return query


# ============ GENERIC CRUD HELPERS ============

async def find_one(table: str, where: dict = None, fields: list = None, order_by: dict = None):
    """Find a single row. Returns dict or None. Falls back to nhost_db if table missing."""
    if table in _missing_tables:
        return await _nhost_fallback("find_one", table, where, fields, order_by)
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
        if _is_table_missing_error(e):
            logger.warning(f"Table '{table}' not in Supabase schema yet — falling back to nhost_db")
            _missing_tables.add(table)
            return await _nhost_fallback("find_one", table, where, fields, order_by)
        logger.error(f"find_one({table}) error: {e}")
        raise


async def find_many(table: str, where: dict = None, fields: list = None,
                    order_by: dict = None, limit: int = 500):
    """Find multiple rows. Falls back to nhost_db if table missing."""
    if table in _missing_tables:
        return await _nhost_fallback("find_many", table, where, fields, order_by, limit)
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
        if _is_table_missing_error(e):
            logger.warning(f"Table '{table}' not in Supabase schema yet — falling back to nhost_db")
            _missing_tables.add(table)
            return await _nhost_fallback("find_many", table, where, fields, order_by, limit)
        logger.error(f"find_many({table}) error: {e}")
        raise


async def insert_one(table: str, obj: dict):
    """Insert a single row. Falls back to nhost_db if table missing."""
    if table in _missing_tables:
        return await _nhost_fallback("insert_one", table, obj)
    try:
        sc = _get_client()
        clean = {k: v for k, v in obj.items() if v is not None or _allow_null(k)}
        r = sc.table(table).insert(clean).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _is_table_missing_error(e):
            logger.warning(f"Table '{table}' not in Supabase schema yet — falling back to nhost_db")
            _missing_tables.add(table)
            return await _nhost_fallback("insert_one", table, obj)
        logger.error(f"insert_one({table}) error: {e}")
        raise


async def update_rows(table: str, where: dict, set_data: dict):
    """Update rows matching where clause. Falls back to nhost_db if table missing."""
    if table in _missing_tables:
        return await _nhost_fallback("update_rows", table, where, set_data)
    try:
        sc = _get_client()
        q = sc.table(table).update(set_data)
        if where:
            q = _build_filter(q, where)
        r = q.execute()
        return {"affected_rows": len(r.data or []), "returning": r.data or []}
    except Exception as e:
        if _is_table_missing_error(e):
            logger.warning(f"Table '{table}' not in Supabase schema yet — falling back to nhost_db")
            _missing_tables.add(table)
            return await _nhost_fallback("update_rows", table, where, set_data)
        logger.error(f"update_rows({table}) error: {e}")
        raise


async def delete_rows(table: str, where: dict):
    """Delete rows matching where clause. Falls back to nhost_db if table missing."""
    if table in _missing_tables:
        return await _nhost_fallback("delete_rows", table, where)
    try:
        sc = _get_client()
        q = sc.table(table).delete()
        if where:
            q = _build_filter(q, where)
        r = q.execute()
        return len(r.data or [])
    except Exception as e:
        if _is_table_missing_error(e):
            logger.warning(f"Table '{table}' not in Supabase schema yet — falling back to nhost_db")
            _missing_tables.add(table)
            return await _nhost_fallback("delete_rows", table, where)
        logger.error(f"delete_rows({table}) error: {e}")
        raise


async def count_rows(table: str, where: dict = None):
    """Count rows matching where clause. Falls back to nhost_db if table missing."""
    if table in _missing_tables:
        try:
            return await _nhost_fallback("count_rows", table, where)
        except Exception:
            return 0
    try:
        sc = _get_client()
        q = sc.table(table).select("id", count="exact", head=True)
        if where:
            q = _build_filter(q, where)
        r = q.execute()
        return r.count or 0
    except Exception as e:
        if _is_table_missing_error(e):
            logger.warning(f"Table '{table}' not in Supabase schema yet — falling back to nhost_db")
            _missing_tables.add(table)
            try:
                return await _nhost_fallback("count_rows", table, where)
            except Exception:
                return 0
        logger.error(f"count_rows({table}) error: {e}")
        return 0


async def upsert_one(table: str, obj: dict, conflict_columns: list, update_columns: list):
    """Insert or update on conflict. Falls back to nhost_db if table missing."""
    if table in _missing_tables:
        return await _nhost_fallback("upsert_one", table, obj, conflict_columns, update_columns)
    try:
        sc = _get_client()
        r = sc.table(table).upsert(obj, on_conflict=",".join(conflict_columns)).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        if _is_table_missing_error(e):
            logger.warning(f"Table '{table}' not in Supabase schema yet — falling back to nhost_db")
            _missing_tables.add(table)
            return await _nhost_fallback("upsert_one", table, obj, conflict_columns, update_columns)
        logger.error(f"upsert_one({table}) error: {e}")
        raise


async def increment_field(table: str, where: dict, field: str, amount: int):
    """Increment a numeric field by reading + updating."""
    if table in _missing_tables:
        return await _nhost_fallback("increment_field", table, where, field, amount)
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
    """
    Execute raw SQL. In Supabase mode this is a no-op (DDL is run via SQL Editor).
    For analytics queries that need SQL, use find_many instead.
    """
    logger.debug(f"execute_sql (no-op in Supabase mode): {sql[:80]}")
    return {"result": [[]]}


async def graphql(query: str, variables: dict = None):
    """Stub: Not used in Supabase mode."""
    raise NotImplementedError("graphql() not available in Supabase mode — use find_one/find_many")


async def run_sql(sql: str):
    """Stub: Same as execute_sql."""
    return await execute_sql(sql)


def _allow_null(field: str) -> bool:
    NULL_OK = {"pending_deletion_at", "last_generation_at", "published_at", "resolved_at",
               "started_at", "completed_at", "voice_settings", "project_state", "storage_files",
               "details", "metadata"}
    return field in NULL_OK
