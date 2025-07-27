from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import JSON
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication and Steam data storage"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True)  # Nullable for migration
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Steam API credentials (encrypted)
    steam_api_key_encrypted = db.Column(db.Text, nullable=True)
    steam_id = db.Column(db.String(20), nullable=True, index=True)
    
    # Account metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    user_games = db.relationship('UserGame', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    steam_achievements = db.relationship('SteamAchievement', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    custom_achievements = db.relationship('CustomAchievement', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    shared_achievements = db.relationship('SharedAchievement', backref='creator', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'steam_id': self.steam_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_verified': self.is_verified,
            'is_active': self.is_active
        }


class Game(db.Model):
    """Steam game metadata"""
    __tablename__ = 'games'
    
    id = db.Column(db.Integer, primary_key=True)
    steam_app_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user_games = db.relationship('UserGame', backref='game', lazy='dynamic', cascade='all, delete-orphan')
    steam_achievements = db.relationship('SteamAchievement', backref='game', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Game {self.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'steam_app_id': self.steam_app_id,
            'name': self.name,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }


class UserGame(db.Model):
    """User's Steam library - games owned by user"""
    __tablename__ = 'user_games'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    
    # Game statistics
    playtime_minutes = db.Column(db.Integer, default=0, nullable=False)
    achievements_total = db.Column(db.Integer, default=0, nullable=False)
    achievements_unlocked = db.Column(db.Integer, default=0, nullable=False)
    
    # Sync metadata
    last_synced = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Constraints
    __table_args__ = (db.UniqueConstraint('user_id', 'game_id', name='unique_user_game'),)
    
    @property
    def playtime_hours(self):
        """Convert minutes to hours for display"""
        return round(self.playtime_minutes / 60, 2) if self.playtime_minutes else 0
    
    @property
    def progress_percentage(self):
        """Calculate achievement completion percentage"""
        if self.achievements_total == 0:
            return 0
        return round((self.achievements_unlocked / self.achievements_total) * 100, 2)
    
    def __repr__(self):
        return f'<UserGame {self.user.username}:{self.game.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'game_id': self.game_id,
            'steam_app_id': self.game.steam_app_id,
            'game_name': self.game.name,
            'playtime_hours': self.playtime_hours,
            'achievements_total': self.achievements_total,
            'achievements_unlocked': self.achievements_unlocked,
            'progress_percentage': self.progress_percentage,
            'last_synced': self.last_synced.isoformat() if self.last_synced else None
        }


class SteamAchievement(db.Model):
    """Individual Steam achievements for users"""
    __tablename__ = 'steam_achievements'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    
    # Achievement data
    api_name = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    achieved = db.Column(db.Boolean, default=False, nullable=False)
    unlock_time = db.Column(db.DateTime, nullable=True)
    
    # Constraints
    __table_args__ = (db.UniqueConstraint('user_id', 'game_id', 'api_name', name='unique_user_game_achievement'),)
    
    def __repr__(self):
        return f'<SteamAchievement {self.user.username}:{self.game.name}:{self.api_name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'api_name': self.api_name,
            'display_name': self.display_name,
            'description': self.description,
            'achieved': self.achieved,
            'unlock_time': self.unlock_time.isoformat() if self.unlock_time else None
        }


class CustomAchievement(db.Model):
    """Custom achievements created by users"""
    __tablename__ = 'custom_achievements'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Achievement details
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    condition_type = db.Column(db.String(50), nullable=False)  # 'all_games_100', 'all_games_owned', 'playtime_total'
    condition_data = db.Column(JSON, nullable=False)  # Store games list, playtime targets, etc.
    
    # Visual
    image_filename = db.Column(db.String(255), nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Import tracking (using simple references instead of foreign keys to avoid circular dependency)
    imported_from_shared_id = db.Column(db.Integer, nullable=True)  # Reference to shared achievement ID
    original_creator_username = db.Column(db.String(50), nullable=True)  # Store username instead of FK
    
    def __repr__(self):
        return f'<CustomAchievement {self.user.username}:{self.name}>'
    
    @property
    def games_list(self):
        """Get list of game IDs from condition_data"""
        return self.condition_data.get('games', []) if self.condition_data else []
    
    @property
    def playtime_target(self):
        """Get playtime target from condition_data"""
        return self.condition_data.get('playtime_target', 0) if self.condition_data else 0
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'condition_type': self.condition_type,
            'condition_data': self.condition_data,
            'image_filename': self.image_filename,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'original_creator': self.original_creator_username
        }


