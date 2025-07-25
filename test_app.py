#!/usr/bin/env python3
"""
Test script for the updated Steam Achievement Tracker app
Tests basic functionality without requiring database connection
"""

import os
import sys
from unittest.mock import Mock, patch

# Set test environment
os.environ['FLASK_ENV'] = 'testing'

# Mock database operations to avoid connection errors
def mock_db_operations():
    """Mock database operations for testing"""
    from unittest.mock import MagicMock
    
    # Mock the database session
    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    
    # Mock database models
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.username = "testuser"
    mock_user.steam_api_key_encrypted = "encrypted_key"
    mock_user.steam_id = "76561198000000000"
    mock_user.is_active = True
    
    return mock_session, mock_user

def test_app_creation():
    """Test that the Flask app can be created"""
    try:
        from app import create_app
        app = create_app()
        print("✅ Flask app creation: SUCCESS")
        return True
    except Exception as e:
        print(f"❌ Flask app creation: FAILED - {e}")
        return False

def test_route_definitions():
    """Test that all routes are properly defined"""
    try:
        from app import app
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append(f"{rule.endpoint}: {rule.rule}")
        
        expected_routes = [
            'login', 'register', 'logout', 'profile', 'index', 
            'game_detail', 'api_games', 'refresh_data',
            'custom_achievements', 'create_achievement', 'delete_achievement',
            'share_achievement_route', 'unshare_achievement',
            'community_achievements', 'import_achievement_route'
        ]
        
        defined_endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
        
        missing_routes = []
        for expected in expected_routes:
            if expected not in defined_endpoints:
                missing_routes.append(expected)
        
        if missing_routes:
            print(f"❌ Route definitions: FAILED - Missing routes: {missing_routes}")
            return False
        else:
            print(f"✅ Route definitions: SUCCESS - {len(defined_endpoints)} routes defined")
            return True
            
    except Exception as e:
        print(f"❌ Route definitions: FAILED - {e}")
        return False

def test_model_relationships():
    """Test that database models have correct relationships"""
    try:
        from models import User, Game, UserGame, SteamAchievement, CustomAchievement, SharedAchievement, AchievementImage
        
        # Check if models have expected attributes
        user_attrs = ['username', 'steam_api_key_encrypted', 'steam_id', 'user_games', 'custom_achievements']
        for attr in user_attrs:
            if not hasattr(User, attr):
                print(f"❌ Model relationships: FAILED - User missing {attr}")
                return False
        
        game_attrs = ['steam_app_id', 'name', 'user_games']
        for attr in game_attrs:
            if not hasattr(Game, attr):
                print(f"❌ Model relationships: FAILED - Game missing {attr}")
                return False
        
        print("✅ Model relationships: SUCCESS")
        return True
        
    except Exception as e:
        print(f"❌ Model relationships: FAILED - {e}")
        return False

def test_encryption_manager():
    """Test that encryption manager can be instantiated"""
    try:
        # Set required environment variable
        os.environ['STEAM_ENCRYPTION_KEY'] = '98ufSmNi3HXH-U_1OiASXZ1Yht_7IBGGjawZoLJf8J4='
        
        from app import EncryptionManager
        encryption_manager = EncryptionManager()
        
        # Test encryption/decryption
        test_key = "test_steam_api_key_12345"
        encrypted = encryption_manager.encrypt_steam_api_key(test_key)
        decrypted = encryption_manager.decrypt_steam_api_key(encrypted)
        
        if decrypted == test_key:
            print("✅ Encryption Manager: SUCCESS")
            return True
        else:
            print("❌ Encryption Manager: FAILED - Decryption mismatch")
            return False
            
    except Exception as e:
        print(f"❌ Encryption Manager: FAILED - {e}")
        return False

def test_forms():
    """Test that WTForms are properly defined"""
    try:
        from app import LoginForm, RegisterForm, ProfileForm, CustomAchievementForm
        
        # Test form instantiation
        login_form = LoginForm()
        register_form = RegisterForm()
        profile_form = ProfileForm()
        custom_form = CustomAchievementForm()
        
        # Check required fields exist
        if not hasattr(login_form, 'username') or not hasattr(login_form, 'password'):
            print("❌ Forms: FAILED - LoginForm missing required fields")
            return False
            
        if not hasattr(profile_form, 'steam_api_key') or not hasattr(profile_form, 'steam_id'):
            print("❌ Forms: FAILED - ProfileForm missing required fields")
            return False
        
        print("✅ Forms: SUCCESS")
        return True
        
    except Exception as e:
        print(f"❌ Forms: FAILED - {e}")
        return False

def run_tests():
    """Run all tests"""
    print("🧪 Testing Steam Achievement Tracker Application")
    print("=" * 50)
    
    tests = [
        test_app_creation,
        test_route_definitions,
        test_model_relationships,
        test_encryption_manager,
        test_forms
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()  # Add blank line between tests
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The application is ready for database testing.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        return False

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)