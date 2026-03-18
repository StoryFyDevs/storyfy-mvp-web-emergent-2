"""
Test Suite: Character-based Voice Workflow & Audition Credit System (Iteration 17)

Tests:
- GET /api/credits returns both generation_credits and audition_credits
- POST /api/tts/audition generates audio, deducts audition credit, caches result
- Cached audition calls return cached=true without deducting credit
- POST /api/admin-9821/users/audition-credits adjusts audition credits
- GET /api/admin-9821/users returns audition_credits field

Requirements verified:
- Dual credit system (generation_credits + audition_credits)
- Audition caching to avoid re-deduction
- Admin can view/modify both credit types per user
"""
import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://daw-timeline-demo.preview.emergentagent.com')

@pytest.fixture(scope="module")
def creator_token():
    """Get creator authentication token"""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "testapi@test.com",
        "password": "password123"
    })
    assert res.status_code == 200, f"Creator login failed: {res.text}"
    return res.json()["token"]

@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    res = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
        "email": "admin@admin.com",
        "password": "admin123"
    })
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    return res.json()["token"]

@pytest.fixture(scope="module")
def creator_user_id():
    """Get creator user_id from login"""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "testapi@test.com",
        "password": "password123"
    })
    return res.json()["user"]["user_id"]


class TestDualCreditsEndpoint:
    """Tests for GET /api/credits returning both credit types"""
    
    def test_credits_returns_both_generation_and_audition(self, creator_token):
        """GET /api/credits returns both generation_credits and audition_credits"""
        res = requests.get(
            f"{BASE_URL}/api/credits",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert res.status_code == 200
        data = res.json()
        
        # Verify both credit types are present
        assert "generation_credits" in data, "Missing generation_credits field"
        assert "audition_credits" in data, "Missing audition_credits field"
        
        # Verify they are numeric
        assert isinstance(data["generation_credits"], (int, float)), "generation_credits must be numeric"
        assert isinstance(data["audition_credits"], (int, float)), "audition_credits must be numeric"
        
        print(f"Credits response: generation={data['generation_credits']}, audition={data['audition_credits']}")


class TestAuditionEndpoint:
    """Tests for POST /api/tts/audition with caching"""
    
    def test_audition_requires_voice_id_and_text(self, creator_token):
        """POST /api/tts/audition requires voice_id and text"""
        # Missing voice_id
        res = requests.post(
            f"{BASE_URL}/api/tts/audition",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={"text": "Hello world"}
        )
        assert res.status_code == 400, "Should reject missing voice_id"
        
        # Missing text
        res = requests.post(
            f"{BASE_URL}/api/tts/audition",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={"voice_id": "Kore"}
        )
        assert res.status_code == 400, "Should reject missing text"
        
        # Empty text
        res = requests.post(
            f"{BASE_URL}/api/tts/audition",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={"voice_id": "Kore", "text": "   "}
        )
        assert res.status_code == 400, "Should reject empty text"
    
    def test_audition_generates_audio_and_deducts_credit(self, creator_token):
        """POST /api/tts/audition generates audio and deducts 1 audition credit"""
        # Get initial credits
        credits_res = requests.get(
            f"{BASE_URL}/api/credits",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        initial_audition_credits = credits_res.json()["audition_credits"]
        
        # Generate unique test text to avoid cache hit
        unique_text = f"टेस्ट ऑडिशन {uuid.uuid4().hex[:8]}"
        
        # Call audition endpoint
        res = requests.post(
            f"{BASE_URL}/api/tts/audition",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={"voice_id": "Kore", "text": unique_text},
            timeout=90
        )
        assert res.status_code == 200, f"Audition failed: {res.text}"
        data = res.json()
        
        # Verify response structure
        assert "audio_url" in data, "Missing audio_url"
        assert "duration_seconds" in data, "Missing duration_seconds"
        assert "cached" in data, "Missing cached field"
        assert data["cached"] == False, "First call should not be cached"
        assert data["audio_url"].startswith("data:audio/"), "audio_url should be data URL"
        
        # Verify credit was deducted
        credits_res = requests.get(
            f"{BASE_URL}/api/credits",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        new_audition_credits = credits_res.json()["audition_credits"]
        assert new_audition_credits == initial_audition_credits - 1, \
            f"Expected {initial_audition_credits - 1}, got {new_audition_credits}"
        
        print(f"Audition generated: cached={data['cached']}, duration={data['duration_seconds']}s")
        return unique_text  # Return for cache test
    
    def test_audition_cached_call_does_not_deduct_credit(self, creator_token):
        """Repeated audition with same voice_id+text returns cached=true without deducting credit"""
        # Use a specific text for this test
        test_text = "यह कैश परीक्षण है"
        
        # First call - may or may not be cached depending on previous test runs
        res1 = requests.post(
            f"{BASE_URL}/api/tts/audition",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={"voice_id": "Achernar", "text": test_text},
            timeout=90
        )
        assert res1.status_code == 200
        
        # Get credits after first call
        credits_res = requests.get(
            f"{BASE_URL}/api/credits",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        credits_after_first = credits_res.json()["audition_credits"]
        
        # Second call - should be cached
        res2 = requests.post(
            f"{BASE_URL}/api/tts/audition",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={"voice_id": "Achernar", "text": test_text},
            timeout=90
        )
        assert res2.status_code == 200
        data2 = res2.json()
        
        # Verify cached=true
        assert data2["cached"] == True, "Second call should be cached"
        
        # Verify credit was NOT deducted
        credits_res = requests.get(
            f"{BASE_URL}/api/credits",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        credits_after_second = credits_res.json()["audition_credits"]
        assert credits_after_second == credits_after_first, \
            f"Cached call should not deduct credits: before={credits_after_first}, after={credits_after_second}"
        
        print(f"Cached audition: cached={data2['cached']}, credits unchanged at {credits_after_second}")


class TestAdminAuditionCredits:
    """Tests for admin audition credit management"""
    
    def test_admin_users_list_includes_audition_credits(self, admin_token):
        """GET /api/admin-9821/users returns audition_credits for each user"""
        res = requests.get(
            f"{BASE_URL}/api/admin-9821/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert res.status_code == 200
        users = res.json()
        
        assert len(users) > 0, "Expected at least one user"
        
        # Check that audition_credits field exists for all users
        for user in users[:5]:  # Check first 5
            assert "audition_credits" in user, f"Missing audition_credits for user {user.get('email')}"
            assert isinstance(user["audition_credits"], (int, float)), "audition_credits must be numeric"
            # Also verify generation credits (limits_remaining) is present
            assert "limits_remaining" in user, f"Missing limits_remaining for user {user.get('email')}"
        
        print(f"Checked {min(5, len(users))} users - all have audition_credits field")
    
    def test_admin_adjust_audition_credits_add(self, admin_token, creator_user_id):
        """POST /api/admin-9821/users/audition-credits can add credits"""
        # Get initial credits
        users_res = requests.get(
            f"{BASE_URL}/api/admin-9821/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        user = next((u for u in users_res.json() if u["user_id"] == creator_user_id), None)
        assert user is not None, "Test user not found"
        initial_credits = user.get("audition_credits", 0)
        
        # Add credits
        res = requests.post(
            f"{BASE_URL}/api/admin-9821/users/audition-credits",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": creator_user_id, "amount": 50, "reason": "Test add audition credits"}
        )
        assert res.status_code == 200, f"Add credits failed: {res.text}"
        data = res.json()
        
        assert data["new_balance"] == initial_credits + 50, \
            f"Expected {initial_credits + 50}, got {data['new_balance']}"
        
        print(f"Added 50 audition credits: {initial_credits} -> {data['new_balance']}")
    
    def test_admin_adjust_audition_credits_deduct(self, admin_token, creator_user_id):
        """POST /api/admin-9821/users/audition-credits can deduct credits"""
        # Get initial credits
        users_res = requests.get(
            f"{BASE_URL}/api/admin-9821/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        user = next((u for u in users_res.json() if u["user_id"] == creator_user_id), None)
        initial_credits = user.get("audition_credits", 0)
        
        # Deduct credits
        res = requests.post(
            f"{BASE_URL}/api/admin-9821/users/audition-credits",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": creator_user_id, "amount": -20, "reason": "Test deduct audition credits"}
        )
        assert res.status_code == 200, f"Deduct credits failed: {res.text}"
        data = res.json()
        
        assert data["new_balance"] == initial_credits - 20, \
            f"Expected {initial_credits - 20}, got {data['new_balance']}"
        
        print(f"Deducted 20 audition credits: {initial_credits} -> {data['new_balance']}")
    
    def test_admin_cannot_set_negative_audition_credits(self, admin_token, creator_user_id):
        """POST /api/admin-9821/users/audition-credits rejects negative balance"""
        res = requests.post(
            f"{BASE_URL}/api/admin-9821/users/audition-credits",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"user_id": creator_user_id, "amount": -99999, "reason": "Should fail"}
        )
        assert res.status_code == 400, "Should reject setting negative balance"
    
    def test_admin_audition_credits_requires_admin_auth(self, creator_token, creator_user_id):
        """POST /api/admin-9821/users/audition-credits requires admin authentication"""
        res = requests.post(
            f"{BASE_URL}/api/admin-9821/users/audition-credits",
            headers={"Authorization": f"Bearer {creator_token}", "Content-Type": "application/json"},
            json={"user_id": creator_user_id, "amount": 10, "reason": "Should fail"}
        )
        assert res.status_code in [401, 403], "Should reject non-admin users"


class TestVoicesAndCharacters:
    """Tests for voices endpoint with Indian names and categories"""
    
    def test_voices_have_indian_display_names_and_categories(self, creator_token):
        """GET /api/tts/settings returns voices with Indian names grouped by category"""
        res = requests.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert res.status_code == 200
        data = res.json()
        
        # Verify voices are present
        voices = data.get("voices", [])
        assert len(voices) == 30, f"Expected 30 voices, got {len(voices)}"
        
        # Verify categories are present
        categories = data.get("voiceCategories", {})
        assert len(categories) == 5, f"Expected 5 categories, got {len(categories)}"
        assert "narrator" in categories
        assert "energetic" in categories
        assert "calm" in categories
        
        # Check sample voice has required fields
        sample_voice = voices[0]
        assert "voice_id" in sample_voice
        assert "name" in sample_voice  # Indian display name
        assert "tone" in sample_voice
        assert "gender" in sample_voice
        assert "category" in sample_voice
        assert "category_label" in sample_voice
        
        # Verify Indian names (spot check)
        names = [v["name"] for v in voices]
        assert "Aarohi" in names, "Missing Indian name Aarohi"
        assert "Arjun" in names, "Missing Indian name Arjun"
        
        print(f"Voices have {len(voices)} entries with Indian names and {len(categories)} categories")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
