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

    def run_focused_tests(self):
        """Run focused tests for the specific requirements"""
        self.log("🚀 Starting StoryFy API focused testing...")
        self.log("Testing specific features requested in the review:")
        
        # Test 1: Health endpoint
        self.log("\n📋 1. HEALTH ENDPOINT TEST")
        self.test_health_endpoint()
        
        # Test 2: Creator login
        self.log("\n🔐 2. CREATOR LOGIN TEST")
        creator_login_success = self.test_creator_login()
        
        # Test 3: Auth /me endpoint (if login successful)
        if creator_login_success:
            self.log("\n👤 3. AUTH ME TEST")
            self.test_auth_me()
        
        # Test 4: Signup API
        self.log("\n📝 4. SIGNUP API TEST")
        self.test_signup_api()
        
        # Test 5: Admin login
        self.log("\n🛡️  5. ADMIN LOGIN TEST")
        self.test_admin_login()
        
        self.print_results()

    def print_results(self):
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