"""
Test suite for Narration-first workflow feature.
Tests:
1. Tab order (Characters → Script Editor → Audio Studio) - frontend only
2. Default route to Characters - frontend only
3. Script Editor narration mode
4. Backend API endpoints for script-data, dialogue-mode, narration/generate
"""
import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
CREATOR_EMAIL = "testuser@test.com"
CREATOR_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"

# Test episode from context
TEST_EPISODE_ID = "ep_51929c8a13cd"
TEST_STORY_ID = "story_404e0aa48b5b"


class TestHealthAndAuth:
    """Basic health and authentication tests."""
    
    def test_health_endpoint(self):
        """Test backend health check."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("✓ Health endpoint working")
    
    def test_creator_login(self):
        """Test creator login."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200, f"Creator login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in login response"
        print(f"✓ Creator login successful, token received")
        return data["token"]
    
    def test_admin_login(self):
        """Test admin login."""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in admin login response"
        print(f"✓ Admin login successful")
        return data["token"]


class TestDialogueModeSettings:
    """Test dialogue mode settings endpoints."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth tokens."""
        # Creator token
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        self.creator_token = response.json().get("token", "")
        
        # Admin token
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        self.admin_token = response.json().get("token", "")
    
    def test_get_dialogue_mode_public(self):
        """Test GET /api/settings/dialogue-mode returns enabled status."""
        response = requests.get(
            f"{BASE_URL}/api/settings/dialogue-mode",
            headers={"Authorization": f"Bearer {self.creator_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "enabled" in data, "Response missing 'enabled' field"
        assert isinstance(data["enabled"], bool), "enabled should be boolean"
        print(f"✓ GET /api/settings/dialogue-mode returns enabled={data['enabled']}")
    
    def test_admin_get_dialogue_mode(self):
        """Test admin GET /api/admin-9821/settings/dialogue-mode."""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/settings/dialogue-mode",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "enabled" in data, "Response missing 'enabled' field"
        print(f"✓ Admin GET dialogue-mode returns enabled={data['enabled']}")
    
    def test_admin_toggle_dialogue_mode(self):
        """Test admin POST /api/admin-9821/settings/dialogue-mode toggles setting."""
        # Get current state
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/settings/dialogue-mode",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        current_enabled = response.json().get("enabled", False)
        
        # Toggle to opposite
        new_enabled = not current_enabled
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/settings/dialogue-mode",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"enabled": new_enabled}
        )
        assert response.status_code == 200, f"Toggle failed: {response.text}"
        data = response.json()
        assert data.get("enabled") == new_enabled, f"Expected enabled={new_enabled}, got {data}"
        print(f"✓ Admin toggle dialogue-mode to {new_enabled}")
        
        # Restore original state
        requests.post(
            f"{BASE_URL}/api/admin-9821/settings/dialogue-mode",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"enabled": current_enabled}
        )
        print(f"✓ Restored dialogue-mode to {current_enabled}")


