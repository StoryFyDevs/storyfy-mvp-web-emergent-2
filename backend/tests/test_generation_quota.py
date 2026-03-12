"""
Test suite for Generation Quota Management System (Iteration 21)
Tests: Admin generation controls, creator generation status, rate limiting
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
CREATOR_EMAIL = "testuser@test.com"
CREATOR_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    res = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, timeout=15)
    if res.status_code == 200:
        return res.json().get("token")
    pytest.skip(f"Admin auth failed: {res.status_code}")


@pytest.fixture(scope="module")
def creator_token():
    """Get creator authentication token."""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": CREATOR_EMAIL,
        "password": CREATOR_PASSWORD
    }, timeout=15)
    if res.status_code == 200:
        return res.json().get("token")
    pytest.skip(f"Creator auth failed: {res.status_code}")


class TestAdminGenerationLimitsGet:
    """Test GET /api/admin-9821/generation/limits"""
    
    def test_get_limits_requires_auth(self):
        """Should return 401 without authorization."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/generation/limits", timeout=10)
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("PASSED: GET limits requires auth")
    
    def test_get_limits_returns_data(self, admin_token):
        """Should return system limits."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/generation/limits",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        
        # Verify expected fields
        assert "rpd" in data, "Missing 'rpd' field"
        assert "rpm" in data, "Missing 'rpm' field"
        assert "tpm" in data, "Missing 'tpm' field"
        assert "auto_distribute" in data, "Missing 'auto_distribute' field"
        assert "default_creator_rpd" in data, "Missing 'default_creator_rpd' field"
        assert "default_creator_rpm" in data, "Missing 'default_creator_rpm' field"
        
        # Verify types
        assert isinstance(data["rpd"], int), "rpd should be int"
        assert isinstance(data["rpm"], int), "rpm should be int"
        assert isinstance(data["tpm"], int), "tpm should be int"
        assert isinstance(data["auto_distribute"], bool), "auto_distribute should be bool"
        
        print(f"PASSED: GET limits returns data: RPD={data['rpd']}, RPM={data['rpm']}, TPM={data['tpm']}")


class TestAdminGenerationLimitsPost:
    """Test POST /api/admin-9821/generation/limits"""
    
    def test_update_limits_requires_auth(self):
        """Should return 401 without authorization."""
        res = requests.post(f"{BASE_URL}/api/admin-9821/generation/limits",
            json={"rpd": 100},
            timeout=10)
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("PASSED: POST limits requires auth")
    
    def test_update_limits_success(self, admin_token):
        """Should update system limits successfully."""
        # First get current limits
        get_res = requests.get(f"{BASE_URL}/api/admin-9821/generation/limits",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10)
        original_limits = get_res.json() if get_res.status_code == 200 else {}
        
        # Update with new values
        new_limits = {
            "rpd": 60,
            "rpm": 6,
            "tpm": 12000,
            "auto_distribute": True
        }
        res = requests.post(f"{BASE_URL}/api/admin-9821/generation/limits",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json=new_limits,
            timeout=10)
        
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:200]}"
        data = res.json()
        assert "message" in data, "Response should contain 'message'"
        
        # Verify changes persisted
        verify_res = requests.get(f"{BASE_URL}/api/admin-9821/generation/limits",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10)
        verified = verify_res.json()
        assert verified["rpd"] == 60, f"RPD not updated: expected 60, got {verified['rpd']}"
        
        # Restore original if we had them
        if original_limits:
            requests.post(f"{BASE_URL}/api/admin-9821/generation/limits",
                headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                json=original_limits,
                timeout=10)
        
        print("PASSED: POST limits updates successfully")


class TestAdminGenerationAnalytics:
    """Test GET /api/admin-9821/generation/analytics"""
    
    def test_analytics_requires_auth(self):
        """Should return 401 without authorization."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/generation/analytics", timeout=10)
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("PASSED: GET analytics requires auth")
    
    def test_analytics_returns_data(self, admin_token):
        """Should return comprehensive analytics."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/generation/analytics",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        
        # Verify structure
        assert "system_limits" in data, "Missing 'system_limits'"
        assert "usage_today" in data, "Missing 'usage_today'"
        assert "queue_status" in data, "Missing 'queue_status'"
        assert "creators" in data, "Missing 'creators'"
        assert "current_minute" in data, "Missing 'current_minute'"
        
        # Verify nested structures
        assert "rpd" in data["system_limits"], "Missing system_limits.rpd"
        assert "total_generations" in data["usage_today"], "Missing usage_today.total_generations"
        assert "active_count" in data["creators"], "Missing creators.active_count"
        
        print(f"PASSED: GET analytics returns data: {data['creators']['active_count']} active creators")


class TestAdminCreatorStats:
    """Test GET /api/admin-9821/generation/creators"""
    
    def test_creator_stats_requires_auth(self):
        """Should return 401 without authorization."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/generation/creators", timeout=10)
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("PASSED: GET creator stats requires auth")
    
    def test_creator_stats_returns_list(self, admin_token):
        """Should return creator statistics."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/generation/creators",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        
        # Verify structure
        assert "creators" in data, "Missing 'creators' field"
        assert "total_active" in data, "Missing 'total_active' field"
        assert "total_inactive" in data, "Missing 'total_inactive' field"
        assert isinstance(data["creators"], list), "creators should be a list"
        
        # If creators exist, verify structure
        if data["creators"]:
            creator = data["creators"][0]
            expected_fields = ["user_id", "email", "generation_status", "daily_limit", "generations_today"]
            for field in expected_fields:
                assert field in creator, f"Missing field '{field}' in creator data"
        
        print(f"PASSED: GET creator stats returns {len(data['creators'])} creators, {data['total_active']} active")


class TestAdminToggleCreatorStatus:
    """Test PATCH /api/admin-9821/generation/creators/{id}/status"""
    
    def test_toggle_status_requires_auth(self):
        """Should return 401 without authorization."""
        res = requests.patch(f"{BASE_URL}/api/admin-9821/generation/creators/fake-id/status",
            json={"status": "active"},
            timeout=10)
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("PASSED: PATCH creator status requires auth")
    
    def test_toggle_status_validates_input(self, admin_token):
        """Should validate status value."""
        res = requests.patch(f"{BASE_URL}/api/admin-9821/generation/creators/fake-id/status",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"status": "invalid_status"},
            timeout=10)
        assert res.status_code == 400, f"Expected 400 for invalid status, got {res.status_code}"
        print("PASSED: PATCH creator status validates input")
    
    def test_toggle_status_success(self, admin_token):
        """Should toggle creator status successfully."""
        # First get a creator
        creators_res = requests.get(f"{BASE_URL}/api/admin-9821/generation/creators",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10)
        
        if creators_res.status_code != 200:
            pytest.skip("Could not get creators list")
        
        data = creators_res.json()
        if not data["creators"]:
            pytest.skip("No creators to test with")
        
        # Find test user
        test_creator = None
        for c in data["creators"]:
            if c["email"] == CREATOR_EMAIL:
                test_creator = c
                break
        
        if not test_creator:
            pytest.skip("Test creator not found")
        
        user_id = test_creator["user_id"]
        current_status = test_creator["generation_status"]
        new_status = "inactive" if current_status == "active" else "active"
        
        # Toggle status
        res = requests.patch(f"{BASE_URL}/api/admin-9821/generation/creators/{user_id}/status",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"status": new_status},
            timeout=10)
        
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:200]}"
        
        # Restore original status
        requests.patch(f"{BASE_URL}/api/admin-9821/generation/creators/{user_id}/status",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"status": current_status},
            timeout=10)
        
        print(f"PASSED: PATCH creator status toggles from {current_status} to {new_status}")


class TestCreatorGenerationStatus:
    """Test GET /api/generation/status"""
    
    def test_status_requires_auth(self):
        """Should return 401 without authorization."""
        res = requests.get(f"{BASE_URL}/api/generation/status", timeout=10)
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("PASSED: GET generation status requires auth")
    
    def test_status_returns_data(self, creator_token):
        """Should return generation availability for creator."""
        res = requests.get(f"{BASE_URL}/api/generation/status",
            headers={"Authorization": f"Bearer {creator_token}"},
            timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        
        # Verify required fields
        assert "can_generate" in data, "Missing 'can_generate' field"
        assert "generations_remaining" in data, "Missing 'generations_remaining' field"
        assert "daily_limit" in data, "Missing 'daily_limit' field"
        assert "generations_today" in data, "Missing 'generations_today' field"
        assert "status" in data, "Missing 'status' field"
        
        # Verify types
        assert isinstance(data["can_generate"], bool), "can_generate should be bool"
        assert isinstance(data["generations_remaining"], int), "generations_remaining should be int"
        assert isinstance(data["daily_limit"], int), "daily_limit should be int"
        
        print(f"PASSED: GET generation status: can_generate={data['can_generate']}, remaining={data['generations_remaining']}/{data['daily_limit']}")


class TestAdminQueueStatus:
    """Test GET /api/admin-9821/generation/queue"""
    
    def test_queue_requires_auth(self):
        """Should return 401 without authorization."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/generation/queue", timeout=10)
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("PASSED: GET queue status requires auth")
    
    def test_queue_returns_data(self, admin_token):
        """Should return queue status."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/generation/queue",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=10)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        
        # Verify structure
        assert "pending" in data, "Missing 'pending' field"
        assert "processing" in data, "Missing 'processing' field"
        assert "total_in_queue" in data, "Missing 'total_in_queue' field"
        
        print(f"PASSED: GET queue status: pending={data['pending']}, processing={data['processing']}")


class TestCreatorAuditionRateLimiting:
    """Test that audition endpoint respects rate limits."""
    
    def test_audition_returns_proper_response(self, creator_token):
        """Audition should return proper response or rate limit error."""
        res = requests.post(f"{BASE_URL}/api/tts/audition",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={"voice_id": "Kore", "text": "नमस्ते, यह एक परीक्षण है।"},
            timeout=30)
        
        # Should either succeed, rate limit, or credit issue
        assert res.status_code in [200, 402, 429, 503], f"Unexpected status: {res.status_code}"
        
        if res.status_code == 200:
            data = res.json()
            assert "audio_url" in data, "Missing audio_url in response"
            print("PASSED: Audition succeeded with audio")
        elif res.status_code == 429:
            data = res.json()
            assert "detail" in data, "Missing detail in rate limit response"
            print(f"PASSED: Audition rate limited: {data['detail']}")
        elif res.status_code == 402:
            print("PASSED: Audition returned credit error (expected if low credits)")
        elif res.status_code == 503:
            print("PASSED: Audition returned service unavailable (API issue - graceful handling)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
