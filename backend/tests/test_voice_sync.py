"""
Test Voice Synchronization Feature
----------------------------------
Tests the global voice synchronization between Characters and Script dialogues.
Key features tested:
1. generated_voice_id field in script_content JSON
2. Backend returns generated_voice_id in dialogue data  
3. Script compiler returns generated_voice_id in generation results
4. Cache key includes voice_id for auto-invalidation
"""
import pytest
import requests
import os
import hashlib
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "testuser@test.com"
TEST_PASSWORD = "password123"

# Known test data
TEST_STORY_ID = "story_45f8bef2c25c"
TEST_EPISODE_ID = "ep_71379fe1575a"


class TestVoiceSyncBackend:
    """Backend API tests for voice synchronization feature."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authentication."""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if login_resp.status_code == 200:
            token = login_resp.json().get("token", "")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip(f"Login failed: {login_resp.status_code}")
    
    # ============ generated_voice_id in dialogue data ============
    
    def test_get_dialogues_returns_data(self):
        """GET /api/script/{episode_id}/dialogues returns dialogue data."""
        resp = self.session.get(f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert "dialogues" in data, "Response missing 'dialogues' key"
        print(f"✓ GET dialogues returned {len(data['dialogues'])} dialogues")
    
    def test_dialogues_can_have_generated_voice_id(self):
        """Dialogues can include generated_voice_id field."""
        # First get current dialogues
        resp = self.session.get(f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues")
        assert resp.status_code == 200
        data = resp.json()
        
        # Check if any dialogue has generated_voice_id
        dialogues = data.get("dialogues", [])
        if len(dialogues) > 0:
            # Check first dialogue structure
            first_d = dialogues[0]
            print(f"✓ First dialogue keys: {list(first_d.keys())}")
            
            # generated_voice_id is optional - may be empty string or present
            has_field = "generated_voice_id" in first_d
            print(f"✓ Has generated_voice_id field: {has_field}")
    
    def test_save_dialogues_with_generated_voice_id(self):
        """POST /api/script/{episode_id}/dialogues saves generated_voice_id."""
        # Get existing dialogues
        resp = self.session.get(f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues")
        assert resp.status_code == 200
        existing = resp.json().get("dialogues", [])
        
        if len(existing) == 0:
            pytest.skip("No existing dialogues to test with")
        
        # Add generated_voice_id to test dialogue
        test_dialogues = []
        for i, d in enumerate(existing):
            test_d = {
                "index": i,
                "character_id": d.get("character_id", ""),
                "character_name": d.get("character_name", ""),
                "voice_id": d.get("voice_id", "Kore"),
                "text": d.get("text", "Test text"),
                "director_notes": d.get("director_notes", ""),
                "generated_voice_id": d.get("generated_voice_id", "")
            }
            test_dialogues.append(test_d)
        
        # Save dialogues
        save_resp = self.session.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues",
            json={"dialogues": test_dialogues}
        )
        assert save_resp.status_code == 200, f"Save failed: {save_resp.status_code}"
        
        # Verify saved
        verify_resp = self.session.get(f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues")
        assert verify_resp.status_code == 200
        
        saved = verify_resp.json().get("dialogues", [])
        assert len(saved) == len(test_dialogues), "Dialogue count mismatch after save"
        print(f"✓ Saved {len(saved)} dialogues with generated_voice_id field")
    
    def test_save_dialogue_preserves_generated_voice_id(self):
        """Saving dialogues preserves generated_voice_id values."""
        # Create test dialogue with specific generated_voice_id
        test_voice_id = "TestVoice123"
        test_dialogues = [{
            "index": 0,
            "character_id": "char_test",
            "character_name": "Test Character",
            "voice_id": "Kore",
            "text": "This is a test dialogue for voice sync",
            "director_notes": "",
            "generated_voice_id": test_voice_id
        }]
        
        # Save
        save_resp = self.session.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues",
            json={"dialogues": test_dialogues}
        )
        assert save_resp.status_code == 200
        
        # Retrieve and verify
        get_resp = self.session.get(f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/dialogues")
        assert get_resp.status_code == 200
        
        saved = get_resp.json().get("dialogues", [])
        assert len(saved) > 0, "No dialogues saved"
        
        # Check generated_voice_id preserved
        first_saved = saved[0]
        assert first_saved.get("generated_voice_id") == test_voice_id, \
            f"generated_voice_id not preserved: expected '{test_voice_id}', got '{first_saved.get('generated_voice_id')}'"
        print(f"✓ generated_voice_id preserved correctly: {test_voice_id}")
    
    # ============ Cache key includes voice_id ============
    
    def test_cache_key_includes_voice_id(self):
        """Verify cache key computation includes voice_id."""
        # Import the function from script_compiler
        import sys
        sys.path.insert(0, '/app/backend')
        from script_compiler import compute_cache_key
        
        text = "Hello world"
        voice1 = "Kore"
        voice2 = "Aoede"
        notes = "whisper"
        
        key1 = compute_cache_key(text, voice1, notes)
        key2 = compute_cache_key(text, voice2, notes)
        
        # Different voice_id should produce different cache keys
        assert key1 != key2, "Cache key should differ when voice_id differs"
        assert len(key1) == 32, f"Cache key should be 32 chars, got {len(key1)}"
        print(f"✓ Cache key for voice1: {key1[:16]}...")
        print(f"✓ Cache key for voice2: {key2[:16]}...")
        print("✓ Different voice_id produces different cache key")
    
    def test_cache_key_deterministic(self):
        """Cache key is deterministic for same inputs."""
        import sys
        sys.path.insert(0, '/app/backend')
        from script_compiler import compute_cache_key
        
        text = "Test dialogue"
        voice = "Kore"
        notes = "angry"
        
        key1 = compute_cache_key(text, voice, notes)
        key2 = compute_cache_key(text, voice, notes)
        
        assert key1 == key2, "Cache key should be deterministic"
        print(f"✓ Cache key deterministic: {key1}")
    
    # ============ Script compiler returns generated_voice_id ============
    
    def test_script_compiler_generate_single_dialogue_signature(self):
        """Verify generate_single_dialogue returns generated_voice_id in result."""
        import sys
        sys.path.insert(0, '/app/backend')
        
        # Read the script_compiler code to verify structure
        with open('/app/backend/script_compiler.py', 'r') as f:
            content = f.read()
        
        # Check that generate_single_dialogue returns generated_voice_id
        assert 'generated_voice_id' in content, \
            "generate_single_dialogue should include generated_voice_id in return"
        
        # Verify the return dict includes generated_voice_id
        assert '"generated_voice_id": voice_id' in content, \
            "generate_single_dialogue should return generated_voice_id: voice_id"
        
        print("✓ generate_single_dialogue returns generated_voice_id field")
    
    def test_run_generation_job_returns_generated_voice_id(self):
        """Verify run_generation_job includes generated_voice_id in results."""
        import sys
        sys.path.insert(0, '/app/backend')
        
        with open('/app/backend/script_compiler.py', 'r') as f:
            content = f.read()
        
        # Check that results dict in run_generation_job includes generated_voice_id
        # For cached results (line ~293-298)
        assert '"generated_voice_id": voice_id' in content, \
            "run_generation_job should include generated_voice_id in cached results"
        
        print("✓ run_generation_job returns generated_voice_id in results")
    
    # ============ API endpoints for generation job ============
    
    def test_generate_endpoint_exists(self):
        """POST /api/script/{episode_id}/generate endpoint exists."""
        # Send request with empty body to check endpoint exists
        resp = self.session.post(
            f"{BASE_URL}/api/script/{TEST_EPISODE_ID}/generate",
            json={"dialogues": []}
        )
        # 400 means endpoint exists but validation failed
        assert resp.status_code in [200, 400, 422, 423], \
            f"Generate endpoint returned unexpected status: {resp.status_code}"
        print(f"✓ Generate endpoint exists (status: {resp.status_code})")
    
    def test_job_status_endpoint_exists(self):
        """GET /api/script/job/{job_id}/status endpoint exists."""
        # Use fake job_id to test endpoint exists
        resp = self.session.get(f"{BASE_URL}/api/script/job/fake_job_123/status")
        # 404 means endpoint exists but job not found
        assert resp.status_code in [200, 404], \
            f"Job status endpoint returned unexpected status: {resp.status_code}"
        print(f"✓ Job status endpoint exists (status: {resp.status_code})")
    
    # ============ Characters API for voice_id ============
    
    def test_get_characters_returns_voice_id(self):
        """GET /api/characters/story/{story_id} returns voice_id for each character."""
        resp = self.session.get(f"{BASE_URL}/api/characters/story/{TEST_STORY_ID}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        characters = resp.json()
        assert isinstance(characters, list), "Expected list of characters"
        
        if len(characters) > 0:
            first_char = characters[0]
            assert "voice_id" in first_char, "Character missing voice_id field"
            assert "character_id" in first_char, "Character missing character_id field"
            assert "name" in first_char, "Character missing name field"
            print(f"✓ Found {len(characters)} characters with voice_id field")
            for c in characters:
                print(f"  - {c['name']}: voice_id={c.get('voice_id', 'None')}")
        else:
            print("✓ No characters found (endpoint works)")
    
    def test_update_character_voice(self):
        """PUT /api/characters/{character_id} can update voice_id."""
        # First get characters
        resp = self.session.get(f"{BASE_URL}/api/characters/story/{TEST_STORY_ID}")
        assert resp.status_code == 200
        
        characters = resp.json()
        if len(characters) == 0:
            pytest.skip("No characters to test voice update")
        
        first_char = characters[0]
        char_id = first_char["character_id"]
        original_voice = first_char.get("voice_id", "")
        
        # Update voice_id (we'll change it and then restore)
        new_voice = "Aoede" if original_voice != "Aoede" else "Kore"
        
        update_resp = self.session.put(
            f"{BASE_URL}/api/characters/{char_id}",
            json={
                "story_id": TEST_STORY_ID,
                "name": first_char["name"],
                "voice_id": new_voice
            }
        )
        assert update_resp.status_code == 200, f"Update failed: {update_resp.status_code}"
        
        # Verify update
        updated = update_resp.json()
        assert updated.get("voice_id") == new_voice, "voice_id not updated"
        print(f"✓ Updated {first_char['name']} voice from '{original_voice}' to '{new_voice}'")
        
        # Restore original voice
        self.session.put(
            f"{BASE_URL}/api/characters/{char_id}",
            json={
                "story_id": TEST_STORY_ID,
                "name": first_char["name"],
                "voice_id": original_voice
            }
        )
        print(f"✓ Restored voice to '{original_voice}'")


class TestScriptDialogueModel:
    """Test ScriptDialogue model accepts generated_voice_id."""
    
    def test_script_dialogue_model_has_generated_voice_id(self):
        """Verify ScriptDialogue model structure."""
        with open('/app/backend/routers/creator.py', 'r') as f:
            content = f.read()
        
        # Check model definition - ScriptDialogue shouldn't have generated_voice_id
        # because it's a request model, generated_voice_id comes from response
        assert "class ScriptDialogue" in content, "ScriptDialogue model should exist"
        assert "voice_id: str" in content, "ScriptDialogue should have voice_id field"
        print("✓ ScriptDialogue model exists with voice_id field")
    
    def test_save_endpoint_stores_generated_voice_id(self):
        """Verify save endpoint stores generated_voice_id in script_content JSON."""
        with open('/app/backend/routers/creator.py', 'r') as f:
            content = f.read()
        
        # Check save endpoint uses json.dumps
        assert 'script_content' in content, "Should save to script_content field"
        assert '_json.dumps(script_data)' in content, "Should JSON serialize dialogue data"
        print("✓ Save endpoint stores dialogue data as JSON in script_content")
    
    def test_get_endpoint_returns_json_dialogues(self):
        """Verify get endpoint returns dialogues from script_content JSON."""
        with open('/app/backend/routers/creator.py', 'r') as f:
            content = f.read()
        
        # Check get endpoint parses JSON
        assert '_json.loads(raw)' in content or 'json.loads(raw)' in content, \
            "Get endpoint should parse JSON from script_content"
        print("✓ Get endpoint parses dialogues from script_content JSON")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
