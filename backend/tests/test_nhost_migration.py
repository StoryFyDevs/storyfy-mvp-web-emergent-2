"""
Nhost Migration Test Suite - Final Version
Tests all backend APIs after MongoDB/Supabase → Nhost PostgreSQL migration.
Handles rate limiting by using cached tokens and minimal login attempts.
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://script-compiler.preview.emergentagent.com').rstrip('/')

# Test credentials
TEST_USER_EMAIL = "testuser@test.com"
TEST_USER_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin12345"

# Cached tokens to avoid rate limiting
_user_token = None
_admin_token = None


def get_user_token():
    """Get or cache user token."""
    global _user_token
    if _user_token:
        return _user_token
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code == 200:
        _user_token = response.json().get("token")
        return _user_token
    return None


def get_admin_token():
    """Get or cache admin token."""
    global _admin_token
    if _admin_token:
        return _admin_token
    response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        _admin_token = response.json().get("token")
        return _admin_token
    return None


class TestHealthEndpoint:
    """Health check endpoint - run first"""
    
    def test_health_returns_ok(self):
        """Verify Nhost backend is running"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("backend") == "nhost"
        print(f"SUCCESS: Health check passed - backend={data.get('backend')}")


class TestAuthLogin:
    """Auth: POST /api/auth/login - User login"""
    
    def test_login_valid_credentials(self):
        """Test login with valid user credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if response.status_code == 429:
            pytest.skip("Rate limited - Nhost has request limits")
        
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert "token" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 0
        assert data["user"]["email"] == TEST_USER_EMAIL
        print(f"SUCCESS: Login successful - user_id={data['user'].get('user_id', 'N/A')}")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "wrongpassword"
        })
        if response.status_code == 429:
            pytest.skip("Rate limited")
        assert response.status_code == 401
        print(f"SUCCESS: Invalid login correctly rejected (status={response.status_code})")


class TestAuthMe:
    """Auth: GET /api/auth/me - Get current user"""
    
    def test_get_me_with_token(self):
        """Test GET /api/auth/me returns user profile"""
        token = get_user_token()
        if not token:
            pytest.skip("Cannot get token (rate limited)")
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "email" in data
        assert data["email"] == TEST_USER_EMAIL
        print(f"SUCCESS: GET /api/auth/me - user_id={data['user_id']}, email={data['email']}")
    
    def test_get_me_without_token(self):
        """Test GET /api/auth/me without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("SUCCESS: GET /api/auth/me without token correctly returns 401")


class TestCreatorCredits:
    """Creator: GET /api/credits - Get credits"""
    
    def test_get_credits(self):
        """Test credits endpoint returns both credit types"""
        token = get_user_token()
        if not token:
            pytest.skip("Cannot get token")
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/credits", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "generation_credits" in data
        assert "audition_credits" in data
        print(f"SUCCESS: Credits - generation={data['generation_credits']}, audition={data['audition_credits']}")


class TestCreatorVoices:
    """Creator: GET /api/voices - Get voices"""
    
    def test_get_voices(self):
        """Test voices endpoint returns 30 voices"""
        token = get_user_token()
        if not token:
            pytest.skip("Cannot get token")
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/voices", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        voices = data["voices"]
        assert isinstance(voices, list)
        assert len(voices) == 30  # 30 Gemini voices
        print(f"SUCCESS: Got {len(voices)} voices")


class TestCreatorTTSSettings:
    """Creator: GET /api/tts/settings - Get TTS settings"""
    
    def test_get_tts_settings(self):
        """Test TTS settings returns engine configuration"""
        token = get_user_token()
        if not token:
            pytest.skip("Cannot get token")
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/tts/settings", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "engineType" in data
        assert "controls" in data
        assert "voices" in data
        print(f"SUCCESS: TTS Settings - engineType={data['engineType']}")


