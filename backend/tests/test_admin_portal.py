"""
Admin Portal API Tests
Tests for StoryFy Admin Portal Phase 1:
- Admin login authentication
- Platform stats
- User management (list, status, limits)
- Non-admin access restrictions
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
ADMIN_API_PATH = "/api/admin-9821"

# Test credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin123"
CREATOR_EMAIL = "testapi@test.com"
CREATOR_PASSWORD = "password123"


class TestAdminLogin:
    """Test admin login endpoint at POST /api/admin-9821/login"""
    
    def test_admin_login_with_valid_credentials(self):
        """Admin should be able to login with admin@admin.com / admin123"""
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "token" in data, "Response should contain 'token'"
        assert "user" in data, "Response should contain 'user'"
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful: {data['user']['email']}")
    
    def test_admin_login_with_invalid_password(self):
        """Admin login should fail with wrong password"""
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/login", json={
            "email": ADMIN_EMAIL,
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Admin login correctly rejected invalid password")
    
    def test_admin_login_with_non_admin_credentials(self):
        """Non-admin user should get 403 when trying to login to admin portal"""
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert "admin" in data.get("detail", "").lower() or "required" in data.get("detail", "").lower()
        print(f"✓ Non-admin login correctly rejected with 403: {data.get('detail')}")
    
    def test_admin_login_with_nonexistent_user(self):
        """Login with non-existent email should return 401"""
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/login", json={
            "email": "nonexistent@example.com",
            "password": "anypassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Non-existent user login correctly rejected with 401")


@pytest.fixture
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Admin login failed - skipping authenticated tests")
    return response.json()["token"]


@pytest.fixture
def creator_token():
    """Get creator (non-admin) authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": CREATOR_EMAIL,
        "password": CREATOR_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Creator login failed - skipping tests")
    return response.json()["token"]


class TestAdminStats:
    """Test admin stats endpoint at GET /api/admin-9821/stats"""
    
    def test_get_stats_with_admin_token(self, admin_token):
        """Admin should be able to view platform stats"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stats", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify all required stats fields
        required_fields = ["total_users", "total_creators", "total_stories", "total_episodes", 
                          "active_creators_7d", "active_creators_30d", "total_limits_consumed",
                          "total_storage_mb", "total_audio_minutes"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
            assert isinstance(data[field], (int, float)), f"Field {field} should be numeric"
        
        print(f"✓ Stats retrieved: {data['total_users']} users, {data['total_creators']} creators, {data['total_stories']} stories")
    
    def test_get_stats_without_token(self):
        """Stats endpoint should require authentication"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stats")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Stats endpoint correctly requires authentication")
    
    def test_get_stats_with_creator_token(self, creator_token):
        """Non-admin token should get 403 on stats endpoint"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stats", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly rejected from stats endpoint with 403")


class TestAdminUserList:
    """Test admin user list endpoint at GET /api/admin-9821/users"""
    
    def test_get_users_with_admin_token(self, admin_token):
        """Admin should be able to list all users"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        users = response.json()
        assert isinstance(users, list), "Response should be a list"
        assert len(users) > 0, "Should have at least one user"
        
        # Verify user structure
        user = users[0]
        required_fields = ["user_id", "email", "role", "status", "limits_remaining"]
        for field in required_fields:
            assert field in user, f"User missing field: {field}"
        
        # Verify no password in response
        assert "password" not in user, "Password should not be in response"
        
        # Verify extra counts added
        assert "stories_count" in user, "User should have stories_count"
        assert "episodes_count" in user, "User should have episodes_count"
        
        print(f"✓ Retrieved {len(users)} users from admin endpoint")
    
    def test_get_users_without_token(self):
        """Users endpoint should require authentication"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/users")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Users endpoint correctly requires authentication")
    
    def test_get_users_with_creator_token(self, creator_token):
        """Non-admin token should get 403 on users endpoint"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/users", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly rejected from users endpoint with 403")


