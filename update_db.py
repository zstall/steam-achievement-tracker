#!/usr/bin/env python3
"""
Database update script to add ActivityFeed table
Simple approach: Drop and recreate all tables (development only)
"""

import os
from flask import Flask
from config import config
from models import db, ActivityFeed

def update_database():
    """Update database with new ActivityFeed table"""
    print("🗄️  Updating database schema...")
    
    # Create Flask app
    app = Flask(__name__)
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    db.init_app(app)
    
    with app.app_context():
        try:
            # Create all tables (including new ActivityFeed)
            db.create_all()
            print("✅ Database schema updated successfully!")
            
            # Verify the new table exists
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            if 'activity_feed' in tables:
                print("✅ ActivityFeed table created successfully!")
                
                # Show table columns
                columns = inspector.get_columns('activity_feed')
                print(f"📊 ActivityFeed table has {len(columns)} columns:")
                for col in columns:
                    print(f"   - {col['name']}: {col['type']}")
            else:
                print("❌ ActivityFeed table not found!")
                return False
            
            print(f"\n📋 Total tables in database: {len(tables)}")
            for table in sorted(tables):
                print(f"  - {table}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating database: {e}")
            return False

if __name__ == '__main__':
    success = update_database()
    if success:
        print("\n🎉 Database update completed!")
        print("🚀 You can now test the Trophy Feed at /trophy-feed")
    else:
        print("\n💥 Database update failed!")
        exit(1)