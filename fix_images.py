#!/usr/bin/env python3
"""
Fix broken achievement image references
"""

import os
from flask import Flask
from config import config
from models import db, CustomAchievement, AchievementImage

def fix_image_references():
    """Fix broken image references by checking what files actually exist"""
    print("🔧 Fixing achievement image references...")
    
    # Create Flask app
    app = Flask(__name__)
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    db.init_app(app)
    
    with app.app_context():
        try:
            # Check what image files actually exist
            image_dir = 'static/achievement_images/'
            if os.path.exists(image_dir):
                existing_files = set(os.listdir(image_dir))
                print(f"📂 Found {len(existing_files)} files: {existing_files}")
            else:
                existing_files = set()
                print("📂 No image directory found")
            
            # Check database references
            achievements_with_images = CustomAchievement.query.filter(
                CustomAchievement.image_filename.isnot(None)
            ).all()
            
            print(f"\n📋 Found {len(achievements_with_images)} achievements with image references:")
            
            fixed_count = 0
            removed_count = 0
            
            for achievement in achievements_with_images:
                print(f"\n🎯 Achievement: '{achievement.name}'")
                print(f"   📄 Database filename: {achievement.image_filename}")
                
                if achievement.image_filename in existing_files:
                    print("   ✅ File exists - no fix needed")
                else:
                    print("   ❌ File missing - removing reference")
                    achievement.image_filename = None
                    removed_count += 1
            
            if removed_count > 0:
                db.session.commit()
                print(f"\n✅ Fixed {removed_count} broken image references")
            else:
                print("\n✅ No fixes needed - all references are valid")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error during fix: {e}")
            return False

if __name__ == '__main__':
    print("🖼️  Achievement Image Fix Tool")
    print("=" * 50)
    success = fix_image_references()
    if success:
        print("\n🎉 Image references fixed!")
    else:
        print("\n💥 Fix failed!")