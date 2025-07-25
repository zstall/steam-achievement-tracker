from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectMultipleField, SelectField
from wtforms.validators import DataRequired, Length
from wtforms.widgets import CheckboxInput, ListWidget
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from cryptography.fernet import Fernet
import csv
import requests
import time
import json
import os
from datetime import datetime
from collections import defaultdict

# Import our models and configuration
from config import config
from models import db, User, Game, UserGame, SteamAchievement, CustomAchievement, SharedAchievement, AchievementImage, ActivityFeed, get_or_create_game, log_activity, get_recent_activities

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    db.init_app(app)
    
    # Create tables on first run (for Railway deployment)
    with app.app_context():
        try:
            # Check if tables exist by trying to query User table
            db.session.execute(db.text('SELECT 1 FROM "user" LIMIT 1'))
            print("✅ Database tables already exist")
        except Exception as e:
            print("🔧 Creating database tables...")
            db.create_all()
            print("✅ Database tables created successfully")
    
    return app

app = create_app()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access your Steam data.'

# Encryption manager for Steam API keys
class EncryptionManager:
    def __init__(self):
        key = app.config.get('STEAM_ENCRYPTION_KEY')
        if not key:
            raise ValueError("STEAM_ENCRYPTION_KEY not found in configuration")
        self.cipher = Fernet(key.encode())
    
    def encrypt_steam_api_key(self, api_key):
        """Encrypt Steam API key for database storage"""
        if not api_key:
            return None
        return self.cipher.encrypt(api_key.encode()).decode()
    
    def decrypt_steam_api_key(self, encrypted_key):
        """Decrypt Steam API key for use"""
        if not encrypted_key:
            return None
        return self.cipher.decrypt(encrypted_key.encode()).decode()

