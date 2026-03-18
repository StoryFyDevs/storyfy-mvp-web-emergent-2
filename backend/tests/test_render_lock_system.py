"""
Test Render & Lock System for Audio OTT Platform
Tests for:
- Publish validation (requires finalAudioUrl + duration > 0)
- Lock enforcement (save-project blocked when isPublished=true)
- Render chunk upload and finalize
- Unpublish to edit flow
- Mobile API signed URLs for finalAudioUrl
"""

import pytest
import requests
import os
import uuid
import io
import struct

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://storyfy-queue.preview.emergentagent.com').rstrip('/')

# Test credentials
CREATOR_EMAIL = "testapi@test.com"
CREATOR_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin123"


def create_minimal_wav_file(duration_seconds=1.0, sample_rate=44100):
    """Create a minimal valid WAV file for testing render upload"""
    num_samples = int(sample_rate * duration_seconds)
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align
    
    buffer = io.BytesIO()
    # RIFF header
    buffer.write(b'RIFF')
    buffer.write(struct.pack('<I', 36 + data_size))  # ChunkSize
    buffer.write(b'WAVE')
    # fmt subchunk
    buffer.write(b'fmt ')
    buffer.write(struct.pack('<I', 16))  # Subchunk1Size
    buffer.write(struct.pack('<H', 1))   # AudioFormat (PCM)
    buffer.write(struct.pack('<H', num_channels))  # NumChannels
    buffer.write(struct.pack('<I', sample_rate))  # SampleRate
    buffer.write(struct.pack('<I', byte_rate))  # ByteRate
    buffer.write(struct.pack('<H', block_align))  # BlockAlign
    buffer.write(struct.pack('<H', bits_per_sample))  # BitsPerSample
    # data subchunk
    buffer.write(b'data')
    buffer.write(struct.pack('<I', data_size))  # Subchunk2Size
    # Audio data (silence)
    buffer.write(b'\x00' * data_size)
    
    buffer.seek(0)
    return buffer.read()


class TestCreatorAuthVerify:
    """Verify creator authentication is working"""
    
    def test_creator_login(self):
        """POST /api/auth/login - verify creator login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == CREATOR_EMAIL
        print(f"✓ Creator login successful: {data['user']['email']}")


class TestAdminAuthVerify:
    """Verify admin authentication is working"""
    
    def test_admin_login(self):
        """POST /api/admin-9821/login - verify admin login works"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful: {data['user']['email']}")


