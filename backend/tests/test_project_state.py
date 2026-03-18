"""
Test cases for Audio Studio project state save/load functionality.
Tests the bug fixes for:
1. Audio clips not persisting after page reload
2. Multiple clips being replaced instead of all being added
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://storyfy-queue.preview.emergentagent.com')

# Test credentials
TEST_EMAIL = "testapi@test.com"
TEST_PASSWORD = "password123"
TEST_STORY_ID = "story_2ea34eb172ac"  # Known story ID from the problem statement


class TestAuth:
    """Authentication tests"""
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        print(f"Login successful, user_id: {data['user']['user_id']}")
        return data["token"]


class TestProjectStateSaveLoad:
    """Tests for project state save and load - the main bug fixes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_get_stories(self):
        """Verify we can get stories list"""
        response = requests.get(
            f"{BASE_URL}/api/stories",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get stories failed: {response.text}"
        stories = response.json()
        print(f"Found {len(stories)} stories")
        
        # Check if test story exists
        test_story = next((s for s in stories if s['story_id'] == TEST_STORY_ID), None)
        if test_story:
            print(f"Found test story: {test_story['title']}")
        return stories
    
    def test_get_episodes_for_story(self):
        """Get episodes for the test story"""
        response = requests.get(
            f"{BASE_URL}/api/episodes/story/{TEST_STORY_ID}",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get episodes failed: {response.text}"
        episodes = response.json()
        print(f"Found {len(episodes)} episodes for story {TEST_STORY_ID}")
        return episodes
    
    def test_save_project_state_with_clips(self):
        """Test saving project state with audio clips - BUG FIX TEST #1"""
        # First get an episode
        response = requests.get(
            f"{BASE_URL}/api/episodes/story/{TEST_STORY_ID}",
            headers=self.headers
        )
        assert response.status_code == 200
        episodes = response.json()
        
        if not episodes:
            pytest.skip("No episodes found for test story")
        
        episode_id = episodes[0]["episode_id"]
        print(f"Using episode: {episode_id}")
        
        # Create test project state with clips
        test_project_state = {
            "tracks": [
                {
                    "id": "voice-1",
                    "name": "Voice Track 1",
                    "type": "voice",
                    "volume": 0.8,
                    "muted": False,
                    "solo": False,
                    "clips": [
                        {
                            "id": "test-clip-1",
                            "name": "Test Voice Clip 1",
                            "url": "data:audio/mpeg;base64,TEST_BASE64_DATA",
                            "start": 0,
                            "duration": 5,
                            "originalDuration": 5,
                            "color": "#00F0FF",
                            "characterName": "Alice",
                            "text": "Test audio clip 1",
                            "type": "voice"
                        },
                        {
                            "id": "test-clip-2",
                            "name": "Test Voice Clip 2",
                            "url": "data:audio/mpeg;base64,TEST_BASE64_DATA_2",
                            "start": 5,
                            "duration": 3,
                            "originalDuration": 3,
                            "color": "#00F0FF",
                            "characterName": "Alice",
                            "text": "Test audio clip 2",
                            "type": "voice"
                        }
                    ]
                },
                {
                    "id": "music-1",
                    "name": "Background Music",
                    "type": "music",
                    "volume": 0.5,
                    "muted": False,
                    "solo": False,
                    "clips": []
                },
                {
                    "id": "sfx-1",
                    "name": "Sound Effects",
                    "type": "sfx",
                    "volume": 0.7,
                    "muted": False,
                    "solo": False,
                    "clips": []
                }
            ],
            "duration": 60,
            "zoom": 1,
            "masterVolume": 0.75,
            "currentTime": 0,
            "savedAt": "2024-01-15T12:00:00.000Z"
        }
        
        # Save project state
        save_response = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/save-project",
            headers=self.headers,
            json=test_project_state
        )
        
        assert save_response.status_code == 200, f"Save project failed: {save_response.text}"
        save_data = save_response.json()
        assert "message" in save_data
        print(f"Project saved successfully: {save_data}")
        
        return episode_id, test_project_state
    
    def test_load_project_state_with_clips(self):
        """Test loading project state verifies clips persist - BUG FIX TEST #1 (load)"""
        # First save a project with clips
        episode_id, saved_state = self.test_save_project_state_with_clips()
        
        # Now load the project state
        load_response = requests.get(
            f"{BASE_URL}/api/episodes/{episode_id}/project-state",
            headers=self.headers
        )
        
        assert load_response.status_code == 200, f"Load project failed: {load_response.text}"
        loaded_state = load_response.json()
        
        # Verify clips are persisted
        assert "tracks" in loaded_state, "No tracks in loaded state"
        
        voice_track = next((t for t in loaded_state["tracks"] if t["id"] == "voice-1"), None)
        assert voice_track is not None, "Voice track not found in loaded state"
        
        clips = voice_track.get("clips", [])
        assert len(clips) >= 2, f"Expected 2 clips, found {len(clips)}"
        
        # Verify clip data is preserved
        clip1 = next((c for c in clips if c["id"] == "test-clip-1"), None)
        assert clip1 is not None, "Test clip 1 not found"
        assert clip1["url"] is not None, "Clip URL not persisted"
        assert clip1["name"] == "Test Voice Clip 1", "Clip name not persisted"
        
        clip2 = next((c for c in clips if c["id"] == "test-clip-2"), None)
        assert clip2 is not None, "Test clip 2 not found"
        
        print(f"Successfully loaded project with {len(clips)} clips persisted")
        print(f"Clip 1: {clip1['name']}, URL length: {len(clip1.get('url', ''))}")
        print(f"Clip 2: {clip2['name']}, URL length: {len(clip2.get('url', ''))}")
        
        return loaded_state
    
    def test_save_multiple_clips_sequentially(self):
        """Test that saving multiple clips preserves ALL clips - BUG FIX TEST #2"""
        # Get an episode
        response = requests.get(
            f"{BASE_URL}/api/episodes/story/{TEST_STORY_ID}",
            headers=self.headers
        )
        episodes = response.json()
        
        if not episodes:
            pytest.skip("No episodes found")
        
        episode_id = episodes[0]["episode_id"]
        
        # First save with 2 clips
        state_with_2_clips = {
            "tracks": [
                {
                    "id": "voice-1",
                    "name": "Voice Track 1",
                    "type": "voice",
                    "volume": 0.8,
                    "muted": False,
                    "solo": False,
                    "clips": [
                        {
                            "id": "multi-clip-1",
                            "name": "First Clip",
                            "url": "data:audio/mpeg;base64,FIRST_CLIP_DATA",
                            "start": 0,
                            "duration": 5,
                            "type": "voice"
                        },
                        {
                            "id": "multi-clip-2",
                            "name": "Second Clip",
                            "url": "data:audio/mpeg;base64,SECOND_CLIP_DATA",
                            "start": 5,
                            "duration": 5,
                            "type": "voice"
                        }
                    ]
                }
            ],
            "duration": 60
        }
        
        save_response = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/save-project",
            headers=self.headers,
            json=state_with_2_clips
        )
        assert save_response.status_code == 200
        
        # Load and verify both clips exist
        load_response = requests.get(
            f"{BASE_URL}/api/episodes/{episode_id}/project-state",
            headers=self.headers
        )
        assert load_response.status_code == 200
        loaded = load_response.json()
        
        voice_track = loaded["tracks"][0]
        clips = voice_track.get("clips", [])
        
        assert len(clips) == 2, f"Expected 2 clips, got {len(clips)} - multiple clips being replaced!"
        
        # Verify both clips are present, not replaced
        clip_ids = [c["id"] for c in clips]
        assert "multi-clip-1" in clip_ids, "First clip was replaced/lost"
        assert "multi-clip-2" in clip_ids, "Second clip was replaced/lost"
        
        print(f"SUCCESS: Both clips persisted correctly - {clip_ids}")
        return True


class TestCharacters:
    """Test character endpoints for voice generation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_characters_for_story(self):
        """Get characters for the test story - needed for voice generation"""
        response = requests.get(
            f"{BASE_URL}/api/characters/story/{TEST_STORY_ID}",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get characters failed: {response.text}"
        characters = response.json()
        print(f"Found {len(characters)} characters")
        
        # Check if Alice character exists
        alice = next((c for c in characters if c['name'] == 'Alice'), None)
        if alice:
            print(f"Found Alice character: {alice['character_id']}, voice_id: {alice.get('voice_id')}")
        
        return characters


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
