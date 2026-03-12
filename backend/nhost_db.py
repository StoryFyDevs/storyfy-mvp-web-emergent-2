"""
Nhost Database Module - Hasura GraphQL client for all DB operations.
Uses admin secret for backend-to-Hasura communication.
"""
import os
import httpx
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend directory
load_dotenv(Path(__file__).parent / '.env')

logger = logging.getLogger("nhost_db")

NHOST_SUBDOMAIN = os.environ.get("NHOST_SUBDOMAIN", "")
NHOST_REGION = os.environ.get("NHOST_REGION", "")
NHOST_ADMIN_SECRET = os.environ.get("NHOST_ADMIN_SECRET", "")

HASURA_URL = f"https://{NHOST_SUBDOMAIN}.hasura.{NHOST_REGION}.nhost.run"
GRAPHQL_URL = f"{HASURA_URL}/v1/graphql"
SQL_URL = f"{HASURA_URL}/v2/query"

_client = None


def _get_client():
    global _client
    if _client is None:
        admin_secret = os.environ.get("NHOST_ADMIN_SECRET", "")
        _client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "x-hasura-admin-secret": admin_secret,
                "Content-Type": "application/json",
            },
        )
    return _client


async def execute_sql(sql: str):
    """Execute raw SQL via Hasura v2/query endpoint."""
    client = _get_client()
    payload = {
        "type": "run_sql",
        "args": {
            "source": "default",
            "sql": sql
        }
    }
    resp = await client.post(SQL_URL, json=payload)
    data = resp.json()
    if "error" in data:
        logger.error(f"SQL error: {data}")
        raise Exception(data.get("error", str(data)))
    return data


async def graphql(query: str, variables: dict = None):
    """Execute a Hasura GraphQL query/mutation with admin secret."""
    client = _get_client()
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = await client.post(GRAPHQL_URL, json=payload)
    data = resp.json()
    if "errors" in data:
        err = data["errors"][0].get("message", str(data["errors"]))
        logger.error(f"GraphQL error: {err}")
        raise Exception(f"GraphQL error: {err}")
    return data.get("data", {})


async def run_sql(sql: str):
    """Execute raw SQL via Hasura."""
    client = _get_client()
    resp = await client.post(SQL_URL, json={
        "type": "run_sql",
        "args": {"source": "default", "sql": sql}
    })
    return resp.json()


# ============ GENERIC HELPERS ============

async def find_one(table: str, where: dict = None, fields: list = None, order_by: dict = None):
    """Find a single row. Returns dict or None."""
    parts = []
    if where:
        parts.append(f"where: {_build_where(where)}")
    if order_by:
        parts.append(f"order_by: {_build_order(order_by)}")
    parts.append("limit: 1")
    args = ", ".join(parts)
    field_str = _field_list(table, fields)
    q = f"query {{ {table}({args}) {{ {field_str} }} }}"
    data = await graphql(q)
    rows = data.get(table, [])
    return rows[0] if rows else None


async def find_many(table: str, where: dict = None, fields: list = None,
                    order_by: dict = None, limit: int = 500):
    """Find multiple rows."""
    parts = []
    if where:
        parts.append(f"where: {_build_where(where)}")
    if order_by:
        parts.append(f"order_by: {_build_order(order_by)}")
    if limit:
        parts.append(f"limit: {limit}")
    args = ", ".join(parts)
    field_str = _field_list(table, fields)
    if args:
        q = f"query {{ {table}({args}) {{ {field_str} }} }}"
    else:
        q = f"query {{ {table} {{ {field_str} }} }}"
    data = await graphql(q)
    return data.get(table, [])


async def insert_one(table: str, obj: dict):
    """Insert a single row. Returns the inserted row."""
    obj_str = _build_object(obj)
    field_str = _field_list(table)
    q = f"mutation {{ insert_{table}_one(object: {obj_str}) {{ {field_str} }} }}"
    data = await graphql(q)
    return data.get(f"insert_{table}_one")


async def update_rows(table: str, where: dict, set_data: dict):
    """Update rows matching where clause. Returns affected rows."""
    where_clause = _build_where(where)
    set_clause = _build_set(set_data)
    field_str = _field_list(table)
    q = f"""mutation {{
        update_{table}(where: {where_clause}, _set: {set_clause}) {{
            affected_rows
            returning {{ {field_str} }}
        }}
    }}"""
    data = await graphql(q)
    result = data.get(f"update_{table}", {})
    return result


async def delete_rows(table: str, where: dict):
    """Delete rows matching where clause."""
    where_clause = _build_where(where)
    q = f"""mutation {{
        delete_{table}(where: {where_clause}) {{
            affected_rows
        }}
    }}"""
    data = await graphql(q)
    return data.get(f"delete_{table}", {}).get("affected_rows", 0)


async def count_rows(table: str, where: dict = None):
    """Count rows matching where clause."""
    parts = []
    if where:
        parts.append(f"where: {_build_where(where)}")
    args = ", ".join(parts)
    if args:
        q = f"query {{ {table}_aggregate({args}) {{ aggregate {{ count }} }} }}"
    else:
        q = f"query {{ {table}_aggregate {{ aggregate {{ count }} }} }}"
    data = await graphql(q)
    return data.get(f"{table}_aggregate", {}).get("aggregate", {}).get("count", 0)
    return data.get(f"{table}_aggregate", {}).get("aggregate", {}).get("count", 0)


