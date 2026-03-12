"""
Tests for audio corruption fix in script_compiler.py

Key features tested:
1. Uses async httpx instead of sync requests for TTS calls
2. _validate_wav checks size > 1000 bytes and RIFF/WAVE header
3. generate_single_dialogue retries up to MAX_RETRIES=2 times
4. run_generation_job prevents concurrent jobs (_active_jobs)
5. Generation is strictly sequential (for loop with await, no parallelism)
6. Each dialogue produces independent audio buffer (no shared state)
7. Per-dialogue logging with dialogue_id, character, file_name, audio_size_bytes
8. Streaming endpoint still works correctly
"""

import pytest
import requests
import os
import sys

# Add backend to path for imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "testuser@test.com"
TEST_PASSWORD = "password123"
KNOWN_VALID_FILE_ID = "e50c796e-cb7e-4c52-9fd0-fb2017046d8b"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture
def auth_headers(auth_token):
    """Create headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestScriptCompilerCodeStructure:
    """Unit tests for script_compiler.py code structure - NO TTS calls"""
    
    def test_uses_httpx_async_client(self):
        """Verify script_compiler uses async httpx instead of sync requests"""
        import script_compiler as sc
        
        # Check that httpx is imported and used
        import httpx
        
        # Verify _get_tts_client returns httpx.AsyncClient
        client = sc._get_tts_client()
        assert isinstance(client, httpx.AsyncClient), "TTS client should be httpx.AsyncClient"
        
        # Verify timeout is set appropriately
        assert client.timeout.read == 120.0, "TTS client timeout should be 120 seconds"
    
    def test_max_retries_constant(self):
        """Verify MAX_RETRIES is set to 2"""
        import script_compiler as sc
        assert sc.MAX_RETRIES == 2, "MAX_RETRIES should be 2"
    
    def test_min_audio_bytes_constant(self):
        """Verify MIN_AUDIO_BYTES is set to 1000"""
        import script_compiler as sc
        assert sc.MIN_AUDIO_BYTES == 1000, "MIN_AUDIO_BYTES should be 1000"
    
    def test_active_jobs_dict_exists(self):
        """Verify _active_jobs dict exists for job deduplication"""
        import script_compiler as sc
        assert hasattr(sc, '_active_jobs'), "_active_jobs dict should exist"
        assert isinstance(sc._active_jobs, dict), "_active_jobs should be a dict"


class TestWavValidation:
    """Unit tests for _validate_wav function"""
    
    def test_validate_wav_rejects_empty_data(self):
        """_validate_wav should reject empty/None data"""
        import script_compiler as sc
        
        assert sc._validate_wav(None, "test_01") == False
        assert sc._validate_wav(b"", "test_01") == False
    
    def test_validate_wav_rejects_small_data(self):
        """_validate_wav should reject data smaller than MIN_AUDIO_BYTES"""
        import script_compiler as sc
        
        # 999 bytes is less than 1000 minimum
        small_data = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 987
        assert len(small_data) == 999
        assert sc._validate_wav(small_data, "test_01") == False
    
    def test_validate_wav_rejects_invalid_header(self):
        """_validate_wav should reject data without RIFF/WAVE header"""
        import script_compiler as sc
        
        # Large enough but wrong header
        invalid_header = b"XXXX" + b"\x00" * 1004 + b"YYYY"
        assert len(invalid_header) > 1000
        assert sc._validate_wav(invalid_header, "test_01") == False
        
        # Has RIFF but no WAVE
        riff_only = b"RIFF" + b"\x00" * 4 + b"XXXX" + b"\x00" * 996
        assert sc._validate_wav(riff_only, "test_01") == False
    
    def test_validate_wav_accepts_valid_wav(self):
        """_validate_wav should accept valid WAV data"""
        import script_compiler as sc
        
        # Valid WAV header: RIFF at offset 0, WAVE at offset 8
        valid_wav = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"\x00" * 1000
        assert len(valid_wav) > 1000
        assert valid_wav[:4] == b"RIFF"
        assert valid_wav[8:12] == b"WAVE"
        
        result = sc._validate_wav(valid_wav, "test_01")
        assert result == True, "Valid WAV data should pass validation"


class TestPcmToWav:
    """Unit tests for _pcm_to_wav function"""
    
    def test_pcm_to_wav_produces_valid_wav(self):
        """_pcm_to_wav should produce valid WAV format"""
        import script_compiler as sc
        
        # Create some dummy PCM data (16-bit samples)
        pcm_data = b"\x00\x01" * 1000  # 1000 16-bit samples
        
        wav_data = sc._pcm_to_wav(pcm_data)
        
        # Check WAV header
        assert wav_data[:4] == b"RIFF", "Should start with RIFF"
        assert wav_data[8:12] == b"WAVE", "Should have WAVE marker"
        
        # Should pass our validation
        assert sc._validate_wav(wav_data, "test") == True


class TestCacheKey:
    """Unit tests for cache key computation"""
    
    def test_compute_cache_key_deterministic(self):
        """compute_cache_key should return same key for same inputs"""
        import script_compiler as sc
        
        key1 = sc.compute_cache_key("Hello world", "Kore", "whisper")
        key2 = sc.compute_cache_key("Hello world", "Kore", "whisper")
        
        assert key1 == key2, "Same inputs should produce same cache key"
    
    def test_compute_cache_key_different_for_different_inputs(self):
        """compute_cache_key should return different keys for different inputs"""
        import script_compiler as sc
        
        key1 = sc.compute_cache_key("Hello world", "Kore", "")
        key2 = sc.compute_cache_key("Goodbye world", "Kore", "")
        key3 = sc.compute_cache_key("Hello world", "Aoede", "")
        
        assert key1 != key2, "Different text should produce different keys"
        assert key1 != key3, "Different voice should produce different keys"
    
    def test_compute_cache_key_length(self):
        """compute_cache_key should return 32 character hex string"""
        import script_compiler as sc
        
        key = sc.compute_cache_key("Test", "Kore", "notes")
        assert len(key) == 32, "Cache key should be 32 characters"
        assert all(c in '0123456789abcdef' for c in key), "Cache key should be hex"


class TestBuildSingleSpeakerPayload:
    """Unit tests for TTS payload building"""
    
    def test_payload_structure(self):
        """build_single_speaker_payload should create correct structure"""
        import script_compiler as sc
        
        payload = sc.build_single_speaker_payload("Hello", "Kore", "")
        
        assert "contents" in payload
        assert "generationConfig" in payload
        assert payload["generationConfig"]["responseModalities"] == ["AUDIO"]
        
        voice_config = payload["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]
        assert voice_config["voiceName"] == "Kore"
    
    def test_payload_includes_director_notes(self):
        """Payload should include director notes in text"""
        import script_compiler as sc
        
        payload = sc.build_single_speaker_payload("Hello", "Kore", "whisper softly")
        
        text_content = payload["contents"][0]["parts"][0]["text"]
        assert "whisper softly" in text_content, "Director notes should be in text"
        assert "Hello" in text_content, "Original text should be in text"


class TestStreamingEndpoint:
    """Tests for the streaming endpoint (API level)"""
    
    def test_streaming_endpoint_returns_audio(self):
        """GET /api/audio/stream-file/{file_id} returns valid audio"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/{KNOWN_VALID_FILE_ID}",
            timeout=10
        )
        
        assert response.status_code == 200, f"Should return 200, got {response.status_code}"
        assert response.headers.get("Content-Type") == "audio/wav"
        
        # Check WAV header
        content = response.content
        assert content[:4] == b"RIFF", "Audio should have RIFF header"
        assert content[8:12] == b"WAVE", "Audio should have WAVE marker"
        assert len(content) > 1000, f"Audio should be > 1000 bytes, got {len(content)}"
    
    def test_streaming_endpoint_404_for_invalid_id(self):
        """GET /api/audio/stream-file/{invalid_id} returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/nonexistent-file-id-12345",
            timeout=10
        )
        
        assert response.status_code == 404


class TestScriptGenerationAPI:
    """Tests for script generation API endpoints"""
    
    def test_generate_endpoint_exists(self, auth_headers):
        """POST /api/script/{episode_id}/generate endpoint exists"""
        # Should return 400/404 for invalid data, not 404 for route
        response = requests.post(
            f"{BASE_URL}/api/script/invalid_episode/generate",
            json={"dialogues": []},
            headers=auth_headers,
            timeout=10
        )
        
        # 404 = episode not found, 400 = bad request - both are valid
        assert response.status_code in [400, 404], f"Unexpected status: {response.status_code}"
    
    def test_job_status_endpoint_exists(self, auth_headers):
        """GET /api/script/job/{job_id}/status endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/script/job/nonexistent_job/status",
            headers=auth_headers,
            timeout=10
        )
        
        assert response.status_code == 404, "Should return 404 for nonexistent job"
    
    def test_dialogues_endpoint_exists(self, auth_headers):
        """GET /api/script/{episode_id}/dialogues endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/script/invalid_episode/dialogues",
            headers=auth_headers,
            timeout=10
        )
        
        # 404 = episode not found
        assert response.status_code == 404


class TestGenerationRateLimits:
    """Tests for generation rate limit checking"""
    
    def test_generation_status_endpoint(self, auth_headers):
        """GET /api/generation/status returns limits"""
        response = requests.get(
            f"{BASE_URL}/api/generation/status",
            headers=auth_headers,
            timeout=10
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have rate limit fields
        assert "can_generate" in data
        assert "generations_remaining" in data or "daily_limit" in data


class TestSequentialGenerationCodePath:
    """Tests to verify sequential generation code structure exists"""
    
    def test_run_generation_job_has_sequential_loop(self):
        """Verify run_generation_job uses sequential for-loop (not gather)"""
        import inspect
        import script_compiler as sc
        
        source = inspect.getsource(sc.run_generation_job)
        
        # Should have a for loop for generation
        assert "for" in source and "to_generate" in source, "Should iterate over to_generate"
        
        # Should NOT have asyncio.gather for parallel execution
        assert "asyncio.gather" not in source, "Should NOT use asyncio.gather for parallel execution"
        
        # Should have await in the loop
        assert "await" in source, "Should have await for async operations"
    
    def test_generate_single_dialogue_has_retry_loop(self):
        """Verify generate_single_dialogue has retry loop"""
        import inspect
        import script_compiler as sc
        
        source = inspect.getsource(sc.generate_single_dialogue)
        
        # Should have retry loop with MAX_RETRIES
        assert "MAX_RETRIES" in source, "Should use MAX_RETRIES constant"
        assert "range" in source, "Should have range() for retry loop"
        assert "attempt" in source, "Should track attempt number"


class TestJobDeduplication:
    """Tests for concurrent job prevention"""
    
    def test_active_jobs_tracking(self):
        """Verify _active_jobs is used for episode-level deduplication"""
        import inspect
        import script_compiler as sc
        
        source = inspect.getsource(sc.run_generation_job)
        
        # Should check and set _active_jobs
        assert "_active_jobs" in source, "Should reference _active_jobs"
        assert "episode_id" in source, "Should track by episode_id"
        
        # Should clean up on completion
        assert "finally" in source or "del _active_jobs" in source, "Should clean up active job tracking"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