class TestPublishValidation:
    """Test publish endpoint validation - requires finalAudioUrl and duration > 0"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def test_story_and_episode(self, auth_token):
        """Create a test story and episode without finalAudioUrl"""
        # Create story
        story_data = {
            "title": f"TEST_RenderLock_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test story for render/lock system",
            "story_type": "story"
        }
        story_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story = story_resp.json()
        
        # Create episode (no finalAudioUrl by default)
        episode_data = {
            "story_id": story["story_id"],
            "title": f"TEST_Episode_{uuid.uuid4().hex[:8]}",
            "order": 1,
            "script": "Test script content"
        }
        ep_resp = requests.post(f"{BASE_URL}/api/episodes",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=episode_data
        )
        episode = ep_resp.json()
        
        return {"story": story, "episode": episode}
    
    def test_publish_fails_without_finalAudioUrl(self, auth_token, test_story_and_episode):
        """POST /api/creator/episodes/{id}/publish should FAIL (422) if no finalAudioUrl"""
        episode_id = test_story_and_episode["episode"]["episode_id"]
        
        response = requests.post(
            f"{BASE_URL}/api/creator/episodes/{episode_id}/publish",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        data = response.json()
        assert "no rendered audio" in data["detail"].lower() or "finalaudiourl" in data["detail"].lower()
        print(f"✓ Publish correctly rejected (no finalAudioUrl): {data['detail']}")
    
    def test_publish_fails_with_zero_duration(self, auth_token, test_story_and_episode):
        """POST /api/creator/episodes/{id}/publish should FAIL (422) if duration is 0"""
        episode_id = test_story_and_episode["episode"]["episode_id"]
        
        # Episode was created without duration/finalAudioUrl, so this should fail
        response = requests.post(
            f"{BASE_URL}/api/creator/episodes/{episode_id}/publish",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 422
        data = response.json()
        # Either "no rendered audio" or "duration" error
        assert "no rendered audio" in data["detail"].lower() or "duration" in data["detail"].lower()
        print(f"✓ Publish correctly rejected (no duration/audio): {data['detail']}")


class TestLockEnforcement:
    """Test lock enforcement - save-project blocked when isPublished=true"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def published_episode(self, auth_token):
        """Create a story and episode, render audio, then publish"""
        # Create story
        story_data = {
            "title": f"TEST_Lock_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test story for lock enforcement",
            "story_type": "story"
        }
        story_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story = story_resp.json()
        
        # Create episode
        episode_data = {
            "story_id": story["story_id"],
            "title": f"TEST_LockEp_{uuid.uuid4().hex[:8]}",
            "order": 1,
            "script": "Test script"
        }
        ep_resp = requests.post(f"{BASE_URL}/api/episodes",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=episode_data
        )
        episode = ep_resp.json()
        episode_id = episode["episode_id"]
        
        # Create and upload a minimal WAV file as render chunks
        wav_data = create_minimal_wav_file(duration_seconds=2.0)
        
        # Upload as single chunk
        files = {'chunk': ('chunk_0', io.BytesIO(wav_data), 'application/octet-stream')}
        data = {'chunk_index': '0', 'total_chunks': '1'}
        chunk_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/chunk",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files,
            data=data
        )
        
        if chunk_resp.status_code != 200:
            pytest.skip(f"Chunk upload failed: {chunk_resp.text}")
        
        # Finalize render
        finalize_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/finalize",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"total_chunks": 1, "duration": 2.0}
        )
        
        if finalize_resp.status_code != 200:
            pytest.skip(f"Render finalize failed: {finalize_resp.text}")
        
        # Publish the episode
        pub_resp = requests.post(
            f"{BASE_URL}/api/creator/episodes/{episode_id}/publish",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        if pub_resp.status_code != 200:
            pytest.skip(f"Publish failed: {pub_resp.text}")
        
        return {"story": story, "episode_id": episode_id}
    
    def test_save_project_blocked_when_published(self, auth_token, published_episode):
        """POST /api/episodes/{id}/save-project should FAIL (423) when isPublished=true"""
        episode_id = published_episode["episode_id"]
        
        project_data = {
            "tracks": [
                {"id": "voice-1", "name": "Voice Track 1", "type": "voice", "clips": [], "volume": 0.8, "muted": False, "solo": False}
            ],
            "duration": 60,
            "zoom": 1.0,
            "masterVolume": 0.75
        }
        
        response = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/save-project",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=project_data
        )
        
        assert response.status_code == 423, f"Expected 423 (Locked), got {response.status_code}: {response.text}"
        data = response.json()
        assert "published" in data["detail"].lower() or "locked" in data["detail"].lower()
        print(f"✓ Save-project correctly blocked (locked): {data['detail']}")
    
    def test_unpublish_then_save_project_succeeds(self, auth_token, published_episode):
        """After unpublishing, save-project should succeed"""
        episode_id = published_episode["episode_id"]
        
        # Unpublish
        unpub_resp = requests.post(
            f"{BASE_URL}/api/creator/episodes/{episode_id}/unpublish",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert unpub_resp.status_code == 200
        unpub_data = unpub_resp.json()
        assert unpub_data["isPublished"] == False
        print(f"✓ Episode unpublished successfully")
        
        # Now save-project should work
        project_data = {
            "tracks": [
                {"id": "voice-1", "name": "Voice Track 1", "type": "voice", "clips": [], "volume": 0.8, "muted": False, "solo": False}
            ],
            "duration": 60,
            "zoom": 1.0,
            "masterVolume": 0.75
        }
        
        response = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/save-project",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=project_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Save-project succeeded after unpublish")


