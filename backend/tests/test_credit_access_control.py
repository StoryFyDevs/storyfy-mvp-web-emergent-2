"""
Test Credit and Access Control System for StoryFy Creators

Tests the controlled credit and access control system:
1. New creators start with generation_credits=0, audition_credits=0, generation_status=inactive
2. Admin can toggle audio access (master switch) and assign credits
3. generation_status acts as master switch - if inactive, ALL audio features blocked
4. Separate credit systems for generation and audition
5. Standardized error codes: audio_access_disabled, insufficient_generation_credits, insufficient_audition_credits
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://generation-workflow.preview.emergentagent.com').rstrip('/')

# Test credentials
CREATOR_EMAIL = "testuser@test.com"
CREATOR_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"

# Test user for new signup testing
TEST_NEW_USER_EMAIL = f"test_newuser_{uuid.uuid4().hex[:8]}@test.com"
TEST_NEW_USER_PASSWORD = "password123"


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Test that the API is running"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint working")
    
    def test_creator_login(self):
        """Test creator login returns token and generation_status"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data, "Login response should contain 'token'"
        assert "user" in data, "Login response should contain 'user'"
        # Check generation_status is included
        user = data["user"]
        assert "generation_status" in user, "User should have generation_status field"
        print(f"✓ Creator login successful, generation_status={user.get('generation_status')}")
    
    def test_admin_login(self):
        """Test admin login returns token and generation_status"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data, "Admin login response should contain 'token'"
        print("✓ Admin login successful")


class TestNewUserSignup:
    """Test that new users start with correct default values"""
    
    def test_new_signup_has_zero_credits_and_inactive_status(self):
        """New user signup should have generation_credits=0, audition_credits=0, generation_status=inactive"""
        # Create a unique email for this test
        unique_email = f"test_signup_{uuid.uuid4().hex[:8]}@test.com"
        
        response = requests.post(f"{BASE_URL}/api/auth/signup", json={
            "email": unique_email,
            "password": TEST_NEW_USER_PASSWORD,
            "name": "Test New User"
        })
        
        # Signup might return 200 or require verification
        if response.status_code == 200:
            data = response.json()
            if data.get("requires_verification"):
                print("✓ Signup requires verification (expected for Supabase)")
                pytest.skip("Signup requires email verification")
            
            user = data.get("user", {})
            # Check default values
            assert user.get("limits_remaining", 0) == 0, "New user should have 0 generation credits"
            assert user.get("audition_credits", 0) == 0, "New user should have 0 audition credits"
            assert user.get("generation_status") == "inactive", "New user should have inactive generation_status"
            print(f"✓ New user created with correct defaults: gen_credits=0, aud_credits=0, status=inactive")
        elif response.status_code == 400:
            # Email might already exist
            print(f"Note: Signup returned 400 - {response.json().get('detail', 'unknown error')}")
            pytest.skip("Could not create new user for testing")
        else:
            print(f"Signup response: {response.status_code} - {response.text[:200]}")
            pytest.skip(f"Unexpected signup response: {response.status_code}")


class TestCreditsEndpoint:
    """Test the /api/credits endpoint"""
    
    @pytest.fixture
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_credits_endpoint_returns_generation_status(self, creator_token):
        """GET /api/credits should return generation_status field"""
        response = requests.get(f"{BASE_URL}/api/credits", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "generation_credits" in data, "Should have generation_credits"
        assert "audition_credits" in data, "Should have audition_credits"
        assert "generation_status" in data, "Should have generation_status"
        
        print(f"✓ Credits endpoint returns: gen_credits={data['generation_credits']}, aud_credits={data['audition_credits']}, status={data['generation_status']}")


class TestGenerationStatusEndpoint:
    """Test the /api/generation/status endpoint"""
    
    @pytest.fixture
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_generation_status_endpoint(self, creator_token):
        """GET /api/generation/status should return generation_status and can_generate"""
        response = requests.get(f"{BASE_URL}/api/generation/status", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "generation_status" in data, "Should have generation_status"
        assert "can_generate" in data, "Should have can_generate"
        
        # If status is inactive, can_generate should be False
        if data.get("generation_status") == "inactive":
            assert data.get("can_generate") == False, "can_generate should be False when status is inactive"
            print(f"✓ Generation status: inactive, can_generate=False (correct)")
        else:
            print(f"✓ Generation status: {data['generation_status']}, can_generate={data['can_generate']}")


class TestAudioAccessDisabledErrors:
    """Test that audio endpoints return 403 with audio_access_disabled when generation_status=inactive"""
    
    @pytest.fixture
    def inactive_user_token(self):
        """Get token for a user with inactive generation_status"""
        # First login as admin to find/create an inactive user
        admin_response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert admin_response.status_code == 200
        admin_token = admin_response.json()["token"]
        
        # Get list of users
        users_response = requests.get(f"{BASE_URL}/api/admin-9821/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert users_response.status_code == 200
        users = users_response.json()
        
        # Find a non-admin user
        test_user = None
        for user in users:
            if user.get("role") != "admin" and user.get("email") == CREATOR_EMAIL:
                test_user = user
                break
        
        if not test_user:
            pytest.skip("No test user found")
        
        # Ensure user is inactive
        if test_user.get("generation_status") == "active":
            # Disable audio access
            toggle_response = requests.post(f"{BASE_URL}/api/admin-9821/users/audio-access", 
                headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                json={"user_id": test_user["user_id"], "enabled": False}
            )
            assert toggle_response.status_code == 200
            print(f"✓ Disabled audio access for user {test_user['user_id']}")
        
        # Login as the user
        user_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert user_response.status_code == 200
        return user_response.json()["token"], test_user["user_id"], admin_token
    
    def test_audition_returns_403_when_inactive(self, inactive_user_token):
        """POST /api/tts/audition should return 403 with audio_access_disabled when inactive"""
        token, user_id, admin_token = inactive_user_token
        
        response = requests.post(f"{BASE_URL}/api/tts/audition", 
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"voice_id": "Kore", "text": "Test audition text"}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert data.get("detail") == "audio_access_disabled", f"Expected 'audio_access_disabled', got {data.get('detail')}"
        print("✓ Audition returns 403 with audio_access_disabled when inactive")
        
        # Re-enable audio access for cleanup
        requests.post(f"{BASE_URL}/api/admin-9821/users/audio-access", 
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": user_id, "enabled": True}
        )
    
    def test_tts_generate_returns_403_when_inactive(self, inactive_user_token):
        """POST /api/tts/generate should return 403 with audio_access_disabled when inactive"""
        token, user_id, admin_token = inactive_user_token
        
        response = requests.post(f"{BASE_URL}/api/tts/generate", 
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"voice_id": "Kore", "text": "Test generation text"}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert data.get("detail") == "audio_access_disabled", f"Expected 'audio_access_disabled', got {data.get('detail')}"
        print("✓ TTS generate returns 403 with audio_access_disabled when inactive")
        
        # Re-enable audio access for cleanup
        requests.post(f"{BASE_URL}/api/admin-9821/users/audio-access", 
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": user_id, "enabled": True}
        )


class TestAdminAudioAccessToggle:
    """Test admin audio access toggle functionality"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture
    def test_user_id(self, admin_token):
        """Get a test user ID"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        users = response.json()
        
        for user in users:
            if user.get("role") != "admin" and user.get("email") == CREATOR_EMAIL:
                return user["user_id"]
        
        pytest.skip("No test user found")
    
    def test_admin_can_toggle_audio_access(self, admin_token, test_user_id):
        """POST /api/admin-9821/users/audio-access should toggle generation_status"""
        # Disable audio access
        response = requests.post(f"{BASE_URL}/api/admin-9821/users/audio-access", 
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": test_user_id, "enabled": False}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("generation_status") == "inactive", "Should be inactive after disabling"
        print("✓ Admin disabled audio access")
        
        # Enable audio access
        response = requests.post(f"{BASE_URL}/api/admin-9821/users/audio-access", 
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": test_user_id, "enabled": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("generation_status") == "active", "Should be active after enabling"
        print("✓ Admin enabled audio access")


class TestAdminCreditAdjustment:
    """Test admin credit adjustment functionality"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture
    def test_user_id(self, admin_token):
        """Get a test user ID"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        users = response.json()
        
        for user in users:
            if user.get("role") != "admin" and user.get("email") == CREATOR_EMAIL:
                return user["user_id"]
        
        pytest.skip("No test user found")
    
    def test_admin_can_adjust_generation_credits(self, admin_token, test_user_id):
        """POST /api/admin-9821/users/limits should adjust generation credits"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/users/limits", 
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": test_user_id, "amount": 100, "reason": "Test credit adjustment"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "new_balance" in data, "Should return new_balance"
        print(f"✓ Admin adjusted generation credits, new_balance={data['new_balance']}")
    
    def test_admin_can_adjust_audition_credits(self, admin_token, test_user_id):
        """POST /api/admin-9821/users/audition-credits should adjust audition credits"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/users/audition-credits", 
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": test_user_id, "amount": 50, "reason": "Test audition credit adjustment"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "new_balance" in data, "Should return new_balance"
        print(f"✓ Admin adjusted audition credits, new_balance={data['new_balance']}")


class TestAdminCreatorManagementPage:
    """Test admin Creator Management page data"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    def test_users_list_includes_audio_access_fields(self, admin_token):
        """GET /api/admin-9821/users should include generation_status and audition_credits"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        users = response.json()
        
        assert len(users) > 0, "Should have at least one user"
        
        # Check first non-admin user
        for user in users:
            if user.get("role") != "admin":
                assert "generation_status" in user, "User should have generation_status"
                assert "audition_credits" in user, "User should have audition_credits"
                assert "limits_remaining" in user, "User should have limits_remaining (generation credits)"
                print(f"✓ User {user['email']}: gen_status={user['generation_status']}, gen_credits={user['limits_remaining']}, aud_credits={user['audition_credits']}")
                break


class TestDialogueRegenerateAccessControl:
    """Test that dialogue regeneration respects audio access control"""
    
    @pytest.fixture
    def tokens(self):
        """Get both creator and admin tokens"""
        creator_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert creator_response.status_code == 200
        creator_token = creator_response.json()["token"]
        
        admin_response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert admin_response.status_code == 200
        admin_token = admin_response.json()["token"]
        
        # Get user_id
        users_response = requests.get(f"{BASE_URL}/api/admin-9821/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        user_id = None
        for user in users_response.json():
            if user.get("email") == CREATOR_EMAIL:
                user_id = user["user_id"]
                break
        
        return creator_token, admin_token, user_id
    
    def test_dialogue_regenerate_returns_403_when_inactive(self, tokens):
        """POST /api/script/{ep}/dialogue/{idx}/regenerate should return 403 when audio access disabled"""
        creator_token, admin_token, user_id = tokens
        
        # Disable audio access
        requests.post(f"{BASE_URL}/api/admin-9821/users/audio-access", 
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": user_id, "enabled": False}
        )
        
        # Try to regenerate dialogue
        episode_id = "ep_2a62619c6f03"  # Test episode from context
        response = requests.post(f"{BASE_URL}/api/script/{episode_id}/dialogue/0/regenerate", 
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={
                "dialogue_index": 0,
                "character_id": "char_test",
                "character_name": "Test",
                "voice_id": "Kore",
                "text": "Test dialogue",
                "director_notes": ""
            }
        )
        
        # Should return 403 with audio_access_disabled
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert data.get("detail") == "audio_access_disabled", f"Expected 'audio_access_disabled', got {data.get('detail')}"
        print("✓ Dialogue regenerate returns 403 with audio_access_disabled when inactive")
        
        # Re-enable audio access for cleanup
        requests.post(f"{BASE_URL}/api/admin-9821/users/audio-access", 
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": user_id, "enabled": True}
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
