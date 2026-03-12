"""
Test: Multi-Provider Voice Generation System
Features tested:
- Admin voice settings API - GET/POST /api/admin-9821/voice-settings
- Creator TTS settings API - GET /api/tts/settings
- Creator voices API - GET /api/voices
- Provider switching between elevenlabs (default) and gemini (alternate)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@admin.com"
ADMIN_PASSWORD = "admin123"
CREATOR_EMAIL = "testapi@test.com"
CREATOR_PASSWORD = "password123"


class TestAdminAuth:
    """Test admin authentication for voice settings access"""
    
    def test_admin_login(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful, token obtained")
        return data["token"]


class TestCreatorAuth:
    """Test creator authentication for TTS settings access"""
    
    def test_creator_login(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        assert response.status_code == 200, f"Creator login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "creator"
        print(f"✓ Creator login successful, token obtained")
        return data["token"]


class TestAdminVoiceSettings:
    """Test admin voice settings endpoints - GET/POST /api/admin-9821/voice-settings"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_get_voice_settings_returns_current_provider(self, admin_token):
        """GET /api/admin-9821/voice-settings returns current active provider"""
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "activeProvider" in data, "Response should contain activeProvider"
        assert data["activeProvider"] in ["elevenlabs", "gemini"], f"Invalid provider: {data['activeProvider']}"
        print(f"✓ GET /api/admin-9821/voice-settings - activeProvider: {data['activeProvider']}")
        return data["activeProvider"]
    
    def test_switch_to_gemini_provider(self, admin_token):
        """POST /api/admin-9821/voice-settings switches provider to gemini"""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "gemini"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["activeProvider"] == "gemini", f"Provider not switched to gemini: {data}"
        print(f"✓ POST /api/admin-9821/voice-settings - switched to gemini")
    
    def test_switch_to_elevenlabs_provider(self, admin_token):
        """POST /api/admin-9821/voice-settings switches provider to elevenlabs"""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "elevenlabs"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["activeProvider"] == "elevenlabs", f"Provider not switched to elevenlabs: {data}"
        print(f"✓ POST /api/admin-9821/voice-settings - switched to elevenlabs")
    
    def test_invalid_provider_rejected(self, admin_token):
        """POST /api/admin-9821/voice-settings rejects invalid provider"""
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "invalid_provider"}
        )
        assert response.status_code == 400, f"Expected 400, got: {response.status_code}"
        print(f"✓ POST /api/admin-9821/voice-settings - rejected invalid provider")
    
    def test_voice_settings_requires_admin_auth(self):
        """Voice settings endpoints require admin authentication"""
        # GET without auth
        response = requests.get(f"{BASE_URL}/api/admin-9821/voice-settings")
        assert response.status_code in [401, 403], f"Expected 401/403, got: {response.status_code}"
        
        # POST without auth
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            json={"activeProvider": "gemini"}
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got: {response.status_code}"
        print(f"✓ Voice settings endpoints correctly require admin auth")


