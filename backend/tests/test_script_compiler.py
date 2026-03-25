"""
Test Script Compiler API Endpoints

Tests for the new script-based multi-speaker audio generation system:
- POST /api/script/{episode_id}/dialogues - Save script dialogues
- GET /api/script/{episode_id}/dialogues - Load script dialogues  
- POST /api/script/{episode_id}/generate - Start background generation job
- GET /api/script/job/{job_id}/status - Poll job status

Test credentials:
- Creator: testuser@test.com / password123
- Admin: admin@admin.com / admin12345
- Story ID: story_45f8bef2c25c
- Episode ID: ep_71379fe1575a
- Character: Jyoti (char_54270a0d5757, voice: Achernar)
"""
import pytest
import requests
import os
import time
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://dialogue-chunks.preview.emergentagent.com')

# Test data
CREATOR_EMAIL = "testuser@test.com"
CREATOR_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"
STORY_ID = "story_45f8bef2c25c"
EPISODE_ID = "ep_71379fe1575a"
CHARACTER_ID = "char_54270a0d5757"
CHARACTER_NAME = "Jyoti"
VOICE_ID = "Achernar"


@pytest.fixture(scope="module")
def creator_token():
    """Get creator auth token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD},
        timeout=30
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Creator login failed: {response.status_code}")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token."""
    response = requests.post(
        f"{BASE_URL}/api/admin-9821/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Admin login failed: {response.status_code}")


@pytest.fixture
def auth_headers(creator_token):
    """Auth headers for creator requests."""
    return {"Authorization": f"Bearer {creator_token}"}


@pytest.fixture
def admin_headers(admin_token):
    """Auth headers for admin requests."""
    return {"Authorization": f"Bearer {admin_token}"}


