"""
Test suite for Gemini 30 Voices Upgrade
Tests: 
- All 30 Gemini voices are returned
- Dual-layer naming (original voice_id + Indian display names)
- Category grouping (Narrator, Deep Voice, Energetic, Calm, Dramatic)
- Admin technical details view
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Expected 30 Gemini voice IDs (Achernar through Zubenelgenubi alphabetically)
EXPECTED_VOICE_IDS = [
    "Achernar", "Achird", "Algenib", "Algieba", "Alnilam", "Aoede", "Autonoe",
    "Callirrhoe", "Charon", "Despina", "Enceladus", "Erinome", "Fenrir", "Gacrux",
    "Iapetus", "Kore", "Laomedeia", "Leda", "Orus", "Puck", "Pulcherrima",
    "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar", "Sulafat", "Umbriel",
    "Vindemiatrix", "Zephyr", "Zubenelgenubi"
]

# Expected Indian display names mapping
EXPECTED_DISPLAY_NAMES = {
    "Achernar": "Aarohi", "Achird": "Arjun", "Algenib": "Kabir", "Algieba": "Vihaan",
    "Alnilam": "Dev", "Aoede": "Meher", "Autonoe": "Tara", "Callirrhoe": "Naina",
    "Charon": "Samar", "Despina": "Rhea", "Enceladus": "Raghav", "Erinome": "Ira",
    "Fenrir": "Aryan", "Gacrux": "Shobha", "Iapetus": "Neel", "Kore": "Kavya",
    "Laomedeia": "Myra", "Leda": "Kiara", "Orus": "Veer", "Puck": "Yash",
    "Pulcherrima": "Ritika", "Rasalgethi": "Aditya", "Sadachbia": "Karan",
    "Sadaltager": "Manav", "Schedar": "Rahul", "Sulafat": "Aisha", "Umbriel": "Rudra",
    "Vindemiatrix": "Suman", "Zephyr": "Zoya", "Zubenelgenubi": "Aman"
}

# Expected categories
EXPECTED_CATEGORIES = {
    "narrator": "Narrator",
    "deep_voice": "Deep Voice",
    "energetic": "Energetic",
    "calm": "Calm",
    "dramatic": "Dramatic"
}


class TestAuthentication:
    """Authentication setup for tests"""
    
    def test_admin_login(self, api_client):
        """Admin login to get token"""
        response = api_client.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": "admin@admin.com",
            "password": "admin123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        pytest.admin_token = data["token"]
        print(f"✓ Admin login successful")
    
    def test_creator_login(self, api_client):
        """Creator login to get token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "testapi@test.com",
            "password": "password123"
        })
        assert response.status_code == 200, f"Creator login failed: {response.text}"
        data = response.json()
        assert "token" in data
        pytest.creator_token = data["token"]
        print(f"✓ Creator login successful")