class TestCreatorTTSSettings:
    """Test creator TTS settings endpoint - GET /api/tts/settings"""
    
    @pytest.fixture
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_tts_settings_with_elevenlabs(self, admin_token, creator_token):
        """GET /api/tts/settings returns default engine config when ElevenLabs active"""
        # First ensure ElevenLabs is active
        requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "elevenlabs"}
        )
        time.sleep(0.5)  # Allow setting to propagate
        
        response = requests.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify ElevenLabs config
        assert data.get("engineType") == "default", f"Expected engineType 'default', got: {data.get('engineType')}"
        assert "controls" in data, "Response should contain controls"
        assert "stability" in data["controls"], "ElevenLabs should have stability control"
        assert "similarity" in data["controls"], "ElevenLabs should have similarity control"
        assert "style" in data["controls"], "ElevenLabs should have style control"
        assert "speed" in data["controls"], "ElevenLabs should have speed control"
        assert "speakerBoost" in data["controls"], "ElevenLabs should have speakerBoost control"
        assert data.get("voices") is None, "ElevenLabs config should not include voices in settings"
        assert data.get("stylePresets") is None, "ElevenLabs config should not include stylePresets"
        print(f"✓ GET /api/tts/settings (ElevenLabs) - engineType: default, controls: {data['controls']}")
    
    def test_tts_settings_with_gemini(self, admin_token, creator_token):
        """GET /api/tts/settings returns alternate engine config when Gemini active"""
        # Switch to Gemini
        requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "gemini"}
        )
        time.sleep(0.5)  # Allow setting to propagate
        
        response = requests.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify Gemini config
        assert data.get("engineType") == "alternate", f"Expected engineType 'alternate', got: {data.get('engineType')}"
        assert "controls" in data, "Response should contain controls"
        assert "stylePreset" in data["controls"], "Gemini should have stylePreset control"
        assert "customInstructions" in data["controls"], "Gemini should have customInstructions control"
        assert "language" in data["controls"], "Gemini should have language control"
        
        # Verify Gemini does NOT have ElevenLabs-specific controls
        assert "stability" not in data["controls"], "Gemini should NOT have stability control"
        assert "similarity" not in data["controls"], "Gemini should NOT have similarity control"
        
        # Verify Gemini voices list
        assert "voices" in data, "Gemini config should include voices"
        assert isinstance(data["voices"], list), "voices should be a list"
        assert len(data["voices"]) > 0, "Gemini should have at least one voice"
        
        # Verify Gemini style presets
        assert "stylePresets" in data, "Gemini config should include stylePresets"
        assert isinstance(data["stylePresets"], list), "stylePresets should be a list"
        expected_presets = ["storytelling", "emotional", "dramatic", "calm", "horror", "casual"]
        for preset in expected_presets:
            assert preset in data["stylePresets"], f"Missing preset: {preset}"
        
        print(f"✓ GET /api/tts/settings (Gemini) - engineType: alternate, voices: {len(data['voices'])}, presets: {data['stylePresets']}")
        
        # Reset to ElevenLabs
        requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "elevenlabs"}
        )


class TestCreatorVoices:
    """Test creator voices endpoint - GET /api/voices"""
    
    @pytest.fixture
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_voices_returns_gemini_voices_when_gemini_active(self, admin_token, creator_token):
        """GET /api/voices returns Gemini voices when Gemini is active provider"""
        # Switch to Gemini
        requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "gemini"}
        )
        time.sleep(0.5)
        
        response = requests.get(
            f"{BASE_URL}/api/voices",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "voices" in data, "Response should contain voices"
        voices = data["voices"]
        
        # Verify Gemini voices
        gemini_voice_names = ["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda", "Orus", "Zephyr"]
        voice_ids = [v["voice_id"] for v in voices]
        voice_names = [v["name"] for v in voices]
        
        for name in gemini_voice_names:
            assert name in voice_ids or name in voice_names, f"Missing Gemini voice: {name}"
        
        print(f"✓ GET /api/voices (Gemini) - returned {len(voices)} Gemini voices: {voice_names}")
        
        # Reset to ElevenLabs
        requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "elevenlabs"}
        )
    
    def test_voices_returns_elevenlabs_voices_when_elevenlabs_active(self, admin_token, creator_token):
        """GET /api/voices returns ElevenLabs voices when ElevenLabs is active provider"""
        # Ensure ElevenLabs is active
        requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "elevenlabs"}
        )
        time.sleep(0.5)
        
        response = requests.get(
            f"{BASE_URL}/api/voices",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "voices" in data, "Response should contain voices"
        voices = data["voices"]
        
        # ElevenLabs voices should NOT be Gemini voices
        gemini_voice_names = ["Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda", "Orus", "Zephyr"]
        voice_names = [v["name"] for v in voices]
        
        # Check it's not returning Gemini voices (at least not all of them)
        gemini_count = sum(1 for name in gemini_voice_names if name in voice_names)
        assert gemini_count == 0 or gemini_count < len(gemini_voice_names), "Should return ElevenLabs voices, not Gemini"
        
        print(f"✓ GET /api/voices (ElevenLabs) - returned {len(voices)} ElevenLabs voices")


class TestProviderNameHiding:
    """Test that provider names (ElevenLabs, Gemini) are NOT exposed to creators"""
    
    @pytest.fixture
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    def test_tts_settings_does_not_expose_provider_name(self, admin_token, creator_token):
        """GET /api/tts/settings should use generic names (default/alternate), not provider names"""
        for provider in ["elevenlabs", "gemini"]:
            # Switch provider
            requests.post(
                f"{BASE_URL}/api/admin-9821/voice-settings",
                headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                json={"activeProvider": provider}
            )
            time.sleep(0.3)
            
            response = requests.get(
                f"{BASE_URL}/api/tts/settings",
                headers={"Authorization": f"Bearer {creator_token}"}
            )
            assert response.status_code == 200
            data = response.json()
            
            # Check response text doesn't contain provider names
            response_str = str(data).lower()
            assert "elevenlabs" not in response_str, f"Response should not contain 'elevenlabs': {data}"
            assert "gemini" not in response_str, f"Response should not contain 'gemini': {data}"
            
            # Verify it uses generic engine type
            assert data.get("engineType") in ["default", "alternate"], f"engineType should be generic: {data.get('engineType')}"
        
        print("✓ Provider names not exposed in TTS settings response")
        
        # Reset to ElevenLabs
        requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "elevenlabs"}
        )


