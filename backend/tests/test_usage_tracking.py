"""
Test Suite for StoryFy Real-Time Usage Tracking System
Tests: Admin usage endpoints, Creator usage endpoint, ElevenLabs sync, Alerts
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin123"
CREATOR_EMAIL = "testapi@test.com"
CREATOR_PASSWORD = "password123"


class TestAuthSetup:
    """Test authentication endpoints first"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    @pytest.fixture(scope="class")
    def creator_token(self):
        """Get creator token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200, f"Creator login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    def test_admin_login(self, admin_token):
        """Verify admin login returns token"""
        assert admin_token is not None
        assert len(admin_token) > 0
        print(f"✓ Admin login successful, token length: {len(admin_token)}")
    
    def test_creator_login(self, creator_token):
        """Verify creator login returns token"""
        assert creator_token is not None
        assert len(creator_token) > 0
        print(f"✓ Creator login successful, token length: {len(creator_token)}")


class TestAdminGlobalStats:
    """Test GET /api/admin-9821/usage/global-stats"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return response.json().get("token")
    
    def test_global_stats_returns_correct_structure(self, admin_token):
        """Test global-stats returns all expected fields"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/global-stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Required fields
        required_fields = [
            "total_credits_used", "total_audio_seconds", "total_audio_minutes",
            "total_file_size_bytes", "total_generations", "total_failed_generations",
            "total_storage_bytes", "total_storage_mb", "active_alerts", "by_type"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify types
        assert isinstance(data["total_credits_used"], (int, float))
        assert isinstance(data["total_generations"], int)
        assert isinstance(data["active_alerts"], int)
        assert isinstance(data["by_type"], list)
        
        # elevenlabs_sync may be None if no syncs yet
        if data.get("elevenlabs_sync"):
            assert "local_total_characters" in data["elevenlabs_sync"]
            assert "elevenlabs_total_characters" in data["elevenlabs_sync"]
            assert "status" in data["elevenlabs_sync"]
        
        print(f"✓ Global stats: {data['total_generations']} generations, {data['total_credits_used']} credits, {data['active_alerts']} alerts")
    
    def test_global_stats_unauthorized(self):
        """Test global-stats without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/usage/global-stats")
        assert response.status_code == 401
        print("✓ Unauthorized request returns 401")


class TestAdminUserSummaries:
    """Test GET /api/admin-9821/usage/user-summaries"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return response.json().get("token")
    
    def test_user_summaries_returns_list(self, admin_token):
        """Test user-summaries returns list with enriched user info"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/user-summaries",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        # If there are summaries, check enrichment
        if len(data) > 0:
            sample = data[0]
            enriched_fields = ["user_email", "user_name", "limits_remaining", "status", "role"]
            for field in enriched_fields:
                assert field in sample, f"Missing enriched field: {field}"
        
        print(f"✓ User summaries: {len(data)} users returned")
    
    def test_user_summaries_unauthorized(self):
        """Test user-summaries without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/usage/user-summaries")
        assert response.status_code == 401
        print("✓ Unauthorized request returns 401")


class TestAdminGenerationLogs:
    """Test GET /api/admin-9821/usage/generation-logs with filters and pagination"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return response.json().get("token")
    
    def test_generation_logs_paginated(self, admin_token):
        """Test generation-logs returns paginated response"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/generation-logs?page=1&per_page=50",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Required pagination fields
        assert "logs" in data, "Missing 'logs' field"
        assert "total" in data, "Missing 'total' field"
        assert "page" in data, "Missing 'page' field"
        assert "total_pages" in data, "Missing 'total_pages' field"
        
        assert isinstance(data["logs"], list)
        assert data["page"] == 1
        
        # If logs exist, check enrichment
        if len(data["logs"]) > 0:
            log = data["logs"][0]
            assert "user_email" in log
            assert "user_name" in log
            assert "type" in log
            assert "credits_used" in log
        
        print(f"✓ Generation logs: {data['total']} total, page {data['page']}/{data['total_pages']}")
    
    def test_generation_logs_filter_by_type(self, admin_token):
        """Test generation-logs with gen_type filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/generation-logs?gen_type=voice",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # All logs should be of type 'voice'
        for log in data.get("logs", []):
            assert log.get("type") == "voice", f"Expected type 'voice', got '{log.get('type')}'"
        
        print(f"✓ Filter by type 'voice': {len(data.get('logs', []))} logs")
    
    def test_generation_logs_filter_by_status(self, admin_token):
        """Test generation-logs with status filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/generation-logs?status=success",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # All logs should have status 'success'
        for log in data.get("logs", []):
            assert log.get("status") == "success", f"Expected status 'success', got '{log.get('status')}'"
        
        print(f"✓ Filter by status 'success': {len(data.get('logs', []))} logs")
    
    def test_generation_logs_unauthorized(self):
        """Test generation-logs without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/usage/generation-logs")
        assert response.status_code == 401
        print("✓ Unauthorized request returns 401")


