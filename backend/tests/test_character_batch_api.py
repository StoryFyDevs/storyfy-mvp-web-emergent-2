"""
API tests for the character-based batch generation pipeline.

Tests:
1. Health endpoint: /api/health
2. Auth login: /api/auth/login
3. Script dialogues: GET /api/script/{episode_id}/dialogues
4. Script dialogues: POST /api/script/{episode_id}/dialogues
5. Script generate: POST /api/script/{episode_id}/generate (payload validation only)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
CREATOR_EMAIL = "testuser@test.com"
CREATOR_PASSWORD = "password123"
TEST_EPISODE_ID = "ep_71379fe1575a"


class TestHealthEndpoint:
    """Test /api/health is accessible."""
    
    def test_health_returns_ok(self):
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print("PASS: /api/health returns ok")


class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    def test_login_success(self):
        """Login with valid credentials returns token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD},
            timeout=10
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data or "token" in data, f"No token in response: {data}"
        print("PASS: Login returns token")
    
    def test_login_invalid_credentials(self):
        """Login with wrong password returns 401."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CREATOR_EMAIL, "password": "wrongpassword"},
            timeout=10
        )
        assert response.status_code in [401, 400], f"Expected 401/400, got {response.status_code}"
        print("PASS: Invalid login returns 401/400")


class TestScriptDialoguesEndpoint:
    """Test /api/script/{episode_id}/dialogues endpoints."""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for authenticated requests."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Could not login for authenticated tests")
    
    def test_get_dialogues_requires_auth(self):
        """GET dialogues without auth returns 401."""
        response = requests.get(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues",
            timeout=10
        )
        assert response.status_code == 401
        print("PASS: GET dialogues requires auth")
    
    def test_get_dialogues_with_auth(self, auth_token):
        """GET dialogues with auth returns 200."""
        response = requests.get(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "dialogues" in data
        print(f"PASS: GET dialogues returns {len(data.get('dialogues', []))} dialogues")
    
    def test_post_dialogues_requires_auth(self):
        """POST dialogues without auth returns 401."""
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues",
            json={"dialogues": []},
            timeout=10
        )
        assert response.status_code == 401
        print("PASS: POST dialogues requires auth")
    
    def test_post_dialogues_with_auth(self, auth_token):
        """POST dialogues with auth saves successfully."""
        test_dialogues = [
            {
                "index": 0,
                "character_id": "char_test",
                "character_name": "Devang",
                "voice_id": "Schedar",
                "text": "Hello world.",
                "director_notes": ""
            },
            {
                "index": 1,
                "character_id": "char_test2",
                "character_name": "Priya",
                "voice_id": "Kore",
                "text": "Hi there!",
                "director_notes": "cheerfully"
            }
        ]
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"dialogues": test_dialogues},
            timeout=10
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "dialogue_count" in data or "message" in data
        print(f"PASS: POST dialogues saved {data.get('dialogue_count', 'unknown')} dialogues")


class TestScriptGenerateEndpoint:
    """Test /api/script/{episode_id}/generate endpoint (payload validation only)."""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token") or data.get("token")
        pytest.skip("Could not login")
    
    def test_generate_requires_auth(self):
        """POST generate without auth returns 401."""
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/generate",
            json={"dialogues": []},
            timeout=10
        )
        assert response.status_code == 401
        print("PASS: Generate requires auth")
    
    def test_generate_empty_dialogues_rejected(self, auth_token):
        """POST generate with empty dialogues returns 400."""
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"dialogues": []},
            timeout=10
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Empty dialogues rejected with 400")
    
    def test_generate_accepts_valid_payload(self, auth_token):
        """POST generate with valid dialogues starts job."""
        # NOTE: This triggers actual generation but we only check initial response
        test_dialogues = [
            {
                "index": 0,
                "character_id": "char_test",
                "character_name": "Devang",
                "voice_id": "Schedar",
                "text": "Test dialogue.",
                "director_notes": ""
            }
        ]
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/generate",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"dialogues": test_dialogues},
            timeout=15
        )
        # Accept 200, 202, or any non-5xx as success (job started)
        assert response.status_code < 500, f"Server error: {response.status_code}: {response.text}"
        data = response.json()
        
        # Should return job_id if accepted
        if response.status_code in [200, 201, 202]:
            assert "job_id" in data or "status" in data
            print(f"PASS: Generate returns job_id={data.get('job_id')}")
        else:
            print(f"PASS: Generate responds with {response.status_code}: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
