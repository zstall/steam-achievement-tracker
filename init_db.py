#!/usr/bin/env python3
"""
Database initialization script for Steam Achievement Tracker
Run this to create the database tables and test the connection
"""

import os
import sys
from flask import Flask
from config import config
from models import db, init_db
from cryptography.fernet import Fernet

def create_app():
    """Create Flask app with database configuration"""
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    db.init_app(app)
    
    return app

def test_database_connection():
    """Test database connection"""
    try:
        # Try to connect and run a simple query
        result = db.session.execute(db.text('SELECT version()'))
        version = result.fetchone()[0]
        print(f"✅ Database connection successful!")
        print(f"PostgreSQL version: {version}")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def generate_encryption_key():
    """Generate encryption key for Steam API keys"""
    key = Fernet.generate_key()
    print(f"\n🔑 Generated encryption key for Steam API keys:")
    print(f"Add this to your .env file:")
    print(f"STEAM_ENCRYPTION_KEY={key.decode()}")
    return key

def main():
    """Main initialization function"""
    print("🚀 Initializing Steam Achievement Tracker Database")
    print("=" * 50)
    
    # Create Flask app
    app = create_app()
    
    with app.app_context():
        # Test database connection
        if not test_database_connection():
            print("\n❌ Please check your database configuration and try again.")
            sys.exit(1)
        
        # Create all tables
        print("\n📋 Creating database tables...")
        try:
            db.create_all()
            print("✅ All database tables created successfully!")
            
            # Print table information
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"\n📊 Created {len(tables)} tables:")
            for table in sorted(tables):
                print(f"  - {table}")
                
        except Exception as e:
            print(f"❌ Error creating tables: {e}")
            sys.exit(1)
        
        # Check if encryption key is set
        if not app.config.get('STEAM_ENCRYPTION_KEY') or app.config['STEAM_ENCRYPTION_KEY'] == 'development-key-replace-with-generated-key-1234567890abcdef':
            print("\n🔐 Generating encryption key for production...")
            generate_encryption_key()
        
        print("\n✅ Database initialization completed successfully!")
        print("\n🔥 Next steps:")
        print("1. Update STEAM_ENCRYPTION_KEY in your .env file (if needed)")
        print("2. Run the migration script to import existing data")
        print("3. Start the Flask application")

if __name__ == '__main__':
    main()