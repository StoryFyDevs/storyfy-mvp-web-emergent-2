"""
Admin Portal Phase 2 API Tests
Tests for StoryFy Admin Portal Phase 2:
- GET /api/admin-9821/stories - List all stories with creator info
- GET /api/admin-9821/stories/:id/episodes - Story detail with episodes
- GET /api/admin-9821/episodes/:id/project - Episode project state
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


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Admin login failed - skipping authenticated tests")
    return response.json()["token"]


@pytest.fixture(scope="module")
def creator_token():
    """Get creator (non-admin) authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": CREATOR_EMAIL,
        "password": CREATOR_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Creator login failed - skipping tests")
    return response.json()["token"]


class TestAdminStoriesList:
    """Test admin stories list endpoint at GET /api/admin-9821/stories"""
    
    def test_get_stories_with_admin_token(self, admin_token):
        """Admin should be able to list all stories with creator info"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        stories = response.json()
        assert isinstance(stories, list), "Response should be a list"
        print(f"✓ Retrieved {len(stories)} stories from admin endpoint")
        
        if len(stories) > 0:
            story = stories[0]
            # Verify story structure includes creator info
            required_fields = ["story_id", "title", "genre", "language", "creator_name", "creator_email", "episodes_count"]
            for field in required_fields:
                assert field in story, f"Story missing field: {field}"
            
            print(f"✓ Story has creator info: {story['creator_name']} ({story['creator_email']})")
            print(f"✓ Story has episodes_count: {story['episodes_count']}")
        else:
            print("⚠ No stories in database - skipping field validation")
    
    def test_get_stories_without_token(self):
        """Stories endpoint should require authentication"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Stories endpoint correctly requires authentication")
    
    def test_get_stories_with_creator_token(self, creator_token):
        """Non-admin token should get 403 on stories endpoint"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly rejected from stories endpoint with 403")


class TestAdminStoryDetail:
    """Test admin story detail endpoint at GET /api/admin-9821/stories/:id/episodes"""
    
    def get_first_story_id(self, admin_token):
        """Helper to get first story ID for testing"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        stories = response.json()
        if not stories:
            pytest.skip("No stories available for testing")
        return stories[0]["story_id"]
    
    def test_get_story_detail_with_admin_token(self, admin_token):
        """Admin should be able to get story detail with episodes"""
        story_id = self.get_first_story_id(admin_token)
        
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories/{story_id}/episodes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "story" in data, "Response should contain 'story'"
        assert "creator_name" in data, "Response should contain 'creator_name'"
        assert "creator_email" in data, "Response should contain 'creator_email'"
        assert "episodes" in data, "Response should contain 'episodes'"
        
        # Verify story structure
        story = data["story"]
        assert story["story_id"] == story_id
        assert "title" in story
        assert "genre" in story
        
        # Verify episodes is a list
        episodes = data["episodes"]
        assert isinstance(episodes, list), "Episodes should be a list"
        
        print(f"✓ Story detail: {story['title']}")
        print(f"✓ Creator: {data['creator_name']} ({data['creator_email']})")
        print(f"✓ Episodes count: {len(episodes)}")
        
        if len(episodes) > 0:
            ep = episodes[0]
            ep_fields = ["episode_id", "title", "order", "status"]
            for field in ep_fields:
                assert field in ep, f"Episode missing field: {field}"
            print(f"✓ Episode structure validated: {ep['title']}")
    
    def test_get_story_detail_not_found(self, admin_token):
        """Should return 404 for non-existent story"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories/nonexistent_id/episodes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Correctly returns 404 for non-existent story")
    
    def test_get_story_detail_without_token(self):
        """Story detail endpoint should require authentication"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories/any_id/episodes")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Story detail endpoint correctly requires authentication")
    
    def test_get_story_detail_with_creator_token(self, admin_token, creator_token):
        """Non-admin token should get 403 on story detail endpoint"""
        story_id = self.get_first_story_id(admin_token)
        
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories/{story_id}/episodes", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly rejected from story detail endpoint with 403")


