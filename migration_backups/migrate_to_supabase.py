"""
Supabase Data Migration Script
Restores nhost_full_backup.json into Supabase via the REST API.

Usage:
    python migration_backups/migrate_to_supabase.py

Requires: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.
"""
import os
import json
import sys
import time
from pathlib import Path

try:
    from supabase import create_client
except ImportError:
    print("ERROR: supabase package not installed. Run: pip install supabase")
    sys.exit(1)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
    sys.exit(1)

BACKUP_FILE = Path(__file__).parent / "nhost_full_backup.json"

# Insert order respects FK dependencies
TABLE_ORDER = [
    "user_profiles",
    "stories",
    "episodes",
    "characters",
    "voice_settings",
    "voice_samples",
    "audition_cache",
    "audio_cache",
    "audio_clips",
    "audio_assets",
    "generation_logs",
    "generation_usage",
    "generation_queue",
    "script_generation_jobs",
    "system_settings",
    "usage_logs",
    "limit_transactions",
    "usage_alerts",
    "generation_metrics",
    "generation_debug_logs",
]

# Tables where 'id' is BIGSERIAL in Supabase (auto-generated) but UUID in Nhost — drop it
DROP_ID_TABLES = {
    "user_profiles", "stories", "episodes", "characters",
    "voice_samples", "audition_cache", "audio_cache",
    "audio_clips", "audio_assets", "generation_logs",
    "generation_usage", "generation_queue", "script_generation_jobs",
    "system_settings", "usage_logs", "limit_transactions",
    "usage_alerts", "generation_metrics", "generation_debug_logs",
}

# Array fields: Nhost stores as JSON string "[]", Supabase needs Python list
ARRAY_FIELDS = {
    "stories": ["tags"],
}

BATCH_SIZE = 50


def _clean_row(table: str, row: dict) -> dict:
    """Normalize a row for Supabase insertion."""
    cleaned = {}
    arr_fields = ARRAY_FIELDS.get(table, [])

    for k, v in row.items():
        # Drop auto-generated id for BIGSERIAL tables
        if k == "id" and table in DROP_ID_TABLES:
            continue

        # Convert JSON-encoded arrays to Python lists
        if k in arr_fields:
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = []
            if not isinstance(v, list):
                v = []

        # Convert JSON-encoded objects to dicts (for JSONB columns)
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            try:
                v = json.loads(v)
            except Exception:
                pass
        if isinstance(v, str) and v.startswith("[") and v.endswith("]"):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    v = parsed
            except Exception:
                pass

        cleaned[k] = v

    return cleaned


def _conflict_col(table: str) -> str:
    """Return the unique conflict column to upsert on."""
    CONFLICT_COLS = {
        "user_profiles": "user_id",
        "stories": "story_id",
        "episodes": "episode_id",
        "characters": "character_id",
        "voice_samples": "voice_id",
        "script_generation_jobs": "job_id",
        "audio_clips": "file_id",
        "audio_cache": "cache_key",
        "system_settings": "setting_key",
        "generation_metrics": "generation_id",
        "generation_debug_logs": "log_id",
    }
    return CONFLICT_COLS.get(table, "")


def migrate():
    print(f"Connecting to Supabase: {SUPABASE_URL}")
    sc = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    with open(BACKUP_FILE) as f:
        backup = json.load(f)

    total_inserted = 0
    total_errors = 0

    for table in TABLE_ORDER:
        rows = backup.get(table, [])
        if not rows:
            print(f"  {table}: 0 rows — skipping")
            continue

        print(f"\n→ Migrating {table} ({len(rows)} rows)...")
        inserted = 0
        errors = 0
        conflict = _conflict_col(table)

        for i in range(0, len(rows), BATCH_SIZE):
            batch = [_clean_row(table, r) for r in rows[i:i + BATCH_SIZE]]
            try:
                if conflict:
                    r = sc.table(table).upsert(batch, on_conflict=conflict).execute()
                else:
                    r = sc.table(table).insert(batch).execute()
                inserted += len(batch)
                print(f"  Batch {i//BATCH_SIZE + 1}: inserted {len(batch)} rows")
            except Exception as e:
                errors += len(batch)
                print(f"  ERROR in batch {i//BATCH_SIZE + 1}: {e}")
                # Try row-by-row fallback
                for row in batch:
                    try:
                        if conflict:
                            sc.table(table).upsert(row, on_conflict=conflict).execute()
                        else:
                            sc.table(table).insert(row).execute()
                        inserted += 1
                        errors -= 1
                    except Exception as e2:
                        print(f"    Row error: {e2} | keys: {list(row.keys())[:5]}")
            time.sleep(0.05)

        print(f"  {table}: {inserted} inserted, {errors} errors")
        total_inserted += inserted
        total_errors += errors

    print(f"\n{'='*50}")
    print(f"Migration complete: {total_inserted} rows inserted, {total_errors} errors")
    if total_errors > 0:
        print("Some rows failed — check logs above for details")
    else:
        print("All data migrated successfully!")


if __name__ == "__main__":
    migrate()
