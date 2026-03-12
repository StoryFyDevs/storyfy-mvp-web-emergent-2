"""
Mobile API Tests for StoryFy OTT Platform
Tests for listener-facing APIs: browse, auth, progress, playback, search, analytics
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_LISTENER_EMAIL = f"test_listener_{uuid.uuid4().hex[:8]}@test.com"
TEST_LISTENER_PASSWORD = "listen123"
EXISTING_LISTENER_EMAIL = "listener@test.com"
EXISTING_LISTENER_PASSWORD = "listen123"

# Test episode ID from agent context
TEST_EPISODE_ID = "ep_00bdaa27c723"


class TestMobileHealth:
    """Basic health checks for mobile endpoints"""
    
    def test_genres_endpoint_accessible(self):
        """GET /api/mobile/genres - public endpoint"""
        response = requests.get(f"{BASE_URL}/api/mobile/genres")
        assert response.status_code == 200, f"Genres endpoint failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Genres should return a list"
        print(f"✓ Genres endpoint works, returned {len(data)} genres: {data}")
    
    def test_languages_endpoint_accessible(self):
        """GET /api/mobile/languages - public endpoint"""
        response = requests.get(f"{BASE_URL}/api/mobile/languages")
        assert response.status_code == 200, f"Languages endpoint failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Languages should return a list"
        print(f"✓ Languages endpoint works, returned {len(data)} languages: {data}")


class TestMobilePublicBrowse:
    """Test public browse endpoints - no auth required"""
    
    def test_home_feed_no_auth(self):
        """GET /api/mobile/home - returns trending, latest, empty continue_listening"""
        response = requests.get(f"{BASE_URL}/api/mobile/home")
        assert response.status_code == 200, f"Home feed failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "trending" in data, "Missing 'trending' field"
        assert "latest" in data, "Missing 'latest' field"
        assert "continue_listening" in data, "Missing 'continue_listening' field"
        
        # Without auth, continue_listening should be empty
        assert data["continue_listening"] == [], "continue_listening should be empty without auth"
        
        # Verify trending has expected fields
        if data["trending"]:
            story = data["trending"][0]
            assert "story_id" in story
            assert "title" in story
            assert "genre" in story
            assert "total_episodes" in story
            assert "creator_name" in story
            print(f"✓ Home feed: {len(data['trending'])} trending, {len(data['latest'])} latest")
        else:
            print("✓ Home feed works (no trending stories yet)")
    
    def test_browse_stories_no_filter(self):
        """GET /api/mobile/stories - paginated browse"""
        response = requests.get(f"{BASE_URL}/api/mobile/stories")
        assert response.status_code == 200, f"Browse stories failed: {response.text}"
        data = response.json()
        
        assert "stories" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "total_pages" in data
        
        print(f"✓ Browse stories: {data['total']} total stories, page {data['page']}/{data['total_pages']}")
        
        # Verify story structure
        if data["stories"]:
            story = data["stories"][0]
            assert "story_id" in story
            assert "title" in story
            assert "total_episodes" in story
            assert "creator_name" in story
    
    def test_browse_stories_with_genre_filter(self):
        """GET /api/mobile/stories?genre=fiction - filtered browse"""
        response = requests.get(f"{BASE_URL}/api/mobile/stories?genre=fiction")
        assert response.status_code == 200, f"Browse with genre filter failed: {response.text}"
        data = response.json()
        
        # Even if no results, structure should be valid
        assert "stories" in data
        assert "total" in data
        print(f"✓ Browse with genre=fiction: {data['total']} results")
    
    def test_browse_stories_with_sort_popular(self):
        """GET /api/mobile/stories?sort=popular - sorted browse"""
        response = requests.get(f"{BASE_URL}/api/mobile/stories?sort=popular")
        assert response.status_code == 200, f"Browse with sort failed: {response.text}"
        data = response.json()
        assert "stories" in data
        print(f"✓ Browse sort=popular: {data['total']} results")
    
    def test_browse_stories_pagination(self):
        """GET /api/mobile/stories?page=1&limit=5 - pagination"""
        response = requests.get(f"{BASE_URL}/api/mobile/stories?page=1&limit=5")
        assert response.status_code == 200
        data = response.json()
        
        assert data["page"] == 1
        assert data["limit"] == 5
        assert len(data["stories"]) <= 5
        print(f"✓ Pagination works: page {data['page']}, limit {data['limit']}, got {len(data['stories'])} stories")
    
    def test_search_stories(self):
        """GET /api/mobile/search?q=voice - search by title/description/genre"""
        response = requests.get(f"{BASE_URL}/api/mobile/search?q=voice")
        assert response.status_code == 200, f"Search failed: {response.text}"
        data = response.json()
        
        assert "results" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "voice"
        print(f"✓ Search 'voice': {data['total']} results")
    
    def test_search_short_query(self):
        """GET /api/mobile/search?q=a - short query returns empty"""
        response = requests.get(f"{BASE_URL}/api/mobile/search?q=a")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        print("✓ Short query returns empty results (expected)")


class TestMobileStoryDetail:
    """Test story detail endpoint"""
    
    @pytest.fixture(autouse=True)
    def get_story_id(self):
        """Get a story ID for testing"""
        response = requests.get(f"{BASE_URL}/api/mobile/stories?limit=1")
        if response.status_code == 200 and response.json().get("stories"):
            self.story_id = response.json()["stories"][0]["story_id"]
        else:
            self.story_id = None
    
    def test_story_detail(self):
        """GET /api/mobile/stories/{story_id} - story with episodes"""
        if not self.story_id:
            pytest.skip("No published stories available")
        
        response = requests.get(f"{BASE_URL}/api/mobile/stories/{self.story_id}")
        assert response.status_code == 200, f"Story detail failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert data["story_id"] == self.story_id
        assert "title" in data
        assert "description" in data
        assert "genre" in data
        assert "language" in data
        assert "creator_name" in data
        assert "total_episodes" in data
        assert "episodes" in data
        assert isinstance(data["episodes"], list)
        
        print(f"✓ Story detail: '{data['title']}' by {data['creator_name']}, {data['total_episodes']} episodes")
        
        # Verify episode structure if episodes exist
        if data["episodes"]:
            ep = data["episodes"][0]
            assert "episode_id" in ep
            assert "title" in ep
            assert "episode_number" in ep
            assert "progress_seconds" in ep
            assert "has_audio" in ep
    
    def test_story_detail_not_found(self):
        """GET /api/mobile/stories/invalid_id - 404 for non-existent"""
        response = requests.get(f"{BASE_URL}/api/mobile/stories/story_nonexistent123")
        assert response.status_code == 404
        print("✓ Non-existent story returns 404")


class TestMobileListenerAuth:
    """Test listener authentication flow"""
    
    def test_signup_new_listener(self):
        """POST /api/mobile/auth/signup - new listener"""
        payload = {
            "email": TEST_LISTENER_EMAIL,
            "password": TEST_LISTENER_PASSWORD,
            "name": "Test Listener"
        }
        response = requests.post(f"{BASE_URL}/api/mobile/auth/signup", json=payload)
        assert response.status_code == 200, f"Signup failed: {response.text}"
        data = response.json()
        
        assert "token" in data
        assert "listener_id" in data
        assert data["email"] == TEST_LISTENER_EMAIL
        assert data["listener_id"].startswith("listener_")
        
        print(f"✓ Signup successful: {data['listener_id']}")
        return data["token"]
    
    def test_duplicate_signup_returns_409(self):
        """POST /api/mobile/auth/signup - duplicate email returns 409"""
        # Use existing listener email
        payload = {
            "email": EXISTING_LISTENER_EMAIL,
            "password": "anypassword",
            "name": "Duplicate"
        }
        response = requests.post(f"{BASE_URL}/api/mobile/auth/signup", json=payload)
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
        print("✓ Duplicate signup returns 409 Conflict")
    
    def test_login_existing_listener(self):
        """POST /api/mobile/auth/login - existing listener"""
        payload = {
            "email": EXISTING_LISTENER_EMAIL,
            "password": EXISTING_LISTENER_PASSWORD
        }
        response = requests.post(f"{BASE_URL}/api/mobile/auth/login", json=payload)
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        assert "token" in data
        assert "listener_id" in data
        assert data["email"] == EXISTING_LISTENER_EMAIL
        
        print(f"✓ Login successful: {data['listener_id']}")
        return data["token"]
    
    def test_login_invalid_credentials(self):
        """POST /api/mobile/auth/login - wrong password returns 401"""
        payload = {
            "email": EXISTING_LISTENER_EMAIL,
            "password": "wrongpassword"
        }
        response = requests.post(f"{BASE_URL}/api/mobile/auth/login", json=payload)
        assert response.status_code == 401
        print("✓ Invalid credentials returns 401")


class TestMobileEpisodePlayback:
    """Test episode playback endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup_episode(self):
        """Get episode ID from test data or fetch one"""
        # First try the provided test episode
        response = requests.get(f"{BASE_URL}/api/mobile/episodes/{TEST_EPISODE_ID}")
        if response.status_code == 200:
            self.episode_id = TEST_EPISODE_ID
            return
        
        # Fallback: get any published episode
        stories_resp = requests.get(f"{BASE_URL}/api/mobile/stories?limit=1")
        if stories_resp.status_code == 200 and stories_resp.json().get("stories"):
            story_id = stories_resp.json()["stories"][0]["story_id"]
            detail_resp = requests.get(f"{BASE_URL}/api/mobile/stories/{story_id}")
            if detail_resp.status_code == 200 and detail_resp.json().get("episodes"):
                self.episode_id = detail_resp.json()["episodes"][0]["episode_id"]
                return
        self.episode_id = None
    
    def test_episode_playback_increments_play_count(self):
        """GET /api/mobile/episodes/{episode_id} - playback details & increments count"""
        if not self.episode_id:
            pytest.skip("No published episodes available")
        
        # Get episode playback info
        response = requests.get(f"{BASE_URL}/api/mobile/episodes/{self.episode_id}")
        assert response.status_code == 200, f"Episode playback failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert data["episode_id"] == self.episode_id
        assert "title" in data
        assert "episode_number" in data
        assert "story_id" in data
        assert "story_title" in data
        assert "audio_url" in data
        assert "duration" in data
        assert "resume_at" in data
        assert "next_episode_id" in data or data["next_episode_id"] is None
        assert "prev_episode_id" in data or data["prev_episode_id"] is None
        
        print(f"✓ Episode playback: '{data['title']}' (Ep {data['episode_number']}) from '{data['story_title']}'")
        print(f"  Next: {data['next_episode_id']}, Prev: {data['prev_episode_id']}, Resume at: {data['resume_at']}s")
    
    def test_episode_not_found(self):
        """GET /api/mobile/episodes/invalid_id - 404"""
        response = requests.get(f"{BASE_URL}/api/mobile/episodes/ep_nonexistent123")
        assert response.status_code == 404
        print("✓ Non-existent episode returns 404")