class SharedAchievement(db.Model):
    """Community shared achievements"""
    __tablename__ = 'shared_achievements'
    
    id = db.Column(db.Integer, primary_key=True)
    original_achievement_id = db.Column(db.Integer, nullable=True)  # Simple reference, no FK
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Achievement details (denormalized for performance)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    condition_type = db.Column(db.String(50), nullable=False)
    condition_data = db.Column(JSON, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)
    
    # Community metrics
    tries_count = db.Column(db.Integer, default=0, nullable=False)
    completions_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Metadata
    shared_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Note: original_achievement_id is a simple reference, not a foreign key
    
    def __repr__(self):
        return f'<SharedAchievement {self.creator.username}:{self.name}>'
    
    def increment_tries(self):
        """Increment the tries counter"""
        self.tries_count += 1
        db.session.commit()
    
    def increment_completions(self):
        """Increment the completions counter"""
        self.completions_count += 1
        db.session.commit()
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'condition_type': self.condition_type,
            'condition_data': self.condition_data,
            'image_filename': self.image_filename,
            'creator': self.creator.username,
            'tries_count': self.tries_count,
            'completions_count': self.completions_count,
            'shared_at': self.shared_at.isoformat() if self.shared_at else None
        }


class AchievementImage(db.Model):
    """Achievement image metadata and tracking"""
    __tablename__ = 'achievement_images'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True, nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(50), nullable=True)
    
    # Upload metadata
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    uploader = db.relationship('User', backref='uploaded_images')
    
    def __repr__(self):
        return f'<AchievementImage {self.filename}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'uploaded_by': self.uploader.username,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None
        }


# Database utility functions
def init_db(app):
    """Initialize database with Flask app"""
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")


def reset_db():
    """Reset database - DROP and CREATE all tables"""
    db.drop_all()
    db.create_all()
    print("Database reset completed!")


def get_or_create_game(steam_app_id, name):
    """Get existing game or create new one"""
    game = Game.query.filter_by(steam_app_id=steam_app_id).first()
    if not game:
        game = Game(steam_app_id=steam_app_id, name=name)
        db.session.add(game)
        db.session.commit()
    elif game.name != name:
        # Update game name if it changed
        game.name = name
        game.last_updated = datetime.utcnow()
        db.session.commit()
    
    return game


class ActivityFeed(db.Model):
    """Community activity feed for user achievements and milestones"""
    __tablename__ = 'activity_feed'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Activity type and content
    activity_type = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # References to related entities (nullable for flexibility)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=True)
    custom_achievement_id = db.Column(db.Integer, db.ForeignKey('custom_achievements.id'), nullable=True)
    shared_achievement_id = db.Column(db.Integer, db.ForeignKey('shared_achievements.id'), nullable=True)
    
    # Activity metadata stored as JSON
    activity_metadata = db.Column(JSON, nullable=True)
    
    # Privacy and display settings
    is_public = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_highlighted = db.Column(db.Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('activities', lazy='dynamic', cascade='all, delete-orphan'))
    game = db.relationship('Game', backref='activities')
    custom_achievement = db.relationship('CustomAchievement', backref='activities')
    shared_achievement = db.relationship('SharedAchievement', backref='activities')
    
    # Constraints for performance
    __table_args__ = (
        db.Index('idx_activity_public_recent', 'is_public', 'created_at'),
        db.Index('idx_activity_user_recent', 'user_id', 'created_at'),
    )
    
    def __repr__(self):
        return f'<ActivityFeed {self.user.username}:{self.activity_type}>'
    
    @property
    def time_ago(self):
        """Human-readable time since activity"""
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "Just now"
    
    def get_type_display(self):
        """Get human-readable activity type"""
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
        return type_map.get(self.activity_type, '📋 Activity')
    
    def get_icon(self):
        """Get emoji icon for activity type"""
        return self.get_type_display().split()[0]
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user': self.user.username,
            'activity_type': self.activity_type,
            'title': self.title,
            'description': self.description,
            'game': self.game.name if self.game else None,
            'custom_achievement': self.custom_achievement.name if self.custom_achievement else None,
            'shared_achievement': self.shared_achievement.name if self.shared_achievement else None,
            'metadata': self.activity_metadata,
            'is_public': self.is_public,
            'is_highlighted': self.is_highlighted,
            'created_at': self.created_at.isoformat(),
            'time_ago': self.time_ago,
            'type_display': self.get_type_display(),
            'icon': self.get_icon()
        }


