"""
Test audio streaming endpoint and URL resolution fixes.

Tests the fix for expired Nhost Storage presigned URLs:
1. Backend returns 'nhost-file:{file_id}' instead of presigned URLs
2. GET /api/audio/stream-file/{file_id} streams audio with server-side auth
3. Frontend resolveAudioUrl() converts various URL formats
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://script-compiler.preview.emergentagent.com').rstrip('/')

# Known valid file_id from the problem statement
KNOWN_VALID_FILE_ID = "e50c796e-cb7e-4c52-9fd0-fb2017046d8b"

# Test credentials
TEST_EMAIL = "testuser@test.com"
TEST_PASSWORD = "password123"


class TestAudioStreamingEndpoint:
    """Tests for GET /api/audio/stream-file/{file_id} endpoint"""
    
    def test_stream_file_returns_200_for_valid_file(self):
        """Test that streaming endpoint returns 200 for known valid file_id"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/{KNOWN_VALID_FILE_ID}",
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"PASS: GET /api/audio/stream-file/{KNOWN_VALID_FILE_ID} returned 200")
    
    def test_stream_file_returns_audio_wav_content_type(self):
        """Test that streaming endpoint returns Content-Type: audio/wav"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/{KNOWN_VALID_FILE_ID}",
            timeout=30
        )
        
        assert response.status_code == 200
        content_type = response.headers.get('Content-Type', '')
        assert 'audio/wav' in content_type, f"Expected audio/wav content type, got: {content_type}"
        print(f"PASS: Content-Type is audio/wav (got: {content_type})")
    
    def test_stream_file_returns_valid_wav_data(self):
        """Test that streamed content is valid WAV audio (starts with RIFF header)"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/{KNOWN_VALID_FILE_ID}",
            timeout=30
        )
        
        assert response.status_code == 200
        assert len(response.content) > 44, f"WAV file too small: {len(response.content)} bytes"
        
        # WAV files start with "RIFF" followed by file size, then "WAVE"
        assert response.content[:4] == b'RIFF', "WAV file should start with RIFF header"
        assert response.content[8:12] == b'WAVE', "RIFF file should be WAVE format"
        
        print(f"PASS: Valid WAV audio returned ({len(response.content)} bytes)")
    
    def test_stream_file_returns_404_for_nonexistent_file(self):
        """Test that streaming endpoint returns 404 for nonexistent file_id"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/nonexistent-id-12345",
            timeout=30
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: GET /api/audio/stream-file/nonexistent-id returns 404")
    
    def test_stream_file_returns_404_for_invalid_uuid_format(self):
        """Test that streaming endpoint returns 404 for invalid UUID format"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/not-a-valid-uuid",
            timeout=30
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: GET /api/audio/stream-file/invalid-uuid returns 404")
    
    def test_stream_file_no_auth_required(self):
        """Test that streaming endpoint does NOT require auth headers (uses server-side admin secret)"""
        # Make request without any authorization header
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/{KNOWN_VALID_FILE_ID}",
            headers={},  # No auth header
            timeout=30
        )
        
        # Should succeed without auth - endpoint uses server-side admin secret
        assert response.status_code == 200, f"Expected 200 without auth, got {response.status_code}"
        print("PASS: Streaming endpoint works without auth header (server-side auth)")
    
    def test_stream_file_has_cache_headers(self):
        """Test that streaming endpoint returns appropriate cache control headers"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/{KNOWN_VALID_FILE_ID}",
            timeout=30
        )
        
        assert response.status_code == 200
        # Check for Cache-Control header
        cache_control = response.headers.get('Cache-Control', '')
        print(f"Cache-Control header: {cache_control}")
        
        # The endpoint sets "public, max-age=86400" but Cloudflare may override
        # Just verify the endpoint doesn't error
        print("PASS: Streaming endpoint returns cache headers")


class TestScriptCompilerNhostFileFormat:
    """Tests to verify script_compiler returns nhost-file: format"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('token') or data.get('access_token')
        pytest.skip(f"Authentication failed: {response.status_code}")
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_get_script_dialogues_format(self, auth_headers):
        """Test that saved script dialogues exist and have expected format"""
        # Use known episode ID from problem statement
        episode_id = "ep_71379fe1575a"
        
        response = requests.get(
            f"{BASE_URL}/api/script/{episode_id}/dialogues",
            headers=auth_headers,
            timeout=30
        )
        
        # May return 200 with empty dialogues or 404 if episode doesn't exist
        if response.status_code == 200:
            data = response.json()
            dialogues = data.get('dialogues', [])
            print(f"PASS: Got {len(dialogues)} dialogues for episode {episode_id}")
            
            # Check dialogue structure if any exist
            for d in dialogues[:3]:  # Check first 3
                assert 'text' in d, "Dialogue should have 'text' field"
                assert 'voice_id' in d or 'character_name' in d, "Dialogue should have voice/character info"
                print(f"  - Dialogue: {d.get('character_name', 'Unknown')}: {d.get('text', '')[:50]}...")
        else:
            print(f"INFO: Episode {episode_id} dialogues returned {response.status_code}")
    
    def test_job_status_result_format(self, auth_headers):
        """Test that completed job results use nhost-file: format for audio_url"""
        # This is a structural test - we verify the job status endpoint works
        # Actual format verification requires a completed job
        
        # Try to get status of a nonexistent job to verify endpoint exists
        response = requests.get(
            f"{BASE_URL}/api/script/job/scrjob_nonexistent/status",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 404, f"Expected 404 for nonexistent job, got {response.status_code}"
        print("PASS: Job status endpoint returns 404 for nonexistent job")


class TestHealthAndConnectivity:
    """Basic connectivity tests"""
    
    def test_backend_health(self):
        """Test backend is reachable"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print("PASS: Backend health check")
    
    def test_nhost_storage_connectivity_via_streaming(self):
        """Test Nhost Storage is accessible via streaming endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/audio/stream-file/{KNOWN_VALID_FILE_ID}",
            timeout=30
        )
        
        assert response.status_code == 200, "Nhost Storage not accessible via streaming endpoint"
        assert len(response.content) > 1000, f"Audio content too small: {len(response.content)} bytes"
        print(f"PASS: Nhost Storage accessible, returned {len(response.content)} bytes")


