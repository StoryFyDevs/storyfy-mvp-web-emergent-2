"""
Test suite for Generation Analytics & Debug Panel API Endpoints
Tests the 3 new admin endpoints:
  - GET /api/admin-9821/analytics/generation/summary
  - GET /api/admin-9821/analytics/generation/runs
  - GET /api/admin-9821/analytics/generation/{generation_id}/debug

Also tests:
  - Auth: 401 for unauthenticated requests
  - Auth: 403 for non-admin users (creators)
  - Correct JSON structure of responses
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_SECRET_PATH = "admin-9821"

# Credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"
CREATOR_EMAIL = "testuser@test.com"
CREATOR_PASSWORD = "password123"


class TestGenerationAnalyticsAuth:
    """Test authentication requirements for analytics endpoints"""

    def test_summary_requires_auth(self):
        """GET /api/admin-9821/analytics/generation/summary returns 401 without token"""
        resp = requests.get(f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/summary")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("✓ Summary endpoint returns 401 for unauthenticated requests")

    def test_runs_requires_auth(self):
        """GET /api/admin-9821/analytics/generation/runs returns 401 without token"""
        resp = requests.get(f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/runs?limit=20")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("✓ Runs endpoint returns 401 for unauthenticated requests")

    def test_debug_requires_auth(self):
        """GET /api/admin-9821/analytics/generation/{id}/debug returns 401 without token"""
        resp = requests.get(f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/test-id/debug")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("✓ Debug endpoint returns 401 for unauthenticated requests")


@pytest.fixture(scope="class")
def admin_token():
    """Get admin auth token via login"""
    resp = requests.post(
        f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} - {resp.text}")
    data = resp.json()
    token = data.get("token", "")
    assert token, "No token returned from admin login"
    print(f"✓ Admin login successful, got token")
    return token


@pytest.fixture(scope="class")
def creator_token():
    """Get creator (non-admin) auth token"""
    # Login via standard auth endpoint
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CREATOR_EMAIL, "password": CREATOR_PASSWORD}
    )
    if resp.status_code != 200:
        pytest.skip(f"Creator login failed: {resp.status_code} - {resp.text}")
    data = resp.json()
    token = data.get("token", "")
    assert token, "No token returned from creator login"
    print(f"✓ Creator login successful, got token")
    return token


class TestGenerationAnalyticsAdminAccess:
    """Test that admin can access analytics endpoints"""

    def test_admin_login(self, admin_token):
        """Verify admin login returns valid token"""
        assert admin_token and len(admin_token) > 10
        print("✓ Admin token is valid")

    def test_summary_endpoint_structure(self, admin_token):
        """GET /api/admin-9821/analytics/generation/summary returns correct JSON structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/summary",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify top-level structure
        assert "today" in data, "Missing 'today' key in response"
        today = data["today"]
        
        # Verify all expected fields
        expected_fields = [
            "total_dialogues",
            "gemini_calls_used",
            "gemini_calls_saved",
            "deepgram_minutes",
            "avg_cost_per_episode",
            "total_cost",
            "cache_hits",
            "cache_misses",
            "cache_hit_rate",
            "total_batches",
            "avg_segmentation_rate",
            "fallback_count",
            "generation_count",
            "avg_generation_time",
            "batch_efficiency"
        ]
        
        for field in expected_fields:
            assert field in today, f"Missing field '{field}' in today's summary"
        
        # Verify types
        assert isinstance(today["total_dialogues"], int), "total_dialogues should be int"
        assert isinstance(today["gemini_calls_used"], int), "gemini_calls_used should be int"
        assert isinstance(today["deepgram_minutes"], (int, float)), "deepgram_minutes should be numeric"
        assert isinstance(today["avg_cost_per_episode"], (int, float)), "avg_cost_per_episode should be numeric"
        assert isinstance(today["batch_efficiency"], (int, float)), "batch_efficiency should be numeric"
        
        print(f"✓ Summary endpoint returns correct structure with {len(expected_fields)} fields")
        print(f"  Today's stats: {today['generation_count']} generations, {today['total_dialogues']} dialogues")

    def test_runs_endpoint_structure(self, admin_token):
        """GET /api/admin-9821/analytics/generation/runs returns correct JSON structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/runs?limit=20",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify top-level structure
        assert "runs" in data, "Missing 'runs' key in response"
        assert "total" in data, "Missing 'total' key in response"
        assert isinstance(data["runs"], list), "runs should be a list"
        assert isinstance(data["total"], int), "total should be an int"
        
        # If there are runs, verify structure of first run
        if len(data["runs"]) > 0:
            run = data["runs"][0]
            expected_run_fields = [
                "generation_id",
                "creator_id",
                "episode_id",
                "dialogue_count",
                "batch_count",
                "gemini_calls_used",
                "gemini_calls_saved",
                "cache_hits",
                "cache_misses",
                "deepgram_audio_minutes",
                "segmentation_success_rate",
                "fallback_triggered",
                "generation_time_seconds",
                "estimated_cost",
                "created_at"
            ]
            for field in expected_run_fields:
                assert field in run, f"Missing field '{field}' in run object"
            print(f"✓ Runs endpoint returns correct structure with {len(data['runs'])} runs")
        else:
            print("✓ Runs endpoint returns correct structure (empty list - no generation runs yet)")
        
        print(f"  Total runs in DB: {data['total']}")

    def test_runs_with_filters(self, admin_token):
        """GET /api/admin-9821/analytics/generation/runs with creator_id and episode_id filters"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Test with creator_id filter
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/runs?creator_id=test-creator&limit=10",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "runs" in data
        print("✓ Runs endpoint accepts creator_id filter")
        
        # Test with episode_id filter
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/runs?episode_id=test-episode&limit=10",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "runs" in data
        print("✓ Runs endpoint accepts episode_id filter")
        
        # Test with both filters
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/runs?creator_id=test&episode_id=test&limit=5",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("✓ Runs endpoint accepts combined filters")

    def test_debug_endpoint_structure(self, admin_token):
        """GET /api/admin-9821/analytics/generation/{id}/debug returns correct JSON structure"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Test with a nonexistent generation_id (should still return empty logs, not 404)
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/nonexistent-id/debug",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "logs" in data, "Missing 'logs' key in response"
        assert isinstance(data["logs"], list), "logs should be a list"
        
        print(f"✓ Debug endpoint returns correct structure (empty logs for nonexistent ID)")


class TestGenerationAnalyticsCreatorForbidden:
    """Test that non-admin users (creators) get 403 Forbidden"""

    def test_creator_cannot_access_summary(self, creator_token):
        """Creators should get 403 when accessing summary endpoint"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/summary",
            headers=headers
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Creator gets 403 on summary endpoint")

    def test_creator_cannot_access_runs(self, creator_token):
        """Creators should get 403 when accessing runs endpoint"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/runs?limit=20",
            headers=headers
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Creator gets 403 on runs endpoint")

    def test_creator_cannot_access_debug(self, creator_token):
        """Creators should get 403 when accessing debug endpoint"""
        headers = {"Authorization": f"Bearer {creator_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/analytics/generation/test-id/debug",
            headers=headers
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("✓ Creator gets 403 on debug endpoint")


class TestAdminDashboardStats:
    """Test existing admin stats endpoint to verify dashboard data"""

    def test_admin_stats_endpoint(self, admin_token):
        """GET /api/admin-9821/stats returns platform stats"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/stats",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        expected_fields = ["total_users", "total_creators", "total_stories", "total_episodes"]
        for field in expected_fields:
            assert field in data, f"Missing field '{field}'"
        
        print(f"✓ Admin stats: {data['total_users']} users, {data['total_stories']} stories, {data['total_episodes']} episodes")

    def test_admin_global_usage_stats(self, admin_token):
        """GET /api/admin-9821/usage/global-stats returns global usage stats"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = requests.get(
            f"{BASE_URL}/api/{ADMIN_SECRET_PATH}/usage/global-stats",
            headers=headers
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        expected_fields = ["total_credits_used", "total_audio_minutes", "total_generations", "active_alerts"]
        for field in expected_fields:
            assert field in data, f"Missing field '{field}'"
        
        print(f"✓ Global stats: {data['total_generations']} generations, {data['total_audio_minutes']} audio minutes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
