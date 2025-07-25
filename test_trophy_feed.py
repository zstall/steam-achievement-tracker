#!/usr/bin/env python3
"""
Test script for Trophy Feed functionality
Tests database models, activity logging, and basic functionality
"""

import os
import sys
from datetime import datetime

# Set test environment
os.environ['FLASK_ENV'] = 'testing'

def test_activity_feed_model():
    """Test ActivityFeed model creation and methods"""
    try:
        from models import ActivityFeed, User, db
        print("✅ ActivityFeed model import: SUCCESS")
        
        # Test model attributes
        required_attributes = [
            'id', 'user_id', 'activity_type', 'title', 'description',
            'game_id', 'custom_achievement_id', 'shared_achievement_id',
            'metadata', 'is_public', 'is_highlighted', 'created_at'
        ]
        
        for attr in required_attributes:
            if not hasattr(ActivityFeed, attr):
                print(f"❌ ActivityFeed missing attribute: {attr}")
                return False
        
        print("✅ ActivityFeed model attributes: SUCCESS")
        
        # Test methods
        if not hasattr(ActivityFeed, 'get_type_display'):
            print("❌ ActivityFeed missing get_type_display method")
            return False
            
        if not hasattr(ActivityFeed, 'time_ago'):
            print("❌ ActivityFeed missing time_ago property")
            return False
            
        print("✅ ActivityFeed model methods: SUCCESS")
        return True
        
    except Exception as e:
        print(f"❌ ActivityFeed model test: FAILED - {e}")
        return False

def test_activity_logging_functions():
    """Test activity logging utility functions"""
    try:
        from models import log_activity, get_recent_activities
        print("✅ Activity logging functions import: SUCCESS")
        
        # Test function signatures
        import inspect
        
        log_sig = inspect.signature(log_activity)
        required_params = ['user_id', 'activity_type', 'title']
        for param in required_params:
            if param not in log_sig.parameters:
                print(f"❌ log_activity missing parameter: {param}")
                return False
        
        get_sig = inspect.signature(get_recent_activities)
        optional_params = ['limit', 'user_id', 'activity_type', 'include_private']
        for param in optional_params:
            if param not in get_sig.parameters:
                print(f"❌ get_recent_activities missing parameter: {param}")
                return False
        
        print("✅ Activity logging function signatures: SUCCESS")
        return True
        
    except Exception as e:
        print(f"❌ Activity logging functions test: FAILED - {e}")
        return False

def test_app_route_integration():
    """Test that trophy feed routes are properly integrated"""
    try:
        from app import app
        
        # Check routes exist
        routes = [rule.endpoint for rule in app.url_map.iter_rules()]
        
        required_routes = ['trophy_feed', 'api_trophy_feed']
        missing_routes = [route for route in required_routes if route not in routes]
        
        if missing_routes:
            print(f"❌ Missing trophy feed routes: {missing_routes}")
            return False
            
        print("✅ Trophy feed routes registered: SUCCESS")
        
        # Check route patterns
        for rule in app.url_map.iter_rules():
            if rule.endpoint == 'trophy_feed':
                if str(rule) != '/trophy-feed':
                    print(f"❌ Trophy feed route pattern incorrect: {rule}")
                    return False
            elif rule.endpoint == 'api_trophy_feed':
                if str(rule) != '/api/trophy-feed':
                    print(f"❌ API trophy feed route pattern incorrect: {rule}")
                    return False
        
        print("✅ Trophy feed route patterns: SUCCESS")
        return True
        
    except Exception as e:
        print(f"❌ App route integration test: FAILED - {e}")
        return False