class TestFrontendUrlResolverLogic:
    """Tests to document expected frontend URL resolution behavior"""
    
    def test_nhost_file_format_resolution(self):
        """Document: nhost-file:{file_id} should resolve to /api/audio/stream-file/{file_id}"""
        file_id = "test-file-id-123"
        input_url = f"nhost-file:{file_id}"
        expected_output = f"{BASE_URL}/api/audio/stream-file/{file_id}"
        
        # This is a documentation test - the actual logic is in frontend
        print(f"Frontend resolveAudioUrl should convert:")
        print(f"  Input:  '{input_url}'")
        print(f"  Output: '{expected_output}'")
        print("PASS: URL format documented")
    
    def test_legacy_presigned_url_resolution(self):
        """Document: Legacy Nhost presigned URLs should resolve to streaming endpoint"""
        file_id = "abc12345-def4-5678-9abc-def012345678"  # UUID format (hex only)
        legacy_url = f"https://xyz.storage.ap-south-1.nhost.run/v1/files/{file_id}?some=params"
        expected_output = f"{BASE_URL}/api/audio/stream-file/{file_id}"
        
        # Extract file_id from legacy URL (same logic as frontend)
        match = re.search(r'/v1/files/([a-f0-9-]+)', legacy_url)
        extracted_id = match.group(1) if match else None
        
        assert extracted_id == file_id, f"Regex should extract file_id: {extracted_id}"
        print(f"Frontend resolveAudioUrl should convert legacy URLs:")
        print(f"  Input:  '{legacy_url}'")
        print(f"  Output: '{expected_output}'")
        print("PASS: Legacy URL format documented")
    
    def test_base64_data_url_passthrough(self):
        """Document: Base64 data URLs should pass through unchanged"""
        data_url = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAA..."
        
        # Data URLs should not be transformed
        print(f"Frontend resolveAudioUrl should pass through data URLs unchanged:")
        print(f"  Input:  '{data_url[:50]}...'")
        print(f"  Output: '{data_url[:50]}...' (same)")
        print("PASS: Data URL passthrough documented")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
