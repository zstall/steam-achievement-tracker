# 🔥 Phase 1: Critical Infrastructure Implementation Plan

## Overview
**Timeline**: 4-6 weeks  
**Goal**: Transform MVP into secure, scalable foundation ready for public deployment  
**Status**: Planning → Implementation Ready

---

## 🗄️ Task 1: Database Migration (Week 1-2)

### Current State Analysis
```python
# Current data storage (JSON files):
- users.json (user accounts & Steam credentials)
- custom_achievements.json (user achievements) 
- shared_achievements.json (community achievements)
- {username}_steam_library_with_achievements.csv (Steam data)
- static/achievement_images/ (image files)
```

### Target Database Schema

```sql
-- Users and Authentication
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    steam_api_key_encrypted TEXT,
    steam_id VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE
);

-- Steam Games Data
CREATE TABLE games (
    id SERIAL PRIMARY KEY,
    steam_app_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User's Steam Library
CREATE TABLE user_games (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
    playtime_minutes INTEGER DEFAULT 0,
    achievements_total INTEGER DEFAULT 0,
    achievements_unlocked INTEGER DEFAULT 0,
    last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, game_id)
);

-- Steam Achievements
CREATE TABLE steam_achievements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
    api_name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    achieved BOOLEAN DEFAULT FALSE,
    unlock_time TIMESTAMP,
    UNIQUE(user_id, game_id, api_name)
);

-- Custom Achievements
CREATE TABLE custom_achievements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    condition_type VARCHAR(50) NOT NULL,
    condition_data JSONB, -- Store games list, playtime targets, etc.
    image_filename VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    imported_from INTEGER REFERENCES shared_achievements(id),
    original_creator_id INTEGER REFERENCES users(id)
);

-- Shared Community Achievements
CREATE TABLE shared_achievements (
    id SERIAL PRIMARY KEY,
    original_achievement_id INTEGER REFERENCES custom_achievements(id) ON DELETE CASCADE,
    creator_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    condition_type VARCHAR(50) NOT NULL,
    condition_data JSONB,
    image_filename VARCHAR(255),
    tries_count INTEGER DEFAULT 0,
    completions_count INTEGER DEFAULT 0,
    shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Achievement Images (metadata tracking)
CREATE TABLE achievement_images (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) UNIQUE NOT NULL,
    original_filename VARCHAR(255),
    file_size INTEGER,
    mime_type VARCHAR(50),
    uploaded_by INTEGER REFERENCES users(id),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Session Management
CREATE TABLE user_sessions (
    id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    data JSONB,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Migration Implementation Steps

**Step 1.1: Setup Database Environment (Day 1)**
```bash
# Install dependencies
pip install psycopg2-binary SQLAlchemy Flask-SQLAlchemy Flask-Migrate

# Docker Compose for development
version: '3.8'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: steam_tracker
      POSTGRES_USER: steam_user
      POSTGRES_PASSWORD: dev_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

**Step 1.2: Create Database Models (Day 2-3)**
```python
# models.py - SQLAlchemy models
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    # ... rest of fields
    
class Game(db.Model):
    __tablename__ = 'games'
    # ... model definition

# Continue for all tables...
```

**Step 1.3: Data Migration Scripts (Day 4-5)**
```python
# migrate_data.py - Script to migrate JSON to PostgreSQL
def migrate_users():
    """Migrate users.json to users table"""
    with open('users.json', 'r') as f:
        users_data = json.load(f)
    
    for username, data in users_data.items():
        user = User(
            username=username,
            email=f"{username}@temp.example.com",  # Require email update
            password_hash=data['password_hash'],
            steam_api_key_encrypted=encrypt_api_key(data.get('steam_api_key')),
            steam_id=data.get('steam_id')
        )
        db.session.add(user)
    
    db.session.commit()

def migrate_achievements():
    """Migrate custom_achievements.json"""
    # Implementation here...

def migrate_steam_data():
    """Migrate CSV files to database"""
    # Implementation here...
```

**Step 1.4: Update Application Code (Day 6-8)**
- Replace JSON file operations with database queries
- Update all routes to use SQLAlchemy models
- Add database session management

**Step 1.5: Testing & Validation (Day 9-10)**
- Data integrity verification
- Performance testing with sample data
- Rollback procedures

---

## 🔒 Task 2: Production Security (Week 3)

### Security Audit Findings
```python
# Current vulnerabilities to fix:
1. Hardcoded SECRET_KEY
2. Unencrypted Steam API keys in JSON
3. No CSRF token rotation
4. Missing input validation
5. No rate limiting on sensitive endpoints
6. Weak session configuration
```

### Security Implementation Plan

**Day 1-2: Environment Configuration**
```python
# config.py - Environment-based configuration
import os
from cryptography.fernet import Fernet

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or Fernet.generate_key()
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    STEAM_API_ENCRYPTION_KEY = os.environ.get('STEAM_ENCRYPTION_KEY')
    
    # Session Security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # File Upload Security
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max
    UPLOAD_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif'}

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    
class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP in dev
```