# Activity feed utility functions
def log_activity(user_id, activity_type, title, description=None, **kwargs):
    """Log user activity for the community feed"""
    activity = ActivityFeed(
        user_id=user_id,
        activity_type=activity_type,
        title=title,
        description=description,
        game_id=kwargs.get('game_id'),
        custom_achievement_id=kwargs.get('custom_achievement_id'),
        shared_achievement_id=kwargs.get('shared_achievement_id'),
        activity_metadata=kwargs.get('metadata', {}),
        is_public=kwargs.get('is_public', True),
        is_highlighted=kwargs.get('is_highlighted', False)
    )
    
    db.session.add(activity)
    # Note: Caller should commit the transaction
    return activity

def get_recent_activities(limit=50, user_id=None, activity_type=None, include_private=False):
    """Get recent community activities with filtering"""
    query = ActivityFeed.query
    
    # Privacy filter
    if not include_private:
        query = query.filter(ActivityFeed.is_public == True)
    
    # User filter
    if user_id:
        query = query.filter(ActivityFeed.user_id == user_id)
    
    # Activity type filter
    if activity_type:
        query = query.filter(ActivityFeed.activity_type == activity_type)
    
    # Order by most recent and limit
    return query.order_by(ActivityFeed.created_at.desc()).limit(limit).all()


class EmailVerificationToken(db.Model):
    """Email verification tokens for new user registration"""
    __tablename__ = 'email_verification_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)  # Store email in case user changes it
    
    # Token metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', backref='verification_tokens')
    
    @property
    def is_expired(self):
        """Check if token has expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.is_used and not self.is_expired
    
    def mark_as_used(self):
        """Mark token as used"""
        self.is_used = True
        self.used_at = datetime.utcnow()

class EmailChangeToken(db.Model):
    """Model for email change tokens"""
    __tablename__ = 'email_change_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(255), unique=True, nullable=False)
    old_email = db.Column(db.String(255), nullable=True)
    new_email = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime, nullable=True)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('email_change_tokens', lazy=True))
    
    @property
    def is_expired(self):
        """Check if token has expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.is_used and not self.is_expired
    
    def mark_as_used(self):
        """Mark token as used"""
        self.is_used = True
        self.used_at = datetime.utcnow()


