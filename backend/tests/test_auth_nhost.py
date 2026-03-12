"""
Nhost Auth API Tests
Tests for authentication endpoints using Nhost Auth service.
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USER_EMAIL = "testuser@test.com"
TEST_USER_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"

# Token cache to avoid rate limiting
_token_cache = {}


def get_cached_token(email, password, is_admin=False):
    """Get token from cache or login fresh (with rate limit awareness)."""
    cache_key = f"{email}_{is_admin}"
    if cache_key in _token_cache:
        return _token_cache[cache_key]
    
    # Wait a bit to avoid rate limiting
    time.sleep(2)
    
    endpoint = f"{BASE_URL}/api/admin-9821/login" if is_admin else f"{BASE_URL}/api/auth/login"
    response = requests.post(
        endpoint,
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("token", "")
        _token_cache[cache_key] = token
        return token
    elif response.status_code == 429:
        pytest.skip("Nhost rate limit hit - skipping test")
    return None


class TestHealthEndpoint:
    """Basic health check endpoint tests."""
    
    def test_health_returns_ok(self):
        """Test /api/health returns ok status."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("backend") == "nhost"
        print(f"✅ Health check passed: {data}")


class TestCreatorLogin:
    """Creator (testuser@test.com) login tests."""
    
    def test_login_valid_credentials(self):
        """Test email login with valid credentials."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 429:
            pytest.skip("Nhost rate limit hit")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user" in data
        assert "token" in data
        assert data["user"]["email"] == TEST_USER_EMAIL
        assert data["user"]["role"] == "creator"
        assert len(data["token"]) > 0
        print(f"✅ Creator login passed: {data['user']['email']}")
    
    def test_login_invalid_credentials(self):
        """Test login fails with invalid credentials."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@test.com", "password": "wrongpassword"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 429:
            pytest.skip("Nhost rate limit hit")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ Invalid credentials correctly rejected")


class TestAdminLogin:
    """Admin (admin@admin.com) login tests."""
    
    def test_admin_login_valid_credentials(self):
        """Test admin login with valid credentials."""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 429:
            pytest.skip("Nhost rate limit hit")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user" in data
        assert "token" in data
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"
        print(f"✅ Admin login passed: {data['user']['email']}")
    
    def test_admin_login_non_admin_user(self):
        """Test admin login fails for non-admin user."""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 429:
            pytest.skip("Nhost rate limit hit")
        
        # Should fail with 403 (not admin) or 401 (not allowed)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("✅ Non-admin correctly rejected from admin login")


class TestAuthMe:
    """Tests for /api/auth/me endpoint."""
    
    def test_get_me_with_valid_token(self):
        """Test getting user profile with valid token."""
        token = get_cached_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        if not token:
            pytest.skip("Could not get token")
        
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("email") == TEST_USER_EMAIL
        assert "user_id" in data
        assert "limits_remaining" in data
        print(f"✅ Get me passed: {data}")
    
    def test_get_me_without_token(self):
        """Test /api/auth/me without token returns 401."""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            timeout=30
        )
        
        assert response.status_code == 401
        print("✅ Get me without token correctly rejected")
    
    def test_get_me_with_invalid_token(self):
        """Test /api/auth/me with invalid token returns 401."""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_xyz"},
            timeout=30
        )
        
        assert response.status_code == 401
        print("✅ Invalid token correctly rejected")


class TestSignupEndpoint:
    """Tests for /api/auth/signup endpoint."""
    
    def test_signup_existing_email(self):
        """Test signup with existing email returns error."""
        response = requests.post(
            f"{BASE_URL}/api/auth/signup",
            json={
                "name": "Test User",
                "email": TEST_USER_EMAIL,
                "password": "password123"
            },
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 429:
            pytest.skip("Nhost rate limit hit")
        
        # Should fail because email already exists
        assert response.status_code in [400, 409], f"Expected 400/409, got {response.status_code}"
        print("✅ Signup with existing email correctly rejected")


class TestOAuthSync:
    """Tests for /api/auth/oauth-sync endpoint."""
    
    def test_oauth_sync_with_token(self):
        """Test OAuth sync with valid token."""
        token = get_cached_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        if not token:
            pytest.skip("Could not get token")
        
        response = requests.post(
            f"{BASE_URL}/api/auth/oauth-sync",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "user" in data
        assert data["message"] == "Profile synced"
        print(f"✅ OAuth sync passed: {data}")


class TestLegacySession:
    """Tests for legacy session endpoint."""
    
    def test_legacy_session_deprecated(self):
        """Test legacy session endpoint returns 410 Gone."""
        response = requests.post(
            f"{BASE_URL}/api/auth/session",
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        assert response.status_code == 410, f"Expected 410, got {response.status_code}"
        print("✅ Legacy session endpoint correctly deprecated")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
