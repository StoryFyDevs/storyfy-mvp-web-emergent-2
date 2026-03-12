"""
Nhost Storage Module - File upload/download via Nhost Storage HTTP API.
"""
import os
import httpx
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend directory
load_dotenv(Path(__file__).parent / '.env')

logger = logging.getLogger("nhost_storage")

NHOST_SUBDOMAIN = os.environ.get("NHOST_SUBDOMAIN", "")
NHOST_REGION = os.environ.get("NHOST_REGION", "")
NHOST_ADMIN_SECRET = os.environ.get("NHOST_ADMIN_SECRET", "")

STORAGE_URL = f"https://{NHOST_SUBDOMAIN}.storage.{NHOST_REGION}.nhost.run"

_client = None


def _get_client():
    global _client
    if _client is None:
        admin_secret = os.environ.get("NHOST_ADMIN_SECRET", "")
        _client = httpx.AsyncClient(
            timeout=60.0,
            headers={"x-hasura-admin-secret": admin_secret},
        )
    return _client


async def upload_file(filename: str, content: bytes, content_type: str, bucket_id: str = "default"):
    """Upload a file to Nhost Storage. Returns file metadata dict."""
    client = _get_client()
    files = {"file[]": (filename, content, content_type)}
    data = {"bucket-id": bucket_id}
    resp = await client.post(f"{STORAGE_URL}/v1/files", files=files, data=data)
    if resp.status_code not in (200, 201):
        logger.error(f"Upload failed: {resp.status_code} - {resp.text[:200]}")
        raise Exception(f"Storage upload failed: {resp.status_code}")
    result = resp.json()
    processed = result.get("processedFiles", [])
    if not processed:
        raise Exception("No files processed")
    return processed[0]


async def get_presigned_url(file_id: str):
    """Get a presigned download URL for a file."""
    client = _get_client()
    resp = await client.get(f"{STORAGE_URL}/v1/files/{file_id}/presignedurl")
    if resp.status_code != 200:
        logger.error(f"Presigned URL failed: {resp.status_code} - {resp.text[:200]}")
        raise Exception(f"Failed to get presigned URL: {resp.status_code}")
    return resp.json().get("url", "")


async def download_file(file_id: str):
    """Download file content by ID."""
    client = _get_client()
    url = await get_presigned_url(file_id)
    resp = await client.get(url)
    if resp.status_code != 200:
        raise Exception(f"Download failed: {resp.status_code}")
    return resp.content


async def delete_file(file_id: str):
    """Delete a file from storage."""
    client = _get_client()
    resp = await client.delete(f"{STORAGE_URL}/v1/files/{file_id}")
    return resp.status_code in (200, 204)