class TestAdminUserStatus:
    """Test admin user status endpoint at PATCH /api/admin-9821/users/status"""
    
    def get_creator_user_id(self, admin_token):
        """Helper to get creator user_id for testing"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        users = response.json()
        for user in users:
            if user.get("email") == CREATOR_EMAIL and user.get("role") != "admin":
                return user["user_id"]
        pytest.skip("No creator user found for status testing")
    
    def test_suspend_user(self, admin_token):
        """Admin should be able to suspend a user"""
        user_id = self.get_creator_user_id(admin_token)
        
        response = requests.patch(f"{BASE_URL}{ADMIN_API_PATH}/users/status", 
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"user_id": user_id, "status": "suspended", "reason": "Test suspension"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Successfully suspended user {user_id}")
        
        # Verify user is now suspended
        users_response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        users = users_response.json()
        user = next((u for u in users if u["user_id"] == user_id), None)
        assert user and user["status"] == "suspended", "User status should be suspended"
        print("✓ Verified user status is now 'suspended'")
    
    def test_reactivate_user(self, admin_token):
        """Admin should be able to reactivate a suspended user"""
        user_id = self.get_creator_user_id(admin_token)
        
        response = requests.patch(f"{BASE_URL}{ADMIN_API_PATH}/users/status", 
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"user_id": user_id, "status": "active", "reason": "Reactivating after test"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ Successfully reactivated user {user_id}")
        
        # Verify user is now active
        users_response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        users = users_response.json()
        user = next((u for u in users if u["user_id"] == user_id), None)
        assert user and user["status"] == "active", "User status should be active"
        print("✓ Verified user status is now 'active'")
    
    def test_cannot_change_admin_status(self, admin_token):
        """Should not be able to change admin user status"""
        # Get admin user_id
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        users = response.json()
        admin_user = next((u for u in users if u.get("role") == "admin"), None)
        if not admin_user:
            pytest.skip("No admin user found")
        
        response = requests.patch(f"{BASE_URL}{ADMIN_API_PATH}/users/status", 
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"user_id": admin_user["user_id"], "status": "suspended"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Correctly prevented changing admin user status")
    
    def test_invalid_status(self, admin_token):
        """Invalid status should return 400"""
        user_id = self.get_creator_user_id(admin_token)
        
        response = requests.patch(f"{BASE_URL}{ADMIN_API_PATH}/users/status", 
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"user_id": user_id, "status": "invalid_status"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Invalid status correctly rejected with 400")
    
    def test_status_update_without_auth(self):
        """Status update should require authentication"""
        response = requests.patch(f"{BASE_URL}{ADMIN_API_PATH}/users/status", 
            json={"user_id": "any_id", "status": "active"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Status update correctly requires authentication")
    
    def test_status_update_with_creator_token(self, admin_token, creator_token):
        """Non-admin should not be able to update status"""
        user_id = self.get_creator_user_id(admin_token)
        
        response = requests.patch(f"{BASE_URL}{ADMIN_API_PATH}/users/status", 
            headers={"Authorization": f"Bearer {creator_token}"},
            json={"user_id": user_id, "status": "suspended"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly rejected from status update with 403")


class TestAdminLimits:
    """Test admin limits adjustment endpoint at POST /api/admin-9821/users/limits"""
    
    def get_creator_user_id(self, admin_token):
        """Helper to get creator user_id and current limits"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        users = response.json()
        for user in users:
            if user.get("email") == CREATOR_EMAIL and user.get("role") != "admin":
                return user["user_id"], user.get("limits_remaining", 0)
        pytest.skip("No creator user found for limits testing")
    
    def test_add_limits(self, admin_token):
        """Admin should be able to add limits to a user"""
        user_id, current_limits = self.get_creator_user_id(admin_token)
        add_amount = 100
        
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/users/limits", 
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"user_id": user_id, "amount": add_amount, "reason": "Test addition"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "new_balance" in data, "Response should contain new_balance"
        expected_balance = current_limits + add_amount
        assert data["new_balance"] == expected_balance, f"Expected {expected_balance}, got {data['new_balance']}"
        print(f"✓ Successfully added {add_amount} limits. New balance: {data['new_balance']}")
    
    def test_deduct_limits(self, admin_token):
        """Admin should be able to deduct limits from a user"""
        user_id, current_limits = self.get_creator_user_id(admin_token)
        deduct_amount = -50
        
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/users/limits", 
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"user_id": user_id, "amount": deduct_amount, "reason": "Test deduction"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        expected_balance = current_limits + deduct_amount
        assert data["new_balance"] == expected_balance, f"Expected {expected_balance}, got {data['new_balance']}"
        print(f"✓ Successfully deducted {abs(deduct_amount)} limits. New balance: {data['new_balance']}")
    
    def test_cannot_set_negative_balance(self, admin_token):
        """Should not be able to set negative balance"""
        user_id, current_limits = self.get_creator_user_id(admin_token)
        # Try to deduct more than current balance
        deduct_amount = -(current_limits + 1000)
        
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/users/limits", 
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"user_id": user_id, "amount": deduct_amount, "reason": "Test over-deduction"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Correctly prevented setting negative balance")
    
    def test_limits_without_auth(self):
        """Limits adjustment should require authentication"""
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/users/limits", 
            json={"user_id": "any_id", "amount": 100, "reason": "test"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Limits adjustment correctly requires authentication")
    
    def test_limits_with_creator_token(self, admin_token, creator_token):
        """Non-admin should not be able to adjust limits"""
        user_id, _ = self.get_creator_user_id(admin_token)
        
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/users/limits", 
            headers={"Authorization": f"Bearer {creator_token}"},
            json={"user_id": user_id, "amount": 100, "reason": "test"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly rejected from limits adjustment with 403")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