class TestAdminAlerts:
    """Test GET /api/admin-9821/usage/alerts and PATCH resolve"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return response.json().get("token")
    
    def test_alerts_returns_list(self, admin_token):
        """Test alerts endpoint returns list"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/alerts",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) > 0:
            alert = data[0]
            required_fields = ["alert_id", "alert_type", "severity", "message", "resolved"]
            for field in required_fields:
                assert field in alert, f"Missing field: {field}"
        
        print(f"✓ Alerts: {len(data)} alerts returned")
    
    def test_alerts_filter_unresolved(self, admin_token):
        """Test alerts with resolved=false filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/alerts?resolved=false",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        for alert in data:
            assert alert.get("resolved") == False, "Expected only unresolved alerts"
        
        print(f"✓ Unresolved alerts: {len(data)}")
    
    def test_alerts_filter_resolved(self, admin_token):
        """Test alerts with resolved=true filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/alerts?resolved=true",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        for alert in data:
            assert alert.get("resolved") == True, "Expected only resolved alerts"
        
        print(f"✓ Resolved alerts: {len(data)}")
    
    def test_resolve_nonexistent_alert(self, admin_token):
        """Test resolving non-existent alert returns 404"""
        response = requests.patch(
            f"{BASE_URL}/api/admin-9821/usage/alerts/nonexistent_alert_id/resolve",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 404
        print("✓ Resolve non-existent alert returns 404")
    
    def test_alerts_unauthorized(self):
        """Test alerts without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/usage/alerts")
        assert response.status_code == 401
        print("✓ Unauthorized request returns 401")


class TestAdminElevenLabsSync:
    """Test GET /api/admin-9821/usage/elevenlabs-sync and POST validate-elevenlabs"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return response.json().get("token")
    
    def test_elevenlabs_sync_returns_list(self, admin_token):
        """Test elevenlabs-sync returns sync history"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/elevenlabs-sync",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        
        if len(data) > 0:
            sync = data[0]
            required_fields = ["sync_id", "local_total_characters", "elevenlabs_total_characters", 
                             "discrepancy", "discrepancy_percent", "status"]
            for field in required_fields:
                assert field in sync, f"Missing field: {field}"
        
        print(f"✓ ElevenLabs sync history: {len(data)} syncs")
    
    def test_validate_elevenlabs_manual_trigger(self, admin_token):
        """Test POST validate-elevenlabs triggers validation"""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/usage/validate-elevenlabs",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Should return sync result
        assert "sync_id" in data, "Missing sync_id in response"
        assert "status" in data, "Missing status in response"
        assert data["status"] in ["ok", "mismatch", "error"], f"Unexpected status: {data['status']}"
        
        print(f"✓ Manual validation: status={data['status']}, local={data.get('local_total_characters')}, EL={data.get('elevenlabs_total_characters')}")
    
    def test_elevenlabs_sync_unauthorized(self):
        """Test elevenlabs-sync without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/usage/elevenlabs-sync")
        assert response.status_code == 401
        print("✓ Unauthorized request returns 401")


class TestCreatorUsage:
    """Test GET /api/usage/me for creator dashboard"""
    
    @pytest.fixture(scope="class")
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL, "password": CREATOR_PASSWORD
        })
        return response.json().get("token")
    
    def test_usage_me_returns_summary(self, creator_token):
        """Test /usage/me returns current user's usage summary"""
        response = requests.get(
            f"{BASE_URL}/api/usage/me",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Required fields
        required_fields = ["user_id", "limits_remaining", "storage_used_mb", "storage_limit_mb",
                         "total_credits_used", "total_audio_seconds", "total_generations"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Types check
        assert isinstance(data["limits_remaining"], (int, float))
        assert isinstance(data["total_credits_used"], (int, float))
        assert isinstance(data["total_generations"], int)
        
        print(f"✓ Creator usage: {data['total_credits_used']} credits used, {data['limits_remaining']} remaining, {data['total_generations']} generations")
    
    def test_usage_me_unauthorized(self):
        """Test /usage/me without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/usage/me")
        assert response.status_code == 401
        print("✓ Unauthorized request returns 401")


class TestAdminForbiddenForCreator:
    """Test admin endpoints return 403 for creator tokens"""
    
    @pytest.fixture(scope="class")
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL, "password": CREATOR_PASSWORD
        })
        return response.json().get("token")
    
    def test_global_stats_forbidden(self, creator_token):
        """Test global-stats returns 403 for creator"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/global-stats",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 403
        print("✓ Global stats returns 403 for creator")
    
    def test_user_summaries_forbidden(self, creator_token):
        """Test user-summaries returns 403 for creator"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/user-summaries",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 403
        print("✓ User summaries returns 403 for creator")
    
    def test_generation_logs_forbidden(self, creator_token):
        """Test generation-logs returns 403 for creator"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/generation-logs",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 403
        print("✓ Generation logs returns 403 for creator")
    
    def test_validate_elevenlabs_forbidden(self, creator_token):
        """Test validate-elevenlabs returns 403 for creator"""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/usage/validate-elevenlabs",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 403
        print("✓ Validate ElevenLabs returns 403 for creator")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