async def increment_field(table: str, where: dict, field: str, amount: int):
    """Increment a numeric field atomically."""
    where_clause = _build_where(where)
    field_str = _field_list(table)
    q = f"""mutation {{
        update_{table}(where: {where_clause}, _inc: {{{field}: {amount}}}) {{
            affected_rows
            returning {{ {field_str} }}
        }}
    }}"""
    data = await graphql(q)
    return data.get(f"update_{table}", {})


async def upsert_one(table: str, obj: dict, conflict_columns: list, update_columns: list):
    """Insert or update on conflict."""
    obj_str = _build_object(obj)
    conflict_cols = ", ".join(conflict_columns)
    update_cols = ", ".join(update_columns)
    field_str = _field_list(table)
    q = f"""mutation {{
        insert_{table}_one(
            object: {obj_str},
            on_conflict: {{
                constraint: {table}_{conflict_columns[0]}_key,
                update_columns: [{update_cols}]
            }}
        ) {{ {field_str} }}
    }}"""
    data = await graphql(q)
    return data.get(f"insert_{table}_one")


# ============ BUILDER HELPERS ============

# Default field sets per table to avoid SELECT *
TABLE_FIELDS = {
    "user_profiles": "id auth_id user_id email name role generation_credits audition_credits limits_remaining is_active avatar_url password_hash generation_status daily_generation_limit per_minute_limit last_generation_at created_at updated_at",
    "stories": "id story_id created_by title genre sub_genre language status description cover_image_url cover_art_url tags published_at play_count story_type created_at updated_at",
    "episodes": "id episode_id story_id created_by title status script_content script final_audio_url audio_url project_state duration_seconds duration order_index is_published published_at play_count storage_files created_at updated_at",
    "characters": "id character_id story_id created_by name voice_id display_name tone category voice_settings created_at updated_at",
    "voice_settings": "id setting_id active_provider updated_at",
    "voice_samples": "id voice_id display_name storage_path storage_file_id audio_url duration_seconds status text_content error created_at updated_at",
    "audition_cache": "id voice_id text_hash audio_url duration_seconds created_at",
    "usage_logs": "id user_id action resource_type resource_id details credits_used credit_type created_at",
    "admin_logs": "id admin_id action target_type target_id details created_at",
    "audio_assets": "id asset_id story_id episode_id created_by name asset_type file_path storage_file_id duration_seconds file_size mime_type created_at",
    "generation_logs": "id user_id gen_type character_name voice_id text_length duration_seconds status provider error details created_at",
    "limit_transactions": "id user_id admin_id credit_type previous_value new_value change_amount reason created_at",
    "elevenlabs_sync_logs": "id status voices_count error created_at",
    "usage_alerts": "id alert_id user_id alert_type message resolved resolved_at created_at",
    "system_settings": "id setting_key setting_value updated_by updated_at",
    "generation_usage": "id user_id generation_date generation_count token_count failed_count last_generation_at created_at updated_at",
    "generation_queue": "id queue_id user_id request_type request_data status result_data error_message started_at completed_at created_at updated_at",
    "audio_cache": "id cache_key voice_id dialogue_text director_notes audio_url duration_seconds created_at",
    "audio_clips": "id file_id audio_url episode_id story_id dialogue_index voice_id cache_key is_cached is_active pending_deletion pending_deletion_at last_used_at created_at",
    "script_generation_jobs": "id job_id episode_id user_id status total_dialogues completed_dialogues batches_total batches_completed result_data error_message created_at updated_at",
}


def _field_list(table: str, fields: list = None):
    if fields:
        return " ".join(fields)
    return TABLE_FIELDS.get(table, "id")


def _build_where(where: dict) -> str:
    """Build Hasura where clause from dict."""
    parts = []
    for k, v in where.items():
        if isinstance(v, dict):
            # Handle operators like {"_in": [...], "_neq": "admin"}
            for op, val in v.items():
                parts.append(f"{k}: {{{op}: {_to_gql_value(val)}}}")
        else:
            parts.append(f"{k}: {{_eq: {_to_gql_value(v)}}}")
    return "{" + ", ".join(parts) + "}"


def _build_order(order: dict) -> str:
    parts = []
    for k, v in order.items():
        parts.append(f"{k}: {v}")
    return "{" + ", ".join(parts) + "}"


def _build_object(obj: dict) -> str:
    parts = []
    for k, v in obj.items():
        parts.append(f"{k}: {_to_gql_value(v)}")
    return "{" + ", ".join(parts) + "}"


def _build_set(data: dict) -> str:
    parts = []
    for k, v in data.items():
        parts.append(f"{k}: {_to_gql_value(v)}")
    return "{" + ", ".join(parts) + "}"


def _to_gql_value(val) -> str:
    import json as _json
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(val, list):
        items = ", ".join(_to_gql_value(v) for v in val)
        return f"[{items}]"
    if isinstance(val, dict):
        return _to_gql_value(_json.dumps(val))
    return f'"{val}"'