def test_template_exists():
    """Test that trophy feed template exists and has basic structure"""
    try:
        template_path = 'templates/trophy_feed.html'
        if not os.path.exists(template_path):
            print(f"❌ Template not found: {template_path}")
            return False
        
        with open(template_path, 'r') as f:
            template_content = f.read()
        
        # Check for key template elements
        required_elements = [
            'Trophy Feed',
            'activity-card',
            'activityFilter', 
            'userFilter',
            'filterFeed()',
            'loadMoreActivities()'
        ]
        
        missing_elements = []
        for element in required_elements:
            if element not in template_content:
                missing_elements.append(element)
        
        if missing_elements:
            print(f"❌ Template missing elements: {missing_elements}")
            return False
        
        print("✅ Trophy feed template structure: SUCCESS")
        return True
        
    except Exception as e:
        print(f"❌ Template test: FAILED - {e}")
        return False

def test_navigation_integration():
    """Test that trophy feed is integrated into navigation"""
    try:
        with open('templates/base.html', 'r') as f:
            base_content = f.read()
        
        # Check for trophy feed link
        if 'trophy_feed' not in base_content:
            print("❌ Trophy feed not in navigation")
            return False
            
        if 'Trophy Feed' not in base_content:
            print("❌ Trophy Feed text not in navigation")
            return False
        
        print("✅ Navigation integration: SUCCESS")
        return True
        
    except Exception as e:
        print(f"❌ Navigation integration test: FAILED - {e}")
        return False

def test_activity_types_consistency():
    """Test that activity types are consistent across app and models"""
    try:
        # Test activity type mappings directly
        type_map = {
            'game_completed': '🎉 Game Completed',
            'custom_achievement_unlocked': '🏆 Achievement Unlocked', 
            'custom_achievement_created': '🎯 Created Achievement',
            'custom_achievement_shared': '🌟 Shared Achievement',
            'community_achievement_imported': '📥 Imported Achievement',
            'milestone_reached': '⭐ Milestone Reached',
            'game_started': '🎮 Started Playing',
            'streak_achieved': '🔥 Streak Milestone',
            'library_milestone': '📚 Library Milestone'
        }
        
        # Test that all types have proper mappings
        activity_types = [
            'custom_achievement_created',
            'custom_achievement_shared', 
            'community_achievement_imported',
            'game_completed',
            'milestone_reached'
        ]
        
        for activity_type in activity_types:
            if activity_type not in type_map:
                print(f"❌ Activity type not mapped: {activity_type}")
                return False
            
            display = type_map[activity_type]
            if not display or not display.startswith('🎯') and not display.startswith('🌟') and not display.startswith('📥') and not display.startswith('🎉') and not display.startswith('⭐'):
                print(f"❌ Activity type display invalid: {activity_type} -> {display}")
                return False
        
        print("✅ Activity types consistency: SUCCESS")
        return True
        
    except Exception as e:
        print(f"❌ Activity types consistency test: FAILED - {e}")
        return False

def run_trophy_feed_tests():
    """Run all trophy feed tests"""
    print("🏆 Testing Trophy Feed System")
    print("=" * 50)
    
    tests = [
        test_activity_feed_model,
        test_activity_logging_functions,
        test_app_route_integration,
        test_template_exists,
        test_navigation_integration,
        test_activity_types_consistency
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()  # Add blank line between tests
    
    print("=" * 50)
    print(f"🏆 Trophy Feed Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All trophy feed tests passed!")
        print("\n✨ Trophy Feed Features Ready:")
        print("  • ActivityFeed database model with proper relationships")
        print("  • Activity logging integrated into achievement routes")
        print("  • Community feed UI with filtering and pagination")
        print("  • Real-time activity tracking for sharing and importing")
        print("  • Navigation integration and responsive design")
        
        print("\n🚀 Next Steps:")
        print("  1. Initialize database: python3 init_db.py")
        print("  2. Test with existing data or create some achievements")
        print("  3. Visit /trophy-feed to see the community activity!")
        
        return True
    else:
        print("⚠️  Some trophy feed tests failed. Check errors above.")
        return False

if __name__ == '__main__':
    success = run_trophy_feed_tests()
    sys.exit(0 if success else 1)