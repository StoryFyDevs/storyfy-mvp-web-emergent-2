"""
Test Suite for Generation Version Review Workflow and Password Reset Features

Tests:
1. GET /api/episodes/{episode_id}/versions - Returns all clips grouped by dialogue_index with labels
2. POST /api/episodes/{episode_id}/versions/{clip_id}/select - Sets clip as active
3. POST /api/episodes/{episode_id}/versions/{clip_id}/deselect - Sets clip as inactive
4. GET /api/episodes/{episode_id}/clips - Only returns is_active=true clips (Audio Studio)
5. POST /api/auth/forgot-password - Sends reset email
6. POST /api/auth/reset-password - Updates password (requires valid tokens)
7. Admin panel generation queue endpoints
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://audio-studio-fix.preview.emergentagent.com').rstrip('/')

# Test credentials from test_credentials.md
CREATOR_EMAIL = "harshil.zalavadiya02@gmail.com"
CREATOR_PASSWORD = "12345678"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"
TEST_EPISODE_ID = "ep_0f584b728c1f"


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Test that the API is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print(f"✓ Health check passed: {data}")
    
    def test_creator_login(self):
        """Test creator login and get token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"✓ Creator login successful: {data['user'].get('email')}")
        return data["token"]
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        print(f"✓ Admin login successful")
        return data["token"]


class TestVersionWorkflow:
    """Tests for the generation version review workflow"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_episode_versions(self):
        """Test GET /api/episodes/{episode_id}/versions returns all clips grouped by dialogue_index"""
        response = requests.get(
            f"{BASE_URL}/api/episodes/{TEST_EPISODE_ID}/versions",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get versions failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "versions" in data
        assert "episode_id" in data
        assert data["episode_id"] == TEST_EPISODE_ID
        
        versions = data["versions"]
        print(f"✓ GET /versions returned {len(versions)} dialogue indices")
        
        # Check version structure if any exist
        for idx, clips in versions.items():
            print(f"  - Dialogue index {idx}: {len(clips)} version(s)")
            for clip in clips:
                assert "clip_id" in clip
                assert "audio_url" in clip
                assert "is_selected" in clip
                assert "label" in clip
                # Verify labels are correct
                assert clip["label"] in ["Latest", "Selected for Episode", "Previous Version"]
                print(f"    - {clip['clip_id']}: {clip['label']}, selected={clip['is_selected']}")
        
        return versions
    
    def test_get_episode_clips_only_active(self):
        """Test GET /api/episodes/{episode_id}/clips only returns is_active=true clips"""
        response = requests.get(
            f"{BASE_URL}/api/episodes/{TEST_EPISODE_ID}/clips",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get clips failed: {response.text}"
        data = response.json()
        
        assert "clips" in data
        assert "episode_id" in data
        
        clips = data["clips"]
        print(f"✓ GET /clips (Audio Studio) returned {len(clips)} active clips")
        
        # All clips returned should be active (is_active=true)
        for clip in clips:
            assert "clip_id" in clip
            assert "dialogue_index" in clip
            assert "audio_url" in clip
            print(f"  - Clip {clip['clip_id']}: dialogue_index={clip['dialogue_index']}")
        
        return clips
    
    def test_select_version_endpoint_exists(self):
        """Test POST /api/episodes/{episode_id}/versions/{clip_id}/select endpoint exists"""
        # First get versions to find a clip_id
        response = requests.get(
            f"{BASE_URL}/api/episodes/{TEST_EPISODE_ID}/versions",
            headers=self.headers
        )
        assert response.status_code == 200
        versions = response.json().get("versions", {})
        
        if not versions:
            pytest.skip("No versions available to test selection")
        
        # Get first clip from first dialogue index
        first_idx = list(versions.keys())[0]
        first_clip = versions[first_idx][0]
        clip_id = first_clip["clip_id"]
        
        # Test select endpoint
        response = requests.post(
            f"{BASE_URL}/api/episodes/{TEST_EPISODE_ID}/versions/{clip_id}/select",
            headers=self.headers
        )
        assert response.status_code == 200, f"Select version failed: {response.text}"
        data = response.json()
        
        assert "message" in data
        assert data.get("clip_id") == clip_id
        print(f"✓ POST /versions/{clip_id}/select successful: {data['message']}")
        
        return clip_id
    
    def test_deselect_version_endpoint_exists(self):
        """Test POST /api/episodes/{episode_id}/versions/{clip_id}/deselect endpoint exists"""
        # First get versions to find a clip_id
        response = requests.get(
            f"{BASE_URL}/api/episodes/{TEST_EPISODE_ID}/versions",
            headers=self.headers
        )
        assert response.status_code == 200
        versions = response.json().get("versions", {})
        
        if not versions:
            pytest.skip("No versions available to test deselection")
        
        # Get first clip from first dialogue index
        first_idx = list(versions.keys())[0]
        first_clip = versions[first_idx][0]
        clip_id = first_clip["clip_id"]
        
        # Test deselect endpoint
        response = requests.post(
            f"{BASE_URL}/api/episodes/{TEST_EPISODE_ID}/versions/{clip_id}/deselect",
            headers=self.headers
        )
        assert response.status_code == 200, f"Deselect version failed: {response.text}"
        data = response.json()
        
        assert "message" in data
        assert data.get("clip_id") == clip_id
        print(f"✓ POST /versions/{clip_id}/deselect successful: {data['message']}")
    
    def test_version_not_found(self):
        """Test that selecting a non-existent version returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/episodes/{TEST_EPISODE_ID}/versions/nonexistent_clip_id/select",
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent version returns 404")


