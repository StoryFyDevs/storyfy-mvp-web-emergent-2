"""
Admin Portal Phase 3: Usage Logs & Analytics API Tests
Tests for:
- GET /api/admin-9821/usage/transactions - enriched limit transactions
- GET /api/admin-9821/usage/actions - enriched admin actions  
- GET /api/admin-9821/usage/analytics - aggregated analytics data
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
        "email": "admin@admin.com",
        "password": "admin123"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Admin authentication failed")

@pytest.fixture(scope="module")
def creator_token():
    """Get creator (non-admin) authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "testapi@test.com",
        "password": "password123"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Creator authentication failed")


class TestUsageTransactions:
    """Tests for /api/admin-9821/usage/transactions endpoint"""
    
    def test_get_transactions_with_admin_token(self, admin_token):
        """Admin can fetch all limit transactions with enriched user info"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/transactions",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Check first transaction has required fields
        if len(data) > 0:
            txn = data[0]
            assert "transaction_id" in txn
            assert "user_id" in txn
            assert "amount" in txn
            assert "balance_after" in txn
            assert "transaction_type" in txn
            assert "created_at" in txn
            # Enriched fields
            assert "user_email" in txn
            assert "user_name" in txn
            print(f"Found {len(data)} transactions, first: {txn['transaction_type']} for {txn['user_email']}")
    
    def test_get_transactions_without_token(self):
        """Unauthenticated request returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/usage/transactions")
        assert response.status_code == 401
    
    def test_get_transactions_with_creator_token(self, creator_token):
        """Non-admin user gets 403 Forbidden"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/transactions",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 403


class TestUsageActions:
    """Tests for /api/admin-9821/usage/actions endpoint"""
    
    def test_get_actions_with_admin_token(self, admin_token):
        """Admin can fetch all admin actions with enriched admin info"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/actions",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Check first action has required fields
        if len(data) > 0:
            action = data[0]
            assert "action_id" in action
            assert "admin_id" in action
            assert "action_type" in action
            assert "target_type" in action
            assert "target_id" in action
            assert "details" in action
            assert "created_at" in action
            # Enriched fields
            assert "admin_email" in action
            assert "admin_name" in action
            print(f"Found {len(data)} admin actions, first: {action['action_type']} by {action['admin_email']}")
    
    def test_get_actions_without_token(self):
        """Unauthenticated request returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/usage/actions")
        assert response.status_code == 401
    
    def test_get_actions_with_creator_token(self, creator_token):
        """Non-admin user gets 403 Forbidden"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/actions",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 403


class TestUsageAnalytics:
    """Tests for /api/admin-9821/usage/analytics endpoint"""
    
    def test_get_analytics_with_admin_token(self, admin_token):
        """Admin can fetch aggregated analytics data"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/analytics",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required analytics fields
        assert "daily_signups" in data
        assert "daily_generations" in data
        assert "transactions_by_type" in data
        assert "top_creators" in data
        
        # Validate daily_signups structure
        assert isinstance(data["daily_signups"], list)
        if len(data["daily_signups"]) > 0:
            signup = data["daily_signups"][0]
            assert "date" in signup
            assert "count" in signup
        
        # Validate transactions_by_type structure
        assert isinstance(data["transactions_by_type"], list)
        if len(data["transactions_by_type"]) > 0:
            txn_type = data["transactions_by_type"][0]
            assert "type" in txn_type
            assert "count" in txn_type
            assert "total_amount" in txn_type
        
        # Validate top_creators structure
        assert isinstance(data["top_creators"], list)
        if len(data["top_creators"]) > 0:
            creator = data["top_creators"][0]
            assert "user_id" in creator
            assert "email" in creator
            assert "limits_remaining" in creator
            assert "stories_count" in creator
        
        print(f"Analytics: {len(data['daily_signups'])} daily signups, {len(data['transactions_by_type'])} txn types, {len(data['top_creators'])} top creators")
    
    def test_get_analytics_without_token(self):
        """Unauthenticated request returns 401"""
        response = requests.get(f"{BASE_URL}/api/admin-9821/usage/analytics")
        assert response.status_code == 401
    
    def test_get_analytics_with_creator_token(self, creator_token):
        """Non-admin user gets 403 Forbidden"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/usage/analytics",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 403


class TestProjectViewerEndpoint:
    """Tests for project viewer endpoint (Phase 2 but used by playable viewer)"""
    
    def test_get_episode_project_returns_audio_data(self, admin_token):
        """Episode project endpoint returns clips with audio URLs"""
        # First get a story to find an episode
        stories_response = requests.get(
            f"{BASE_URL}/api/admin-9821/stories",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert stories_response.status_code == 200
        stories = stories_response.json()
        
        if len(stories) == 0:
            pytest.skip("No stories found")
        
        # Get episodes for first story
        story_id = stories[0]["story_id"]
        episodes_response = requests.get(
            f"{BASE_URL}/api/admin-9821/stories/{story_id}/episodes",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert episodes_response.status_code == 200
        episodes_data = episodes_response.json()
        
        if len(episodes_data.get("episodes", [])) == 0:
            pytest.skip("No episodes found")
        
        episode_id = episodes_data["episodes"][0]["episode_id"]
        
        # Get project state
        project_response = requests.get(
            f"{BASE_URL}/api/admin-9821/episodes/{episode_id}/project",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert project_response.status_code == 200
        project_data = project_response.json()
        
        assert "episode" in project_data
        assert "story" in project_data
        assert "creator_name" in project_data
        assert "project_state" in project_data
        
        project_state = project_data["project_state"]
        if project_state:
            # Check for tracks structure
            if "tracks" in project_state:
                tracks = project_state["tracks"]
                for track in tracks:
                    assert "id" in track
                    assert "name" in track
                    assert "type" in track
                    # Check clips have audio URLs
                    if "clips" in track:
                        for clip in track["clips"]:
                            assert "id" in clip
                            assert "name" in clip
                            if "url" in clip:
                                # Audio URL should be present for playback
                                assert clip["url"] is not None
                print(f"Project has {len(tracks)} tracks with audio clips for playback")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