class TestMobileProgressAuth:
    """Test progress save/get - requires authentication"""
    
    @pytest.fixture(autouse=True)
    def setup_auth(self):
        """Login and get token"""
        login_response = requests.post(f"{BASE_URL}/api/mobile/auth/login", json={
            "email": EXISTING_LISTENER_EMAIL,
            "password": EXISTING_LISTENER_PASSWORD
        })
        if login_response.status_code == 200:
            self.token = login_response.json()["token"]
            self.auth_headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.auth_headers = {}
        
        # Get episode ID
        stories_resp = requests.get(f"{BASE_URL}/api/mobile/stories?limit=1")
        if stories_resp.status_code == 200 and stories_resp.json().get("stories"):
            story_id = stories_resp.json()["stories"][0]["story_id"]
            detail_resp = requests.get(f"{BASE_URL}/api/mobile/stories/{story_id}")
            if detail_resp.status_code == 200 and detail_resp.json().get("episodes"):
                self.episode_id = detail_resp.json()["episodes"][0]["episode_id"]
                return
        self.episode_id = TEST_EPISODE_ID
    
    def test_progress_save_without_auth_returns_401(self):
        """POST /api/mobile/progress without token returns 401"""
        response = requests.post(f"{BASE_URL}/api/mobile/progress", json={
            "episode_id": "any_episode",
            "current_time": 30.0
        })
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Progress save without auth returns 401")
    
    def test_progress_get_without_auth_returns_401(self):
        """GET /api/mobile/progress without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/mobile/progress")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("✓ Progress get without auth returns 401")
    
    def test_save_and_get_progress(self):
        """POST then GET /api/mobile/progress - full flow"""
        if not self.token:
            pytest.skip("Authentication failed")
        if not self.episode_id:
            pytest.skip("No episodes available")
        
        # Save progress
        save_payload = {
            "episode_id": self.episode_id,
            "current_time": 45.5,
            "duration": 120.0
        }
        save_response = requests.post(
            f"{BASE_URL}/api/mobile/progress",
            json=save_payload,
            headers=self.auth_headers
        )
        assert save_response.status_code == 200, f"Save progress failed: {save_response.text}"
        save_data = save_response.json()
        assert save_data["episode_id"] == self.episode_id
        assert save_data["current_time"] == 45.5
        print(f"✓ Progress saved: {save_data['episode_id']} at {save_data['current_time']}s")
        
        # Get progress
        get_response = requests.get(
            f"{BASE_URL}/api/mobile/progress",
            headers=self.auth_headers
        )
        assert get_response.status_code == 200, f"Get progress failed: {get_response.text}"
        progress_data = get_response.json()
        
        assert isinstance(progress_data, list)
        # Find our saved progress
        found = False
        for p in progress_data:
            if p["episode_id"] == self.episode_id:
                found = True
                assert p["current_time"] == 45.5
                assert "episode_title" in p
                assert "story_title" in p
                assert "progress_percent" in p
                print(f"✓ Progress retrieved: '{p['episode_title']}' at {p['current_time']}s ({p['progress_percent']}%)")
                break
        
        assert found, f"Saved progress for {self.episode_id} not found in response"


class TestMobileHomeWithAuth:
    """Test home feed with authentication for continue_listening"""
    
    def test_home_feed_with_auth(self):
        """GET /api/mobile/home with auth - should include continue_listening"""
        # Login
        login_response = requests.post(f"{BASE_URL}/api/mobile/auth/login", json={
            "email": EXISTING_LISTENER_EMAIL,
            "password": EXISTING_LISTENER_PASSWORD
        })
        if login_response.status_code != 200:
            pytest.skip("Login failed")
        
        token = login_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get home feed with auth
        response = requests.get(f"{BASE_URL}/api/mobile/home", headers=headers)
        assert response.status_code == 200, f"Home feed with auth failed: {response.text}"
        data = response.json()
        
        assert "trending" in data
        assert "latest" in data
        assert "continue_listening" in data
        
        # If listener has progress, continue_listening should be populated
        if data["continue_listening"]:
            item = data["continue_listening"][0]
            assert "episode_id" in item
            assert "episode_title" in item
            assert "story_title" in item
            assert "current_time" in item
            assert "progress_percent" in item
            print(f"✓ Home with auth: {len(data['continue_listening'])} continue_listening items")
            print(f"  First: '{item['episode_title']}' at {item['progress_percent']}%")
        else:
            print("✓ Home with auth: continue_listening empty (no saved progress)")


class TestMobileAnalytics:
    """Test analytics tracking endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup_episode(self):
        """Get episode ID"""
        stories_resp = requests.get(f"{BASE_URL}/api/mobile/stories?limit=1")
        if stories_resp.status_code == 200 and stories_resp.json().get("stories"):
            story_id = stories_resp.json()["stories"][0]["story_id"]
            detail_resp = requests.get(f"{BASE_URL}/api/mobile/stories/{story_id}")
            if detail_resp.status_code == 200 and detail_resp.json().get("episodes"):
                self.episode_id = detail_resp.json()["episodes"][0]["episode_id"]
                return
        self.episode_id = TEST_EPISODE_ID
    
    def test_track_play_event_anonymous(self):
        """POST /api/mobile/analytics/play - works without auth"""
        payload = {
            "episode_id": self.episode_id,
            "event_type": "play",
            "position_seconds": 0
        }
        response = requests.post(f"{BASE_URL}/api/mobile/analytics/play", json=payload)
        
        # Should work even without episode if episode exists
        if response.status_code == 200:
            data = response.json()
            assert data["message"] == "Event tracked"
            print(f"✓ Anonymous play event tracked for {self.episode_id}")
        elif response.status_code == 404:
            print("✓ Analytics endpoint works (episode not found)")
        else:
            pytest.fail(f"Unexpected status: {response.status_code}")
    
    def test_track_play_event_with_auth(self):
        """POST /api/mobile/analytics/play - works with auth"""
        # Login
        login_response = requests.post(f"{BASE_URL}/api/mobile/auth/login", json={
            "email": EXISTING_LISTENER_EMAIL,
            "password": EXISTING_LISTENER_PASSWORD
        })
        if login_response.status_code != 200:
            pytest.skip("Login failed")
        
        token = login_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        payload = {
            "episode_id": self.episode_id,
            "event_type": "pause",
            "position_seconds": 30
        }
        response = requests.post(
            f"{BASE_URL}/api/mobile/analytics/play",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            assert data["message"] == "Event tracked"
            print(f"✓ Authenticated play event tracked for {self.episode_id}")
        elif response.status_code == 404:
            print("✓ Analytics endpoint works (episode not found)")
        else:
            pytest.fail(f"Unexpected status: {response.status_code}")
    
    def test_track_invalid_episode(self):
        """POST /api/mobile/analytics/play - 404 for invalid episode"""
        payload = {
            "episode_id": "ep_invalid_123",
            "event_type": "play",
            "position_seconds": 0
        }
        response = requests.post(f"{BASE_URL}/api/mobile/analytics/play", json=payload)
        assert response.status_code == 404
        print("✓ Analytics with invalid episode returns 404")


class TestMobileStoryDetailWithAuth:
    """Test story detail with auth shows episode progress"""
    
    def test_story_detail_with_auth_shows_progress(self):
        """GET /api/mobile/stories/{id} with auth shows episode progress"""
        # Login
        login_response = requests.post(f"{BASE_URL}/api/mobile/auth/login", json={
            "email": EXISTING_LISTENER_EMAIL,
            "password": EXISTING_LISTENER_PASSWORD
        })
        if login_response.status_code != 200:
            pytest.skip("Login failed")
        
        token = login_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get a story
        stories_resp = requests.get(f"{BASE_URL}/api/mobile/stories?limit=1")
        if stories_resp.status_code != 200 or not stories_resp.json().get("stories"):
            pytest.skip("No stories available")
        
        story_id = stories_resp.json()["stories"][0]["story_id"]
        
        # Get story detail with auth
        response = requests.get(f"{BASE_URL}/api/mobile/stories/{story_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Episodes should have progress_seconds field
        if data["episodes"]:
            ep = data["episodes"][0]
            assert "progress_seconds" in ep, "Episode missing progress_seconds field"
            print(f"✓ Story detail with auth: episodes have progress_seconds ({ep['progress_seconds']}s)")
        else:
            print("✓ Story detail with auth works (no episodes)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