class TestAdminEpisodeProject:
    """Test admin episode project endpoint at GET /api/admin-9821/episodes/:id/project"""
    
    def get_episode_with_project(self, admin_token):
        """Helper to get an episode ID with project data for testing"""
        # First get all stories
        stories_response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        stories = stories_response.json()
        
        # Find a story with episodes that have project data
        for story in stories:
            detail_response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories/{story['story_id']}/episodes", headers={
                "Authorization": f"Bearer {admin_token}"
            })
            if detail_response.status_code == 200:
                data = detail_response.json()
                for episode in data.get("episodes", []):
                    project_state = episode.get("project_state")
                    if project_state and project_state.get("tracks"):
                        return episode["episode_id"], story["story_id"]
        
        # If no episode with project found, return first episode
        for story in stories:
            detail_response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/stories/{story['story_id']}/episodes", headers={
                "Authorization": f"Bearer {admin_token}"
            })
            if detail_response.status_code == 200:
                data = detail_response.json()
                if data.get("episodes"):
                    return data["episodes"][0]["episode_id"], story["story_id"]
        
        pytest.skip("No episodes available for testing")
    
    def test_get_episode_project_with_admin_token(self, admin_token):
        """Admin should be able to get episode project state"""
        episode_id, story_id = self.get_episode_with_project(admin_token)
        
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/episodes/{episode_id}/project", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "episode" in data, "Response should contain 'episode'"
        assert "story" in data, "Response should contain 'story'"
        assert "creator_name" in data, "Response should contain 'creator_name'"
        assert "project_state" in data, "Response should contain 'project_state'"
        
        # Verify episode structure
        episode = data["episode"]
        assert episode["episode_id"] == episode_id
        assert "title" in episode
        
        # Verify story is linked
        story = data["story"]
        assert story["story_id"] == story_id
        
        print(f"✓ Episode project: {episode['title']}")
        print(f"✓ Story: {story['title']}")
        print(f"✓ Creator: {data['creator_name']}")
        
        # Check project state structure if available
        project_state = data["project_state"]
        if project_state and "tracks" in project_state:
            tracks = project_state["tracks"]
            print(f"✓ Project has {len(tracks)} tracks")
            if tracks:
                track = tracks[0]
                if "clips" in track:
                    print(f"✓ First track has {len(track['clips'])} clips")
        else:
            print("⚠ Episode has no project_state or empty project")
    
    def test_get_episode_project_not_found(self, admin_token):
        """Should return 404 for non-existent episode"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/episodes/nonexistent_ep_id/project", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Correctly returns 404 for non-existent episode")
    
    def test_get_episode_project_without_token(self):
        """Episode project endpoint should require authentication"""
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/episodes/any_id/project")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Episode project endpoint correctly requires authentication")
    
    def test_get_episode_project_with_creator_token(self, admin_token, creator_token):
        """Non-admin token should get 403 on episode project endpoint"""
        episode_id, _ = self.get_episode_with_project(admin_token)
        
        response = requests.get(f"{BASE_URL}{ADMIN_API_PATH}/episodes/{episode_id}/project", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Non-admin correctly rejected from episode project endpoint with 403")


class TestUnifiedLoginEndpoints:
    """Test that login page uses correct endpoints for Creator vs Admin mode"""
    
    def test_creator_login_uses_auth_endpoint(self):
        """Creator mode should use /api/auth/login endpoint"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "token" in data
        assert data.get("user", {}).get("role") == "creator"
        print(f"✓ Creator login successful via /api/auth/login")
    
    def test_admin_login_uses_admin_endpoint(self):
        """Admin mode should use /api/admin-9821/login endpoint"""
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "token" in data
        assert data.get("user", {}).get("role") == "admin"
        print(f"✓ Admin login successful via {ADMIN_API_PATH}/login")
    
    def test_creator_rejected_from_admin_login(self):
        """Creator trying admin login should get 403"""
        response = requests.post(f"{BASE_URL}{ADMIN_API_PATH}/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Creator correctly rejected from admin login with 403")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
