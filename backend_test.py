#!/usr/bin/env python3

import requests
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

class StoryFyAPITester:
    def __init__(self, base_url="https://code-importer-41.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.token = None
        self.user_data = None
        self.tests_run = 0
        self.tests_passed = 0
        self.current_story_id = None
        self.current_episode_id = None
        self.current_character_id = None
        self.current_asset_id = None

    def log(self, message):
        """Log test messages"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, 
                 data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
                 files: Optional[Dict[str, Any]] = None) -> tuple[bool, Dict[str, Any]]:
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if headers:
            test_headers.update(headers)
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                if files:
                    # Remove Content-Type header for multipart/form-data requests
                    test_headers.pop('Content-Type', None)
                    response = requests.post(url, headers=test_headers, data=data, files=files, timeout=30)
                else:
                    response = requests.post(url, headers=test_headers, json=data, timeout=30)
            elif method == 'PUT':
                if files:
                    test_headers.pop('Content-Type', None)
                    response = requests.put(url, headers=test_headers, data=data, files=files, timeout=30)
                else:
                    response = requests.put(url, headers=test_headers, json=data, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ Passed - Status: {response.status_code}")
            else:
                self.log(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                if response.text:
                    self.log(f"Response: {response.text[:200]}...")

            try:
                response_data = response.json() if response.text else {}
            except json.JSONDecodeError:
                response_data = {"raw_response": response.text}

            return success, response_data

        except requests.exceptions.Timeout:
            self.log(f"❌ Failed - Request timeout")
            return False, {"error": "timeout"}
        except Exception as e:
            self.log(f"❌ Failed - Error: {str(e)}")
            return False, {"error": str(e)}

    def test_auth_signup(self, name: str, email: str, password: str) -> bool:
        """Test user signup"""
        success, response = self.run_test(
            "User Signup",
            "POST",
            "auth/signup",
            200,
            data={"name": name, "email": email, "password": password}
        )
        
        if success and 'token' in response and 'user' in response:
            self.token = response['token']
            self.user_data = response['user']
            self.log(f"✅ User created: {self.user_data['name']} ({self.user_data['email']})")
            return True
        return False

    def test_auth_login(self, email: str, password: str) -> bool:
        """Test user login"""
        success, response = self.run_test(
            "User Login",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password}
        )
        
        if success and 'token' in response and 'user' in response:
            self.token = response['token']
            self.user_data = response['user']
            self.log(f"✅ User logged in: {self.user_data['name']}")
            return True
        return False

    def test_auth_me(self) -> bool:
        """Test get current user"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        
        if success and 'user_id' in response:
            self.log(f"✅ Current user: {response.get('name', 'N/A')}")
            return True
        return False

    def test_story_creation(self, title: str, genre: str, description: str) -> bool:
        """Test story creation"""
        success, response = self.run_test(
            "Create Story",
            "POST",
            "stories",
            200,
            data={
                "title": title,
                "genre": genre,
                "language": "English",
                "description": description,
                "story_type": "story"
            }
        )
        
        if success and 'story_id' in response:
            self.current_story_id = response['story_id']
            self.log(f"✅ Story created: {response['title']} (ID: {self.current_story_id})")
            return True
        return False

    def test_get_stories(self) -> bool:
        """Test get stories"""
        success, response = self.run_test(
            "Get Stories",
            "GET",
            "stories",
            200
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Retrieved {len(response)} stories")
            return True
        return False

    def test_episode_creation(self, title: str, order: int) -> bool:
        """Test episode creation"""
        if not self.current_story_id:
            self.log("❌ No story ID available for episode creation")
            return False
            
        success, response = self.run_test(
            "Create Episode",
            "POST",
            "episodes",
            200,
            data={
                "story_id": self.current_story_id,
                "title": title,
                "order": order,
                "script": "Test script content"
            }
        )
        
        if success and 'episode_id' in response:
            self.current_episode_id = response['episode_id']
            self.log(f"✅ Episode created: {response['title']} (ID: {self.current_episode_id})")
            return True
        return False

    def test_get_episodes(self) -> bool:
        """Test get episodes for story"""
        if not self.current_story_id:
            self.log("❌ No story ID available for getting episodes")
            return False
            
        success, response = self.run_test(
            "Get Episodes",
            "GET",
            f"episodes/story/{self.current_story_id}",
            200
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Retrieved {len(response)} episodes")
            return True
        return False

    def test_character_creation(self, name: str) -> bool:
        """Test character creation"""
        if not self.current_story_id:
            self.log("❌ No story ID available for character creation")
            return False
            
        success, response = self.run_test(
            "Create Character",
            "POST",
            "characters",
            200,
            data={
                "story_id": self.current_story_id,
                "name": name,
                "voice_id": None,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0
                }
            }
        )
        
        if success and 'character_id' in response:
            self.current_character_id = response['character_id']
            self.log(f"✅ Character created: {response['name']} (ID: {self.current_character_id})")
            return True
        return False

    def test_get_characters(self) -> bool:
        """Test get characters for story"""
        if not self.current_story_id:
            self.log("❌ No story ID available for getting characters")
            return False
            
        success, response = self.run_test(
            "Get Characters",
            "GET",
            f"characters/story/{self.current_story_id}",
            200
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Retrieved {len(response)} characters")
            return True
        return False

    def test_get_voices(self) -> bool:
        """Test get ElevenLabs voices"""
        success, response = self.run_test(
            "Get ElevenLabs Voices",
            "GET",
            "voices",
            200
        )
        
        if success and 'voices' in response and isinstance(response['voices'], list):
            self.log(f"✅ Retrieved {len(response['voices'])} voices from ElevenLabs")
            return True
        return False

    def test_tts_generation(self) -> bool:
        """Test TTS generation with ElevenLabs"""
        # First get voices to use one
        voices_success, voices_response = self.run_test(
            "Get Voices for TTS",
            "GET",
            "voices",
            200
        )
        
        if not voices_success or not voices_response.get('voices'):
            self.log("❌ No voices available for TTS test")
            return False
            
        # Use the first available voice
        voice_id = voices_response['voices'][0]['voice_id']
        
        success, response = self.run_test(
            "Generate TTS",
            "POST",
            "tts/generate",
            200,
            data={
                "text": "Hello, this is a test of the text-to-speech functionality.",
                "voice_id": voice_id,
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        )
        
        if success and 'audio_url' in response:
            self.log(f"✅ TTS generated successfully with voice {voice_id}")
            return True
        return False

    def test_audio_assets(self) -> bool:
        """Test get audio assets"""
        if not self.current_story_id:
            self.log("❌ No story ID available for getting audio assets")
            return False
            
        success, response = self.run_test(
            "Get Audio Assets",
            "GET",
            f"audio/assets/{self.current_story_id}",
            200
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Retrieved {len(response)} audio assets")
            return True
        return False

    def test_logout(self) -> bool:
        """Test user logout"""
        success, response = self.run_test(
            "User Logout",
            "POST",
            "auth/logout",
            200
        )
        
        if success:
            self.token = None
            self.user_data = None
            self.log("✅ User logged out successfully")
            return True
        return False

    def run_comprehensive_tests(self):
        """Run all API tests"""
        self.log("🚀 Starting StoryFy API comprehensive testing...")
        
        # Test data
        timestamp = int(time.time())
        test_email = f"test_user_{timestamp}@storyfy.com"
        test_password = "TestPass123!"
        test_name = f"Test User {timestamp}"
        
        # Authentication Tests
        self.log("\n📋 AUTHENTICATION TESTS")
        self.test_auth_signup(test_name, test_email, test_password)
        
        if self.token:
            self.test_auth_me()
            
            # Content Creation Tests
            self.log("\n📚 STORY MANAGEMENT TESTS")
            self.test_story_creation("Test Story", "fiction", "A test story for API validation")
            self.test_get_stories()
            
            # Episode Tests
            self.log("\n🎬 EPISODE MANAGEMENT TESTS")
            self.test_episode_creation("Episode 1: The Beginning", 1)
            self.test_get_episodes()
            
            # Character Tests
            self.log("\n👤 CHARACTER MANAGEMENT TESTS")
            self.test_character_creation("Test Character")
            self.test_get_characters()
            
            # ElevenLabs Integration Tests
            self.log("\n🔊 ELEVENLABS INTEGRATION TESTS")
            self.test_get_voices()
            # Give ElevenLabs API some time between requests
            time.sleep(2)
            self.test_tts_generation()
            
            # Audio Asset Tests
            self.log("\n🎵 AUDIO ASSET TESTS")
            self.test_audio_assets()
            
            # Cleanup
            self.log("\n🧹 CLEANUP TESTS")
            self.test_logout()
        
        # Test login with existing user
        self.log("\n🔐 LOGIN TEST WITH EXISTING USER")
        self.test_auth_login(test_email, test_password)
        
        self.print_results()

    def print_results(self):
        """Print final test results"""
        self.log("\n" + "="*60)
        self.log("🏁 FINAL TEST RESULTS")
        self.log("="*60)
        self.log(f"Tests run: {self.tests_run}")
        self.log(f"Tests passed: {self.tests_passed}")
        self.log(f"Tests failed: {self.tests_run - self.tests_passed}")
        self.log(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0.0%")
        
        if self.tests_passed == self.tests_run:
            self.log("🎉 ALL TESTS PASSED!")
        else:
            self.log("⚠️  Some tests failed. Check the logs above for details.")
        
        return self.tests_passed == self.tests_run

def main():
    """Main function to run the tests"""
    tester = StoryFyAPITester()
    success = tester.run_comprehensive_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())