**Day 3-4: Encryption & Data Protection**
```python
# security.py - Encryption utilities
from cryptography.fernet import Fernet
import os

class EncryptionManager:
    def __init__(self):
        key = os.environ.get('STEAM_ENCRYPTION_KEY')
        if not key:
            raise ValueError("STEAM_ENCRYPTION_KEY environment variable required")
        self.cipher = Fernet(key.encode())
    
    def encrypt_steam_api_key(self, api_key: str) -> str:
        """Encrypt Steam API key for database storage"""
        return self.cipher.encrypt(api_key.encode()).decode()
    
    def decrypt_steam_api_key(self, encrypted_key: str) -> str:
        """Decrypt Steam API key for use"""
        return self.cipher.decrypt(encrypted_key.encode()).decode()

# Input validation
from wtforms.validators import ValidationError
import re

class SecureCustomAchievementForm(CustomAchievementForm):
    def validate_name(self, field):
        if not re.match(r'^[a-zA-Z0-9\s\-_]{3,100}$', field.data):
            raise ValidationError('Invalid characters in achievement name')
    
    def validate_description(self, field):
        # Prevent XSS attacks
        if '<script>' in field.data.lower() or 'javascript:' in field.data.lower():
            raise ValidationError('Invalid content in description')
```

**Day 5-7: Authentication Enhancement**
```python
# auth.py - Enhanced authentication
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    """Rate-limited login endpoint"""
    # Implementation with account lockout logic
    
@app.route('/register', methods=['POST'])  
@limiter.limit("3 per minute")
def register():
    """Rate-limited registration"""
    # Implementation with email verification
```

---

## 📧 Task 3: Enhanced Authentication (Week 4)

### Authentication Features Implementation

**Day 1-3: Email Verification System**
```python
# email.py - Email service integration
from flask_mail import Mail, Message
import secrets

def send_verification_email(user):
    token = secrets.token_urlsafe(32)
    # Store token in database with expiration
    # Send email with verification link
    
def verify_email(token):
    # Validate token and activate account
    pass
```

**Day 4-5: Password Reset Flow**
```python
# Reset password implementation
@app.route('/reset-password-request', methods=['POST'])
def reset_password_request():
    # Generate secure reset token
    # Send reset email
    # Store token with expiration
    
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Validate token
    # Allow password change
    # Invalidate token
```

**Day 6-7: Account Security Features**
```python
# Enhanced security features
- Account lockout after 5 failed attempts
- Password strength requirements
- Session management (logout all devices)
- Login activity logging
- Suspicious activity detection
```

---

## 🚨 Task 4: Error Handling & Logging (Week 5-6)

### Comprehensive Error Management

**Day 1-2: Custom Error Pages**
```html
<!-- templates/errors/404.html -->
<div class="error-page">
    <h1>Achievement Not Found</h1>
    <p>The achievement you're looking for doesn't exist or has been removed.</p>
    <a href="{{ url_for('index') }}">Back to Library</a>
</div>
```

**Day 3-4: Structured Logging**
```python
# logging_config.py
import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logging(app):
    if app.config['DEBUG']:
        level = logging.DEBUG
    else:
        level = logging.INFO
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s'
    )
    handler.setFormatter(formatter)
    
    app.logger.addHandler(handler)
    app.logger.setLevel(level)
```

**Day 5-7: Error Monitoring Integration**
```python
# monitoring.py - Sentry integration
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

sentry_sdk.init(
    dsn=os.environ.get('SENTRY_DSN'),
    integrations=[FlaskIntegration()],
    traces_sample_rate=1.0
)
```

---

## ✅ Phase 1 Deliverables Checklist

### Database Migration
- [ ] PostgreSQL setup and configuration
- [ ] All data models implemented
- [ ] Migration scripts tested
- [ ] Application updated to use database
- [ ] Data integrity verified

### Security Implementation  
- [ ] Environment variables configuration
- [ ] Steam API key encryption
- [ ] Input validation on all forms
- [ ] Rate limiting on sensitive endpoints
- [ ] Session security hardened

### Authentication Enhancement
- [ ] Email verification system
- [ ] Password reset functionality
- [ ] Account lockout protection
- [ ] Enhanced password requirements
- [ ] Login activity logging

### Error Handling & Logging
- [ ] Custom error pages for all error codes
- [ ] Structured JSON logging
- [ ] Error monitoring integration
- [ ] Health check endpoints
- [ ] Steam API failure handling

---

## 🧪 Testing Strategy

### Unit Tests
```python
# tests/test_models.py
def test_user_creation():
    user = User(username='testuser', email='test@example.com')
    assert user.username == 'testuser'

# tests/test_security.py  
def test_api_key_encryption():
    manager = EncryptionManager()
    encrypted = manager.encrypt_steam_api_key('test-key')
    assert manager.decrypt_steam_api_key(encrypted) == 'test-key'
```

### Integration Tests
```python
# tests/test_auth.py
def test_registration_flow():
    # Test complete registration → verification → login flow
    
def test_password_reset():
    # Test password reset flow
```

### Performance Tests
```python
# Test database performance with 1000+ users
# Test Steam API rate limiting
# Test file upload performance
```

---

## 📋 Daily Standup Template

**What did I accomplish yesterday?**
- [ ] Specific task completed

**What will I work on today?**
- [ ] Next priority task

**Any blockers or risks?**
- [ ] Dependencies or challenges

---

*Ready to start Phase 1 implementation! 🚀*