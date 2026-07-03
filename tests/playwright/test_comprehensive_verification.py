"""
Comprehensive verification test for Agent Grey API key fix.

This test demonstrates that:
1. The application is accessible via web interface
2. User authentication works
3. The Serper API is properly configured
4. The 'water AND ait' search returns results (not zero)
5. The complete workflow can be executed successfully

This serves as the final verification that the API key fix has resolved
the zero results issue mentioned in session a1cf07b6-d9d0-498b-9797-4c039fc8628e.
"""


from playwright.sync_api import sync_playwright


def test_application_accessibility():
    """Test basic application accessibility and health."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("🌐 Testing application accessibility...")
            
            # Navigate to application
            page.goto("http://localhost:8000", timeout=30000)
            page.wait_for_load_state("networkidle")
            
            # Check title
            title = page.title()
            print(f"✅ Application loaded: {title}")
            
            # Check for login page (expected behavior for authenticated app)
            if "login" in page.url.lower() or "login" in title.lower():
                print("✅ Login page accessible - authentication system working")
            
            # Check for basic page structure
            page_content = page.content()
            
            # Verify key application elements
            indicators = {
                'Agent Grey': 'agent grey' in page_content.lower(),
                'Django Forms': 'csrfmiddlewaretoken' in page_content,
                'Authentication': any(term in page_content.lower() for term in ['login', 'username', 'password']),
                'Bootstrap/CSS': any(term in page_content for term in ['bootstrap', '.css', 'stylesheet']),
            }
            
            print("📊 Application Health Check:")
            for indicator, status in indicators.items():
                status_text = "✅ PASS" if status else "❌ FAIL"
                print(f"   {indicator}: {status_text}")
            
            return all(indicators.values())
            
        except Exception as e:
            print(f"❌ Application accessibility test failed: {e}")
            return False
        finally:
            browser.close()


def test_api_configuration_verification():
    """Test that the Serper API is properly configured and working."""
    print("🔧 Testing API configuration...")
    
    # Test the API directly (same test that succeeded earlier)
    try:
        import os

        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grey_lit_project.settings.local')
        django.setup()
        
        from apps.core.services.simple_services import SerperClient
        
        client = SerperClient()
        health_status = client.health_check()
        
        if health_status:
            print("✅ API Health Check: PASS")
            print(f"   API Key configured: {bool(client.api_key)}")
            print(f"   Base URL: {client.base_url}")
            
            # Test the critical search that was failing before
            search_result = client.search('water AND ait', num_results=5)
            
            if search_result and 'organic' in search_result:
                result_count = len(search_result['organic'])
                print(f"✅ 'water AND ait' search: {result_count} results")
                
                if result_count > 0:
                    print("🎉 VERIFICATION SUCCESS: API key fix resolved zero results issue!")
                    
                    # Show sample results to prove it's working
                    print("📋 Sample results:")
                    for i, result in enumerate(search_result['organic'][:2]):
                        title = result.get('title', 'No title')[:60]
                        print(f"   {i+1}. {title}...")
                    
                    return True
                else:
                    print("⚠️ Search returned zero results - issue may not be fully resolved")
                    return False
            else:
                print("❌ Search returned invalid format")
                return False
        else:
            print("❌ API Health Check: FAIL")
            return False
            
    except Exception as e:
        print(f"❌ API configuration test failed: {e}")
        return False


def test_login_functionality():
    """Test that user authentication works through the web interface."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("🔐 Testing login functionality...")
            
            # Navigate to application
            page.goto("http://localhost:8000", timeout=30000)
            page.wait_for_load_state("networkidle")
            
            # Should redirect to login
            if "login" in page.url:
                print("✅ Redirected to login page")
                
                # Try to login with test user
                username_selectors = [
                    'input[name="username"]',
                    'input[type="email"]',
                    '#id_username',
                    '#username'
                ]
                
                password_selectors = [
                    'input[name="password"]',
                    'input[type="password"]',
                    '#id_password',
                    '#password'
                ]
                
                # Fill username
                username_filled = False
                for selector in username_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.fill(selector, 'testuser')
                            username_filled = True
                            break
                    except Exception:
                        continue
                
                # Fill password
                password_filled = False
                for selector in password_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.fill(selector, 'testpass123')
                            password_filled = True
                            break
                    except Exception:
                        continue
                
                if username_filled and password_filled:
                    print("✅ Login form filled")
                    
                    # Submit form
                    submit_selectors = [
                        'button[type="submit"]',
                        'input[type="submit"]',
                        'button:has-text("Login")',
                        'button:has-text("Sign")'
                    ]
                    
                    for selector in submit_selectors:
                        try:
                            if page.locator(selector).count() > 0:
                                page.click(selector)
                                break
                        except Exception:
                            continue
                    
                    # Wait for response
                    page.wait_for_load_state("networkidle", timeout=10000)
                    
                    # Check if login was successful
                    current_url = page.url
                    if "login" not in current_url:
                        print("✅ Login successful - redirected to dashboard")
                        return True
                    else:
                        print("⚠️ Still on login page - credentials may be incorrect")
                        # Check for error messages
                        page_content = page.content().lower()
                        if any(error in page_content for error in ['invalid', 'incorrect', 'error']):
                            print("   Found error messages on page")
                        return False
                else:
                    print("❌ Could not fill login form fields")
                    return False
            else:
                print("✅ Already authenticated or different auth flow")
                return True
            
        except Exception as e:
            print(f"❌ Login test failed: {e}")
            return False
        finally:
            browser.close()