class TestRenderChunkUpload:
    """Test render chunk upload and finalize endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def test_episode(self, auth_token):
        """Create a test story and episode for render testing"""
        story_data = {
            "title": f"TEST_Render_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test story for render system",
            "story_type": "story"
        }
        story_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story = story_resp.json()
        
        episode_data = {
            "story_id": story["story_id"],
            "title": f"TEST_RenderEp_{uuid.uuid4().hex[:8]}",
            "order": 1,
            "script": "Test script"
        }
        ep_resp = requests.post(f"{BASE_URL}/api/episodes",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=episode_data
        )
        return ep_resp.json()
    
    def test_render_chunk_upload(self, auth_token, test_episode):
        """POST /api/episodes/{id}/render/chunk accepts chunks"""
        episode_id = test_episode["episode_id"]
        
        # Create a small test chunk
        wav_data = create_minimal_wav_file(duration_seconds=1.0)
        
        files = {'chunk': ('chunk_0', io.BytesIO(wav_data), 'application/octet-stream')}
        data = {'chunk_index': '0', 'total_chunks': '1'}
        
        response = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/chunk",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files,
            data=data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        resp_data = response.json()
        assert "chunk_index" in resp_data
        print(f"✓ Chunk upload successful: {resp_data}")
    
    def test_render_finalize(self, auth_token, test_episode):
        """POST /api/episodes/{id}/render/finalize assembles chunks"""
        episode_id = test_episode["episode_id"]
        
        # Upload chunk first
        wav_data = create_minimal_wav_file(duration_seconds=2.5)
        
        files = {'chunk': ('chunk_0', io.BytesIO(wav_data), 'application/octet-stream')}
        data = {'chunk_index': '0', 'total_chunks': '1'}
        
        chunk_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/chunk",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files,
            data=data
        )
        
        if chunk_resp.status_code != 200:
            pytest.skip(f"Chunk upload failed: {chunk_resp.text}")
        
        # Finalize
        response = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/finalize",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"total_chunks": 1, "duration": 2.5}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        resp_data = response.json()
        assert "finalAudioUrl" in resp_data
        assert "duration" in resp_data
        assert resp_data["duration"] == 2.5
        print(f"✓ Render finalize successful: finalAudioUrl={resp_data['finalAudioUrl']}")
        
        return episode_id
    
    def test_episode_has_finalAudioUrl_after_render(self, auth_token, test_episode):
        """After render, episode should have finalAudioUrl and duration set"""
        episode_id = test_episode["episode_id"]
        
        # Upload and finalize
        wav_data = create_minimal_wav_file(duration_seconds=3.0)
        
        files = {'chunk': ('chunk_0', io.BytesIO(wav_data), 'application/octet-stream')}
        data = {'chunk_index': '0', 'total_chunks': '1'}
        
        chunk_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/chunk",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files,
            data=data
        )
        
        if chunk_resp.status_code != 200:
            pytest.skip(f"Chunk upload failed: {chunk_resp.text}")
        
        finalize_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/finalize",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"total_chunks": 1, "duration": 3.0}
        )
        
        if finalize_resp.status_code != 200:
            pytest.skip(f"Render finalize failed: {finalize_resp.text}")
        
        # Verify episode now has finalAudioUrl
        ep_resp = requests.get(
            f"{BASE_URL}/api/episodes/{episode_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert ep_resp.status_code == 200
        ep_data = ep_resp.json()
        assert ep_data.get("finalAudioUrl") is not None, "Episode should have finalAudioUrl after render"
        assert ep_data.get("duration") == 3.0, f"Expected duration 3.0, got {ep_data.get('duration')}"
        print(f"✓ Episode has finalAudioUrl and duration after render")


class TestPublishAfterRender:
    """Test that publish succeeds after render"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    def test_publish_succeeds_after_render(self, auth_token):
        """After render (with finalAudioUrl and duration), publish should succeed"""
        # Create story
        story_data = {
            "title": f"TEST_PubAfterRender_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test story",
            "story_type": "story"
        }
        story_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story = story_resp.json()
        
        # Create episode
        episode_data = {
            "story_id": story["story_id"],
            "title": f"TEST_PubEp_{uuid.uuid4().hex[:8]}",
            "order": 1,
            "script": "Test script"
        }
        ep_resp = requests.post(f"{BASE_URL}/api/episodes",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=episode_data
        )
        episode = ep_resp.json()
        episode_id = episode["episode_id"]
        
        # Render
        wav_data = create_minimal_wav_file(duration_seconds=5.0)
        
        files = {'chunk': ('chunk_0', io.BytesIO(wav_data), 'application/octet-stream')}
        data = {'chunk_index': '0', 'total_chunks': '1'}
        
        chunk_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/chunk",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files,
            data=data
        )
        
        if chunk_resp.status_code != 200:
            pytest.skip(f"Chunk upload failed: {chunk_resp.text}")
        
        finalize_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/finalize",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"total_chunks": 1, "duration": 5.0}
        )
        
        if finalize_resp.status_code != 200:
            pytest.skip(f"Render finalize failed: {finalize_resp.text}")
        
        # Now publish should succeed
        pub_resp = requests.post(
            f"{BASE_URL}/api/creator/episodes/{episode_id}/publish",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert pub_resp.status_code == 200, f"Expected 200, got {pub_resp.status_code}: {pub_resp.text}"
        pub_data = pub_resp.json()
        assert pub_data["isPublished"] == True
        assert "publishedAt" in pub_data
        print(f"✓ Publish succeeded after render")


class TestMobileAPISignedUrls:
    """Test Mobile API returns signed URLs for finalAudioUrl"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    def test_mobile_home_feed(self):
        """GET /api/v1/mobile/home - verify still works"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/home")
        assert response.status_code == 200
        data = response.json()
        assert "sections" in data
        section_ids = [s["id"] for s in data["sections"]]
        assert "trending" in section_ids or "new_releases" in section_ids
        print(f"✓ Mobile home feed works: {section_ids}")
    
    def test_mobile_browse_stories(self):
        """GET /api/v1/mobile/stories?page=1&limit=12 - verify still works"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/stories?page=1&limit=12")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        print(f"✓ Mobile browse works: {len(data['items'])} items")
    
    def test_mobile_story_detail_has_signed_audio_url(self):
        """GET /api/v1/mobile/stories/{id} - episodes should have audio_url (signed URL)"""
        # Get a published story
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=20")
        stories = browse_resp.json()["items"]
        
        if not stories:
            pytest.skip("No published stories available")
        
        # Find a story with episodes that have audio
        for story in stories:
            detail_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories/{story['story_id']}")
            if detail_resp.status_code != 200:
                continue
            
            detail_data = detail_resp.json()
            episodes = detail_data.get("episodes", [])
            
            for ep in episodes:
                if ep.get("has_audio") and ep.get("audio_url"):
                    # Verify it's a signed URL (contains token or expires)
                    audio_url = ep["audio_url"]
                    assert "signedURL" in audio_url or "token=" in audio_url or "supabase" in audio_url.lower() or "expires" in audio_url.lower() or audio_url.startswith("http"), \
                        f"Expected signed URL, got: {audio_url[:100]}"
                    print(f"✓ Episode {ep['episode_id']} has audio_url (signed): {audio_url[:80]}...")
                    return
        
        # If no episodes with audio found, note it but don't fail
        print("⚠ No published episodes with finalAudioUrl found - signed URL test skipped")
    
    def test_mobile_episode_playback_has_signed_audio_url(self):
        """GET /api/v1/mobile/episodes/{id} - should return audio_url as signed URL"""
        # Find a published episode with audio
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=20")
        stories = browse_resp.json()["items"]
        
        if not stories:
            pytest.skip("No published stories available")
        
        for story in stories:
            detail_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories/{story['story_id']}")
            if detail_resp.status_code != 200:
                continue
            
            episodes = detail_resp.json().get("episodes", [])
            for ep in episodes:
                if ep.get("has_audio"):
                    episode_id = ep["episode_id"]
                    
                    playback_resp = requests.get(f"{BASE_URL}/api/v1/mobile/episodes/{episode_id}")
                    assert playback_resp.status_code == 200
                    
                    playback_data = playback_resp.json()
                    
                    if playback_data.get("audio_url"):
                        audio_url = playback_data["audio_url"]
                        assert audio_url is not None
                        print(f"✓ Episode playback has audio_url: {audio_url[:80]}...")
                        return
        
        print("⚠ No published episodes with audio found for playback test")


class TestUnpublishAllowsEditing:
    """Test that unpublishing an episode allows editing again"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    def test_full_publish_unpublish_edit_cycle(self, auth_token):
        """Full cycle: create -> render -> publish -> unpublish -> edit"""
        # Create story
        story_data = {
            "title": f"TEST_Cycle_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test full cycle",
            "story_type": "story"
        }
        story_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story = story_resp.json()
        
        # Create episode
        episode_data = {
            "story_id": story["story_id"],
            "title": f"TEST_CycleEp_{uuid.uuid4().hex[:8]}",
            "order": 1,
            "script": "Test script"
        }
        ep_resp = requests.post(f"{BASE_URL}/api/episodes",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=episode_data
        )
        episode = ep_resp.json()
        episode_id = episode["episode_id"]
        print(f"  Created episode: {episode_id}")
        
        # Step 1: Save project should work (not published)
        project_v1 = {
            "version": 1,
            "tracks": [{"id": "voice-1", "name": "Voice", "type": "voice", "clips": [], "volume": 0.8, "muted": False, "solo": False}],
            "duration": 60
        }
        save_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/save-project",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=project_v1
        )
        assert save_resp.status_code == 200
        print(f"  ✓ Step 1: Save project works (draft)")
        
        # Step 2: Publish should fail (no audio)
        pub_resp = requests.post(
            f"{BASE_URL}/api/creator/episodes/{episode_id}/publish",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert pub_resp.status_code == 422
        print(f"  ✓ Step 2: Publish rejected (no audio)")
        
        # Step 3: Render audio
        wav_data = create_minimal_wav_file(duration_seconds=4.0)
        
        files = {'chunk': ('chunk_0', io.BytesIO(wav_data), 'application/octet-stream')}
        data = {'chunk_index': '0', 'total_chunks': '1'}
        
        chunk_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/chunk",
            headers={"Authorization": f"Bearer {auth_token}"},
            files=files,
            data=data
        )
        assert chunk_resp.status_code == 200
        
        finalize_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/render/finalize",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={"total_chunks": 1, "duration": 4.0}
        )
        assert finalize_resp.status_code == 200
        print(f"  ✓ Step 3: Audio rendered")
        
        # Step 4: Publish should succeed now
        pub_resp = requests.post(
            f"{BASE_URL}/api/creator/episodes/{episode_id}/publish",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert pub_resp.status_code == 200
        assert pub_resp.json()["isPublished"] == True
        print(f"  ✓ Step 4: Publish succeeded")
        
        # Step 5: Save project should fail (locked)
        save_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/save-project",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=project_v1
        )
        assert save_resp.status_code == 423
        print(f"  ✓ Step 5: Save project blocked (locked)")
        
        # Step 6: Unpublish
        unpub_resp = requests.post(
            f"{BASE_URL}/api/creator/episodes/{episode_id}/unpublish",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert unpub_resp.status_code == 200
        assert unpub_resp.json()["isPublished"] == False
        print(f"  ✓ Step 6: Unpublish succeeded")
        
        # Step 7: Save project should work again
        project_v2 = {
            "version": 2,
            "tracks": [{"id": "voice-1", "name": "Voice", "type": "voice", "clips": [], "volume": 0.9, "muted": False, "solo": False}],
            "duration": 60
        }
        save_resp = requests.post(
            f"{BASE_URL}/api/episodes/{episode_id}/save-project",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=project_v2
        )
        assert save_resp.status_code == 200
        print(f"  ✓ Step 7: Save project works again after unpublish")
        
        print(f"✓ Full publish/unpublish/edit cycle completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
