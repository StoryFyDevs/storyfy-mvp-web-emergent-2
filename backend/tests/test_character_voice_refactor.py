"""
Test suite for Character & Voice Refactor (Iteration 18)
Tests:
- GET /api/voices/samples - Returns all 30 available voice samples
- GET /api/voices/preview/{voice_id} - Returns free preview audio (no credit deduction)
- POST /api/tts/audition - Generates custom dialogue (deducts audition credit)
- PUT /api/characters/{character_id} - Edits character name and voice
- POST /api/characters - Creates new character
- DELETE /api/characters/{character_id} - Deletes character
- GET /api/credits - Returns both generation and audition credits
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for creator user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "testapi@test.com",
        "password": "password123"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("token")

@pytest.fixture(scope="module")
def headers(auth_token):
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

class TestVoiceSamplesEndpoint:
    """Test GET /api/voices/samples - returns available voice samples"""

    def test_voices_samples_returns_status(self, headers):
        """GET /api/voices/samples should return sample availability"""
        response = requests.get(f"{BASE_URL}/api/voices/samples", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "samples" in data, "Response should contain 'samples' field"
        assert "total_available" in data, "Response should contain 'total_available' field"
        assert "total_voices" in data, "Response should contain 'total_voices' field"
        
        # Verify total_voices is 30 (the master list)
        assert data["total_voices"] == 30, f"Expected 30 total voices, got {data['total_voices']}"
        
        # samples should be a dict mapping voice_id -> True
        assert isinstance(data["samples"], dict), "samples should be a dictionary"
        print(f"Voice samples status: {data['total_available']}/{data['total_voices']} ready")


class TestVoicePreviewEndpoint:
    """Test GET /api/voices/preview/{voice_id} - returns free preview audio"""

    def test_voice_preview_returns_audio_url(self, headers):
        """GET /api/voices/preview/{voice_id} should return audio_url without deducting credits"""
        # First get available samples
        samples_resp = requests.get(f"{BASE_URL}/api/voices/samples", headers=headers)
        samples_data = samples_resp.json()
        
        if samples_data["total_available"] == 0:
            pytest.skip("No voice samples available yet")
        
        # Get a random available voice_id
        available_voices = [vid for vid, available in samples_data["samples"].items() if available]
        test_voice_id = available_voices[0]
        
        # Get credits before
        credits_resp = requests.get(f"{BASE_URL}/api/credits", headers=headers)
        credits_before = credits_resp.json()
        
        # Get preview
        response = requests.get(f"{BASE_URL}/api/voices/preview/{test_voice_id}", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "audio_url" in data, "Response should contain 'audio_url'"
        assert "voice_id" in data, "Response should contain 'voice_id'"
        assert "display_name" in data, "Response should contain 'display_name'"
        assert data["voice_id"] == test_voice_id
        assert data["audio_url"].startswith("data:audio/"), "audio_url should be a data URL"
        
        # Verify credits NOT deducted (free preview)
        credits_resp = requests.get(f"{BASE_URL}/api/credits", headers=headers)
        credits_after = credits_resp.json()
        assert credits_after["audition_credits"] == credits_before["audition_credits"], \
            "Free preview should NOT deduct audition credits"
        
        print(f"Free preview for voice {test_voice_id} ({data['display_name']}) - Credits unchanged")

    def test_voice_preview_invalid_voice_id(self, headers):
        """GET /api/voices/preview/{invalid_voice_id} should return 404"""
        response = requests.get(f"{BASE_URL}/api/voices/preview/invalid_voice_123", headers=headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestAuditionEndpoint:
    """Test POST /api/tts/audition - custom dialogue generation (costs credits)"""

    def test_audition_generates_audio_and_deducts_credit(self, headers):
        """POST /api/tts/audition should generate audio and deduct 1 audition credit"""
        # Get available voice
        samples_resp = requests.get(f"{BASE_URL}/api/voices/samples", headers=headers)
        samples_data = samples_resp.json()
        
        available_voices = [vid for vid, available in samples_data["samples"].items() if available]
        if not available_voices:
            pytest.skip("No voice samples available yet")
        
        test_voice_id = available_voices[0]
        
        # Get credits before
        credits_resp = requests.get(f"{BASE_URL}/api/credits", headers=headers)
        credits_before = credits_resp.json()
        
        if credits_before["audition_credits"] <= 0:
            pytest.skip("No audition credits available")
        
        # Generate unique text to avoid cache
        unique_text = f"यह एक टेस्ट है - {time.time()}"
        
        # Generate audition
        response = requests.post(f"{BASE_URL}/api/tts/audition", headers=headers, json={
            "voice_id": test_voice_id,
            "text": unique_text
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "audio_url" in data, "Response should contain 'audio_url'"
        assert data["audio_url"].startswith("data:audio/"), "audio_url should be a data URL"
        assert "cached" in data, "Response should indicate if cached"
        
        if not data["cached"]:
            # Verify credit deducted
            credits_resp = requests.get(f"{BASE_URL}/api/credits", headers=headers)
            credits_after = credits_resp.json()
            assert credits_after["audition_credits"] == credits_before["audition_credits"] - 1, \
                f"Expected audition_credits to decrease by 1, before={credits_before['audition_credits']}, after={credits_after['audition_credits']}"
        
        print(f"Custom audition generated - cached={data['cached']}")

    def test_audition_requires_voice_id_and_text(self, headers):
        """POST /api/tts/audition should require voice_id and text"""
        # Missing voice_id
        response = requests.post(f"{BASE_URL}/api/tts/audition", headers=headers, json={"text": "test"})
        assert response.status_code == 400, f"Expected 400 for missing voice_id, got {response.status_code}"
        
        # Missing text
        response = requests.post(f"{BASE_URL}/api/tts/audition", headers=headers, json={"voice_id": "Achernar"})
        assert response.status_code == 400, f"Expected 400 for missing text, got {response.status_code}"


class TestCharacterCRUD:
    """Test character CRUD operations - Create, Read, Update, Delete"""

    def test_create_character(self, headers):
        """POST /api/characters should create a new character"""
        response = requests.post(f"{BASE_URL}/api/characters", headers=headers, json={
            "story_id": "story_2ea34eb172ac",
            "name": "TEST_NewChar_" + str(int(time.time())),
            "voice_id": "Achernar"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "character_id" in data, "Response should contain 'character_id'"
        assert "name" in data, "Response should contain 'name'"
        assert "voice_id" in data, "Response should contain 'voice_id'"
        assert data["voice_id"] == "Achernar"
        
        # Store for later cleanup
        pytest.created_char_id = data["character_id"]
        print(f"Created character: {data['character_id']}")

    def test_update_character(self, headers):
        """PUT /api/characters/{character_id} should update character name and voice"""
        # Use existing character char_9446c8ef88ac
        char_id = "char_9446c8ef88ac"
        
        # Get current state
        response = requests.get(f"{BASE_URL}/api/characters/story/story_2ea34eb172ac", headers=headers)
        assert response.status_code == 200
        chars = response.json()
        
        char = next((c for c in chars if c["character_id"] == char_id), None)
        if not char:
            pytest.skip(f"Character {char_id} not found")
        
        original_name = char["name"]
        original_voice = char.get("voice_id", "")
        
        # Update character
        new_name = f"Updated_{int(time.time())}"
        new_voice = "Achird"  # Different voice
        
        response = requests.put(f"{BASE_URL}/api/characters/{char_id}", headers=headers, json={
            "story_id": "story_2ea34eb172ac",
            "name": new_name,
            "voice_id": new_voice
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["name"] == new_name, f"Expected name '{new_name}', got '{data['name']}'"
        assert data["voice_id"] == new_voice, f"Expected voice_id '{new_voice}', got '{data['voice_id']}'"
        
        # Verify with GET
        response = requests.get(f"{BASE_URL}/api/characters/story/story_2ea34eb172ac", headers=headers)
        chars = response.json()
        updated_char = next((c for c in chars if c["character_id"] == char_id), None)
        assert updated_char is not None
        assert updated_char["name"] == new_name
        assert updated_char["voice_id"] == new_voice
        
        # Restore original
        requests.put(f"{BASE_URL}/api/characters/{char_id}", headers=headers, json={
            "story_id": "story_2ea34eb172ac",
            "name": original_name,
            "voice_id": original_voice or "Achernar"
        })
        
        print(f"Character update verified: {char_id}")

    def test_delete_character(self, headers):
        """DELETE /api/characters/{character_id} should delete character"""
        # First create a character to delete
        response = requests.post(f"{BASE_URL}/api/characters", headers=headers, json={
            "story_id": "story_2ea34eb172ac",
            "name": "TEST_ToDelete_" + str(int(time.time())),
            "voice_id": "Algenib"
        })
        assert response.status_code == 200
        char_id = response.json()["character_id"]
        
        # Delete it
        response = requests.delete(f"{BASE_URL}/api/characters/{char_id}", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify deleted
        response = requests.get(f"{BASE_URL}/api/characters/story/story_2ea34eb172ac", headers=headers)
        chars = response.json()
        assert all(c["character_id"] != char_id for c in chars), "Character should be deleted"
        
        print(f"Character deleted: {char_id}")

    def test_delete_nonexistent_character(self, headers):
        """DELETE /api/characters/{invalid_id} should return 404"""
        response = requests.delete(f"{BASE_URL}/api/characters/invalid_char_123", headers=headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestCreditsEndpoint:
    """Test GET /api/credits - returns both generation and audition credits"""

    def test_credits_returns_both_types(self, headers):
        """GET /api/credits should return generation_credits and audition_credits"""
        response = requests.get(f"{BASE_URL}/api/credits", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "generation_credits" in data, "Response should contain 'generation_credits'"
        assert "audition_credits" in data, "Response should contain 'audition_credits'"
        assert isinstance(data["generation_credits"], (int, float)), "generation_credits should be a number"
        assert isinstance(data["audition_credits"], (int, float)), "audition_credits should be a number"
        
        print(f"Credits: generation={data['generation_credits']}, audition={data['audition_credits']}")


class TestVoicesList:
    """Test GET /api/voices - returns all 30 voices with metadata"""

    def test_voices_list_has_30_voices(self, headers):
        """GET /api/tts/settings should return 30 voices with Indian display names"""
        response = requests.get(f"{BASE_URL}/api/tts/settings", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "voices" in data, "Response should contain 'voices'"
        assert len(data["voices"]) == 30, f"Expected 30 voices, got {len(data['voices'])}"
        
        # Check voice structure
        voice = data["voices"][0]
        assert "voice_id" in voice, "Voice should have 'voice_id'"
        assert "name" in voice, "Voice should have 'name'"
        assert "tone" in voice, "Voice should have 'tone'"
        assert "gender" in voice, "Voice should have 'gender'"
        assert "category" in voice, "Voice should have 'category'"
        assert "category_label" in voice, "Voice should have 'category_label'"
        
        # Check categories
        categories = set(v["category"] for v in data["voices"])
        expected_categories = {"narrator", "deep_voice", "energetic", "calm", "dramatic"}
        assert categories == expected_categories, f"Expected categories {expected_categories}, got {categories}"
        
        print(f"Verified 30 voices with categories: {categories}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