class PasswordResetToken(db.Model):
    """Password reset tokens for forgot password functionality"""
    __tablename__ = 'password_reset_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)  # Store email for security
    
    # Token metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    
    # IP tracking for security
    request_ip = db.Column(db.String(45), nullable=True)  # IPv6 support
    
    # Relationships
    user = db.relationship('User', backref='reset_tokens')
    
    @property
    def is_expired(self):
        """Check if token has expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.is_used and not self.is_expired
    
    def mark_as_used(self):
        """Mark token as used"""
        self.is_used = True
        self.used_at = datetime.utcnow()


class AchievementCollection(db.Model):
    """Curated collections of achievements for themed campaigns"""
    __tablename__ = 'achievement_collections'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    
    # Collection metadata
    collection_type = db.Column(db.String(50), nullable=False, default='seasonal')  # 'seasonal', 'featured', 'event', 'challenge'
    difficulty_level = db.Column(db.String(20), nullable=False, default='medium')  # 'easy', 'medium', 'hard', 'extreme'
    estimated_time = db.Column(db.String(50), nullable=True)  # '1-2 weeks', '1 month', etc.
    
    # Visual branding
    banner_image = db.Column(db.String(255), nullable=True)
    icon_image = db.Column(db.String(255), nullable=True)
    color_theme = db.Column(db.String(20), nullable=True, default='primary')  # Bootstrap color classes
    
    # Scheduling and availability
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    
    # Engagement metrics
    views_count = db.Column(db.Integer, default=0, nullable=False)
    participants_count = db.Column(db.Integer, default=0, nullable=False)
    completions_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Administrative
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    creator = db.relationship('User', backref='created_collections')
    items = db.relationship('CollectionItem', backref='collection', lazy='dynamic', cascade='all, delete-orphan')
    user_progress = db.relationship('UserCollectionProgress', backref='collection', lazy='dynamic', cascade='all, delete-orphan')
    
    # Constraints and indexes
    __table_args__ = (
        db.Index('idx_collection_active_featured', 'is_active', 'is_featured'),
        db.Index('idx_collection_type_active', 'collection_type', 'is_active'),
        db.Index('idx_collection_dates', 'start_date', 'end_date'),
    )
    
    def __repr__(self):
        return f'<AchievementCollection {self.name}>'
    
    @property
    def is_currently_active(self):
        """Check if collection is active within its date range"""
        if not self.is_active:
            return False
        
        now = datetime.utcnow()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True
    
    @property
    def progress_percentage(self):
        """Calculate average completion percentage across all participants"""
        if self.participants_count == 0:
            return 0
        
        total_progress = db.session.query(db.func.avg(UserCollectionProgress.completion_percentage)).filter(
            UserCollectionProgress.collection_id == self.id
        ).scalar()
        
        return round(total_progress or 0, 1)
    
    @property
    def total_achievements(self):
        """Get total number of achievements in this collection"""
        return self.items.count()
    
    def get_user_progress(self, user_id):
        """Get user's progress for this collection"""
        return UserCollectionProgress.query.filter_by(
            collection_id=self.id,
            user_id=user_id
        ).first()
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'collection_type': self.collection_type,
            'difficulty_level': self.difficulty_level,
            'estimated_time': self.estimated_time,
            'banner_image': self.banner_image,
            'icon_image': self.icon_image,
            'color_theme': self.color_theme,
            'is_active': self.is_active,
            'is_featured': self.is_featured,
            'is_currently_active': self.is_currently_active,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'views_count': self.views_count,
            'participants_count': self.participants_count,
            'completions_count': self.completions_count,
            'progress_percentage': self.progress_percentage,
            'total_achievements': self.total_achievements,
            'creator': self.creator.username,
            'created_at': self.created_at.isoformat()
        }


class CollectionItem(db.Model):
    """Individual achievements within a collection"""
    __tablename__ = 'collection_items'
    
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey('achievement_collections.id'), nullable=False)
    shared_achievement_id = db.Column(db.Integer, db.ForeignKey('shared_achievements.id'), nullable=False)
    
    # Item configuration
    order_index = db.Column(db.Integer, nullable=False, default=0)  # Order within collection
    is_required = db.Column(db.Boolean, default=True, nullable=False)  # Required vs optional
    point_value = db.Column(db.Integer, default=10, nullable=False)  # Points awarded for completion
    unlock_condition = db.Column(db.String(50), nullable=True)  # 'sequential', 'any', 'after_date', etc.
    
    # Item metadata
    added_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationships
    shared_achievement = db.relationship('SharedAchievement', backref='collection_items')
    adder = db.relationship('User', backref='added_collection_items')
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('collection_id', 'shared_achievement_id', name='unique_collection_achievement'),
        db.Index('idx_collection_order', 'collection_id', 'order_index'),
    )
    
    def __repr__(self):
        return f'<CollectionItem {self.collection.name}:{self.shared_achievement.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'collection_id': self.collection_id,
            'shared_achievement_id': self.shared_achievement_id,
            'order_index': self.order_index,
            'is_required': self.is_required,
            'point_value': self.point_value,
            'unlock_condition': self.unlock_condition,
            'achievement': self.shared_achievement.to_dict(),
            'added_at': self.added_at.isoformat()
        }


