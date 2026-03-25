"""
Voice Generator Upgrade Tests - Iteration 11
Tests for:
- POST /api/tts/isolate endpoint (ElevenLabs Audio Isolation)
- POST /api/tts/generate (with usage tracking)
- Admin and Creator login flows
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://dialogue-chunks.preview.emergentagent.com')

# Test credentials
CREATOR_EMAIL = "testapi@test.com"
CREATOR_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin123"
STORY_ID = "story_2ea34eb172ac"


@pytest.fixture(scope="module")
def creator_token():
    """Get creator authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD}
    )
    assert response.status_code == 200, f"Creator login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/admin-9821/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]


class TestAuthFlows:
    """Test authentication flows for admin and creator"""
    
    def test_creator_login_success(self):
        """Test creator login returns token and user data"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == CREATOR_EMAIL
        assert data["user"]["role"] == "creator"
        
    def test_admin_login_success(self):
        """Test admin login returns token and admin user data"""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["role"] == "admin"
        
    def test_admin_login_wrong_password(self):
        """Test admin login with wrong password returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/login",
            json={"email": ADMIN_EMAIL, "password": "wrongpassword"}
        )
        assert response.status_code == 401
        
    def test_admin_login_creator_credentials(self):
        """Test admin login with creator credentials returns 403"""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/login",
            json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD}
        )
        assert response.status_code == 403  # Admin access required


class TestTTSIsolateEndpoint:
    """Test POST /api/tts/isolate endpoint"""
    
    def test_isolate_requires_auth(self):
        """Test isolate endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/tts/isolate",
            json={}
        )
        assert response.status_code == 401
        
    def test_isolate_validates_empty_body(self, creator_token):
        """Test isolate endpoint returns 400 for empty body"""
        response = requests.post(
            f"{BASE_URL}/api/tts/isolate",
            headers={"Authorization": f"Bearer {creator_token}"},
            json={}
        )
        assert response.status_code == 400
        data = response.json()
        assert "audio_base64 is required" in data.get("detail", "")
        
    def test_isolate_validates_missing_audio(self, creator_token):
        """Test isolate endpoint returns 400 when audio_base64 is missing"""
        response = requests.post(
            f"{BASE_URL}/api/tts/isolate",
            headers={"Authorization": f"Bearer {creator_token}"},
            json={"other_field": "value"}
        )
        assert response.status_code == 400
        assert "audio_base64 is required" in response.json().get("detail", "")


class TestTTSGenerateEndpoint:
    """Test POST /api/tts/generate endpoint with usage tracking"""
    
    def test_generate_requires_auth(self):
        """Test generate endpoint requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/tts/generate",
            json={"text": "test", "voice_id": "test"}
        )
        assert response.status_code == 401
        
    def test_get_voices(self, creator_token):
        """Test GET /api/voices returns voice list"""
        response = requests.get(
            f"{BASE_URL}/api/voices",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        assert isinstance(data["voices"], list)
        
    def test_get_tts_models(self, creator_token):
        """Test GET /api/tts/models returns model info with audio tags"""
        response = requests.get(
            f"{BASE_URL}/api/tts/models",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert "audio_tags" in data
        # Check v3 model is available
        model_ids = [m["model_id"] for m in data["models"]]
        assert "eleven_v3" in model_ids
        # Check audio tags structure
        assert "emotions" in data["audio_tags"]
        assert "actions" in data["audio_tags"]


class TestStoriesAndCharacters:
    """Test stories and characters endpoints for Voice Generator context"""
    
    def test_get_stories(self, creator_token):
        """Test GET /api/stories returns user stories"""
        response = requests.get(
            f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        stories = response.json()
        assert isinstance(stories, list)
        # Find the test story
        story_ids = [s["story_id"] for s in stories]
        assert STORY_ID in story_ids
        
    def test_get_characters(self, creator_token):
        """Test GET /api/characters/story/{story_id} returns characters"""
        response = requests.get(
            f"{BASE_URL}/api/characters/story/{STORY_ID}",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        characters = response.json()
        assert isinstance(characters, list)


class TestUsageTracking:
    """Test usage tracking endpoints"""
    
    def test_usage_me(self, creator_token):
        """Test GET /api/usage/me returns user usage summary"""
        response = requests.get(
            f"{BASE_URL}/api/usage/me",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Check required fields exist
        assert "limits_remaining" in data
        # total_credits_used may be at top level or nested
        
    def test_user_has_limits(self, creator_token):
        """Test user has limits_remaining for generation"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        user = response.json()
        assert "limits_remaining" in user
        assert user["limits_remaining"] > 0  # User should have credits


class TestAdminDashboardAccess:
    """Test admin dashboard access"""
    
    def test_admin_stats(self, admin_token):
        """Test GET /api/admin-9821/stats returns dashboard stats"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "total_creators" in data
        assert "total_stories" in data
        
    def test_admin_users_list(self, admin_token):
        """Test GET /api/admin-9821/users returns user list with usage"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        users = response.json()
        assert isinstance(users, list)
        assert len(users) > 0
        # Check first user has usage fields
        user = users[0]
        assert "total_credits_used" in user
        assert "total_generations" in user


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
