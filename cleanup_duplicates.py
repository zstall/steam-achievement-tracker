#!/usr/bin/env python3
"""
Clean up duplicate shared achievements created before duplicate prevention
"""

import os
from flask import Flask
from config import config
from models import db, SharedAchievement, User

def cleanup_duplicate_shared_achievements():
    """Remove duplicate shared achievements, keeping the most recent one"""
    print("🧹 Cleaning up duplicate shared achievements...")
    
    # Create Flask app
    app = Flask(__name__)
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    db.init_app(app)
    
    with app.app_context():
        try:
            # Find duplicates by creator and name
            all_shared = SharedAchievement.query.all()
            seen = {}  # key: (creator_id, name), value: [achievement_objects]
            
            for achievement in all_shared:
                key = (achievement.creator_id, achievement.name)
                if key not in seen:
                    seen[key] = []
                seen[key].append(achievement)
            
            # Find and handle duplicates
            duplicates_found = 0
            duplicates_removed = 0
            
            for (creator_id, name), achievements in seen.items():
                if len(achievements) > 1:
                    duplicates_found += len(achievements) - 1
                    creator = User.query.get(creator_id)
                    print(f"\n🔍 Found {len(achievements)} duplicates of '{name}' by {creator.username}")
                    
                    # Sort by created date, keep the most recent one
                    achievements.sort(key=lambda x: x.shared_at, reverse=True)
                    keep = achievements[0]
                    remove = achievements[1:]
                    
                    print(f"   ✅ Keeping: ID {keep.id} (shared {keep.shared_at})")
                    
                    for dup in remove:
                        print(f"   🗑️  Removing: ID {dup.id} (shared {dup.shared_at})")
                        db.session.delete(dup)
                        duplicates_removed += 1
            
            if duplicates_removed > 0:
                db.session.commit()
                print(f"\n✅ Cleanup completed!")
                print(f"   📊 Found {duplicates_found} duplicate achievements")
                print(f"   🗑️  Removed {duplicates_removed} duplicates")
                print(f"   💾 Kept the most recent version of each")
            else:
                print("\n✅ No duplicates found! Database is clean.")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error during cleanup: {e}")
            return False

def show_current_shared_achievements():
    """Show all current shared achievements for verification"""
    print("\n📋 Current shared achievements:")
    
    app = Flask(__name__)
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    db.init_app(app)
    
    with app.app_context():
        shared_achievements = SharedAchievement.query.join(User).order_by(
            SharedAchievement.shared_at.desc()
        ).all()
        
        if shared_achievements:
            for ach in shared_achievements:
                print(f"   - '{ach.name}' by {ach.creator.username} (ID: {ach.id}, shared: {ach.shared_at})")
        else:
            print("   (No shared achievements found)")

if __name__ == '__main__':
    print("🗄️  Shared Achievement Cleanup Tool")
    print("=" * 50)
    
    # Show current state
    show_current_shared_achievements()
    
    # Ask for confirmation
    response = input("\n🤔 Do you want to clean up duplicates? (y/N): ")
    if response.lower() in ['y', 'yes']:
        success = cleanup_duplicate_shared_achievements()
        if success:
            print("\n📋 After cleanup:")
            show_current_shared_achievements()
        else:
            print("\n💥 Cleanup failed!")
    else:
        print("👍 No changes made.")