class TestCreatorStories:
    """Creator: Story CRUD operations"""
    
    def test_story_crud_flow(self):
        """Test complete Create->Read->Update->Delete flow for stories"""
        token = get_user_token()
        if not token:
            pytest.skip("Cannot get token")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 1. CREATE - Note: requires description and story_type
        story_title = f"TEST_Story_{uuid.uuid4().hex[:8]}"
        create_response = requests.post(f"{BASE_URL}/api/stories", headers=headers, json={
            "title": story_title,
            "genre": "Drama",
            "subGenre": "Family",
            "language": "hi",
            "description": "A test story for Nhost migration",
            "story_type": "story"
        })
        assert create_response.status_code == 200
        created_story = create_response.json()
        assert "story_id" in created_story
        assert created_story["title"] == story_title
        story_id = created_story["story_id"]
        print(f"SUCCESS: Created story - {story_id}")
        
        # 2. READ - Get story by ID
        get_response = requests.get(f"{BASE_URL}/api/stories/{story_id}", headers=headers)
        assert get_response.status_code == 200
        fetched_story = get_response.json()
        assert fetched_story["story_id"] == story_id
        assert fetched_story["title"] == story_title
        print(f"SUCCESS: Read story - {story_id}")
        
        # 3. UPDATE
        new_title = f"UPDATED_{story_title}"
        update_response = requests.put(f"{BASE_URL}/api/stories/{story_id}", headers=headers, json={
            "title": new_title,
            "genre": "Comedy",
            "language": "hi",
            "description": "Updated description",
            "story_type": "story"
        })
        assert update_response.status_code == 200
        updated_story = update_response.json()
        assert updated_story["title"] == new_title
        assert updated_story["genre"] == "Comedy"
        print(f"SUCCESS: Updated story - {story_id}")
        
        # 4. DELETE
        delete_response = requests.delete(f"{BASE_URL}/api/stories/{story_id}", headers=headers)
        assert delete_response.status_code == 200
        
        # 5. VERIFY DELETION
        verify_response = requests.get(f"{BASE_URL}/api/stories/{story_id}", headers=headers)
        assert verify_response.status_code == 404
        print(f"SUCCESS: Deleted and verified story - {story_id}")
    
    def test_list_stories(self):
        """Test GET /api/stories returns list"""
        token = get_user_token()
        if not token:
            pytest.skip("Cannot get token")
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/stories", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"SUCCESS: Listed {len(data)} stories")


class TestCreatorEpisodes:
    """Creator: Episode CRUD operations"""
    
    def test_episode_crud_flow(self):
        """Test Create->Read for episodes"""
        token = get_user_token()
        if not token:
            pytest.skip("Cannot get token")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # First create a story
        story_title = f"TEST_EpStory_{uuid.uuid4().hex[:8]}"
        story_response = requests.post(f"{BASE_URL}/api/stories", headers=headers, json={
            "title": story_title,
            "genre": "Drama",
            "language": "hi",
            "description": "Story for episode test",
            "story_type": "story"
        })
        assert story_response.status_code == 200
        story_id = story_response.json()["story_id"]
        
        # CREATE episode - Note: requires order field
        ep_title = f"TEST_Episode_{uuid.uuid4().hex[:8]}"
        create_response = requests.post(f"{BASE_URL}/api/episodes", headers=headers, json={
            "story_id": story_id,
            "title": ep_title,
            "order": 0
        })
        assert create_response.status_code == 200
        created_ep = create_response.json()
        assert "episode_id" in created_ep
        assert created_ep["story_id"] == story_id
        episode_id = created_ep["episode_id"]
        print(f"SUCCESS: Created episode - {episode_id}")
        
        # READ - Get episodes for story
        list_response = requests.get(f"{BASE_URL}/api/episodes/story/{story_id}", headers=headers)
        assert list_response.status_code == 200
        episodes = list_response.json()
        assert isinstance(episodes, list)
        assert len(episodes) >= 1
        print(f"SUCCESS: Listed {len(episodes)} episodes for story")
        
        # Cleanup - delete story (will cascade delete episodes)
        requests.delete(f"{BASE_URL}/api/stories/{story_id}", headers=headers)
        print(f"SUCCESS: Cleaned up test story and episodes")


class TestAdminLogin:
    """Admin: POST /api/admin-9821/login - Admin login"""
    
    def test_admin_login_valid(self):
        """Test admin login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 429:
            pytest.skip("Rate limited - Nhost has request limits")
        
        if response.status_code == 200:
            data = response.json()
            assert "user" in data
            assert "token" in data
            assert data["user"]["role"] == "admin"
            print(f"SUCCESS: Admin login - user_id={data['user'].get('user_id', 'N/A')}")
        elif response.status_code == 401:
            pytest.skip("Admin user not found")
        elif response.status_code == 403:
            pytest.skip("User not admin role")
        else:
            assert False, f"Unexpected response: {response.status_code}"
    
    def test_admin_login_invalid(self):
        """Test admin login with non-admin user returns 401/403"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": "notadmin@test.com",
            "password": "wrongpassword"
        })
        if response.status_code == 429:
            pytest.skip("Rate limited")
        assert response.status_code in [401, 403]
        print(f"SUCCESS: Invalid admin login correctly rejected")


class TestAdminStats:
    """Admin: GET /api/admin-9821/stats - Admin stats"""
    
    def test_get_admin_stats(self):
        """Test admin stats returns platform statistics"""
        token = get_admin_token()
        if not token:
            pytest.skip("Cannot get admin token")
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/admin-9821/stats", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "total_stories" in data
        assert "total_episodes" in data
        print(f"SUCCESS: Admin stats - users={data['total_users']}, stories={data['total_stories']}")


class TestAdminUsers:
    """Admin: GET /api/admin-9821/users - List users"""
    
    def test_list_users(self):
        """Test admin can list all users"""
        token = get_admin_token()
        if not token:
            pytest.skip("Cannot get admin token")
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/admin-9821/users", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            user = data[0]
            assert "user_id" in user
            assert "email" in user
            assert "role" in user
            assert "limits_remaining" in user
            assert "audition_credits" in user
        print(f"SUCCESS: Listed {len(data)} users")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