encryption_manager = EncryptionManager()

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID from database"""
    return User.query.get(int(user_id))

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Sign Up')

class ProfileForm(FlaskForm):
    steam_api_key = StringField('Steam API Key', validators=[DataRequired(), Length(min=32, max=32)])
    steam_id = StringField('Steam ID', validators=[DataRequired(), Length(min=17, max=17)])
    submit = SubmitField('Update Profile')

class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()

class CustomAchievementForm(FlaskForm):
    name = StringField('Achievement Name', validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(min=10, max=500)])
    condition_type = SelectField('Condition Type', choices=[
        ('all_games_100', 'Complete all selected games 100%'),
        ('all_games_owned', 'Own all selected games'),
        ('playtime_total', 'Total playtime across selected games'),
        ('specific_achievements', 'Unlock specific achievements in selected games')
    ], validators=[DataRequired()])
    games = MultiCheckboxField('Select Games', coerce=str)
    playtime_target = StringField('Target Hours (for playtime conditions)', default='0')
    achievement_image = FileField('Achievement Image', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')
    ])
    submit = SubmitField('Create Achievement')

# Legacy CSV loading function removed - now using database queries

def process_achievement_image(image_file, achievement_id):
    """Process and save achievement image"""
    if not image_file:
        return None
    
    # Create filename
    filename = secure_filename(f"{achievement_id}_{image_file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # Create directory if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Open and resize image
    image = Image.open(image_file)
    
    # Resize to standard achievement size (128x128)
    image = image.resize((128, 128), Image.Resampling.LANCZOS)
    
    # Convert to RGB if necessary (for PNG with transparency)
    if image.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', image.size, (26, 32, 56))  # Steam dark blue
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if 'A' in image.mode else None)
        image = background
    
    # Save image
    image.save(filepath, 'JPEG', quality=85, optimize=True)
    
    return filename

# Legacy JSON functions removed - now using database operations

def check_custom_achievement_progress_db(user_id, custom_achievement, games_list=None):
    """Check if a custom achievement is completed using database data"""
    condition_type = custom_achievement.condition_type
    required_games = custom_achievement.games_list
    
    if condition_type == 'all_games_100':
        # Check if all required games are 100% complete
        for game_id in required_games:
            user_game = UserGame.query.join(Game).filter(
                UserGame.user_id == user_id,
                Game.steam_app_id == game_id
            ).first()
            if not user_game or user_game.progress_percentage < 100:
                return False
        return True
    
    elif condition_type == 'all_games_owned':
        # Check if all required games are owned
        owned_games = UserGame.query.join(Game).filter(
            UserGame.user_id == user_id
        ).all()
        owned_game_ids = {ug.game.steam_app_id for ug in owned_games}
        return all(game_id in owned_game_ids for game_id in required_games)
    
    elif condition_type == 'playtime_total':
        # Check if total playtime across games meets target
        target_hours = float(custom_achievement.playtime_target or 0)
        user_games = UserGame.query.join(Game).filter(
            UserGame.user_id == user_id,
            Game.steam_app_id.in_(required_games)
        ).all()
        total_playtime = sum(ug.playtime_hours for ug in user_games)
        return total_playtime >= target_hours
    
    return False

def get_custom_achievement_progress_db(user_id, custom_achievement):
    """Get progress percentage for a custom achievement using database data"""
    condition_type = custom_achievement.condition_type
    required_games = custom_achievement.games_list
    
    if condition_type == 'all_games_100':
        completed_games = 0
        for game_id in required_games:
            user_game = UserGame.query.join(Game).filter(
                UserGame.user_id == user_id,
                Game.steam_app_id == game_id
            ).first()
            if user_game and user_game.progress_percentage >= 100:
                completed_games += 1
        return (completed_games / len(required_games)) * 100 if required_games else 0
    
    elif condition_type == 'all_games_owned':
        owned_games = UserGame.query.join(Game).filter(
            UserGame.user_id == user_id
        ).all()
        owned_game_ids = {ug.game.steam_app_id for ug in owned_games}
        owned_count = sum(1 for game_id in required_games if game_id in owned_game_ids)
        return (owned_count / len(required_games)) * 100 if required_games else 0
    
    elif condition_type == 'playtime_total':
        target_hours = float(custom_achievement.playtime_target or 0)
        if target_hours == 0:
            return 0
        user_games = UserGame.query.join(Game).filter(
            UserGame.user_id == user_id,
            Game.steam_app_id.in_(required_games)
        ).all()
        total_playtime = sum(ug.playtime_hours for ug in user_games)
        return min((total_playtime / target_hours) * 100, 100)
    
    return 0

# Legacy functions removed - now using database-based functions check_custom_achievement_progress_db and get_custom_achievement_progress_db

def fetch_and_save_steam_data(steam_api_key, steam_id):
    """Fetch Steam data and save to database with progress feedback"""
    print("🎮 Starting Steam data fetch...")
    
    # Step 1: Fetch owned games list
    print("📋 Fetching owned games list...")
    games_url = 'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/'
    games_params = {
        'key': steam_api_key,
        'steamid': steam_id,
        'include_appinfo': True,
        'include_played_free_games': True
    }
    
    try:
        games_response = requests.get(games_url, params=games_params)
        if games_response.status_code != 200:
            return False, f"Failed to fetch games! Status: {games_response.status_code}"
        
        games_data = games_response.json().get('response', {}).get('games', [])
        total_games = len(games_data)
        
        if total_games == 0:
            return True, "No games found in your Steam library"
        
        print(f"📊 Found {total_games} games in library. Processing achievements...")
        
        user_id = current_user.id
        games_processed = 0
        achievements_processed = 0
        games_with_achievements = 0
        
        # Process games in batches for better performance
        batch_size = 10
        
        for i, game in enumerate(games_data):
            appid = str(game['appid'])
            name = game.get('name', f'App {appid}')
            playtime_minutes = game['playtime_forever']
            
            # Progress logging every 10 games or at significant milestones
            if games_processed % batch_size == 0 or games_processed < 5:
                progress_percent = int((games_processed / total_games) * 100)
                print(f"⏳ Processing game {games_processed + 1}/{total_games} ({progress_percent}%): {name}")
            
            # Get or create game
            game_obj = get_or_create_game(appid, name)
            
            # Get achievements from Steam API
            achievements_url = 'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/'
            achievements_params = {
                'key': steam_api_key,
                'steamid': steam_id,
                'appid': appid
            }
            
            schema_url = 'https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/'
            schema_params = {
                'key': steam_api_key,
                'appid': appid
            }
            
            achievements_list = []
            try:
                # Fetch achievement data with timeout
                ach_response = requests.get(achievements_url, params=achievements_params, timeout=10)
                schema_response = requests.get(schema_url, params=schema_params, timeout=10)
                
                if ach_response.status_code == 200 and schema_response.status_code == 200:
                    ach_data = ach_response.json().get('playerstats', {})
                    ach_list = ach_data.get('achievements', [])
                    schema_data = schema_response.json().get('game', {}).get('availableGameStats', {}).get('achievements', [])
                    
                    if ach_list and schema_data:
                        games_with_achievements += 1
                        schema_map = {a['name']: a for a in schema_data}
                        
                        for ach in ach_list:
                            api_name = ach['apiname']
                            achieved = bool(ach['achieved'])
                            unlocktime = ach['unlocktime']
                            
                            schema = schema_map.get(api_name, {})
                            display_name = schema.get('displayName', api_name)
                            description = schema.get('description', '')
                            
                            unlock_time = None
                            if unlocktime > 0:
                                unlock_time = datetime.utcfromtimestamp(unlocktime)
                            
                            # Update or create Steam achievement
                            steam_ach = SteamAchievement.query.filter_by(
                                user_id=user_id,
                                game_id=game_obj.id,
                                api_name=api_name
                            ).first()
                            
                            if steam_ach:
                                # Update existing
                                steam_ach.display_name = display_name
                                steam_ach.description = description
                                steam_ach.achieved = achieved
                                steam_ach.unlock_time = unlock_time
                            else:
                                # Create new
                                steam_ach = SteamAchievement(
                                    user_id=user_id,
                                    game_id=game_obj.id,
                                    api_name=api_name,
                                    display_name=display_name,
                                    description=description,
                                    achieved=achieved,
                                    unlock_time=unlock_time
                                )
                                db.session.add(steam_ach)
                            
                            achievements_list.append(steam_ach)
                            achievements_processed += 1
                        
                        # Log achievement count for games with many achievements
                        if len(achievements_list) > 50:
                            print(f"   🏆 {name}: {len(achievements_list)} achievements")
                
            except requests.exceptions.Timeout:
                print(f"   ⏰ Timeout fetching achievements for {name}")
            except Exception as e:
                print(f"   ⚠️ Error fetching achievements for {name}: {str(e)[:100]}")
            
            # Update or create UserGame record
            user_game = UserGame.query.filter_by(user_id=user_id, game_id=game_obj.id).first()
            total_achievements = len(achievements_list)
            unlocked_achievements = sum(1 for ach in achievements_list if ach.achieved)
            
            if user_game:
                # Update existing
                user_game.playtime_minutes = playtime_minutes
                user_game.achievements_total = total_achievements
                user_game.achievements_unlocked = unlocked_achievements
                user_game.last_synced = datetime.utcnow()
            else:
                # Create new
                user_game = UserGame(
                    user_id=user_id,
                    game_id=game_obj.id,
                    playtime_minutes=playtime_minutes,
                    achievements_total=total_achievements,
                    achievements_unlocked=unlocked_achievements,
                    last_synced=datetime.utcnow()
                )
                db.session.add(user_game)
            
            games_processed += 1
            
            # Commit in batches to avoid long transactions
            if games_processed % batch_size == 0:
                try:
                    db.session.commit()
                    print(f"   💾 Saved batch {int(games_processed/batch_size)}")
                except Exception as e:
                    print(f"   ⚠️ Error saving batch: {e}")
                    db.session.rollback()
            
            # Rate limiting - be nice to Steam's API
            time.sleep(0.2)
        
        # Final commit for remaining games
        try:
            db.session.commit()
            print("✅ All data saved successfully!")
        except Exception as e:
            print(f"❌ Error in final commit: {e}")
            db.session.rollback()
            return False, f"Error saving final batch: {str(e)}"
        
        # Generate success message with statistics
        success_message = f"🎉 Steam sync completed successfully!\n"
        success_message += f"📊 Processed {games_processed} games\n"
        success_message += f"🏆 Found {achievements_processed} achievements\n"
        success_message += f"🎮 {games_with_achievements} games have achievements\n"
        success_message += f"⏰ Sync took approximately {int(games_processed * 0.2)} seconds"
        
        print(success_message)
        return True, success_message.replace('\n', ' • ')
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error fetching Steam data: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        user = User.query.filter_by(username=username).first()
        
        if user and user.is_active and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user:
            flash('Username already exists')
        else:
            user = User(
                username=username,
                email=f"{username}@temp.example.com",  # Temporary email
                password_hash=generate_password_hash(form.password.data),
                created_at=datetime.utcnow(),
                is_verified=False,
                is_active=True
            )
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please log in.')
            return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm()
    
    if form.validate_on_submit():
        # Encrypt and store Steam API key
        encrypted_api_key = encryption_manager.encrypt_steam_api_key(form.steam_api_key.data)
        
        # Update user in database
        current_user.steam_api_key_encrypted = encrypted_api_key
        current_user.steam_id = form.steam_id.data
        current_user.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Profile updated successfully!')
        return redirect(url_for('profile'))
    
    # Pre-populate form with existing data
    if current_user.steam_api_key_encrypted:
        decrypted_key = encryption_manager.decrypt_steam_api_key(current_user.steam_api_key_encrypted)
        form.steam_api_key.data = decrypted_key
    if current_user.steam_id:
        form.steam_id.data = current_user.steam_id
    
    return render_template('profile.html', form=form)

@app.route('/')
@login_required
def index():
    """Main page showing game library"""
    # Load user's games from database
    user_games = UserGame.query.filter_by(user_id=current_user.id).join(Game).all()
    
    games = []
    for user_game in user_games:
        # Convert to format expected by templates
        games.append({
            'appid': user_game.game.steam_app_id,
            'name': user_game.game.name,
            'playtime': user_game.playtime_hours,
            'progress': user_game.progress_percentage,
            'total_achievements': user_game.achievements_total,
            'unlocked_achievements': user_game.achievements_unlocked,
            'achievements': []  # Will be populated if needed for detail view
        })
    
    # Load completed custom achievements for trophy showcase
    user_custom_achievements = CustomAchievement.query.filter_by(user_id=current_user.id).all()
    
    completed_achievements = []
    for custom_ach in user_custom_achievements:
        if check_custom_achievement_progress_db(current_user.id, custom_ach, games):
            completed_achievements.append({
                'id': custom_ach.id,
                'name': custom_ach.name,
                'description': custom_ach.description,
                'image_filename': custom_ach.image_filename,
                'created_date': custom_ach.created_at.isoformat() if custom_ach.created_at else ''
            })
    
    # Sort by creation date (newest first)
    completed_achievements.sort(key=lambda x: x.get('created_date', ''), reverse=True)
    
    return render_template('index.html', games=games, completed_achievements=completed_achievements)

@app.route('/game/<appid>')
@login_required
def game_detail(appid):
    """Individual game achievement page"""
    # Find game and user's data for this game
    game_obj = Game.query.filter_by(steam_app_id=appid).first()
    if not game_obj:
        return "Game not found", 404
    
    user_game = UserGame.query.filter_by(user_id=current_user.id, game_id=game_obj.id).first()
    if not user_game:
        return "Game not in your library", 404
    
    # Load achievements for this game
    steam_achievements = SteamAchievement.query.filter_by(
        user_id=current_user.id, 
        game_id=game_obj.id
    ).all()
    
    achievements = []
    for ach in steam_achievements:
        achievements.append({
            'api_name': ach.api_name,
            'display_name': ach.display_name,
            'description': ach.description,
            'achieved': 1 if ach.achieved else 0,
            'unlock_time': ach.unlock_time.isoformat() if ach.unlock_time else ''
        })
    
    # Build game data structure expected by template
    game = {
        'appid': game_obj.steam_app_id,
        'name': game_obj.name,
        'playtime': user_game.playtime_hours,
        'progress': user_game.progress_percentage,
        'total_achievements': user_game.achievements_total,
        'unlocked_achievements': user_game.achievements_unlocked,
        'achievements': achievements
    }
    
    return render_template('game_detail.html', game=game)

@app.route('/api/refresh')
@login_required
def refresh_data():
    """API endpoint to refresh Steam data"""
    if not current_user.steam_api_key_encrypted or not current_user.steam_id:
        return jsonify({'error': 'Steam API credentials not configured. Please update your profile.'}), 400
    
    # Decrypt Steam API key
    steam_api_key = encryption_manager.decrypt_steam_api_key(current_user.steam_api_key_encrypted)
    
    success, message = fetch_and_save_steam_data(steam_api_key, current_user.steam_id)
    
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 500

@app.route('/api/games')
@login_required
def api_games():
    """JSON API for games data"""
    user_games = UserGame.query.filter_by(user_id=current_user.id).join(Game).all()
    
    games = []
    for user_game in user_games:
        games.append({
            'appid': user_game.game.steam_app_id,
            'name': user_game.game.name,
            'playtime': user_game.playtime_hours,
            'progress': user_game.progress_percentage,
            'total_achievements': user_game.achievements_total,
            'unlocked_achievements': user_game.achievements_unlocked
        })
    
    return jsonify(games)

@app.route('/custom-achievements')
@login_required
def custom_achievements():
    """Display custom achievements page"""
    # Load user's custom achievements from database
    user_custom_achievements = CustomAchievement.query.filter_by(user_id=current_user.id).all()
    
    # Calculate progress for each achievement
    achievement_status = []
    for custom_ach in user_custom_achievements:
        progress = get_custom_achievement_progress_db(current_user.id, custom_ach)
        completed = check_custom_achievement_progress_db(current_user.id, custom_ach)
        
        # Get game names for display
        game_names = []
        for game_id in custom_ach.games_list:
            game = Game.query.filter_by(steam_app_id=game_id).first()
            if game:
                game_names.append(game.name)
            else:
                game_names.append(f"App {game_id}")
        
        achievement_status.append({
            'id': custom_ach.id,
            'name': custom_ach.name,
            'description': custom_ach.description,
            'condition_type': custom_ach.condition_type,
            'games': game_names,
            'progress': progress,
            'completed': completed,
            'playtime_target': custom_ach.playtime_target,
            'image_filename': custom_ach.image_filename,
            'original_creator': custom_ach.original_creator_username
        })
    
    return render_template('custom_achievements.html', achievements=achievement_status)

@app.route('/create-achievement', methods=['GET', 'POST'])
@login_required
def create_achievement():
    """Create a new custom achievement"""
    # Load user's games from database for the form
    user_games = UserGame.query.filter_by(user_id=current_user.id).join(Game).all()
    games = [{'appid': ug.game.steam_app_id, 'name': ug.game.name} for ug in user_games]
    
    form = CustomAchievementForm()
    
    # Populate game choices
    game_choices = [(g['appid'], g['name']) for g in games if g['name']]
    form.games.choices = game_choices
    
    if form.validate_on_submit():
        # Process image upload
        image_filename = None
        if form.achievement_image.data:
            # Create a unique filename
            achievement_id = f"custom_{current_user.id}_{int(time.time())}"
            image_filename = process_achievement_image(form.achievement_image.data, achievement_id)
            
            # Store image metadata in database
            achievement_image = AchievementImage(
                filename=image_filename,
                original_filename=form.achievement_image.data.filename,
                file_size=0,  # Could calculate actual size
                mime_type='image/jpeg',
                uploaded_by=current_user.id,
                uploaded_at=datetime.utcnow()
            )
            db.session.add(achievement_image)
        
        # Create condition_data JSON
        condition_data = {
            'games': form.games.data,
            'playtime_target': form.playtime_target.data if form.condition_type.data == 'playtime_total' else '0'
        }
        
        # Create custom achievement
        custom_achievement = CustomAchievement(
            user_id=current_user.id,
            name=form.name.data,
            description=form.description.data,
            condition_type=form.condition_type.data,
            condition_data=condition_data,
            image_filename=image_filename,
            created_at=datetime.utcnow()
        )
        
        db.session.add(custom_achievement)
        
        # Log activity for creating custom achievement
        log_activity(
            user_id=current_user.id,
            activity_type='custom_achievement_created',
            title=f'Created custom achievement "{form.name.data}"',
            description=form.description.data,
            custom_achievement_id=custom_achievement.id,
            metadata={
                'condition_type': form.condition_type.data,
                'games_count': len(form.games.data)
            }
        )
        
        db.session.commit()
        
        flash(f'Custom achievement "{form.name.data}" created successfully!')
        return redirect(url_for('custom_achievements'))
    
    return render_template('create_achievement.html', form=form, games=games)

@app.route('/delete-achievement/<int:achievement_id>')
@login_required
def delete_achievement(achievement_id):
    """Delete a custom achievement"""
    custom_achievement = CustomAchievement.query.filter_by(
        id=achievement_id, 
        user_id=current_user.id
    ).first()
    
    if custom_achievement:
        achievement_name = custom_achievement.name
        
        # Delete associated image if exists
        if custom_achievement.image_filename:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], custom_achievement.image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)
            
            # Remove from image database
            achievement_image = AchievementImage.query.filter_by(
                filename=custom_achievement.image_filename
            ).first()
            if achievement_image:
                db.session.delete(achievement_image)
        
        db.session.delete(custom_achievement)
        db.session.commit()
        flash(f'Achievement "{achievement_name}" deleted successfully!')
    else:
        flash('Achievement not found!')
    
    return redirect(url_for('custom_achievements'))

@app.route('/share-achievement/<int:achievement_id>')
@login_required
def share_achievement_route(achievement_id):
    """Share an achievement to the community"""
    custom_achievement = CustomAchievement.query.filter_by(
        id=achievement_id,
        user_id=current_user.id
    ).first()
    
    if not custom_achievement:
        flash('Achievement not found!')
        return redirect(url_for('custom_achievements'))
    
    # Check if already shared
    existing_shared = SharedAchievement.query.filter_by(
        creator_id=current_user.id,
        original_achievement_id=achievement_id
    ).first()
    
    if existing_shared:
        flash('Achievement is already shared to the community!')
        return redirect(url_for('custom_achievements'))
    
    # Create shared achievement
    shared_achievement = SharedAchievement(
        creator_id=current_user.id,
        original_achievement_id=achievement_id,
        name=custom_achievement.name,
        description=custom_achievement.description,
        condition_type=custom_achievement.condition_type,
        condition_data=custom_achievement.condition_data,
        image_filename=custom_achievement.image_filename,
        tries_count=0,
        completions_count=0,
        shared_at=datetime.utcnow(),
        is_active=True
    )
    
    db.session.add(shared_achievement)
    
    # Log activity for sharing achievement
    log_activity(
        user_id=current_user.id,
        activity_type='custom_achievement_shared',
        title=f'Shared "{custom_achievement.name}" with the community',
        description=custom_achievement.description,
        custom_achievement_id=achievement_id,
        shared_achievement_id=shared_achievement.id,
        metadata={
            'condition_type': custom_achievement.condition_type,
            'games_count': len(custom_achievement.games_list)
        }
    )
    
    db.session.commit()
    
    flash(f'Achievement "{custom_achievement.name}" shared to the community!')
    return redirect(url_for('custom_achievements'))

@app.route('/unshare-achievement/<int:achievement_id>')
@login_required
def unshare_achievement(achievement_id):
    """Remove an achievement from community sharing"""
    shared_achievement = SharedAchievement.query.filter_by(
        creator_id=current_user.id,
        original_achievement_id=achievement_id
    ).first()
    
    if shared_achievement:
        db.session.delete(shared_achievement)
        db.session.commit()
        flash('Achievement removed from community sharing!')
    else:
        flash('Achievement was not shared!')
    
    return redirect(url_for('custom_achievements'))

@app.route('/community-achievements')
@login_required
def community_achievements():
    """Display community shared achievements"""
    # Load shared achievements from database (exclude user's own)
    shared_achievements = SharedAchievement.query.filter(
        SharedAchievement.creator_id != current_user.id,
        SharedAchievement.is_active == True
    ).join(User).all()
    
    # Load user's games to check compatibility
    user_games = UserGame.query.filter_by(user_id=current_user.id).join(Game).all()
    user_game_ids = {ug.game.steam_app_id for ug in user_games}
    
    # Get user's imported achievements for checking duplicates
    user_imported = CustomAchievement.query.filter_by(user_id=current_user.id).filter(
        CustomAchievement.imported_from_shared_id.isnot(None)
    ).all()
    imported_shared_ids = {ach.imported_from_shared_id for ach in user_imported}
    
    # Process shared achievements for display
    community_list = []
    for shared_ach in shared_achievements:
        # Check compatibility (how many required games the user owns)
        required_games = shared_ach.condition_data.get('games', [])
        owned_required = len([gid for gid in required_games if gid in user_game_ids])
        compatibility = (owned_required / len(required_games)) * 100 if required_games else 0
        
        # Get game names
        game_names = []
        for game_id in required_games:
            game = Game.query.filter_by(steam_app_id=game_id).first()
            if game:
                game_names.append(game.name)
            else:
                game_names.append(f"App {game_id}")
        
        # Check if already imported
        already_imported = shared_ach.id in imported_shared_ids
        
        community_list.append({
            'shared_id': shared_ach.id,
            'name': shared_ach.name,
            'description': shared_ach.description,
            'creator': shared_ach.creator.username,
            'condition_type': shared_ach.condition_type,
            'games': game_names,
            'tries': shared_ach.tries_count,
            'completions': shared_ach.completions_count,
            'compatibility': compatibility,
            'image_filename': shared_ach.image_filename,
            'shared_date': shared_ach.shared_at.isoformat() if shared_ach.shared_at else '',
            'playtime_target': shared_ach.condition_data.get('playtime_target', 0),
            'already_imported': already_imported
        })
    
    # Sort by popularity (tries + completions) and compatibility
    community_list.sort(key=lambda x: (x['tries'] + x['completions'], x['compatibility']), reverse=True)
    
    return render_template('community_achievements.html', achievements=community_list)

@app.route('/import-achievement/<int:shared_id>')
@login_required
def import_achievement_route(shared_id):
    """Import a shared achievement to user's collection"""
    shared_achievement = SharedAchievement.query.get(shared_id)
    
    if not shared_achievement or not shared_achievement.is_active:
        flash('Shared achievement not found!')
        return redirect(url_for('community_achievements'))
    
    # Check if user already imported this specific shared achievement
    existing_import = CustomAchievement.query.filter_by(
        user_id=current_user.id,
        imported_from_shared_id=shared_achievement.id
    ).first()
    
    if existing_import:
        flash(f'You have already imported "{shared_achievement.name}" from the community!')
        return redirect(url_for('community_achievements'))
    
    # Also check if user already has an achievement with the same name
    existing_name = CustomAchievement.query.filter_by(
        user_id=current_user.id,
        name=shared_achievement.name
    ).first()
    
    if existing_name:
        flash(f'You already have an achievement named "{shared_achievement.name}". Try renaming it first if you want to import this version.')
        return redirect(url_for('community_achievements'))
    
    # Create custom achievement for user
    custom_achievement = CustomAchievement(
        user_id=current_user.id,
        name=shared_achievement.name,
        description=shared_achievement.description,
        condition_type=shared_achievement.condition_type,
        condition_data=shared_achievement.condition_data,
        image_filename=shared_achievement.image_filename,
        created_at=datetime.utcnow(),
        imported_from_shared_id=shared_achievement.id,
        original_creator_username=shared_achievement.creator.username
    )
    
    db.session.add(custom_achievement)
    
    # Increment tries counter
    shared_achievement.tries_count += 1
    
    # Log activity for importing achievement
    log_activity(
        user_id=current_user.id,
        activity_type='community_achievement_imported',
        title=f'Imported "{shared_achievement.name}" from the community',
        description=f'Originally created by @{shared_achievement.creator.username}',
        custom_achievement_id=custom_achievement.id,
        shared_achievement_id=shared_achievement.id,
        metadata={
            'original_creator': shared_achievement.creator.username,
            'condition_type': shared_achievement.condition_type
        }
    )
    
    db.session.commit()
    
    flash(f'Achievement "{shared_achievement.name}" imported successfully!')
    return redirect(url_for('community_achievements'))