class TestFullProviderSwitchCycle:
    """Test complete provider switch cycle"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/admin-9821/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return response.json()["token"]
    
    @pytest.fixture
    def creator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CREATOR_EMAIL,
            "password": CREATOR_PASSWORD
        })
        return response.json()["token"]
    
    def test_full_switch_cycle(self, admin_token, creator_token):
        """Test: Default -> Gemini -> Default (full cycle with verification)"""
        
        # Step 1: Ensure starting state is ElevenLabs (default)
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "elevenlabs"}
        )
        assert response.status_code == 200
        print("✓ Step 1: Set provider to ElevenLabs (default)")
        time.sleep(0.5)
        
        # Step 2: Verify creator gets default engine settings
        response = requests.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["engineType"] == "default"
        assert "stability" in data["controls"]
        print("✓ Step 2: Creator sees default engine settings")
        
        # Step 3: Switch to Gemini
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "gemini"}
        )
        assert response.status_code == 200
        print("✓ Step 3: Admin switched provider to Gemini")
        time.sleep(0.5)
        
        # Step 4: Verify admin sees Gemini active
        response = requests.get(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert response.json()["activeProvider"] == "gemini"
        print("✓ Step 4: Admin voice settings shows Gemini active")
        
        # Step 5: Verify creator gets alternate engine settings
        response = requests.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["engineType"] == "alternate"
        assert "stylePreset" in data["controls"]
        assert data["voices"] is not None
        print("✓ Step 5: Creator sees alternate engine settings with style presets and voices")
        
        # Step 6: Verify creator gets Gemini voices
        response = requests.get(
            f"{BASE_URL}/api/voices",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        voices = response.json()["voices"]
        voice_names = [v["name"] for v in voices]
        assert "Kore" in voice_names, "Gemini voice 'Kore' should be present"
        print(f"✓ Step 6: Creator gets Gemini voices: {voice_names[:4]}...")
        
        # Step 7: Switch back to ElevenLabs
        response = requests.post(
            f"{BASE_URL}/api/admin-9821/voice-settings",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"activeProvider": "elevenlabs"}
        )
        assert response.status_code == 200
        print("✓ Step 7: Admin switched provider back to ElevenLabs")
        time.sleep(0.5)
        
        # Step 8: Verify creator gets default settings again
        response = requests.get(
            f"{BASE_URL}/api/tts/settings",
            headers={"Authorization": f"Bearer {creator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["engineType"] == "default"
        print("✓ Step 8: Creator sees default engine settings again")
        
        print("\n✓ FULL PROVIDER SWITCH CYCLE COMPLETE")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
