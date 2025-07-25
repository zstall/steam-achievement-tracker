#!/usr/bin/env python3
"""
Data Migration Script - JSON to PostgreSQL
Migrates existing Steam Achievement Tracker data from JSON files to PostgreSQL database
"""

import os
import sys
import json
import csv
import glob
from datetime import datetime
from flask import Flask
from config import config
from models import db, User, Game, UserGame, SteamAchievement, CustomAchievement, SharedAchievement, AchievementImage, get_or_create_game
from cryptography.fernet import Fernet

class DataMigrator:
    def __init__(self):
        self.app = self.create_app()
        self.encryption_manager = None
        self.stats = {
            'users': 0,
            'games': 0,
            'user_games': 0,
            'steam_achievements': 0,
            'custom_achievements': 0,
            'shared_achievements': 0,
            'images': 0,
            'errors': []
        }
    
    def create_app(self):
        """Create Flask app with database configuration"""
        app = Flask(__name__)
        config_name = os.environ.get('FLASK_ENV', 'development')
        app.config.from_object(config[config_name])
        db.init_app(app)
        return app
    
    def setup_encryption(self):
        """Setup encryption for Steam API keys"""
        key = self.app.config.get('STEAM_ENCRYPTION_KEY')
        if not key:
            print("❌ STEAM_ENCRYPTION_KEY not found in environment!")
            sys.exit(1)
        
        try:
            self.encryption_manager = Fernet(key.encode())
            print("✅ Encryption manager initialized")
        except Exception as e:
            print(f"❌ Failed to initialize encryption: {e}")
            sys.exit(1)
    
    def encrypt_steam_api_key(self, api_key):
        """Encrypt Steam API key for secure storage"""
        if not api_key or not self.encryption_manager:
            return None
        try:
            return self.encryption_manager.encrypt(api_key.encode()).decode()
        except Exception as e:
            print(f"⚠️  Warning: Failed to encrypt API key: {e}")
            return None
    
    def backup_existing_data(self):
        """Create backups of existing JSON files"""
        backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(backup_dir, exist_ok=True)
        
        files_to_backup = [
            'users.json',
            'custom_achievements.json', 
            'shared_achievements.json'
        ]
        
        # Also backup CSV files
        csv_files = glob.glob('*_steam_library_with_achievements.csv')
        files_to_backup.extend(csv_files)
        
        backed_up = []
        for filename in files_to_backup:
            if os.path.exists(filename):
                backup_path = os.path.join(backup_dir, filename)
                os.system(f'cp "{filename}" "{backup_path}"')
                backed_up.append(filename)
        
        if backed_up:
            print(f"✅ Backed up {len(backed_up)} files to {backup_dir}/")
            return backup_dir
        else:
            print("ℹ️  No existing data files found to backup")
            return None
    
    def migrate_users(self):
        """Migrate users from users.json to users table"""
        print("👥 Migrating users...")
        
        if not os.path.exists('users.json'):
            print("⚠️  users.json not found, skipping user migration")
            return
        
        try:
            with open('users.json', 'r') as f:
                users_data = json.load(f)
            
            for username, data in users_data.items():
                # Check if user already exists
                existing_user = User.query.filter_by(username=username).first()
                if existing_user:
                    print(f"   User {username} already exists, skipping...")
                    continue
                
                # Encrypt Steam API key if present
                encrypted_api_key = None
                if data.get('steam_api_key'):
                    encrypted_api_key = self.encrypt_steam_api_key(data['steam_api_key'])
                
                # Create new user
                user = User(
                    username=username,
                    email=f"{username}@temp.example.com",  # Temporary email, user can update
                    password_hash=data.get('password_hash', ''),
                    steam_api_key_encrypted=encrypted_api_key,
                    steam_id=data.get('steam_id'),
                    created_at=datetime.utcnow(),
                    is_verified=False,  # Users will need to verify email
                    is_active=True
                )
                
                db.session.add(user)
                self.stats['users'] += 1
                print(f"   ✅ Migrated user: {username}")
            
            db.session.commit()
            print(f"✅ Successfully migrated {self.stats['users']} users")
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Failed to migrate users: {e}"
            print(f"❌ {error_msg}")
            self.stats['errors'].append(error_msg)
    
    def migrate_steam_data(self):
        """Migrate Steam game data from CSV files"""
        print("🎮 Migrating Steam game data...")
        
        csv_files = glob.glob('*_steam_library_with_achievements.csv')
        if not csv_files:
            print("⚠️  No Steam CSV files found, skipping Steam data migration")
            return
        
        for csv_file in csv_files:
            # Extract username from filename
            username = csv_file.replace('_steam_library_with_achievements.csv', '')
            user = User.query.filter_by(username=username).first()
            
            if not user:
                print(f"⚠️  User {username} not found for CSV {csv_file}, skipping...")
                continue
            
            print(f"   Processing {csv_file} for user {username}...")
            
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    game_data = {}
                    
                    for row in reader:
                        app_id = row['App ID']
                        game_name = row['Game Name']
                        playtime_hours = float(row['Playtime (Hours)']) if row['Playtime (Hours)'] else 0
                        
                        # Get or create game
                        game = get_or_create_game(app_id, game_name)
                        
                        # Track game data for this user
                        if app_id not in game_data:
                            game_data[app_id] = {
                                'game': game,
                                'playtime_minutes': int(playtime_hours * 60),
                                'achievements': []
                            }
                        
                        # Add achievement if present
                        if row['Achievement API Name']:
                            achievement_data = {
                                'api_name': row['Achievement API Name'],
                                'display_name': row['Achievement Display Name'],
                                'description': row['Description'],
                                'achieved': int(row['Achieved (1=Yes)']),
                                'unlock_time': row['Unlock Time (UTC)']
                            }
                            game_data[app_id]['achievements'].append(achievement_data)
                    
                    # Create UserGame and SteamAchievement records
                    for app_id, data in game_data.items():
                        game = data['game']
                        achievements = data['achievements']
                        
                        # Create or update UserGame
                        user_game = UserGame.query.filter_by(user_id=user.id, game_id=game.id).first()
                        if not user_game:
                            user_game = UserGame(
                                user_id=user.id,
                                game_id=game.id,
                                playtime_minutes=data['playtime_minutes'],
                                achievements_total=len(achievements),
                                achievements_unlocked=sum(1 for ach in achievements if ach['achieved']),
                                last_synced=datetime.utcnow()
                            )
                            db.session.add(user_game)
                            self.stats['user_games'] += 1
                        
                        # Add achievements
                        for ach in achievements:
                            # Check if achievement already exists
                            existing_ach = SteamAchievement.query.filter_by(
                                user_id=user.id,
                                game_id=game.id,
                                api_name=ach['api_name']
                            ).first()
                            
                            if not existing_ach:
                                unlock_time = None
                                if ach['unlock_time']:
                                    try:
                                        unlock_time = datetime.fromisoformat(ach['unlock_time'].replace('Z', '+00:00'))
                                    except:
                                        unlock_time = None
                                
                                steam_achievement = SteamAchievement(
                                    user_id=user.id,
                                    game_id=game.id,
                                    api_name=ach['api_name'],
                                    display_name=ach['display_name'],
                                    description=ach['description'],
                                    achieved=bool(ach['achieved']),
                                    unlock_time=unlock_time
                                )
                                db.session.add(steam_achievement)
                                self.stats['steam_achievements'] += 1
                
                db.session.commit()
                print(f"   ✅ Migrated Steam data for {username}")
                
            except Exception as e:
                db.session.rollback()
                error_msg = f"Failed to migrate Steam data for {username}: {e}"
                print(f"❌ {error_msg}")
                self.stats['errors'].append(error_msg)
        
        print(f"✅ Steam data migration completed: {self.stats['user_games']} games, {self.stats['steam_achievements']} achievements")
    
    def migrate_custom_achievements(self):
        """Migrate custom achievements from custom_achievements.json"""
        print("🏆 Migrating custom achievements...")
        
        if not os.path.exists('custom_achievements.json'):
            print("⚠️  custom_achievements.json not found, skipping custom achievements migration")
            return
        
        try:
            with open('custom_achievements.json', 'r') as f:
                achievements_data = json.load(f)
            
            for username, user_achievements in achievements_data.items():
                user = User.query.filter_by(username=username).first()
                if not user:
                    print(f"⚠️  User {username} not found, skipping their custom achievements...")
                    continue
                
                for ach_id, ach_data in user_achievements.items():
                    # Check if already exists
                    existing = CustomAchievement.query.filter_by(
                        user_id=user.id,
                        name=ach_data['name']
                    ).first()
                    
                    if existing:
                        print(f"   Achievement '{ach_data['name']}' already exists for {username}, skipping...")
                        continue
                    
                    # Handle imported achievements (store username directly)
                    original_creator_username = ach_data.get('original_creator')
                    
                    # Create condition_data JSON
                    condition_data = {
                        'games': ach_data.get('games', []),
                        'playtime_target': ach_data.get('playtime_target', '0')
                    }
                    
                    # Parse created_date
                    created_at = datetime.utcnow()
                    if ach_data.get('created_date'):
                        try:
                            created_at = datetime.fromisoformat(ach_data['created_date'].replace('Z', '+00:00'))
                        except:
                            pass
                    
                    custom_achievement = CustomAchievement(
                        user_id=user.id,
                        name=ach_data['name'],
                        description=ach_data['description'],
                        condition_type=ach_data['condition_type'],
                        condition_data=condition_data,
                        image_filename=ach_data.get('image_filename'),
                        created_at=created_at,
                        original_creator_username=original_creator_username
                    )
                    
                    db.session.add(custom_achievement)
                    self.stats['custom_achievements'] += 1
                    print(f"   ✅ Migrated custom achievement: {ach_data['name']} for {username}")
            
            db.session.commit()
            print(f"✅ Successfully migrated {self.stats['custom_achievements']} custom achievements")
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Failed to migrate custom achievements: {e}"
            print(f"❌ {error_msg}")
            self.stats['errors'].append(error_msg)
    
    def migrate_shared_achievements(self):
        """Migrate shared achievements from shared_achievements.json"""
        print("🌟 Migrating shared achievements...")
        
        if not os.path.exists('shared_achievements.json'):
            print("⚠️  shared_achievements.json not found, skipping shared achievements migration")
            return
        
        try:
            with open('shared_achievements.json', 'r') as f:
                shared_data = json.load(f)
            
            for shared_id, ach_data in shared_data.items():
                creator = User.query.filter_by(username=ach_data['creator']).first()
                if not creator:
                    print(f"⚠️  Creator {ach_data['creator']} not found, skipping shared achievement...")
                    continue
                
                # Check if already exists
                existing = SharedAchievement.query.filter_by(
                    creator_id=creator.id,
                    name=ach_data['name']
                ).first()
                
                if existing:
                    print(f"   Shared achievement '{ach_data['name']}' already exists, skipping...")
                    continue
                
                # Create condition_data JSON
                condition_data = {
                    'games': ach_data.get('games', []),
                    'playtime_target': ach_data.get('playtime_target', '0')
                }
                
                # Parse shared_date
                shared_at = datetime.utcnow()
                if ach_data.get('shared_date'):
                    try:
                        shared_at = datetime.fromisoformat(ach_data['shared_date'].replace('Z', '+00:00'))
                    except:
                        pass
                
                shared_achievement = SharedAchievement(
                    creator_id=creator.id,
                    original_achievement_id=None,  # Simple reference, no FK constraint
                    name=ach_data['name'],
                    description=ach_data['description'],
                    condition_type=ach_data['condition_type'],
                    condition_data=condition_data,
                    image_filename=ach_data.get('image_filename'),
                    tries_count=ach_data.get('tries', 0),
                    completions_count=ach_data.get('completions', 0),
                    shared_at=shared_at,
                    is_active=True
                )
                
                db.session.add(shared_achievement)
                self.stats['shared_achievements'] += 1
                print(f"   ✅ Migrated shared achievement: {ach_data['name']} by {ach_data['creator']}")
            
            db.session.commit()
            print(f"✅ Successfully migrated {self.stats['shared_achievements']} shared achievements")
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Failed to migrate shared achievements: {e}"
            print(f"❌ {error_msg}")
            self.stats['errors'].append(error_msg)
    
    def migrate_achievement_images(self):
        """Track achievement images in database"""
        print("🖼️  Cataloging achievement images...")
        
        image_dir = 'static/achievement_images'
        if not os.path.exists(image_dir):
            print(f"⚠️  Image directory {image_dir} not found, skipping image catalog")
            return
        
        try:
            image_files = glob.glob(os.path.join(image_dir, '*'))
            
            for image_path in image_files:
                filename = os.path.basename(image_path)
                
                # Check if already cataloged
                existing = AchievementImage.query.filter_by(filename=filename).first()
                if existing:
                    continue
                
                # Try to determine uploader from filename pattern
                uploader_id = None
                if '_' in filename:
                    # Format is usually: custom_X_timestamp_originalname.ext
                    parts = filename.split('_')
                    if len(parts) >= 2 and parts[0] == 'custom':
                        # Try to find the user who created this achievement
                        # This is best-effort based on filename patterns
                        pass
                
                # Get file stats
                file_size = os.path.getsize(image_path)
                
                # Create image record
                achievement_image = AchievementImage(
                    filename=filename,
                    original_filename=filename,
                    file_size=file_size,
                    mime_type='image/jpeg',  # Default, could be improved
                    uploaded_by=1,  # Default to first user, can be corrected later
                    uploaded_at=datetime.utcfromtimestamp(os.path.getctime(image_path))
                )
                
                db.session.add(achievement_image)
                self.stats['images'] += 1
            
            db.session.commit()
            print(f"✅ Cataloged {self.stats['images']} achievement images")
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Failed to catalog images: {e}"
            print(f"❌ {error_msg}")
            self.stats['errors'].append(error_msg)
    
    def print_migration_summary(self):
        """Print summary of migration results"""
        print("\n" + "="*60)
        print("📊 MIGRATION SUMMARY")
        print("="*60)
        print(f"👥 Users migrated:           {self.stats['users']}")
        print(f"🎮 Games processed:          {self.stats['games']}")
        print(f"📚 User games created:       {self.stats['user_games']}")
        print(f"⭐ Steam achievements:       {self.stats['steam_achievements']}")
        print(f"🏆 Custom achievements:      {self.stats['custom_achievements']}")
        print(f"🌟 Shared achievements:      {self.stats['shared_achievements']}")
        print(f"🖼️  Images cataloged:         {self.stats['images']}")
        
        if self.stats['errors']:
            print(f"\n⚠️  Errors encountered:      {len(self.stats['errors'])}")
            for error in self.stats['errors']:
                print(f"   - {error}")
        else:
            print(f"\n✅ Migration completed successfully with no errors!")
        
        print("\n🔥 Next steps:")
        print("1. Verify the migrated data in the database")
        print("2. Update your Flask application to use the database")
        print("3. Test the application functionality")
        print("4. Archive the original JSON files")
    
    def run_migration(self):
        """Run the complete migration process"""
        print("🚀 Starting data migration from JSON to PostgreSQL")
        print("="*60)
        
        with self.app.app_context():
            # Setup
            self.setup_encryption()
            backup_dir = self.backup_existing_data()
            
            # Run migrations in order
            self.migrate_users()
            self.migrate_steam_data()
            self.migrate_custom_achievements()
            self.migrate_shared_achievements()
            self.migrate_achievement_images()
            
            # Summary
            self.print_migration_summary()
            
            if backup_dir:
                print(f"\n💾 Original data backed up to: {backup_dir}")

def main():
    """Main function"""
    migrator = DataMigrator()
    migrator.run_migration()

if __name__ == '__main__':
    main()