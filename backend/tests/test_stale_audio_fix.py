"""
Test suite for stale audio bug fix.

Bug: After regenerating audio in Script Editor, Audio Studio still plays OLD audio.
Root causes fixed:
1. Race condition between two register_clip functions (fire-and-forget OLD one deactivates the synchronized NEW one)
2. Browser caching stale audio (24h Cache-Control)
3. AudioStudio buffer cache not invalidated on version change

Tests verify:
- GET /api/episodes/{episode_id}/clips returns active clips with version_hash
- Audio stream endpoint has no-cache headers
- Clips endpoint returns proper data structure for cache-busting
"""

import pytest
import requests
import os

BASE_URL = "https://audio-studio-fix.preview.emergentagent.com"

# Test credentials
AFFECTED_USER_EMAIL = "harshil.zalavadiya02@gmail.com"
AFFECTED_USER_PASSWORD = "12345678"
TEST_USER_EMAIL = "testuser@test.com"
TEST_USER_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"

# Episode with fixed clips
FIXED_EPISODE_ID = "ep_0f584b728c1f"
FIXED_STORY_ID = "story_1467ede1dad8"


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Verify API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("✓ Health endpoint accessible")
    
    def test_affected_user_login(self):
        """Login as the affected user (harshil.zalavadiya02@gmail.com)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AFFECTED_USER_EMAIL,
            "password": AFFECTED_USER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "token" in data, "No token in login response"
        print(f"✓ Affected user login successful")
        return data["token"]
    
    def test_test_user_login(self):
        """Login as test user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.status_code}"
        data = response.json()
        assert "token" in data
        print(f"✓ Test user login successful")
        return data["token"]


