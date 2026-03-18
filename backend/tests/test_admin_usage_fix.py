"""
Test Admin Panel Usage Data Fix - Iteration 10
Tests per-user usage data in admin panel matches creator dashboard
Verifies: admin_list_users, admin_user_usage_summaries, admin_creator_usage_detail, usage_me
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://storyfy-queue.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin123"
CREATOR_EMAIL = "testapi@test.com"
CREATOR_PASSWORD = "password123"
STORYFY_EMAIL = "storyfydevelopment@gmail.com"


class TestAuthSetup:
    """Authentication tests - run first"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin token"""
        res = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert res.status_code == 200, f"Admin login failed: {res.text}"
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def creator_token(self):
        """Get creator token"""
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL, "password": CREATOR_PASSWORD
        })
        assert res.status_code == 200, f"Creator login failed: {res.text}"
        return res.json()["token"]
    
    def test_admin_login_success(self, admin_token):
        """Admin login returns valid token"""
        assert admin_token and len(admin_token) > 10
        print(f"Admin token obtained")
    
    def test_creator_login_success(self, creator_token):
        """Creator login returns valid token"""
        assert creator_token and len(creator_token) > 10
        print(f"Creator token obtained")


class TestAdminListUsersWithUsageData:
    """Test GET /api/admin-9821/users includes usage data"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return res.json()["token"]
    
    def test_users_endpoint_returns_usage_fields(self, admin_token):
        """Each user in /admin-9821/users has total_credits_used, total_audio_seconds, total_generations, total_storage_used"""
        res = requests.get(f"{BASE_URL}/api/admin-9821/users",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        users = res.json()
        assert isinstance(users, list)
        assert len(users) >= 9, f"Expected at least 9 users, got {len(users)}"
        
        # Check required usage fields exist
        required_fields = ["total_credits_used", "total_audio_seconds", "total_generations", "total_storage_used"]
        for user in users[:5]:
            for field in required_fields:
                assert field in user, f"User {user.get('email')} missing field: {field}"
        print(f"All {len(users)} users have required usage fields")
    
    def test_storyfy_user_has_correct_usage(self, admin_token):
        """StoryFy user shows 22 credits used and 1 generation"""
        res = requests.get(f"{BASE_URL}/api/admin-9821/users",
                          headers={"Authorization": f"Bearer {admin_token}"})
        users = res.json()
        storyfy_user = next((u for u in users if u.get("email") == STORYFY_EMAIL), None)
        
        assert storyfy_user, f"StoryFy user not found"
        assert storyfy_user.get("total_credits_used") == 22, f"Expected 22 credits used, got {storyfy_user.get('total_credits_used')}"
        assert storyfy_user.get("total_generations") == 1, f"Expected 1 generation, got {storyfy_user.get('total_generations')}"
        assert storyfy_user.get("total_audio_seconds") == 2.38, f"Expected 2.38 audio seconds, got {storyfy_user.get('total_audio_seconds')}"
        print(f"StoryFy user usage: {storyfy_user.get('total_credits_used')} credits, {storyfy_user.get('total_generations')} gen")


class TestAdminUserSummaries:
    """Test GET /api/admin-9821/usage/user-summaries returns ALL creators"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return res.json()["token"]
    
    def test_returns_all_9_creators(self, admin_token):
        """User summaries returns all 9 creators (not just those with usage)"""
        res = requests.get(f"{BASE_URL}/api/admin-9821/usage/user-summaries",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        summaries = res.json()
        assert isinstance(summaries, list)
        assert len(summaries) == 9, f"Expected 9 creators, got {len(summaries)}"
        
        # Verify admin is NOT in the list
        admin_in_list = any(s.get("user_email") == ADMIN_EMAIL for s in summaries)
        assert not admin_in_list, "Admin should not be in creator summaries"
        print(f"Returned {len(summaries)} creators (admin excluded)")
    
    def test_summaries_have_required_fields(self, admin_token):
        """Each summary has user_email, user_name, limits_remaining, total_credits_used, etc."""
        res = requests.get(f"{BASE_URL}/api/admin-9821/usage/user-summaries",
                          headers={"Authorization": f"Bearer {admin_token}"})
        summaries = res.json()
        
        required_fields = ["user_id", "user_email", "user_name", "limits_remaining", 
                          "total_credits_used", "total_audio_seconds", "total_generations", 
                          "total_storage_used", "total_failed_generations"]
        for s in summaries[:3]:
            for field in required_fields:
                assert field in s, f"Summary for {s.get('user_email')} missing field: {field}"
        print("All summaries have required fields")
    
    def test_storyfy_in_summaries_with_correct_usage(self, admin_token):
        """StoryFy user in summaries shows 22 credits and 1 generation"""
        res = requests.get(f"{BASE_URL}/api/admin-9821/usage/user-summaries",
                          headers={"Authorization": f"Bearer {admin_token}"})
        summaries = res.json()
        storyfy = next((s for s in summaries if s.get("user_email") == STORYFY_EMAIL), None)
        
        assert storyfy, "StoryFy user not in summaries"
        assert storyfy.get("total_credits_used") == 22, f"Expected 22, got {storyfy.get('total_credits_used')}"
        assert storyfy.get("total_generations") == 1, f"Expected 1, got {storyfy.get('total_generations')}"
        print(f"StoryFy in summaries: credits_used={storyfy.get('total_credits_used')}, gens={storyfy.get('total_generations')}")


class TestAdminCreatorUsageDetail:
    """Test GET /api/admin-9821/creators/{user_id}/usage returns detailed per-creator usage"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def storyfy_user_id(self, admin_token):
        """Get StoryFy user_id"""
        res = requests.get(f"{BASE_URL}/api/admin-9821/users",
                          headers={"Authorization": f"Bearer {admin_token}"})
        users = res.json()
        user = next((u for u in users if u.get("email") == STORYFY_EMAIL), None)
        return user.get("user_id") if user else None
    
    def test_returns_detailed_usage(self, admin_token, storyfy_user_id):
        """Returns detailed usage with by_type breakdown and recent_generations"""
        assert storyfy_user_id, "StoryFy user_id not found"
        res = requests.get(f"{BASE_URL}/api/admin-9821/creators/{storyfy_user_id}/usage",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        data = res.json()
        
        # Check required fields
        assert data.get("user_id") == storyfy_user_id
        assert data.get("email") == STORYFY_EMAIL
        assert "total_credits_used" in data
        assert "total_audio_minutes" in data
        assert "total_generations" in data
        assert "total_file_size_bytes" in data
        assert "by_type" in data
        assert "recent_generations" in data
        print(f"Detail endpoint returned: {data.get('total_credits_used')} credits, {data.get('total_generations')} gens")
    
    def test_storyfy_detail_correct_values(self, admin_token, storyfy_user_id):
        """StoryFy detail shows 22 credits, 1 generation, by_type voice"""
        res = requests.get(f"{BASE_URL}/api/admin-9821/creators/{storyfy_user_id}/usage",
                          headers={"Authorization": f"Bearer {admin_token}"})
        data = res.json()
        
        assert data.get("total_credits_used") == 22, f"Expected 22, got {data.get('total_credits_used')}"
        assert data.get("total_generations") == 1, f"Expected 1, got {data.get('total_generations')}"
        assert data.get("limits_remaining") == 978, f"Expected 978, got {data.get('limits_remaining')}"
        
        # Check by_type
        by_type = data.get("by_type", [])
        assert len(by_type) == 1, f"Expected 1 type, got {len(by_type)}"
        assert by_type[0].get("type") == "voice"
        assert by_type[0].get("count") == 1
        assert by_type[0].get("credits") == 22
        
        # Check recent_generations
        recent = data.get("recent_generations", [])
        assert len(recent) == 1, f"Expected 1 recent generation, got {len(recent)}"
        assert recent[0].get("type") == "voice"
        assert recent[0].get("credits_used") == 22
        print(f"Detail verified: by_type={by_type}, recent_count={len(recent)}")
    
    def test_nonexistent_user_returns_404(self, admin_token):
        """Non-existent user_id returns 404"""
        res = requests.get(f"{BASE_URL}/api/admin-9821/creators/nonexistent_user/usage",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 404


class TestCreatorUsageMe:
    """Test GET /api/usage/me returns creator's own usage"""
    
    @pytest.fixture(scope="class")
    def creator_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL, "password": CREATOR_PASSWORD
        })
        return res.json()["token"]
    
    def test_returns_user_usage_summary(self, creator_token):
        """Returns limits_remaining, storage_used_mb, total_credits_used, total_generations"""
        res = requests.get(f"{BASE_URL}/api/usage/me",
                          headers={"Authorization": f"Bearer {creator_token}"})
        assert res.status_code == 200
        data = res.json()
        
        required_fields = ["user_id", "limits_remaining", "storage_used_mb", "storage_limit_mb",
                          "total_credits_used", "total_audio_seconds", "total_generations", 
                          "total_storage_used", "total_failed_generations"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        print(f"Usage/me returned: limits_remaining={data.get('limits_remaining')}, credits_used={data.get('total_credits_used')}, gens={data.get('total_generations')}")
    
    def test_unauthorized_returns_401(self):
        """Unauthorized request returns 401"""
        res = requests.get(f"{BASE_URL}/api/usage/me")
        assert res.status_code == 401


class TestDataConsistency:
    """Verify data consistency between admin view and creator's own view"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        res = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def creator_token(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL, "password": CREATOR_PASSWORD
        })
        return res.json()["token"]
    
    @pytest.fixture(scope="class")
    def creator_user_id(self, creator_token):
        res = requests.get(f"{BASE_URL}/api/auth/me",
                          headers={"Authorization": f"Bearer {creator_token}"})
        return res.json().get("user_id")
    
    def test_creator_usage_me_matches_admin_view(self, admin_token, creator_token, creator_user_id):
        """GET /api/usage/me for testapi matches GET /api/admin-9821/creators/{user_id}/usage"""
        # Get creator's own view
        creator_res = requests.get(f"{BASE_URL}/api/usage/me",
                                  headers={"Authorization": f"Bearer {creator_token}"})
        assert creator_res.status_code == 200
        creator_data = creator_res.json()
        
        # Get admin's view of same user
        admin_res = requests.get(f"{BASE_URL}/api/admin-9821/creators/{creator_user_id}/usage",
                                headers={"Authorization": f"Bearer {admin_token}"})
        assert admin_res.status_code == 200
        admin_data = admin_res.json()
        
        # Compare key fields
        assert creator_data.get("limits_remaining") == admin_data.get("limits_remaining"), \
            f"limits_remaining mismatch: creator={creator_data.get('limits_remaining')}, admin={admin_data.get('limits_remaining')}"
        assert creator_data.get("total_credits_used") == admin_data.get("total_credits_used"), \
            f"total_credits_used mismatch: creator={creator_data.get('total_credits_used')}, admin={admin_data.get('total_credits_used')}"
        assert creator_data.get("total_generations") == admin_data.get("total_generations"), \
            f"total_generations mismatch: creator={creator_data.get('total_generations')}, admin={admin_data.get('total_generations')}"
        
        print(f"Data consistency VERIFIED: creator and admin see same values for user {creator_user_id}")
        print(f"  limits_remaining={creator_data.get('limits_remaining')}, credits_used={creator_data.get('total_credits_used')}, gens={creator_data.get('total_generations')}")
    
    def test_admin_users_list_matches_user_summaries(self, admin_token):
        """/admin-9821/users and /usage/user-summaries show same usage data for same user"""
        # Get from /users
        users_res = requests.get(f"{BASE_URL}/api/admin-9821/users",
                                headers={"Authorization": f"Bearer {admin_token}"})
        users = users_res.json()
        storyfy_from_users = next((u for u in users if u.get("email") == STORYFY_EMAIL), None)
        
        # Get from /usage/user-summaries
        summaries_res = requests.get(f"{BASE_URL}/api/admin-9821/usage/user-summaries",
                                    headers={"Authorization": f"Bearer {admin_token}"})
        summaries = summaries_res.json()
        storyfy_from_summaries = next((s for s in summaries if s.get("user_email") == STORYFY_EMAIL), None)
        
        assert storyfy_from_users and storyfy_from_summaries
        
        # Compare
        assert storyfy_from_users.get("total_credits_used") == storyfy_from_summaries.get("total_credits_used"), \
            f"credits_used mismatch: users={storyfy_from_users.get('total_credits_used')}, summaries={storyfy_from_summaries.get('total_credits_used')}"
        assert storyfy_from_users.get("total_generations") == storyfy_from_summaries.get("total_generations"), \
            f"generations mismatch: users={storyfy_from_users.get('total_generations')}, summaries={storyfy_from_summaries.get('total_generations')}"
        
        print(f"Admin endpoints consistent: /users and /usage/user-summaries show same StoryFy usage data")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