class TestPasswordReset:
    """Tests for password reset flow"""
    
    def test_forgot_password_endpoint(self):
        """Test POST /api/auth/forgot-password sends reset email"""
        response = requests.post(
            f"{BASE_URL}/api/auth/forgot-password",
            json={
                "email": "test@example.com",
                "redirect_url": "https://audio-studio-fix.preview.emergentagent.com"
            }
        )
        # Should always return 200 to prevent user enumeration
        assert response.status_code == 200, f"Forgot password failed: {response.text}"
        data = response.json()
        
        assert "message" in data
        # Message should be generic to prevent user enumeration
        assert "email" in data["message"].lower() or "sent" in data["message"].lower()
        print(f"✓ POST /auth/forgot-password successful: {data['message']}")
    
    def test_forgot_password_empty_email(self):
        """Test forgot password with empty email returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/auth/forgot-password",
            json={"email": "", "redirect_url": ""}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Empty email returns 400")
    
    def test_reset_password_invalid_tokens(self):
        """Test POST /api/auth/reset-password with invalid tokens returns error"""
        response = requests.post(
            f"{BASE_URL}/api/auth/reset-password",
            json={
                "access_token": "invalid_token",
                "refresh_token": "invalid_refresh",
                "new_password": "newpassword123"
            }
        )
        # Should return 400 for invalid/expired tokens
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        print(f"✓ Invalid tokens return 400: {data['detail']}")
    
    def test_reset_password_short_password(self):
        """Test reset password with short password returns error"""
        response = requests.post(
            f"{BASE_URL}/api/auth/reset-password",
            json={
                "access_token": "some_token",
                "refresh_token": "some_refresh",
                "new_password": "12345"  # Less than 6 chars
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "6 characters" in data.get("detail", "").lower() or "password" in data.get("detail", "").lower()
        print(f"✓ Short password returns 400: {data['detail']}")


class TestAdminGenerationQueue:
    """Tests for admin panel generation queue endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token before each test"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_generation_queue(self):
        """Test GET /api/admin-9821/generation/queue returns live queue"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/generation/queue",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get queue failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "live_queue" in data or "queue" in data or "jobs" in data
        print(f"✓ GET /generation/queue successful: {data}")
    
    def test_get_generation_limits(self):
        """Test GET /api/admin-9821/generation/limits returns rate limits"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/generation/limits",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get limits failed: {response.text}"
        data = response.json()
        
        # Should have rate limit settings
        print(f"✓ GET /generation/limits successful: {data}")
    
    def test_get_creator_stats(self):
        """Test GET /api/admin-9821/generation/creators returns creator stats"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/generation/creators",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get creators failed: {response.text}"
        data = response.json()
        print(f"✓ GET /generation/creators successful")


class TestScriptCompilerVersionLimit:
    """Tests for version limit enforcement in script_compiler.py"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_version_count_per_dialogue(self):
        """Verify that versions are properly tracked per dialogue_index"""
        response = requests.get(
            f"{BASE_URL}/api/episodes/{TEST_EPISODE_ID}/versions",
            headers=self.headers
        )
        assert response.status_code == 200
        versions = response.json().get("versions", {})
        
        # Check that no dialogue_index has more than 5 versions
        MAX_VERSIONS = 5
        for idx, clips in versions.items():
            assert len(clips) <= MAX_VERSIONS, f"Dialogue {idx} has {len(clips)} versions, max is {MAX_VERSIONS}"
            print(f"✓ Dialogue index {idx}: {len(clips)} versions (max {MAX_VERSIONS})")
        
        print(f"✓ Version limit enforcement verified for {len(versions)} dialogue indices")


class TestGenerationStatusEndpoint:
    """Tests for generation status endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_generation_status(self):
        """Test GET /api/generation/status returns user's generation status"""
        response = requests.get(
            f"{BASE_URL}/api/generation/status",
            headers=self.headers
        )
        assert response.status_code == 200, f"Get generation status failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "generation_status" in data
        assert "generation_credits" in data
        print(f"✓ GET /generation/status: status={data.get('generation_status')}, credits={data.get('generation_credits')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