class TestScriptDataEndpoints:
    """Test script-data save/load endpoints."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        self.token = response.json().get("token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_script_data(self):
        """Test GET /api/script/{episode_id}/script-data loads data."""
        response = requests.get(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/script-data",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should have mode field
        assert "mode" in data, "Response missing 'mode' field"
        assert data["mode"] in ["narration", "dialogue"], f"Invalid mode: {data['mode']}"
        
        # Should have parts and dialogues arrays
        assert "parts" in data or "dialogues" in data, "Response missing parts/dialogues"
        
        print(f"✓ GET script-data returns mode={data['mode']}")
        if data.get("voice_id"):
            print(f"  voice_id={data['voice_id']}")
        if data.get("parts"):
            print(f"  parts count={len(data['parts'])}")
    
    def test_save_script_data_narration_mode(self):
        """Test POST /api/script/{episode_id}/script-data saves narration data."""
        # First get current data to restore later
        response = requests.get(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/script-data",
            headers=self.headers
        )
        original_data = response.json()
        
        # Save new narration data
        test_data = {
            "mode": "narration",
            "voice_id": "Kore",
            "parts": [
                {"part_number": 1, "text": "Test narration part 1", "director_notes": "Read slowly"},
                {"part_number": 2, "text": "Test narration part 2", "director_notes": ""}
            ],
            "dialogues": []
        }
        
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/script-data",
            headers={**self.headers, "Content-Type": "application/json"},
            json=test_data
        )
        assert response.status_code == 200, f"Save failed: {response.text}"
        data = response.json()
        assert data.get("mode") == "narration", f"Expected mode=narration, got {data}"
        print(f"✓ POST script-data saves narration mode")
        
        # Verify data was saved
        response = requests.get(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/script-data",
            headers=self.headers
        )
        loaded = response.json()
        assert loaded.get("mode") == "narration", "Mode not saved correctly"
        assert loaded.get("voice_id") == "Kore", "voice_id not saved correctly"
        assert len(loaded.get("parts", [])) == 2, "Parts not saved correctly"
        print(f"✓ Verified saved data: mode={loaded['mode']}, voice_id={loaded['voice_id']}, parts={len(loaded['parts'])}")
        
        # Restore original data
        requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/script-data",
            headers={**self.headers, "Content-Type": "application/json"},
            json=original_data
        )
        print(f"✓ Restored original script data")


class TestNarrationGeneration:
    """Test narration generation endpoint."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        self.token = response.json().get("token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_narration_generate_validates_15k_limit(self):
        """Test POST /api/script/{episode_id}/narration/generate validates 15k char limit."""
        # Create text that exceeds 15000 characters
        long_text = "A" * 15001
        
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/narration/generate",
            headers={**self.headers, "Content-Type": "application/json"},
            json={
                "voice_id": "Kore",
                "parts": [
                    {"part_number": 1, "text": long_text, "director_notes": ""}
                ]
            }
        )
        
        # Should return 422 with content_too_long
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "content_too_long" in str(data.get("detail", "")), f"Expected content_too_long error, got {data}"
        print(f"✓ Narration generate validates 15k limit (returns 422 content_too_long)")
    
    def test_narration_generate_requires_voice_id(self):
        """Test narration generate requires voice_id."""
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/narration/generate",
            headers={**self.headers, "Content-Type": "application/json"},
            json={
                "voice_id": "",
                "parts": [
                    {"part_number": 1, "text": "Test text", "director_notes": ""}
                ]
            }
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print(f"✓ Narration generate requires voice_id (returns 400)")
    
    def test_narration_generate_requires_parts(self):
        """Test narration generate requires parts."""
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/narration/generate",
            headers={**self.headers, "Content-Type": "application/json"},
            json={
                "voice_id": "Kore",
                "parts": []
            }
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print(f"✓ Narration generate requires parts (returns 400)")
    
    def test_narration_generate_returns_job_id(self):
        """Test narration generate returns job_id for valid request."""
        response = requests.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/narration/generate",
            headers={**self.headers, "Content-Type": "application/json"},
            json={
                "voice_id": "Kore",
                "parts": [
                    {"part_number": 1, "text": "This is a test narration for the StoryFy platform.", "director_notes": "Read naturally"}
                ]
            }
        )
        
        # Should return 200 with job_id (or 403 if audio access disabled, or 423 if published)
        if response.status_code == 200:
            data = response.json()
            assert "job_id" in data, f"Response missing job_id: {data}"
            assert data.get("status") in ["pending", "queued"], f"Unexpected status: {data}"
            print(f"✓ Narration generate returns job_id={data['job_id']}, status={data['status']}")
        elif response.status_code == 403:
            print(f"✓ Narration generate returns 403 (audio access disabled) - expected if user has no access")
        elif response.status_code == 423:
            print(f"✓ Narration generate returns 423 (episode locked) - expected if episode is published")
        else:
            pytest.fail(f"Unexpected response: {response.status_code} {response.text}")


class TestVoicesEndpoint:
    """Test voices endpoint for narrator voice selection."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        self.token = response.json().get("token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_voices(self):
        """Test GET /api/voices returns available voices."""
        response = requests.get(
            f"{BASE_URL}/api/voices",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "voices" in data, "Response missing 'voices' field"
        voices = data["voices"]
        assert len(voices) > 0, "No voices returned"
        
        # Check voice structure
        first_voice = voices[0]
        assert "voice_id" in first_voice, "Voice missing voice_id"
        assert "name" in first_voice, "Voice missing name"
        
        print(f"✓ GET /api/voices returns {len(voices)} voices")
        print(f"  Sample voice: {first_voice['name']} ({first_voice['voice_id']})")


class TestGenerationStatus:
    """Test generation status endpoint."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        self.token = response.json().get("token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_generation_status(self):
        """Test GET /api/generation/status returns user's generation access."""
        response = requests.get(
            f"{BASE_URL}/api/generation/status",
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should have generation_status field
        assert "generation_status" in data, "Response missing generation_status"
        assert "generation_credits" in data, "Response missing generation_credits"
        
        print(f"✓ GET /api/generation/status returns:")
        print(f"  generation_status={data.get('generation_status')}")
        print(f"  generation_credits={data.get('generation_credits')}")
        print(f"  can_generate={data.get('can_generate')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
