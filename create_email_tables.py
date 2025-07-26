#!/usr/bin/env python3
"""
Create email verification and password reset tables manually
"""

import os
from flask import Flask
from config import config
from models import db

def create_email_tables():
    """Create email tables manually to avoid conflicts"""
    print("📧 Creating email verification and password reset tables...")
    
    # Create Flask app
    app = Flask(__name__)
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    db.init_app(app)
    
    with app.app_context():
        try:
            # Drop tables if they exist (to avoid conflicts)
            db.session.execute(db.text('DROP TABLE IF EXISTS email_verification_tokens CASCADE'))
            db.session.execute(db.text('DROP TABLE IF EXISTS password_reset_tokens CASCADE'))
            
            # Create tables with raw SQL to avoid sequence conflicts
            email_verification_sql = """
            CREATE TABLE IF NOT EXISTS email_verification_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                is_used BOOLEAN NOT NULL DEFAULT FALSE,
                used_at TIMESTAMP WITHOUT TIME ZONE
            );
            CREATE INDEX IF NOT EXISTS idx_email_verification_token ON email_verification_tokens(token);
            """
            
            password_reset_sql = """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                is_used BOOLEAN NOT NULL DEFAULT FALSE,
                used_at TIMESTAMP WITHOUT TIME ZONE,
                request_ip VARCHAR(45)
            );
            CREATE INDEX IF NOT EXISTS idx_password_reset_token ON password_reset_tokens(token);
            """
            
            db.session.execute(db.text(email_verification_sql))
            db.session.execute(db.text(password_reset_sql))
            db.session.commit()
            
            print("✅ Email tables created successfully!")
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error creating email tables: {e}")
            return False

if __name__ == '__main__':
    print("📧 Email Tables Setup")
    print("=" * 50)
    success = create_email_tables()
    if success:
        print("🎉 Email system ready!")
    else:
        print("💥 Setup failed!")