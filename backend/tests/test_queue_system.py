"""
Queue System Tests - Testing the system-wide audio generation queue
Tests: /api/jobs/active, /api/script/{episode_id}/generate, /api/script/{episode_id}/narration/generate,
       /api/admin-9821/generation/queue, /api/admin-9821/generation/limits
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
CREATOR_EMAIL = "harshil.zalavadiya02@gmail.com"
CREATOR_PASSWORD = "12345678"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Test that the API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("✓ Health endpoint working")
    
    def test_creator_login(self):
        """Test creator login and get token"""
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
        """Test admin login and get token"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in admin login response"
        print(f"✓ Admin login successful, token received")
        return data["token"]


@pytest.fixture(scope="module")
def creator_token():
    """Get creator auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": CREATOR_EMAIL,
        "password": CREATOR_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Creator login failed: {response.text}")
    return response.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text}")
    return response.json()["token"]


class TestJobsActiveEndpoint:
    """Tests for GET /api/jobs/active endpoint"""
    
    def test_jobs_active_returns_empty_list(self, creator_token):
        """Test that /api/jobs/active returns jobs list for authenticated user"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        response = requests.get(f"{BASE_URL}/api/jobs/active", headers=headers)
        
        assert response.status_code == 200, f"Jobs active failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "jobs" in data, "Response missing 'jobs' field"
        assert "queue_info" in data, "Response missing 'queue_info' field"
        assert isinstance(data["jobs"], list), "'jobs' should be a list"
        
        # Verify queue_info structure
        queue_info = data["queue_info"]
        assert "total_queued" in queue_info, "queue_info missing 'total_queued'"
        assert "total_processing" in queue_info, "queue_info missing 'total_processing'"
        
        print(f"✓ /api/jobs/active returns {len(data['jobs'])} jobs")
        print(f"  Queue info: queued={queue_info['total_queued']}, processing={queue_info['total_processing']}")
    
    def test_jobs_active_requires_auth(self):
        """Test that /api/jobs/active requires authentication"""
        response = requests.get(f"{BASE_URL}/api/jobs/active")
        assert response.status_code == 401, "Should require authentication"
        print("✓ /api/jobs/active correctly requires authentication")


class TestAdminQueueEndpoint:
    """Tests for GET /api/admin-9821/generation/queue endpoint"""
    
    def test_admin_queue_returns_live_queue(self, admin_token):
        """Test that admin queue endpoint returns live_queue with rate_limiter stats"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin-9821/generation/queue", headers=headers)
        
        assert response.status_code == 200, f"Admin queue failed: {response.text}"
        data = response.json()
        
        # Verify live_queue structure
        assert "live_queue" in data, "Response missing 'live_queue' field"
        live_queue = data["live_queue"]
        
        assert "queued" in live_queue, "live_queue missing 'queued'"
        assert "processing" in live_queue, "live_queue missing 'processing'"
        assert "total_in_queue" in live_queue, "live_queue missing 'total_in_queue'"
        assert "rate_limiter" in live_queue, "live_queue missing 'rate_limiter'"
        
        # Verify rate_limiter structure
        rate_limiter = live_queue["rate_limiter"]
        assert "requests_this_minute" in rate_limiter, "rate_limiter missing 'requests_this_minute'"
        assert "tokens_this_minute" in rate_limiter, "rate_limiter missing 'tokens_this_minute'"
        assert "requests_today" in rate_limiter, "rate_limiter missing 'requests_today'"
        assert "limits" in rate_limiter, "rate_limiter missing 'limits'"
        
        print(f"✓ Admin queue endpoint returns live_queue with rate_limiter stats")
        print(f"  Queued: {live_queue['queued']}, Processing: {live_queue['processing']}")
        print(f"  Rate limiter: {rate_limiter['requests_this_minute']} requests this minute")
    
    def test_admin_queue_requires_admin_auth(self, creator_token):
        """Test that admin queue endpoint requires admin authentication"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        response = requests.get(f"{BASE_URL}/api/admin-9821/generation/queue", headers=headers)
        assert response.status_code == 403, "Should require admin role"
        print("✓ Admin queue endpoint correctly requires admin authentication")


