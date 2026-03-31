"""
Vertex AI Authentication Helper
Generates OAuth2 Bearer tokens from the service account JSON key
for authenticating Gemini API calls via Vertex AI endpoints.
"""
import os
import logging
from google.oauth2 import service_account
from google.auth.transport.requests import Request

logger = logging.getLogger("vertex_auth")

SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")
VERTEX_AI_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

PROJECT_ID = "gen-lang-client-0988882713"
REGION = "us-central1"
MODEL_ID = "gemini-2.5-pro-tts"

VERTEX_TTS_URL = (
    f"https://{REGION}-aiplatform.googleapis.com/v1/"
    f"projects/{PROJECT_ID}/locations/{REGION}/"
    f"publishers/google/models/{MODEL_ID}:generateContent"
)

_credentials = None


def _get_credentials():
    global _credentials
    if _credentials is None:
        _credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=VERTEX_AI_SCOPES
        )
    return _credentials


def get_access_token() -> str:
    creds = _get_credentials()
    if not creds.valid:
        creds.refresh(Request())
    return creds.token


def get_auth_headers() -> dict:
    token = get_access_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
