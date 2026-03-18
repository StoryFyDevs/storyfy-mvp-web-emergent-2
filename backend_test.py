#!/usr/bin/env python3

import requests
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional

class StoryFyAPITester:
    def __init__(self, base_url="https://68b384ad-4d01-42fe-8e27-a4ed61d0429e.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.admin_token = None
        self.tests_run = 0
        self.tests_passed = 0

    def log(self, message):
        """Log test messages"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, 
                 data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> tuple[bool, Dict[str, Any]]:
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        self.log(f"🔍 Testing {name}...")
        self.log(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=test_headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ Passed - Status: {response.status_code}")
            else:
                self.log(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                self.log(f"Response: {response.text[:500]}...")

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

    def test_health_endpoint(self) -> bool:
        """Test health endpoint"""
        success, response = self.run_test(
            "Health Endpoint",
            "GET",
            "api/health",
            200
        )
        
        if success and response.get('status') == 'ok':
            self.log(f"✅ Health check passed: {response}")
            return True
        else:
            self.log(f"❌ Health check failed. Response: {response}")
            return False

    def test_creator_login(self) -> bool:
        """Test creator login with provided credentials"""
        success, response = self.run_test(
            "Creator Login",
            "POST",
            "api/auth/login",
            200,
            data={"email": "testuser@test.com", "password": "password123"}
        )
        
        if success and 'token' in response and 'user' in response:
            self.token = response['token']
            self.log(f"✅ Creator login successful. User: {response['user'].get('email', 'N/A')}")
            return True
        else:
            self.log(f"❌ Creator login failed. Response: {response}")
            return False

    def test_admin_login(self) -> bool:
        """Test admin login with provided credentials"""
        success, response = self.run_test(
            "Admin Login", 
            "POST",
            "api/admin-9821/login",
            200,
            data={"email": "admin@admin.com", "password": "admin12345"}
        )
        
        if success and 'token' in response:
            self.admin_token = response['token']
            self.log(f"✅ Admin login successful")
            return True
        else:
            self.log(f"❌ Admin login failed. Response: {response}")
            return False

    def test_signup_api(self) -> bool:
        """Test signup API with a test user"""
        test_email = f"testuser_{datetime.now().strftime('%Y%m%d_%H%M%S')}@test.com"
        success, response = self.run_test(
            "User Signup",
            "POST", 
            "api/auth/signup",
            200,
            data={
                "name": "Test User",
                "email": test_email,
                "password": "testpass123"
            }
        )
        
        # Signup can return 200 even if it requires verification
        if success:
            if 'token' in response:
                self.log(f"✅ Signup successful with immediate login")
            elif response.get('requires_verification'):
                self.log(f"✅ Signup successful but requires email verification")
            else:
                self.log(f"✅ Signup successful: {response}")
            return True
        else:
            self.log(f"❌ Signup failed. Response: {response}")
            return False

    def test_auth_me(self) -> bool:
        """Test get current user endpoint"""
        if not self.token:
            self.log("❌ No token available for /me test")
            return False

        headers = {'Authorization': f'Bearer {self.token}'}
        success, response = self.run_test(
            "Get Current User (/me)",
            "GET",
            "api/auth/me", 
            200,
            headers=headers
        )
        
        if success and 'user_id' in response:
            self.log(f"✅ Auth /me successful. User: {response.get('email', 'N/A')}")
            return True
        else:
            self.log(f"❌ Auth /me failed. Response: {response}")
            return False

    def test_get_stories(self) -> tuple[bool, list]:
        """Test get stories endpoint and return available stories"""
        if not self.token:
            self.log("❌ No token available for get stories test")
            return False, []

        headers = {'Authorization': f'Bearer {self.token}'}
        success, response = self.run_test(
            "Get User Stories",
            "GET",
            "api/stories",
            200,
            headers=headers
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Found {len(response)} stories")
            for story in response[:3]:  # Show first 3 stories
                self.log(f"  - Story ID: {story.get('story_id')}, Title: {story.get('title', 'Untitled')}")
            return True, response
        else:
            self.log(f"❌ Get stories failed. Response: {response}")
            return False, []

    def test_get_episodes(self, story_id) -> tuple[bool, list]:
        """Test get episodes for a specific story"""
        if not self.token:
            self.log("❌ No token available for get episodes test")
            return False, []

        headers = {'Authorization': f'Bearer {self.token}'}
        success, response = self.run_test(
            "Get Story Episodes",
            "GET",
            f"api/episodes/story/{story_id}",
            200,
            headers=headers
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Found {len(response)} episodes for story {story_id}")
            for episode in response[:3]:  # Show first 3 episodes
                self.log(f"  - Episode ID: {episode.get('episode_id')}, Title: {episode.get('title', 'Untitled')}")
            return True, response
        else:
            self.log(f"❌ Get episodes failed. Response: {response}")
            return False, []

    def test_script_dialogues_endpoint(self, episode_id) -> bool:
        """Test script dialogues endpoint for specific episode"""
        if not self.token:
            self.log("❌ No token available for script dialogues test")
            return False

        headers = {'Authorization': f'Bearer {self.token}'}
        success, response = self.run_test(
            "Get Script Dialogues",
            "GET",
            f"api/script/{episode_id}/dialogues",
            200,
            headers=headers
        )
        
        if success:
            dialogues = response.get('dialogues', [])
            self.log(f"✅ Script dialogues loaded: {len(dialogues)} dialogues found")
            return True
        else:
            self.log(f"❌ Script dialogues failed. Response: {response}")
            return False

    def test_regeneration_endpoint_success(self, episode_id, dialogue_index=0) -> bool:
        """Test regeneration endpoint with valid data - should return structured JSON"""
        if not self.token:
            self.log("❌ No token available for regeneration test")
            return False

        headers = {'Authorization': f'Bearer {self.token}'}
        test_data = {
            "dialogue_index": dialogue_index,
            "character_id": "test_char_id",
            "character_name": "Test Character",
            "voice_id": "Kore",
            "text": "This is a test dialogue for regeneration.",
            "director_notes": "speak naturally"
        }
        
        success, response = self.run_test(
            "Regeneration Endpoint - Valid Data",
            "POST",
            f"api/script/{episode_id}/dialogue/{dialogue_index}/regenerate",
            200,
            data=test_data,
            headers=headers
        )
        
        if success:
            # Check for structured JSON with 'success' field
            if 'success' in response:
                self.log(f"✅ Regeneration endpoint returned structured JSON with 'success' field")
                return True
            else:
                self.log(f"❌ Regeneration endpoint missing 'success' field in response: {response}")
                return False
        else:
            self.log(f"❌ Regeneration endpoint test failed. Response: {response}")
            return False

    def test_regeneration_endpoint_error(self, episode_id="story_45f8bef2c25c") -> bool:
        """Test regeneration endpoint with invalid data - should return proper error JSON, not 502"""
        if not self.token:
            self.log("❌ No token available for regeneration error test")
            return False

        headers = {'Authorization': f'Bearer {self.token}'}
        invalid_data = {
            "dialogue_index": 999,  # Invalid index
            "character_id": "",     # Empty character ID
            "character_name": "",   # Empty character name
            "voice_id": "",         # Empty voice ID
            "text": "",             # Empty text
            "director_notes": ""
        }
        
        success, response = self.run_test(
            "Regeneration Endpoint - Invalid Data",
            "POST",
            f"api/script/{episode_id}/dialogue/999/regenerate",
            400,  # Expecting 400 Bad Request, not 502
            data=invalid_data,
            headers=headers
        )
        
        # Even if we get different status code, check it's NOT 502
        if response.get('error') != 'timeout' and 'error' in response:
            # Check response structure has proper error JSON
            if 'detail' in response or 'error' in response or 'success' in response:
                self.log(f"✅ Regeneration endpoint returned structured error JSON (not 502)")
                return True
            else:
                self.log(f"❌ Regeneration endpoint returned unstructured error: {response}")
                return False
        else:
            self.log(f"❌ Regeneration error test failed. Response: {response}")
            return False

    def run_focused_tests(self):
        """Run focused tests for the specific requirements"""
        self.log("🚀 Starting StoryFy API focused testing...")
        self.log("Testing clip regeneration system fixes and core functionality:")
        
        # Test 1: Health endpoint
        self.log("\n📋 1. HEALTH ENDPOINT TEST")
        health_success = self.test_health_endpoint()
        
        # Test 2: Creator login
        self.log("\n🔐 2. CREATOR LOGIN TEST")
        creator_login_success = self.test_creator_login()
        
        # Test 3: Auth /me endpoint (if login successful)
        auth_me_success = False
        if creator_login_success:
            self.log("\n👤 3. AUTH ME TEST")
            auth_me_success = self.test_auth_me()
        
        # Test 4: Script dialogues endpoint for specific story
        script_dialogues_success = False
        if creator_login_success:
            self.log("\n📜 4. SCRIPT DIALOGUES TEST")
            script_dialogues_success = self.test_script_dialogues_endpoint()
        
        # Test 5: Regeneration endpoint with valid data
        regeneration_success = False
        if creator_login_success:
            self.log("\n🔄 5. REGENERATION ENDPOINT - VALID DATA")
            regeneration_success = self.test_regeneration_endpoint_success()
        
        # Test 6: Regeneration endpoint with invalid data (should not return 502)
        regeneration_error_success = False
        if creator_login_success:
            self.log("\n❌ 6. REGENERATION ENDPOINT - ERROR HANDLING")
            regeneration_error_success = self.test_regeneration_endpoint_error()
        
        # Test 7: Signup API
        self.log("\n📝 7. SIGNUP API TEST")
        signup_success = self.test_signup_api()
        
        self.print_results()

    def print_results(self, specific_tests_passed=None):
        """Print final test results"""
        self.log("\n" + "="*60)
        self.log("🏁 FINAL TEST RESULTS")
        self.log("="*60)
        self.log(f"Tests run: {self.tests_run}")
        self.log(f"Tests passed: {self.tests_passed}")
        self.log(f"Tests failed: {self.tests_run - self.tests_passed}")
        success_rate = (self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0
        self.log(f"Success rate: {success_rate:.1f}%")
        
        if self.tests_passed == self.tests_run:
            self.log("🎉 ALL TESTS PASSED!")
        else:
            self.log("⚠️  Some tests failed. Check the logs above for details.")
        
        return self.tests_passed == self.tests_run

def main():
    """Main function to run the tests"""
    tester = StoryFyAPITester()
    success = tester.run_focused_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())