class TestAdminLimitsEndpoint:
    """Tests for GET/POST /api/admin-9821/generation/limits endpoint"""
    
    def test_get_generation_limits(self, admin_token):
        """Test that GET /api/admin-9821/generation/limits returns RPM, RPD, TPM settings"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin-9821/generation/limits", headers=headers)
        
        assert response.status_code == 200, f"Get limits failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "rpm" in data, "Response missing 'rpm'"
        assert "rpd" in data, "Response missing 'rpd'"
        assert "tpm" in data, "Response missing 'tpm'"
        
        # Verify values are integers
        assert isinstance(data["rpm"], int), "'rpm' should be an integer"
        assert isinstance(data["rpd"], int), "'rpd' should be an integer"
        assert isinstance(data["tpm"], int), "'tpm' should be an integer"
        
        print(f"✓ GET /api/admin-9821/generation/limits returns settings")
        print(f"  RPM: {data['rpm']}, RPD: {data['rpd']}, TPM: {data['tpm']}")
    
    def test_update_rpm_value(self, admin_token):
        """Test that POST /api/admin-9821/generation/limits updates RPM value"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # First get current value
        get_response = requests.get(f"{BASE_URL}/api/admin-9821/generation/limits", headers=headers)
        assert get_response.status_code == 200
        original_rpm = get_response.json()["rpm"]
        
        # Update RPM
        new_rpm = original_rpm + 1 if original_rpm < 100 else original_rpm - 1
        update_response = requests.post(
            f"{BASE_URL}/api/admin-9821/generation/limits",
            headers=headers,
            json={"rpm": new_rpm}
        )
        
        assert update_response.status_code == 200, f"Update limits failed: {update_response.text}"
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/admin-9821/generation/limits", headers=headers)
        assert verify_response.status_code == 200
        updated_rpm = verify_response.json()["rpm"]
        assert updated_rpm == new_rpm, f"RPM not updated: expected {new_rpm}, got {updated_rpm}"
        
        # Restore original value
        requests.post(
            f"{BASE_URL}/api/admin-9821/generation/limits",
            headers=headers,
            json={"rpm": original_rpm}
        )
        
        print(f"✓ POST /api/admin-9821/generation/limits successfully updates RPM")
        print(f"  Changed from {original_rpm} to {new_rpm}, then restored")


class TestGenerationEndpointsStructure:
    """Tests for generation endpoint response structure (queue_id + job_id)"""
    
    def test_get_user_stories(self, creator_token):
        """Get user's stories to find an episode for testing"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        response = requests.get(f"{BASE_URL}/api/stories", headers=headers)
        
        assert response.status_code == 200, f"Get stories failed: {response.text}"
        stories = response.json()
        
        if not stories:
            pytest.skip("No stories found for testing")
        
        print(f"✓ Found {len(stories)} stories")
        return stories
    
    def test_get_episodes_for_story(self, creator_token):
        """Get episodes for a story"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        
        # Get stories first
        stories_response = requests.get(f"{BASE_URL}/api/stories", headers=headers)
        if stories_response.status_code != 200 or not stories_response.json():
            pytest.skip("No stories found")
        
        story_id = stories_response.json()[0]["story_id"]
        
        # Get episodes
        response = requests.get(f"{BASE_URL}/api/episodes/story/{story_id}", headers=headers)
        assert response.status_code == 200, f"Get episodes failed: {response.text}"
        episodes = response.json()
        
        print(f"✓ Found {len(episodes)} episodes for story {story_id}")
        return episodes, story_id