class UserCollectionProgress(db.Model):
    """Track user progress through achievement collections"""
    __tablename__ = 'user_collection_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    collection_id = db.Column(db.Integer, db.ForeignKey('achievement_collections.id'), nullable=False)
    
    # Progress tracking
    achievements_completed = db.Column(db.Integer, default=0, nullable=False)
    total_achievements = db.Column(db.Integer, default=0, nullable=False)
    points_earned = db.Column(db.Integer, default=0, nullable=False)
    total_points = db.Column(db.Integer, default=0, nullable=False)
    
    # Status and timing
    status = db.Column(db.String(20), default='in_progress', nullable=False)  # 'not_started', 'in_progress', 'completed', 'abandoned'
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Progress metadata stored as JSON
    progress_data = db.Column(JSON, nullable=True)  # Store specific achievement completion status, unlock dates, etc.
    
    # Relationships
    user = db.relationship('User', backref='collection_progress')
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('user_id', 'collection_id', name='unique_user_collection'),
        db.Index('idx_user_collection_status', 'user_id', 'status'),
        db.Index('idx_collection_progress', 'collection_id', 'status'),
    )
    
    def __repr__(self):
        return f'<UserCollectionProgress {self.user.username}:{self.collection.name}>'
    
    @property
    def completion_percentage(self):
        """Calculate completion percentage"""
        if self.total_achievements == 0:
            return 0
        return round((self.achievements_completed / self.total_achievements) * 100, 1)
    
    @property
    def points_percentage(self):
        """Calculate points completion percentage"""
        if self.total_points == 0:
            return 0
        return round((self.points_earned / self.total_points) * 100, 1)
    
    @property
    def is_completed(self):
        """Check if collection is fully completed"""
        return self.status == 'completed' and self.achievements_completed == self.total_achievements
    
    def update_progress(self):
        """Recalculate progress based on current collection items"""
        from sqlalchemy import and_
        
        # Get all collection items
        collection_items = CollectionItem.query.filter_by(collection_id=self.collection_id).all()
        
        if not collection_items:
            return
        
        # Count total achievements and points
        self.total_achievements = len(collection_items)
        self.total_points = sum(item.point_value for item in collection_items)
        
        # Count completed achievements
        completed_count = 0
        earned_points = 0
        progress_data = self.progress_data or {}
        
        for item in collection_items:
            # Check if user has imported this shared achievement
            user_custom_achievement = CustomAchievement.query.filter(
                and_(
                    CustomAchievement.user_id == self.user_id,
                    CustomAchievement.imported_from_shared_id == item.shared_achievement_id
                )
            ).first()
            
            if user_custom_achievement:
                completed_count += 1
                earned_points += item.point_value
                progress_data[str(item.id)] = {
                    'completed': True,
                    'completed_at': user_custom_achievement.created_at.isoformat(),
                    'points': item.point_value
                }
        
        # Update progress
        self.achievements_completed = completed_count
        self.points_earned = earned_points
        self.progress_data = progress_data
        self.last_activity = datetime.utcnow()
        
        # Update status
        if self.achievements_completed == self.total_achievements:
            if self.status != 'completed':
                self.status = 'completed'
                self.completed_at = datetime.utcnow()
        elif self.achievements_completed > 0:
            self.status = 'in_progress'
        else:
            self.status = 'not_started'
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'collection_id': self.collection_id,
            'achievements_completed': self.achievements_completed,
            'total_achievements': self.total_achievements,
            'points_earned': self.points_earned,
            'total_points': self.total_points,
            'completion_percentage': self.completion_percentage,
            'points_percentage': self.points_percentage,
            'status': self.status,
            'is_completed': self.is_completed,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'last_activity': self.last_activity.isoformat(),
            'progress_data': self.progress_data
        }