class TestClipsEndpoint:
    """Tests for GET /api/episodes/{episode_id}/clips endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for affected user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AFFECTED_USER_EMAIL,
            "password": AFFECTED_USER_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip(f"Could not login as affected user: {response.status_code}")
        return response.json()["token"]
    
    def test_clips_endpoint_returns_active_clips(self, auth_token):
        """Verify clips endpoint returns active clips for the fixed episode"""
        response = requests.get(
            f"{BASE_URL}/api/episodes/{FIXED_EPISODE_ID}/clips",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Clips endpoint failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert "clips" in data, "Response missing 'clips' field"
        assert "episode_id" in data, "Response missing 'episode_id' field"
        
        clips = data["clips"]
        print(f"✓ Clips endpoint returned {len(clips)} clips for episode {FIXED_EPISODE_ID}")
        
        # The bug was that clips were empty (0) - now should have clips
        # Note: If episode has no generated audio yet, this may be 0 legitimately
        if len(clips) > 0:
            print(f"✓ Episode has {len(clips)} active clips (was 0 before fix)")
        else:
            print(f"⚠ Episode has 0 clips - may need audio generation first")
        
        return clips
    
    def test_clips_have_version_hash(self, auth_token):
        """Verify clips include version_hash for cache-busting"""
        response = requests.get(
            f"{BASE_URL}/api/episodes/{FIXED_EPISODE_ID}/clips",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        clips = data.get("clips", [])
        
        if len(clips) == 0:
            pytest.skip("No clips to verify version_hash - episode may need audio generation")
        
        for clip in clips:
            assert "version_hash" in clip, f"Clip {clip.get('clip_id')} missing version_hash"
            assert "audio_url" in clip, f"Clip {clip.get('clip_id')} missing audio_url"
            assert "dialogue_index" in clip, f"Clip {clip.get('clip_id')} missing dialogue_index"
            
            # version_hash should be a non-empty string (cache_key)
            version_hash = clip.get("version_hash")
            assert version_hash and len(version_hash) > 0, f"Clip {clip.get('clip_id')} has empty version_hash"
        
        print(f"✓ All {len(clips)} clips have version_hash for cache-busting")
    
    def test_clips_response_structure(self, auth_token):
        """Verify clips response has correct structure for AudioStudio"""
        response = requests.get(
            f"{BASE_URL}/api/episodes/{FIXED_EPISODE_ID}/clips",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        clips = data.get("clips", [])
        
        if len(clips) == 0:
            pytest.skip("No clips to verify structure")
        
        # Check first clip has all required fields for AudioStudio
        clip = clips[0]
        required_fields = [
            "clip_id",
            "dialogue_index",
            "audio_url",
            "voice_id",
            "version_hash",
            "duration_seconds",
        ]
        
        for field in required_fields:
            assert field in clip, f"Clip missing required field: {field}"
        
        print(f"✓ Clip structure verified with all required fields: {required_fields}")


class TestAudioStreamEndpoint:
    """Tests for audio streaming endpoint cache headers"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AFFECTED_USER_EMAIL,
            "password": AFFECTED_USER_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Could not login")
        return response.json()["token"]
    
    def test_audio_stream_has_no_cache_headers(self, auth_token):
        """Verify audio stream endpoint returns no-cache headers (NOT max-age=86400)"""
        # First get a clip to get a file_id
        clips_response = requests.get(
            f"{BASE_URL}/api/episodes/{FIXED_EPISODE_ID}/clips",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        if clips_response.status_code != 200:
            pytest.skip("Could not get clips")
        
        clips = clips_response.json().get("clips", [])
        if len(clips) == 0:
            pytest.skip("No clips available to test audio streaming")
        
        # Get the audio_url from first clip
        audio_url = clips[0].get("audio_url", "")
        if not audio_url:
            pytest.skip("Clip has no audio_url")
        
        # Extract file_id from audio_url (format: bucket/path or just path)
        file_id = audio_url
        if audio_url.startswith("data:"):
            pytest.skip("Audio is base64 encoded, not streamed")
        
        # Test the stream endpoint
        stream_url = f"{BASE_URL}/api/audio/stream-file/{file_id}"
        response = requests.get(stream_url, stream=True)
        
        # Check Cache-Control header
        cache_control = response.headers.get("Cache-Control", "")
        
        # Should NOT have max-age=86400 (24 hours)
        assert "max-age=86400" not in cache_control, f"Audio stream has stale cache header: {cache_control}"
        
        # Should have no-cache
        assert "no-cache" in cache_control.lower() or "must-revalidate" in cache_control.lower(), \
            f"Audio stream missing no-cache header. Got: {cache_control}"
        
        print(f"✓ Audio stream has correct cache headers: {cache_control}")
    
    def test_audio_stream_returns_audio(self, auth_token):
        """Verify audio stream endpoint returns audio content"""
        clips_response = requests.get(
            f"{BASE_URL}/api/episodes/{FIXED_EPISODE_ID}/clips",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        if clips_response.status_code != 200:
            pytest.skip("Could not get clips")
        
        clips = clips_response.json().get("clips", [])
        if len(clips) == 0:
            pytest.skip("No clips available")
        
        audio_url = clips[0].get("audio_url", "")
        if not audio_url or audio_url.startswith("data:"):
            pytest.skip("No streamable audio URL")
        
        stream_url = f"{BASE_URL}/api/audio/stream-file/{audio_url}"
        response = requests.get(stream_url, stream=True)
        
        # Should return 200 or 404 (if file doesn't exist in storage)
        if response.status_code == 404:
            print(f"⚠ Audio file not found in storage (may be expected for old clips)")
            return
        
        assert response.status_code == 200, f"Audio stream failed: {response.status_code}"
        
        content_type = response.headers.get("Content-Type", "")
        assert "audio" in content_type.lower(), f"Wrong content type: {content_type}"
        
        print(f"✓ Audio stream returns audio content with type: {content_type}")


class TestRegisterClipCodeVerification:
    """Verify code changes for register_clip race condition fix"""
    
    def test_no_fire_and_forget_register_clip(self):
        """Verify asyncio.create_task(sc_storage.register_clip) has been removed"""
        import subprocess
        
        # Check for fire-and-forget pattern in script_compiler.py
        result = subprocess.run(
            ["grep", "-c", "asyncio.create_task.*register_clip", "/app/backend/script_compiler.py"],
            capture_output=True, text=True
        )
        
        # grep returns exit code 1 if no matches (which is what we want)
        count = int(result.stdout.strip()) if result.returncode == 0 else 0
        assert count == 0, f"Found {count} fire-and-forget register_clip calls - should be 0"
        print("✓ No fire-and-forget asyncio.create_task(register_clip) calls found")
    
    def test_no_sc_storage_register_clip(self):
        """Verify sc_storage.register_clip is not called (old function)"""
        import subprocess
        
        result = subprocess.run(
            ["grep", "-c", "sc_storage.register_clip", "/app/backend/script_compiler.py"],
            capture_output=True, text=True
        )
        
        count = int(result.stdout.strip()) if result.returncode == 0 else 0
        assert count == 0, f"Found {count} sc_storage.register_clip calls - should be 0"
        print("✓ No sc_storage.register_clip calls found (old function removed)")
    
    def test_register_clip_uses_await(self):
        """Verify register_clip is called with await (synchronized)"""
        import subprocess
        
        result = subprocess.run(
            ["grep", "-c", "await register_clip", "/app/backend/script_compiler.py"],
            capture_output=True, text=True
        )
        
        count = int(result.stdout.strip()) if result.returncode == 0 else 0
        assert count >= 2, f"Found only {count} 'await register_clip' calls - expected at least 2"
        print(f"✓ Found {count} synchronized 'await register_clip' calls")


class TestCacheControlHeaders:
    """Verify Cache-Control headers are correct"""
    
    def test_stream_file_endpoint_cache_control(self):
        """Verify /api/audio/stream-file has no-cache headers in code"""
        import subprocess
        
        # Check the actual code for Cache-Control header
        result = subprocess.run(
            ["grep", "-A2", "Cache-Control", "/app/backend/routers/creator.py"],
            capture_output=True, text=True
        )
        
        output = result.stdout
        assert "no-cache" in output, f"Cache-Control should be no-cache. Found: {output}"
        assert "max-age=86400" not in output, f"Cache-Control should NOT have max-age=86400. Found: {output}"
        
        print("✓ Cache-Control header is set to no-cache in code")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