class TestSetGeminiActive:
    """Ensure Gemini is the active provider for subsequent tests"""
    
    def test_switch_to_gemini(self, api_client):
        """Switch to Gemini provider"""
        response = api_client.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            json={"activeProvider": "gemini"},
            headers={"Authorization": f"Bearer {pytest.admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("activeProvider") == "gemini"
        print(f"✓ Voice provider set to Gemini")


class TestCreatorTTSSettings:
    """Test GET /api/tts/settings returns all 30 voices with display names"""
    
    def test_returns_30_voices(self, api_client):
        """Verify exactly 30 voices are returned"""
        response = api_client.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check engineType is alternate
        assert data.get("engineType") == "alternate", f"Expected engineType='alternate', got '{data.get('engineType')}'"
        
        # Check voices count
        voices = data.get("voices", [])
        assert len(voices) == 30, f"Expected 30 voices, got {len(voices)}"
        print(f"✓ GET /api/tts/settings returns 30 voices")
    
    def test_voices_have_indian_display_names(self, api_client):
        """Verify voices have Indian display names in 'name' field"""
        response = api_client.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        # Check each voice has correct display name
        for voice in voices:
            voice_id = voice.get("voice_id")
            name = voice.get("name")
            expected_name = EXPECTED_DISPLAY_NAMES.get(voice_id)
            assert name == expected_name, f"Voice {voice_id}: expected name '{expected_name}', got '{name}'"
        
        print(f"✓ All voices have correct Indian display names")
    
    def test_voices_have_tone_labels(self, api_client):
        """Verify voices have tone labels (e.g., 'Soft Storyteller')"""
        response = api_client.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        for voice in voices:
            assert "tone" in voice, f"Voice {voice.get('voice_id')} missing 'tone' field"
            assert voice["tone"], f"Voice {voice.get('voice_id')} has empty 'tone'"
        
        # Spot check some tone labels
        voice_by_id = {v["voice_id"]: v for v in voices}
        assert voice_by_id["Achernar"]["tone"] == "Soft Storyteller"
        assert voice_by_id["Zubenelgenubi"]["tone"] == "Deep & Resonant"
        print(f"✓ All voices have tone labels")
    
    def test_voices_have_gender(self, api_client):
        """Verify voices have gender field"""
        response = api_client.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        for voice in voices:
            assert "gender" in voice, f"Voice {voice.get('voice_id')} missing 'gender' field"
            assert voice["gender"] in ["Male", "Female"], f"Voice {voice.get('voice_id')} has invalid gender: {voice['gender']}"
        
        print(f"✓ All voices have gender field")
    
    def test_voices_have_categories(self, api_client):
        """Verify voices have category and category_label"""
        response = api_client.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        valid_categories = set(EXPECTED_CATEGORIES.keys())
        for voice in voices:
            assert "category" in voice, f"Voice {voice.get('voice_id')} missing 'category'"
            assert "category_label" in voice, f"Voice {voice.get('voice_id')} missing 'category_label'"
            assert voice["category"] in valid_categories, f"Invalid category: {voice['category']}"
            assert voice["category_label"] == EXPECTED_CATEGORIES[voice["category"]]
        
        print(f"✓ All voices have category and category_label")
    
    def test_voice_categories_mapping_returned(self, api_client):
        """Verify voiceCategories map is in response"""
        response = api_client.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        voice_categories = data.get("voiceCategories")
        assert voice_categories is not None, "Missing 'voiceCategories' in response"
        assert voice_categories == EXPECTED_CATEGORIES, f"Expected {EXPECTED_CATEGORIES}, got {voice_categories}"
        print(f"✓ voiceCategories map returned correctly")


class TestCreatorVoicesEndpoint:
    """Test GET /api/voices returns all 30 voices with Indian names"""
    
    def test_returns_30_voices(self, api_client):
        """Verify exactly 30 voices are returned"""
        response = api_client.get(
            f"{BASE_URL}/api/voices",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        assert len(voices) == 30, f"Expected 30 voices, got {len(voices)}"
        print(f"✓ GET /api/voices returns 30 voices")
    
    def test_voice_ids_are_original_gemini_names(self, api_client):
        """Verify voice_id field contains original Gemini voice names"""
        response = api_client.get(
            f"{BASE_URL}/api/voices",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        voice_ids = [v["voice_id"] for v in voices]
        for expected_id in EXPECTED_VOICE_IDS:
            assert expected_id in voice_ids, f"Missing voice_id: {expected_id}"
        
        print(f"✓ All 30 original Gemini voice IDs present (Achernar through Zubenelgenubi)")


class TestAdminVoiceDetails:
    """Test GET /api/admin-9821/voice-settings/voices returns full technical details"""
    
    def test_returns_provider_and_model(self, api_client):
        """Verify provider and model info is returned"""
        response = api_client.get(
            f"{BASE_URL}/api/admin-9821/voice-settings/voices",
            headers={"Authorization": f"Bearer {pytest.admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("provider") == "gemini"
        assert data.get("model") == "gemini-2.5-pro-tts"
        assert data.get("total_voices") == 30
        print(f"✓ Admin voice details includes provider, model, total_voices")
    
    def test_returns_30_voices_with_full_details(self, api_client):
        """Verify all 30 voices have full technical details"""
        response = api_client.get(
            f"{BASE_URL}/api/admin-9821/voice-settings/voices",
            headers={"Authorization": f"Bearer {pytest.admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        assert len(voices) == 30, f"Expected 30 voices, got {len(voices)}"
        
        required_fields = ["voice_id", "display_name", "gender", "tone", "category", "model", "provider"]
        for voice in voices:
            for field in required_fields:
                assert field in voice, f"Voice {voice.get('voice_id')} missing field: {field}"
        
        print(f"✓ All 30 admin voices have full technical details")
    
    def test_voice_id_is_original_not_display_name(self, api_client):
        """Verify voice_id is the original Gemini name, not display name"""
        response = api_client.get(
            f"{BASE_URL}/api/admin-9821/voice-settings/voices",
            headers={"Authorization": f"Bearer {pytest.admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        voice_ids = [v["voice_id"] for v in voices]
        # Check original names are in voice_id
        assert "Achernar" in voice_ids
        assert "Zubenelgenubi" in voice_ids
        # Check display names are NOT in voice_id
        assert "Aarohi" not in voice_ids
        assert "Aman" not in voice_ids
        
        print(f"✓ Admin voice_id contains original Gemini names, not display names")
    
    def test_admin_sees_model_and_provider_per_voice(self, api_client):
        """Verify each voice has model and provider fields"""
        response = api_client.get(
            f"{BASE_URL}/api/admin-9821/voice-settings/voices",
            headers={"Authorization": f"Bearer {pytest.admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        for voice in voices:
            assert voice.get("model") == "gemini-2.5-pro-tts"
            assert voice.get("provider") == "gemini"
        
        print(f"✓ Admin sees model and provider for each voice")


class TestCategoryDistribution:
    """Verify voices are distributed across all 5 categories"""
    
    def test_all_categories_have_voices(self, api_client):
        """Verify each category has at least one voice"""
        response = api_client.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {pytest.creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        voices = data.get("voices", [])
        
        category_counts = {}
        for voice in voices:
            cat = voice.get("category")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        for expected_cat in EXPECTED_CATEGORIES.keys():
            assert expected_cat in category_counts, f"No voices in category: {expected_cat}"
            assert category_counts[expected_cat] > 0, f"Empty category: {expected_cat}"
        
        print(f"✓ Category distribution: {category_counts}")
        print(f"✓ All 5 categories have voices")


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session
