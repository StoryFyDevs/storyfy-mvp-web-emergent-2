"""
Supabase Storage Module - File upload/download via Supabase Storage API.
"""
import os
import logging
import mimetypes
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(Path(__file__).parent / '.env')

logger = logging.getLogger("supabase_storage")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET_AUDIO = os.environ.get("SUPABASE_BUCKET_AUDIO", "storyfy-audio")
BUCKET_CACHE = os.environ.get("SUPABASE_BUCKET_CACHE", "storyfy-cache")
BUCKET_EXPORTS = os.environ.get("SUPABASE_BUCKET_EXPORTS", "storyfy-exports")

_client: Client = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client


def _ensure_buckets():
    """Create storage buckets if they don't exist."""
    sc = _get_client()
    for bucket in [BUCKET_AUDIO, BUCKET_CACHE, BUCKET_EXPORTS]:
        try:
            sc.storage.create_bucket(bucket, options={"public": True})
            logger.info(f"Created storage bucket: {bucket}")
        except Exception as e:
            if "already exists" in str(e).lower() or "Duplicate" in str(e):
                pass
            else:
                logger.warning(f"Bucket {bucket} create: {e}")


async def upload_file(filename: str, content: bytes, content_type: str, bucket_id: str = None):
    """
    Upload a file to Supabase Storage.
    Returns a metadata dict with id, name, bucketId, mimeType, size, publicUrl.
    The returned 'id' is in 'bucket/path' format (e.g. 'storyfy-audio/scripts/ep_x/file.wav').
    """
    if bucket_id is None or bucket_id == "default":
        bucket_id = BUCKET_AUDIO

    sc = _get_client()
    path = filename

    try:
        # Try to remove existing file to avoid conflict
        try:
            sc.storage.from_(bucket_id).remove([path])
        except Exception:
            pass

        r = sc.storage.from_(bucket_id).upload(
            path=path,
            file=content,
            file_options={"content-type": content_type, "upsert": "true"},
        )

        # file_id encodes bucket + path so we can retrieve/delete later
        file_id = f"{bucket_id}/{path}"
        public_url = sc.storage.from_(bucket_id).get_public_url(path)

        return {
            "id": file_id,
            "name": filename,
            "bucketId": bucket_id,
            "mimeType": content_type,
            "size": len(content),
            "publicUrl": public_url,
        }
    except Exception as e:
        logger.error(f"upload_file({filename}) error: {e}")
        raise Exception(f"Storage upload failed: {e}")


async def get_presigned_url(file_id: str):
    """Get a signed download URL for a file."""
    sc = _get_client()
    bucket, path = _parse_file_id(file_id)
    try:
        r = sc.storage.from_(bucket).create_signed_url(path, expires_in=3600)
        return r.get("signedURL", "") or r.get("signed_url", "")
    except Exception as e:
        # Fall back to public URL
        try:
            return sc.storage.from_(bucket).get_public_url(path)
        except Exception as e2:
            logger.error(f"get_presigned_url({file_id}): {e2}")
            raise


async def get_public_url(file_id: str) -> str:
    """Get the public URL for a file."""
    sc = _get_client()
    bucket, path = _parse_file_id(file_id)
    return sc.storage.from_(bucket).get_public_url(path)


async def download_file(file_id: str) -> bytes:
    """Download file content by ID."""
    sc = _get_client()
    bucket, path = _parse_file_id(file_id)
    try:
        data = sc.storage.from_(bucket).download(path)
        return data
    except Exception as e:
        logger.error(f"download_file({file_id}): {e}")
        raise


async def delete_file(file_id: str) -> bool:
    """Delete a file from storage."""
    sc = _get_client()
    bucket, path = _parse_file_id(file_id)
    try:
        sc.storage.from_(bucket).remove([path])
        logger.info(f"Deleted storage file: {bucket}/{path}")
        return True
    except Exception as e:
        logger.warning(f"delete_file({file_id}): {e}")
        return False


def _parse_file_id(file_id: str) -> tuple[str, str]:
    """Parse 'bucket/path' format file_id back into (bucket, path).
    Also handles legacy 'nhost-file:bucket/path' prefix from old DB records."""
    if file_id.startswith("nhost-file:"):
        file_id = file_id[len("nhost-file:"):]
    if "/" not in file_id:
        return BUCKET_AUDIO, file_id
    parts = file_id.split("/", 1)
    return parts[0], parts[1]


def audio_url_from_file_id(file_id: str) -> str:
    """Return the canonical audio URL stored in the database for a given file_id.
    Format: 'bucket/path' (e.g. 'storyfy-audio/scripts/ep_x/file.wav')."""
    return file_id


def resolve_audio_url(audio_url: str) -> str:
    """
    Convert a stored audio_url to a public HTTPS Supabase Storage URL.

    Handles:
      - 'bucket/path'              — current canonical format
      - 'nhost-file:bucket/path'   — legacy prefix from old DB records (prefix stripped)
      - 'https://...'              — already an absolute URL, returned as-is
      - ''                         — returns ''

    Returns '' for dead/stale refs that cannot be resolved:
      - bare UUID with no slash    — old Nhost-only IDs with no Supabase bucket path
      - nhost-file:<UUID>          — same, wrapped with legacy prefix
    """
    if not audio_url:
        return ""
    if audio_url.startswith("http"):
        return audio_url
    # Strip legacy prefix if present
    file_id = audio_url[len("nhost-file:"):] if audio_url.startswith("nhost-file:") else audio_url
    # Bare UUID with no slash — this is a dead old Nhost ref with no Supabase equivalent
    if "/" not in file_id:
        return ""
    sc = _get_client()
    bucket, path = _parse_file_id(file_id)
    return sc.storage.from_(bucket).get_public_url(path)
