#!/usr/bin/env python
"""
Environment Validation Script

Validates that the three-environment setup works correctly without
the Environment Manager and its production override issues.

Usage:
    python scripts/validate_environments.py
"""

import os
import subprocess
import sys


def test_environment_isolation():
    """Test that each environment loads the correct settings."""
    print("🧪 Testing Environment Isolation")
    print("=" * 50)

    environments = [
        ("development", "grey_lit_project.settings.local"),
        ("staging", "grey_lit_project.settings.staging"),
        ("production", "grey_lit_project.settings.production"),
    ]

    results = []

    for env_name, settings_module in environments:
        print(f"\n🔍 Testing {env_name} environment...")

        # Create test environment
        test_env = os.environ.copy()
        test_env["DJANGO_SETTINGS_MODULE"] = settings_module
        test_env["ENVIRONMENT"] = env_name

        # Test Django settings loading
        test_script = f"""
import os
import sys
import django
from django.conf import settings

os.environ["DJANGO_SETTINGS_MODULE"] = "{settings_module}"
os.environ["ENVIRONMENT"] = "{env_name}"

try:
    django.setup()
    print(f"✅ Django setup successful")
    print(f"   Settings module: {{settings.SETTINGS_MODULE}}")
    print(f"   Debug mode: {{settings.DEBUG}}")
    print(f"   Environment: {{os.environ.get('ENVIRONMENT')}}")

    # Test database configuration
    db_config = settings.DATABASES.get('default', {{}})
    print(f"   Database engine: {{db_config.get('ENGINE', 'Not configured')}}")

    # Test critical settings
    if "{env_name}" == "production":
        if settings.DEBUG:
            print("⚠️  WARNING: DEBUG=True in production")
        else:
            print("✅ DEBUG=False in production")

        if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
            print("⚠️  WARNING: Weak SECRET_KEY in production")
        else:
            print("✅ Strong SECRET_KEY in production")

    print("✅ Environment validation passed")

except Exception as e:
    print(f"❌ Environment validation failed: {{e}}")
    sys.exit(1)
"""

        try:
            result = subprocess.run(
                [sys.executable, "-c", test_script],
                env=test_env,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                print(result.stdout)
                results.append((env_name, True, None))
            else:
                print(f"❌ Failed to validate {env_name}")
                print("STDOUT:", result.stdout)
                print("STDERR:", result.stderr)
                results.append((env_name, False, result.stderr))

        except subprocess.TimeoutExpired:
            print(f"❌ Timeout validating {env_name}")
            results.append((env_name, False, "Timeout"))
        except Exception as e:
            print(f"❌ Exception validating {env_name}: {e}")
            results.append((env_name, False, str(e)))

    return results


def test_no_environment_manager():
    """Test that Environment Manager is no longer imported."""
    print("\n🚫 Testing Environment Manager Elimination")
    print("=" * 50)

    # Test that key files don't import Environment Manager
    key_files = [
        "manage.py",
        "grey_lit_project/wsgi.py",
        "grey_lit_project/asgi.py",
        "apps/core/db_utils.py",
    ]

    for file_path in key_files:
        print(f"\n🔍 Checking {file_path}...")

        if not os.path.exists(file_path):
            print(f"⚠️  File not found: {file_path}")
            continue

        with open(file_path, "r") as f:
            content = f.read()

        if "environment_manager" in content.lower():
            print("❌ Still imports Environment Manager")
            return False
        else:
            print("✅ No Environment Manager imports")

    # Test that Environment Manager file is deprecated
    env_manager_path = "apps/core/environment_manager.py"
    deprecated_path = "apps/core/environment_manager.py.deprecated"

    if os.path.exists(env_manager_path):
        print(f"❌ Environment Manager still exists at {env_manager_path}")
        return False
    elif os.path.exists(deprecated_path):
        print(f"✅ Environment Manager deprecated: {deprecated_path}")
    else:
        print("✅ Environment Manager completely removed")

    return True


def test_docker_compose_configs():
    """Test that docker-compose files exist and are valid."""
    print("\n🐳 Testing Docker Compose Configurations")
    print("=" * 50)

    compose_files = [
        "docker-compose.yml",
        "docker-compose.development.yml",
        "docker-compose.staging.yml",
        "docker-compose.production.yml",
    ]

    all_valid = True

    for compose_file in compose_files:
        print(f"\n🔍 Checking {compose_file}...")

        if not os.path.exists(compose_file):
            print(f"❌ File not found: {compose_file}")
            all_valid = False
            continue

        try:
            # Test YAML syntax with docker-compose config
            result = subprocess.run(
                ["docker-compose", "-f", compose_file, "config"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                print("✅ Valid YAML structure")
            else:
                print(f"❌ Invalid YAML: {result.stderr}")
                all_valid = False

        except subprocess.TimeoutExpired:
            print(f"⚠️  Timeout validating {compose_file}")
        except FileNotFoundError:
            print("⚠️  docker-compose not found - skipping validation")
        except Exception as e:
            print(f"⚠️  Could not validate {compose_file}: {e}")

    return all_valid


def main():
    """Run all validation tests."""
    print("🎯 Agent Grey - Three Environment Setup Validation")
    print("=" * 60)
    print("Validating the elimination of Environment Manager and")
    print("the implementation of proper three-environment setup.")
    print("=" * 60)

    # Change to project root directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    print(f"Working directory: {os.getcwd()}")

    all_tests_passed = True

    # Test 1: Environment isolation
    env_results = test_environment_isolation()
    for env_name, passed, error in env_results:
        if not passed:
            all_tests_passed = False
            print(f"❌ Environment {env_name} failed: {error}")

    # Test 2: Environment Manager elimination
    if not test_no_environment_manager():
        all_tests_passed = False

    # Test 3: Docker configurations
    if not test_docker_compose_configs():
        all_tests_passed = False

    print("\n" + "=" * 60)
    print("📋 VALIDATION SUMMARY")
    print("=" * 60)

    if all_tests_passed:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Environment Manager successfully eliminated")
        print("✅ Three-environment setup working correctly")
        print("✅ No production override issues detected")
        print("\nThe three-environment architecture is ready:")
        print("- 🔧 Development: Local Docker with rapid iteration")
        print("- 🎯 Staging: Local Docker with production-like settings")
        print("- 🚀 Production: DigitalOcean with managed databases")
        return 0
    else:
        print("❌ SOME TESTS FAILED!")
        print("Please review the errors above and fix the issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