@app.route('/admin/cleanup-duplicates')
@login_required
def admin_cleanup_duplicates():
    """Admin route to clean up duplicate shared achievements"""
    if current_user.username != 'admin':  # Simple admin check
        flash('Access denied!')
        return redirect(url_for('index'))
    
    # Find duplicates
    all_shared = SharedAchievement.query.all()
    seen = {}
    
    for achievement in all_shared:
        key = (achievement.creator_id, achievement.name)
        if key not in seen:
            seen[key] = []
        seen[key].append(achievement)
    
    duplicates_removed = 0
    for achievements in seen.values():
        if len(achievements) > 1:
            # Keep the most recent, remove the rest
            achievements.sort(key=lambda x: x.shared_at, reverse=True)
            for dup in achievements[1:]:
                db.session.delete(dup)
                duplicates_removed += 1
    
    if duplicates_removed > 0:
        db.session.commit()
        flash(f'Cleaned up {duplicates_removed} duplicate shared achievements!')
    else:
        flash('No duplicates found!')
    
    return redirect(url_for('community_achievements'))

@app.route('/trophy-feed')
@login_required
def trophy_feed():
    """Display the community trophy feed"""
    # Get filter parameters
    activity_filter = request.args.get('filter', 'all')
    user_filter = request.args.get('user')
    page = int(request.args.get('page', 1))
    
    # Base query parameters
    query_params = {
        'limit': 20 * page,  # Load more as we paginate
        'include_private': False
    }
    
    # Apply filters
    if activity_filter != 'all':
        query_params['activity_type'] = activity_filter
    
    if user_filter and user_filter != 'all':
        user = User.query.filter_by(username=user_filter).first()
        if user:
            query_params['user_id'] = user.id
    
    # Get activities
    activities = get_recent_activities(**query_params)
    
    # Get unique users for filter dropdown
    recent_users = db.session.query(User).join(ActivityFeed).filter(
        ActivityFeed.is_public == True
    ).distinct().limit(20).all()
    
    # Activity type options for filter
    activity_types = [
        ('all', '🏆 All Activities'),
        ('custom_achievement_shared', '🌟 Shared Achievements'),
        ('community_achievement_imported', '📥 Imported Achievements'),
        ('custom_achievement_created', '🎯 Created Achievements'),
        ('game_completed', '🎉 Game Completions'),
        ('milestone_reached', '⭐ Milestones')
    ]
    
    return render_template('trophy_feed.html', 
                         activities=activities,
                         activity_types=activity_types,
                         recent_users=recent_users,
                         current_filter=activity_filter,
                         current_user_filter=user_filter,
                         page=page)

@app.route('/api/trophy-feed')
@login_required
def api_trophy_feed():
    """JSON API for trophy feed (for AJAX loading)"""
    activity_filter = request.args.get('filter', 'all')
    user_filter = request.args.get('user')
    limit = int(request.args.get('limit', 20))
    
    query_params = {
        'limit': limit,
        'include_private': False
    }
    
    if activity_filter != 'all':
        query_params['activity_type'] = activity_filter
    
    if user_filter and user_filter != 'all':
        user = User.query.filter_by(username=user_filter).first()
        if user:
            query_params['user_id'] = user.id
    
    activities = get_recent_activities(**query_params)
    
    return jsonify({
        'activities': [activity.to_dict() for activity in activities],
        'count': len(activities)
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)