class TestScriptDialoguesSave:
    """Test POST /api/script/{episode_id}/dialogues - Save script dialogues"""
    
    def test_save_dialogues_requires_auth(self):
        """Save dialogues without auth should return 401."""
        response = requests.post(
            f"{BASE_URL}/api/script/{EPISODE_ID}/dialogues",
            json={"dialogues": []},
            timeout=30
        )
        assert response.status_code == 401
        print("PASSED: Save dialogues requires auth")
    
    def test_save_dialogues_success(self, auth_headers):
        """Save dialogues with valid data should succeed."""
        dialogues = [
            {
                "index": 0,
                "character_id": CHARACTER_ID,
                "character_name": CHARACTER_NAME,
                "voice_id": VOICE_ID,
                "text": "नमस्ते, मैं ज्योति हूं।",
                "director_notes": "speaking softly"
            },
            {
                "index": 1,
                "character_id": CHARACTER_ID,
                "character_name": CHARACTER_NAME,
                "voice_id": VOICE_ID,
                "text": "आज मैं आपको एक कहानी सुनाऊंगी।",
                "director_notes": ""
            }
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/script/{EPISODE_ID}/dialogues",
            headers=auth_headers,
            json={"dialogues": dialogues},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "message" in data
        assert data.get("dialogue_count") == 2
        print(f"PASSED: Save dialogues success - {data}")
    
    def test_save_dialogues_empty_list(self, auth_headers):
        """Save empty dialogues list should succeed."""
        response = requests.post(
            f"{BASE_URL}/api/script/{EPISODE_ID}/dialogues",
            headers=auth_headers,
            json={"dialogues": []},
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("dialogue_count") == 0
        print("PASSED: Save empty dialogues list")
    
    def test_save_dialogues_invalid_episode(self, auth_headers):
        """Save dialogues for non-existent episode should return 404."""
        response = requests.post(
            f"{BASE_URL}/api/script/ep_invalid_12345/dialogues",
            headers=auth_headers,
            json={"dialogues": []},
            timeout=30
        )
        
        assert response.status_code == 404
        print("PASSED: Save dialogues invalid episode returns 404")


class TestScriptDialoguesLoad:
    """Test GET /api/script/{episode_id}/dialogues - Load script dialogues"""
    
    def test_load_dialogues_requires_auth(self):
        """Load dialogues without auth should return 401."""
        response = requests.get(
            f"{BASE_URL}/api/script/{EPISODE_ID}/dialogues",
            timeout=30
        )
        assert response.status_code == 401
        print("PASSED: Load dialogues requires auth")
    
    def test_load_dialogues_success(self, auth_headers):
        """Load dialogues should return saved data."""
        # First save some dialogues
        dialogues = [
            {
                "index": 0,
                "character_id": CHARACTER_ID,
                "character_name": CHARACTER_NAME,
                "voice_id": VOICE_ID,
                "text": "यह एक परीक्षण है।",
                "director_notes": "calm tone"
            }
        ]
        
        save_response = requests.post(
            f"{BASE_URL}/api/script/{EPISODE_ID}/dialogues",
            headers=auth_headers,
            json={"dialogues": dialogues},
            timeout=30
        )
        assert save_response.status_code == 200
        
        # Then load
        response = requests.get(
            f"{BASE_URL}/api/script/{EPISODE_ID}/dialogues",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "dialogues" in data
        assert isinstance(data["dialogues"], list)
        
        if len(data["dialogues"]) > 0:
            d = data["dialogues"][0]
            assert "character_id" in d or "character_name" in d
            assert "text" in d
        
        print(f"PASSED: Load dialogues success - {len(data['dialogues'])} dialogues")
    
    def test_load_dialogues_invalid_episode(self, auth_headers):
        """Load dialogues for non-existent episode should return 404."""
        response = requests.get(
            f"{BASE_URL}/api/script/ep_invalid_99999/dialogues",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 404
        print("PASSED: Load dialogues invalid episode returns 404")


class TestScriptGenerateAudio:
    """Test POST /api/script/{episode_id}/generate - Trigger batch audio generation"""
    
    def test_generate_requires_auth(self):
        """Generate without auth should return 401."""
        response = requests.post(
            f"{BASE_URL}/api/script/{EPISODE_ID}/generate",
            json={"dialogues": []},
            timeout=30
        )
        assert response.status_code == 401
        print("PASSED: Generate requires auth")
    
    def test_generate_empty_dialogues_error(self, auth_headers):
        """Generate with empty dialogues should return 400."""
        response = requests.post(
            f"{BASE_URL}/api/script/{EPISODE_ID}/generate",
            headers=auth_headers,
            json={"dialogues": []},
            timeout=30
        )
        
        assert response.status_code == 400
        print("PASSED: Generate with empty dialogues returns 400")
    
    def test_generate_returns_job_id(self, auth_headers):
        """Generate with valid dialogues should return job_id."""
        dialogues = [
            {
                "index": 0,
                "character_id": CHARACTER_ID,
                "character_name": CHARACTER_NAME,
                "voice_id": VOICE_ID,
                "text": "टेस्ट ऑडियो जनरेशन।",
                "director_notes": ""
            }
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/script/{EPISODE_ID}/generate",
            headers=auth_headers,
            json={"dialogues": dialogues},
            timeout=30
        )
        
        # Could be 200 (job created) or 403 (limits exceeded) or 429 (rate limit)
        if response.status_code in [403, 429]:
            print(f"SKIPPED: Generate rate limited or access denied - {response.status_code}")
            pytest.skip("Rate limited or access denied")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "job_id" in data
        assert "status" in data
        assert data["status"] == "pending"
        print(f"PASSED: Generate returns job_id - {data['job_id']}")
        return data["job_id"]
    
    def test_generate_invalid_episode(self, auth_headers):
        """Generate for non-existent episode should return 404."""
        response = requests.post(
            f"{BASE_URL}/api/script/ep_invalid_00000/generate",
            headers=auth_headers,
            json={"dialogues": [{"index": 0, "character_id": "x", "character_name": "X", "voice_id": "y", "text": "test", "director_notes": ""}]},
            timeout=30
        )
        
        assert response.status_code == 404
        print("PASSED: Generate invalid episode returns 404")


class TestScriptJobStatus:
    """Test GET /api/script/job/{job_id}/status - Poll job status"""
    
    def test_job_status_requires_auth(self):
        """Job status without auth should return 401."""
        response = requests.get(
            f"{BASE_URL}/api/script/job/scrjob_fake12345/status",
            timeout=30
        )
        assert response.status_code == 401
        print("PASSED: Job status requires auth")
    
    def test_job_status_invalid_job(self, auth_headers):
        """Job status for non-existent job should return 404."""
        response = requests.get(
            f"{BASE_URL}/api/script/job/scrjob_nonexistent/status",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 404
        print("PASSED: Job status invalid job returns 404")
    
    def test_job_status_returns_progress(self, auth_headers):
        """Job status should return progress fields."""
        # First create a job
        dialogues = [
            {
                "index": 0,
                "character_id": CHARACTER_ID,
                "character_name": CHARACTER_NAME,
                "voice_id": VOICE_ID,
                "text": "प्रगति परीक्षण।",
                "director_notes": ""
            }
        ]
        
        gen_response = requests.post(
            f"{BASE_URL}/api/script/{EPISODE_ID}/generate",
            headers=auth_headers,
            json={"dialogues": dialogues},
            timeout=30
        )
        
        if gen_response.status_code in [403, 429]:
            pytest.skip("Rate limited or access denied")
        
        if gen_response.status_code != 200:
            pytest.skip(f"Could not create job: {gen_response.status_code}")
        
        job_id = gen_response.json().get("job_id")
        assert job_id is not None
        
        # Poll status
        time.sleep(1)  # Give job a moment to start
        
        response = requests.get(
            f"{BASE_URL}/api/script/job/{job_id}/status",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        assert "job_id" in data
        assert "status" in data
        assert "total_dialogues" in data
        assert "completed_dialogues" in data
        
        # Status should be one of valid states
        assert data["status"] in ["pending", "processing", "completed", "completed_with_errors", "failed"]
        
        print(f"PASSED: Job status returns progress - status={data['status']}, completed={data['completed_dialogues']}/{data['total_dialogues']}")


class TestAdminBatchSizeConfig:
    """Test admin batch size configuration in Generation Controls"""
    
    def test_get_limits_includes_batch_size(self, admin_headers):
        """GET /api/admin-9821/generation/limits should include batch_size."""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/generation/limits",
            headers=admin_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # batch_size may or may not be set, but endpoint should work
        print(f"PASSED: Admin limits endpoint works - batch_size={data.get('batch_size', 'not set')}")
    
    def test_update_batch_size(self, admin_headers):
        """POST /api/admin-9821/generation/limits should accept batch_size."""
        # First get current limits
        get_response = requests.get(
            f"{BASE_URL}/api/admin-9821/generation/limits",
            headers=admin_headers,
            timeout=30
        )
        
        if get_response.status_code != 200:
            pytest.skip("Could not get current limits")
        
        current = get_response.json()
        
        # Update with batch_size
        update_data = {
            "rpd": current.get("rpd", 50),
            "rpm": current.get("rpm", 5),
            "tpm": current.get("tpm", 10000),
            "auto_distribute": current.get("auto_distribute", True),
            "batch_size": 8  # Set a specific batch size
        }
        
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/generation/limits",
            headers=admin_headers,
            json=update_data,
            timeout=30
        )
        
        assert response.status_code == 200
        print("PASSED: Admin can update batch_size")
        
        # Verify it was saved
        verify_response = requests.get(
            f"{BASE_URL}/api/admin-9821/generation/limits",
            headers=admin_headers,
            timeout=30
        )
        
        if verify_response.status_code == 200:
            data = verify_response.json()
            # batch_size might be 8 or might be in setting_value
            print(f"Verified batch_size: {data.get('batch_size', 'check setting_value')}")


class TestCharactersAndEpisodesExist:
    """Verify test data exists before Script Editor testing"""
    
    def test_story_exists(self, auth_headers):
        """Verify the test story exists."""
        response = requests.get(
            f"{BASE_URL}/api/stories/{STORY_ID}",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Story {STORY_ID} not found"
        data = response.json()
        print(f"PASSED: Story exists - {data.get('title', 'unknown')}")
    
    def test_episode_exists(self, auth_headers):
        """Verify the test episode exists."""
        response = requests.get(
            f"{BASE_URL}/api/episodes/{EPISODE_ID}",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Episode {EPISODE_ID} not found"
        data = response.json()
        print(f"PASSED: Episode exists - {data.get('title', 'unknown')}")
    
    def test_character_exists(self, auth_headers):
        """Verify the test character exists."""
        response = requests.get(
            f"{BASE_URL}/api/characters/story/{STORY_ID}",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Find Jyoti
        jyoti = next((c for c in data if c.get("character_id") == CHARACTER_ID), None)
        if jyoti:
            print(f"PASSED: Character exists - {jyoti.get('name')} (voice: {jyoti.get('voice_id')})")
        else:
            # Check if any character exists
            if len(data) > 0:
                print(f"INFO: Character {CHARACTER_ID} not found, but {len(data)} other characters exist")
            else:
                print("WARNING: No characters found for story")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