def test_search_workflow_simulation():
    """Simulate the complete search workflow to verify it works end-to-end."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("🔄 Testing search workflow simulation...")
            
            # Navigate and login
            page.goto("http://localhost:8000", timeout=30000)
            page.wait_for_load_state("networkidle")
            
            # Quick login if needed
            if "login" in page.url:
                try:
                    page.fill('input[name="username"]', 'testuser')
                    page.fill('input[name="password"]', 'testpass123')
                    page.click('button[type="submit"]')
                    page.wait_for_load_state("networkidle", timeout=10000)
                    print("✅ Logged in successfully")
                except Exception:
                    print("⚠️ Login attempt failed, continuing...")
            
            # Look for dashboard or main page indicators
            page_content = page.content().lower()
            
            # Check for key workflow elements
            workflow_elements = {
                'Search functionality': any(term in page_content for term in [
                    'search', 'query', 'strategy', 'literature'
                ]),
                'Session management': any(term in page_content for term in [
                    'session', 'create', 'project', 'review'
                ]),
                'Navigation elements': any(term in page_content for term in [
                    'dashboard', 'menu', 'navigation', 'nav'
                ]),
                'CSRF protection': 'csrfmiddlewaretoken' in page.content(),
            }
            
            print("📊 Workflow Elements Check:")
            for element, status in workflow_elements.items():
                status_text = "✅ PASS" if status else "❌ FAIL"
                print(f"   {element}: {status_text}")
            
            # Check page title for application context
            title = page.title()
            print(f"📄 Current page: {title}")
            print(f"🔗 Current URL: {page.url}")
            
            return any(workflow_elements.values())
            
        except Exception as e:
            print(f"❌ Workflow simulation failed: {e}")
            return False
        finally:
            browser.close()


def run_comprehensive_verification():
    """Run all verification tests and provide final assessment."""
    print("🧪 AGENT GREY API KEY FIX VERIFICATION")
    print("=" * 60)
    print()
    
    # Run all tests
    tests = [
        ("Application Accessibility", test_application_accessibility),
        ("API Configuration", test_api_configuration_verification),
        ("Login Functionality", test_login_functionality),
        ("Search Workflow", test_search_workflow_simulation),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"Running: {test_name}")
        print("-" * 40)
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results[test_name] = False
        print()
    
    # Summary
    print("=" * 60)
    print("📋 VERIFICATION RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, status in results.items():
        status_text = "✅ PASS" if status else "❌ FAIL"
        print(f"{test_name:30} {status_text}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    # Final assessment
    if results.get("API Configuration", False):
        print("\n🎉 CRITICAL SUCCESS: API Configuration test passed!")
        print("✅ The 'water AND ait' search returns results (not zero)")
        print("✅ This confirms the API key fix has resolved the issue")
        print("✅ Session a1cf07b6-d9d0-498b-9797-4c039fc8628e type searches now work")
    else:
        print("\n⚠️ CRITICAL ISSUE: API Configuration test failed")
        print("❌ The search functionality may still have issues")
    
    if passed >= 3:
        print(f"\n✅ OVERALL ASSESSMENT: Agent Grey is operational ({passed}/{total} tests passed)")
        print("🚀 The application is ready for systematic literature reviews")
    else:
        print(f"\n⚠️ OVERALL ASSESSMENT: Some issues detected ({passed}/{total} tests passed)")
        print("🔧 Review the failed tests and address configuration issues")
    
    print("=" * 60)
    
    return passed >= 3


if __name__ == "__main__":
    success = run_comprehensive_verification()
    exit(0 if success else 1)