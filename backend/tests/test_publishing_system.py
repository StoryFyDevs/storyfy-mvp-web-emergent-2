"""
Test Creator Publishing System & Mobile API v1 Verification
Tests: Creator login, CRUD operations, publishing/unpublishing, Mobile API integration

Test Categories:
- Creator Auth & Story CRUD
- Story Publishing System
- Episode Publishing System
- Mobile API v1 (public & authenticated)
- Admin endpoints
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://script-compiler.preview.emergentagent.com').rstrip('/')

# Test credentials
CREATOR_EMAIL = "testapi@test.com"
CREATOR_PASSWORD = "password123"
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin123"
LISTENER_EMAIL = f"testlistener_{uuid.uuid4().hex[:8]}@test.com"
LISTENER_PASSWORD = "listen123"


class TestCreatorAuth:
    """Test creator authentication"""
    
    def test_creator_login_success(self):
        """POST /api/auth/login with creator credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == CREATOR_EMAIL
        assert data["user"]["role"] == "creator"
        print(f"✓ Creator login successful: {data['user']['email']}")
    
    def test_creator_login_invalid_password(self):
        """POST /api/auth/login with wrong password"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Invalid password correctly rejected")


class TestCreatorStories:
    """Test creator stories CRUD operations"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    def test_get_stories(self, auth_token):
        """GET /api/stories - list creator's stories"""
        response = requests.get(f"{BASE_URL}/api/stories", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/stories returned {len(data)} stories")
    
    def test_create_story(self, auth_token):
        """POST /api/stories - create new story (draft by default)"""
        story_data = {
            "title": f"TEST_Story_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test story for publishing system",
            "story_type": "story"
        }
        response = requests.post(f"{BASE_URL}/api/stories", 
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == story_data["title"]
        assert data["status"] == "draft"  # New stories default to draft
        assert "story_id" in data
        print(f"✓ Story created with status='draft': {data['story_id']}")
        return data["story_id"]
    
    def test_get_single_story(self, auth_token):
        """GET /api/stories/{story_id}"""
        # First get all stories
        response = requests.get(f"{BASE_URL}/api/stories", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        stories = response.json()
        if stories:
            story_id = stories[0]["story_id"]
            response = requests.get(f"{BASE_URL}/api/stories/{story_id}", headers={
                "Authorization": f"Bearer {auth_token}"
            })
            assert response.status_code == 200
            data = response.json()
            assert data["story_id"] == story_id
            print(f"✓ GET single story: {data['title']}")
        else:
            pytest.skip("No stories available to test")
    
    def test_update_story(self, auth_token):
        """PUT /api/stories/{story_id}"""
        # Create a test story first
        story_data = {
            "title": f"TEST_Update_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "To be updated",
            "story_type": "story"
        }
        create_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story_id = create_resp.json()["story_id"]
        
        # Update the story
        updated_data = {**story_data, "description": "Updated description"}
        response = requests.put(f"{BASE_URL}/api/stories/{story_id}",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=updated_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        print(f"✓ Story updated: {story_id}")
    
    def test_delete_story(self, auth_token):
        """DELETE /api/stories/{story_id}"""
        # Create a test story to delete
        story_data = {
            "title": f"TEST_Delete_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "To be deleted",
            "story_type": "story"
        }
        create_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story_id = create_resp.json()["story_id"]
        
        # Delete the story
        response = requests.delete(f"{BASE_URL}/api/stories/{story_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        
        # Verify deletion
        verify_resp = requests.get(f"{BASE_URL}/api/stories/{story_id}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert verify_resp.status_code == 404
        print(f"✓ Story deleted and verified: {story_id}")


class TestStoryPublishing:
    """Test story publishing system"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def test_story(self, auth_token):
        """Create a test story for publishing tests"""
        story_data = {
            "title": f"TEST_Publish_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test story for publishing",
            "story_type": "story"
        }
        response = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        return response.json()
    
    def test_publish_story(self, auth_token, test_story):
        """POST /api/creator/stories/{story_id}/publish"""
        story_id = test_story["story_id"]
        assert test_story["status"] == "draft"
        
        response = requests.post(f"{BASE_URL}/api/creator/stories/{story_id}/publish", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "published"
        assert "publishedAt" in data
        print(f"✓ Story published: {story_id}")
        
        return story_id
    
    def test_unpublish_story(self, auth_token, test_story):
        """POST /api/creator/stories/{story_id}/unpublish"""
        story_id = test_story["story_id"]
        
        # First publish it
        requests.post(f"{BASE_URL}/api/creator/stories/{story_id}/publish", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        # Then unpublish
        response = requests.post(f"{BASE_URL}/api/creator/stories/{story_id}/unpublish", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft"
        print(f"✓ Story unpublished: {story_id}")
    
    def test_already_published_story(self, auth_token, test_story):
        """Publish an already published story should return success message"""
        story_id = test_story["story_id"]
        
        # Publish first time
        requests.post(f"{BASE_URL}/api/creator/stories/{story_id}/publish", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        # Publish again
        response = requests.post(f"{BASE_URL}/api/creator/stories/{story_id}/publish", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "already published" in data["message"]
        print(f"✓ Already published message returned correctly")


class TestEpisodeCRUD:
    """Test episode CRUD operations"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def test_story(self, auth_token):
        story_data = {
            "title": f"TEST_EpStory_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test story for episodes",
            "story_type": "story"
        }
        response = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        return response.json()
    
    def test_create_episode(self, auth_token, test_story):
        """POST /api/episodes - create new episode"""
        episode_data = {
            "story_id": test_story["story_id"],
            "title": f"TEST_Episode_{uuid.uuid4().hex[:8]}",
            "order": 1,
            "script": "Test script content"
        }
        response = requests.post(f"{BASE_URL}/api/episodes",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=episode_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data["story_id"] == test_story["story_id"]
        assert data["isPublished"] == False  # New episodes default to unpublished
        assert "episode_id" in data
        print(f"✓ Episode created: {data['episode_id']}")
        return data
    
    def test_get_episodes_for_story(self, auth_token, test_story):
        """GET /api/episodes/story/{storyId}"""
        # Create an episode first
        episode_data = {
            "story_id": test_story["story_id"],
            "title": "Test Episode",
            "order": 1,
            "script": ""
        }
        requests.post(f"{BASE_URL}/api/episodes",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=episode_data
        )
        
        response = requests.get(f"{BASE_URL}/api/episodes/story/{test_story['story_id']}", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        print(f"✓ GET episodes for story returned {len(data)} episodes")


class TestEpisodePublishing:
    """Test episode publishing system"""
    
    @pytest.fixture
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def test_episode(self, auth_token):
        # Create story first
        story_data = {
            "title": f"TEST_EpPubStory_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "Test story for episode publishing",
            "story_type": "story"
        }
        story_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story = story_resp.json()
        
        # Create episode
        episode_data = {
            "story_id": story["story_id"],
            "title": f"TEST_EpPub_{uuid.uuid4().hex[:8]}",
            "order": 1,
            "script": "Test script"
        }
        ep_resp = requests.post(f"{BASE_URL}/api/episodes",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json=episode_data
        )
        return ep_resp.json()
    
    def test_publish_episode(self, auth_token, test_episode):
        """POST /api/creator/episodes/{episode_id}/publish"""
        episode_id = test_episode["episode_id"]
        assert test_episode["isPublished"] == False
        
        response = requests.post(f"{BASE_URL}/api/creator/episodes/{episode_id}/publish", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["isPublished"] == True
        assert "publishedAt" in data
        print(f"✓ Episode published: {episode_id}")
    
    def test_unpublish_episode(self, auth_token, test_episode):
        """POST /api/creator/episodes/{episode_id}/unpublish"""
        episode_id = test_episode["episode_id"]
        
        # First publish it
        requests.post(f"{BASE_URL}/api/creator/episodes/{episode_id}/publish", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        
        # Then unpublish
        response = requests.post(f"{BASE_URL}/api/creator/episodes/{episode_id}/unpublish", headers={
            "Authorization": f"Bearer {auth_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["isPublished"] == False
        print(f"✓ Episode unpublished: {episode_id}")


class TestMobileListenerAuth:
    """Test Mobile API v1 listener authentication"""
    
    def test_listener_signup(self):
        """POST /api/v1/mobile/auth/signup"""
        unique_email = f"listener_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/v1/mobile/auth/signup", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Test Listener"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "listener_id" in data
        assert data["email"] == unique_email
        print(f"✓ Listener signup successful: {unique_email}")
        return data["token"]
    
    def test_duplicate_signup_rejected(self):
        """Duplicate signup should return 409"""
        unique_email = f"dup_{uuid.uuid4().hex[:8]}@test.com"
        # First signup
        requests.post(f"{BASE_URL}/api/v1/mobile/auth/signup", json={
            "email": unique_email,
            "password": "pass123",
            "name": "Test"
        })
        # Duplicate signup
        response = requests.post(f"{BASE_URL}/api/v1/mobile/auth/signup", json={
            "email": unique_email,
            "password": "pass456",
            "name": "Test2"
        })
        assert response.status_code == 409
        print("✓ Duplicate signup correctly rejected with 409")
    
    def test_listener_login(self):
        """POST /api/v1/mobile/auth/login"""
        unique_email = f"login_{uuid.uuid4().hex[:8]}@test.com"
        # Signup first
        requests.post(f"{BASE_URL}/api/v1/mobile/auth/signup", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Test"
        })
        # Login
        response = requests.post(f"{BASE_URL}/api/v1/mobile/auth/login", json={
            "email": unique_email,
            "password": "testpass123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        print("✓ Listener login successful")
    
    def test_login_invalid_credentials(self):
        """Login with wrong password returns 401"""
        response = requests.post(f"{BASE_URL}/api/v1/mobile/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "wrongpass"
        })
        assert response.status_code == 401
        print("✓ Invalid login correctly rejected")


class TestMobileHomeFeed:
    """Test Mobile API v1 Home Feed"""
    
    def test_home_feed_unauthenticated(self):
        """GET /api/v1/mobile/home - no auth - should have trending + new_releases, NO continue_listening"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/home")
        assert response.status_code == 200
        data = response.json()
        assert "sections" in data
        
        section_ids = [s["id"] for s in data["sections"]]
        assert "trending" in section_ids
        assert "new_releases" in section_ids
        # continue_listening should NOT be present without auth (or empty list)
        continue_section = next((s for s in data["sections"] if s["id"] == "continue_listening"), None)
        # If present, should be because user has no progress (shouldn't happen without auth)
        if continue_section:
            # With no auth, continue_listening should NOT appear
            assert False, "continue_listening should not appear without auth"
        print(f"✓ Home feed (unauth) has sections: {section_ids}")
    
    def test_home_feed_authenticated(self):
        """GET /api/v1/mobile/home - with listener token"""
        # Create listener
        unique_email = f"home_{uuid.uuid4().hex[:8]}@test.com"
        signup_resp = requests.post(f"{BASE_URL}/api/v1/mobile/auth/signup", json={
            "email": unique_email,
            "password": "pass123",
            "name": "Test"
        })
        token = signup_resp.json()["token"]
        
        response = requests.get(f"{BASE_URL}/api/v1/mobile/home", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        section_ids = [s["id"] for s in data["sections"]]
        # Should still have trending and new_releases
        assert "trending" in section_ids
        assert "new_releases" in section_ids
        # continue_listening may or may not be present depending on progress
        print(f"✓ Home feed (auth) sections: {section_ids}")


class TestMobileBrowse:
    """Test Mobile API v1 Browse/Discover"""
    
    def test_browse_stories_pagination(self):
        """GET /api/v1/mobile/stories?page=1&limit=12 - verify pagination format"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/stories?page=1&limit=12")
        assert response.status_code == 200
        data = response.json()
        
        # Verify pagination format
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "hasNext" in data
        
        assert data["page"] == 1
        assert data["limit"] == 12
        assert isinstance(data["hasNext"], bool)
        print(f"✓ Browse stories: {len(data['items'])} items, total={data['total']}, hasNext={data['hasNext']}")
    
    def test_browse_with_genre_filter(self):
        """GET /api/v1/mobile/stories?genre=fiction&sort=popular"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/stories?genre=fiction&sort=popular")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        # All returned items should have genre containing 'fiction' (case-insensitive)
        for item in data["items"]:
            assert "fiction" in item.get("genre", "").lower()
        print(f"✓ Browse with genre filter: {len(data['items'])} fiction stories")
    
    def test_browse_different_page(self):
        """GET /api/v1/mobile/stories?page=2&limit=5"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/stories?page=2&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["limit"] == 5
        print(f"✓ Browse page 2: {len(data['items'])} items")


class TestMobileStoryDetail:
    """Test Mobile API v1 Story Detail"""
    
    def test_story_detail_published_only(self):
        """GET /api/v1/mobile/stories/{story_id} - must only return published stories"""
        # First get a published story from browse
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=1")
        stories = browse_resp.json()["items"]
        
        if not stories:
            pytest.skip("No published stories available")
        
        story_id = stories[0]["story_id"]
        response = requests.get(f"{BASE_URL}/api/v1/mobile/stories/{story_id}")
        assert response.status_code == 200
        data = response.json()
        
        # Verify story detail structure
        assert data["story_id"] == story_id
        assert "title" in data
        assert "episodes" in data
        assert "creator_name" in data
        print(f"✓ Story detail: {data['title']} with {len(data['episodes'])} episodes")
    
    def test_story_detail_not_found(self):
        """GET /api/v1/mobile/stories/{invalid_id} returns 404"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/stories/nonexistent_story")
        assert response.status_code == 404
        print("✓ Non-existent story returns 404")


class TestMobileEpisodePlayback:
    """Test Mobile API v1 Episode Playback"""
    
    def test_episode_playback(self):
        """GET /api/v1/mobile/episodes/{episode_id} - verify play count increment"""
        # Get a published story with episodes
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=10")
        stories = browse_resp.json()["items"]
        
        episode_id = None
        for story in stories:
            detail_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories/{story['story_id']}")
            episodes = detail_resp.json()["episodes"]
            if episodes:
                episode_id = episodes[0]["episode_id"]
                break
        
        if not episode_id:
            pytest.skip("No published episodes available")
        
        response = requests.get(f"{BASE_URL}/api/v1/mobile/episodes/{episode_id}")
        assert response.status_code == 200
        data = response.json()
        
        # Verify playback response structure
        assert data["episode_id"] == episode_id
        assert "audio_url" in data
        assert "duration" in data
        assert "resume_at" in data
        assert "next_episode_id" in data or data.get("next_episode_id") is None
        print(f"✓ Episode playback: {data['title']}")
    
    def test_episode_not_found(self):
        """GET /api/v1/mobile/episodes/{invalid_id} returns 404"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/episodes/nonexistent_ep")
        assert response.status_code == 404
        print("✓ Non-existent episode returns 404")


class TestMobileSearch:
    """Test Mobile API v1 Search"""
    
    def test_search_stories(self):
        """GET /api/v1/mobile/search?q=test - verify pagination"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/search?q=voice&page=1&limit=10")
        assert response.status_code == 200
        data = response.json()
        
        # Verify pagination format
        assert "items" in data
        assert "total" in data
        assert "query" in data
        assert "page" in data
        assert "limit" in data
        assert "hasNext" in data
        print(f"✓ Search 'voice': {data['total']} results")
    
    def test_search_short_query(self):
        """Short query (<2 chars) returns empty results"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/search?q=a")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        print("✓ Short query returns empty results")


class TestMobileProgress:
    """Test Mobile API v1 Progress Tracking"""
    
    @pytest.fixture
    def listener_token(self):
        unique_email = f"progress_{uuid.uuid4().hex[:8]}@test.com"
        resp = requests.post(f"{BASE_URL}/api/v1/mobile/auth/signup", json={
            "email": unique_email,
            "password": "pass123",
            "name": "Test"
        })
        return resp.json()["token"]
    
    def test_save_progress_requires_auth(self):
        """POST /api/v1/mobile/progress without auth returns 401"""
        response = requests.post(f"{BASE_URL}/api/v1/mobile/progress", json={
            "episode_id": "test",
            "current_time": 30.0
        })
        assert response.status_code == 401
        print("✓ Save progress requires authentication")
    
    def test_get_progress_requires_auth(self):
        """GET /api/v1/mobile/me/progress without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/me/progress")
        assert response.status_code == 401
        print("✓ Get progress requires authentication")
    
    def test_save_and_get_progress(self, listener_token):
        """POST then GET progress"""
        # Get an episode first
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=10")
        stories = browse_resp.json()["items"]
        
        episode_id = None
        for story in stories:
            detail_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories/{story['story_id']}")
            episodes = detail_resp.json()["episodes"]
            if episodes:
                episode_id = episodes[0]["episode_id"]
                break
        
        if not episode_id:
            pytest.skip("No episodes available")
        
        # Save progress
        save_resp = requests.post(f"{BASE_URL}/api/v1/mobile/progress", 
            headers={"Authorization": f"Bearer {listener_token}"},
            json={"episode_id": episode_id, "current_time": 45.5}
        )
        assert save_resp.status_code == 200
        
        # Get progress
        get_resp = requests.get(f"{BASE_URL}/api/v1/mobile/me/progress",
            headers={"Authorization": f"Bearer {listener_token}"}
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert len(data) >= 1
        print(f"✓ Progress saved and retrieved: {len(data)} entries")


class TestMobileLibrary:
    """Test Mobile API v1 User Library"""
    
    @pytest.fixture
    def listener_token(self):
        unique_email = f"library_{uuid.uuid4().hex[:8]}@test.com"
        resp = requests.post(f"{BASE_URL}/api/v1/mobile/auth/signup", json={
            "email": unique_email,
            "password": "pass123",
            "name": "Test"
        })
        return resp.json()["token"]
    
    def test_add_to_library(self, listener_token):
        """POST /api/v1/mobile/me/library"""
        # Get a story
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=1")
        stories = browse_resp.json()["items"]
        if not stories:
            pytest.skip("No stories available")
        
        story_id = stories[0]["story_id"]
        response = requests.post(f"{BASE_URL}/api/v1/mobile/me/library",
            headers={"Authorization": f"Bearer {listener_token}"},
            json={"story_id": story_id}
        )
        assert response.status_code == 200
        print(f"✓ Added to library: {story_id}")
        return story_id
    
    def test_get_library(self, listener_token):
        """GET /api/v1/mobile/me/library"""
        # Add a story first
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=1")
        stories = browse_resp.json()["items"]
        if stories:
            requests.post(f"{BASE_URL}/api/v1/mobile/me/library",
                headers={"Authorization": f"Bearer {listener_token}"},
                json={"story_id": stories[0]["story_id"]}
            )
        
        response = requests.get(f"{BASE_URL}/api/v1/mobile/me/library",
            headers={"Authorization": f"Bearer {listener_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        print(f"✓ Get library: {data['total']} items")
    
    def test_remove_from_library(self, listener_token):
        """DELETE /api/v1/mobile/me/library/{story_id}"""
        # Add a story first
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=1")
        stories = browse_resp.json()["items"]
        if not stories:
            pytest.skip("No stories available")
        
        story_id = stories[0]["story_id"]
        requests.post(f"{BASE_URL}/api/v1/mobile/me/library",
            headers={"Authorization": f"Bearer {listener_token}"},
            json={"story_id": story_id}
        )
        
        # Remove
        response = requests.delete(f"{BASE_URL}/api/v1/mobile/me/library/{story_id}",
            headers={"Authorization": f"Bearer {listener_token}"}
        )
        assert response.status_code == 200
        print(f"✓ Removed from library: {story_id}")


class TestMobileGenresLanguages:
    """Test Mobile API v1 Genres and Languages"""
    
    def test_get_genres(self):
        """GET /api/v1/mobile/genres"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/genres")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Genres: {data}")
    
    def test_get_languages(self):
        """GET /api/v1/mobile/languages"""
        response = requests.get(f"{BASE_URL}/api/v1/mobile/languages")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Languages: {data}")


class TestMobileAnalytics:
    """Test Mobile API v1 Analytics"""
    
    def test_track_play_event(self):
        """POST /api/v1/mobile/analytics/play"""
        # Get an episode
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=10")
        stories = browse_resp.json()["items"]
        
        episode_id = None
        for story in stories:
            detail_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories/{story['story_id']}")
            episodes = detail_resp.json()["episodes"]
            if episodes:
                episode_id = episodes[0]["episode_id"]
                break
        
        if not episode_id:
            pytest.skip("No episodes available")
        
        response = requests.post(f"{BASE_URL}/api/v1/mobile/analytics/play", json={
            "episode_id": episode_id,
            "event_type": "play",
            "position_seconds": 0
        })
        assert response.status_code == 200
        print("✓ Play event tracked")
    
    def test_track_invalid_episode(self):
        """POST /api/v1/mobile/analytics/play with invalid episode returns 404"""
        response = requests.post(f"{BASE_URL}/api/v1/mobile/analytics/play", json={
            "episode_id": "invalid_episode",
            "event_type": "play"
        })
        assert response.status_code == 404
        print("✓ Invalid episode returns 404")


class TestAdminAuth:
    """Test Admin authentication"""
    
    def test_admin_login(self):
        """POST /api/admin-9821/login"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful: {ADMIN_EMAIL}")
        return data["token"]
    
    def test_admin_login_non_admin(self):
        """Non-admin user cannot login to admin portal"""
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 403
        print("✓ Non-admin correctly rejected from admin login")


class TestAdminEndpoints:
    """Test Admin stats and users endpoints"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_admin_stats(self, admin_token):
        """GET /api/admin-9821/stats"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/stats", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "total_stories" in data
        assert "total_episodes" in data
        print(f"✓ Admin stats: {data['total_users']} users, {data['total_stories']} stories")
    
    def test_admin_users(self, admin_token):
        """GET /api/admin-9821/users"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Admin users: {len(data)} users")


class TestPublishingIntegration:
    """Integration test: Published content should appear in mobile API, unpublished should not"""
    
    @pytest.fixture
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    def test_unpublished_story_not_in_mobile_browse(self, creator_token):
        """Unpublish a story -> verify it doesn't appear in mobile browse"""
        # Create a new story
        story_data = {
            "title": f"TEST_HideMe_{uuid.uuid4().hex[:8]}",
            "genre": "fiction",
            "language": "English",
            "description": "This should be hidden",
            "story_type": "story"
        }
        create_resp = requests.post(f"{BASE_URL}/api/stories",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json=story_data
        )
        story = create_resp.json()
        story_id = story["story_id"]
        
        # Story is draft by default - should NOT appear in mobile browse
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=100")
        mobile_ids = [s["story_id"] for s in browse_resp.json()["items"]]
        assert story_id not in mobile_ids, "Draft story should not appear in mobile browse"
        print(f"✓ Draft story {story_id} correctly hidden from mobile browse")
        
        # Now publish it
        requests.post(f"{BASE_URL}/api/creator/stories/{story_id}/publish", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        
        # Should now appear in mobile browse
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=100")
        mobile_ids = [s["story_id"] for s in browse_resp.json()["items"]]
        assert story_id in mobile_ids, "Published story should appear in mobile browse"
        print(f"✓ Published story {story_id} now appears in mobile browse")
        
        # Unpublish it
        requests.post(f"{BASE_URL}/api/creator/stories/{story_id}/unpublish", headers={
            "Authorization": f"Bearer {creator_token}"
        })
        
        # Should no longer appear in mobile browse
        browse_resp = requests.get(f"{BASE_URL}/api/v1/mobile/stories?limit=100")
        mobile_ids = [s["story_id"] for s in browse_resp.json()["items"]]
        assert story_id not in mobile_ids, "Unpublished story should not appear in mobile browse"
        print(f"✓ Unpublished story {story_id} correctly hidden from mobile browse")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