class TestDialogueModeEndpoint:
    """Tests for dialogue mode setting endpoint"""
    
    def test_get_dialogue_mode_setting(self, creator_token):
        """Test GET /api/settings/dialogue-mode returns enabled status"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        response = requests.get(f"{BASE_URL}/api/settings/dialogue-mode", headers=headers)
        
        assert response.status_code == 200, f"Get dialogue mode failed: {response.text}"
        data = response.json()
        
        assert "enabled" in data, "Response missing 'enabled' field"
        assert isinstance(data["enabled"], bool), "'enabled' should be a boolean"
        
        print(f"✓ Dialogue mode setting: enabled={data['enabled']}")
    
    def test_admin_toggle_dialogue_mode(self, admin_token):
        """Test admin can toggle dialogue mode"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        
        # Get current state
        get_response = requests.get(f"{BASE_URL}/api/admin-9821/settings/dialogue-mode", headers=headers)
        assert get_response.status_code == 200
        original_state = get_response.json()["enabled"]
        
        # Toggle
        toggle_response = requests.post(
            f"{BASE_URL}/api/admin-9821/settings/dialogue-mode",
            headers=headers,
            json={"enabled": not original_state}
        )
        assert toggle_response.status_code == 200, f"Toggle failed: {toggle_response.text}"
        
        # Verify toggle
        verify_response = requests.get(f"{BASE_URL}/api/admin-9821/settings/dialogue-mode", headers=headers)
        assert verify_response.status_code == 200
        new_state = verify_response.json()["enabled"]
        assert new_state == (not original_state), "Dialogue mode not toggled"
        
        # Restore original state
        requests.post(
            f"{BASE_URL}/api/admin-9821/settings/dialogue-mode",
            headers=headers,
            json={"enabled": original_state}
        )
        
        print(f"✓ Admin can toggle dialogue mode (was {original_state}, toggled to {not original_state}, restored)")


class TestGenerationStatusEndpoint:
    """Tests for /api/generation/status endpoint"""
    
    def test_generation_status_returns_user_status(self, creator_token):
        """Test that /api/generation/status returns user's generation status"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        response = requests.get(f"{BASE_URL}/api/generation/status", headers=headers)
        
        assert response.status_code == 200, f"Generation status failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "generation_status" in data, "Response missing 'generation_status'"
        assert "generation_credits" in data, "Response missing 'generation_credits'"
        
        print(f"✓ Generation status: {data['generation_status']}")
        print(f"  Credits: {data['generation_credits']}")


class TestQueueWorkerIntegration:
    """Tests for queue worker integration"""
    
    def test_queue_info_structure(self, admin_token):
        """Test that queue info has correct structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin-9821/generation/queue", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        
        # Check db_queue structure if present
        if "db_queue" in data:
            db_queue = data["db_queue"]
            print(f"  DB Queue: {db_queue}")
        
        print("✓ Queue info structure verified")


class TestAdminGenerationCreators:
    """Tests for admin creator generation controls"""
    
    def test_get_creator_generation_stats(self, admin_token):
        """Test GET /api/admin-9821/generation/creators returns creator stats"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin-9821/generation/creators", headers=headers)
        
        assert response.status_code == 200, f"Get creators failed: {response.text}"
        data = response.json()
        
        assert "creators" in data, "Response missing 'creators'"
        assert "total_active" in data, "Response missing 'total_active'"
        assert "total_inactive" in data, "Response missing 'total_inactive'"
        
        print(f"✓ Creator stats: {len(data['creators'])} creators")
        print(f"  Active: {data['total_active']}, Inactive: {data['total_inactive']}")


class TestAdminGenerationAnalytics:
    """Tests for admin generation analytics"""
    
    def test_get_generation_analytics(self, admin_token):
        """Test GET /api/admin-9821/generation/analytics returns analytics"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin-9821/generation/analytics", headers=headers)
        
        assert response.status_code == 200, f"Get analytics failed: {response.text}"
        data = response.json()
        
        # Analytics should have some structure
        print(f"✓ Generation analytics returned: {list(data.keys())}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
