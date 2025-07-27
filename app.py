from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectMultipleField, SelectField
from wtforms.validators import DataRequired, Length, Email, ValidationError
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
from models import db, User, Game, UserGame, SteamAchievement, CustomAchievement, SharedAchievement, AchievementImage, ActivityFeed, EmailVerificationToken, PasswordResetToken, AchievementCollection, CollectionItem, UserCollectionProgress, UserFriendship, get_or_create_game, log_activity, get_recent_activities, get_user_friends, get_mutual_friends, are_friends, get_friendship_status
from s3_manager import s3_manager
from email_service import email_service

def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    config_name = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    
    # Initialize database
    db.init_app(app)
    
    # Initialize S3 manager
    s3_manager.init_app(app)
    
    # Initialize email service
    email_service.init_app(app)
    
    # Create tables on first run (for Railway deployment)
    with app.app_context():
        try:
            # Check if tables exist by trying to query User table
            db.session.execute(db.text('SELECT 1 FROM "user" LIMIT 1'))
            print("✅ Database tables already exist")
            
            # Check if email tables exist, if not suggest manual creation
            try:
                db.session.execute(db.text('SELECT 1 FROM email_verification_tokens LIMIT 1'))
                print("✅ Email tables already exist")
            except Exception:
                print("⚠️  Email tables missing - run create_email_tables.py manually")
            
            # Fix existing users automatically
            try:
                users_to_fix = User.query.filter(
                    db.or_(
                        User.is_verified == False,
                        User.email.like('%@temp.example.com'),
                        User.email == None
                    )
                ).all()
                
                if users_to_fix:
                    print(f"🔧 Fixing {len(users_to_fix)} existing users...")
                    for user in users_to_fix:
                        if not user.email or '@temp.example.com' in user.email or user.email is None:
                            user.email = f"{user.username}@temp-verified.local"
                        user.is_verified = True
                        print(f"   ✅ Fixed user: {user.username} (email: {user.email})")
                    
                    db.session.commit()
                    print("✅ All existing users fixed and can now log in")
                else:
                    print("✅ All users already have proper verification status")
                    
            except Exception as e:
                print(f"⚠️  Could not fix existing users: {e}")
                # Don't fail the app startup for this
                
        except Exception as e:
            print("🔧 Creating basic database tables...")
            # Only create basic tables, skip email tables to avoid conflicts
            from models import User, Game, UserGame, SteamAchievement, CustomAchievement, SharedAchievement, AchievementImage, ActivityFeed
            
            # Create tables individually to avoid email table conflicts
            User.__table__.create(db.engine, checkfirst=True)
            Game.__table__.create(db.engine, checkfirst=True)
            UserGame.__table__.create(db.engine, checkfirst=True)
            SteamAchievement.__table__.create(db.engine, checkfirst=True)
            CustomAchievement.__table__.create(db.engine, checkfirst=True)
            SharedAchievement.__table__.create(db.engine, checkfirst=True)
            AchievementImage.__table__.create(db.engine, checkfirst=True)
            ActivityFeed.__table__.create(db.engine, checkfirst=True)
            
            print("✅ Basic database tables created successfully")
            print("⚠️  Run create_email_tables.py to add email functionality")
    
    return app

app = create_app()

# Template helper function for image URLs
@app.template_global()
def get_achievement_image_url(filename):
    """Get the correct URL for an achievement image (S3 or local)"""
    if not filename:
        return None
    return s3_manager.get_image_url(filename)

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
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Sign Up')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=255)])
    submit = SubmitField('Send Reset Link')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm New Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Reset Password')
    
    def validate_confirm_password(self, field):
        if field.data != self.password.data:
            raise ValidationError('Passwords must match')

class ProfileForm(FlaskForm):
    email = StringField('Email Address', validators=[Email(message="Invalid email address")])
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

def process_achievement_image(image_file, user_id, achievement_id):
    """Process and save achievement image using S3 or local storage"""
    if not image_file:
        return None, None
    
    # Use S3 manager to upload image
    filename, url = s3_manager.upload_image(image_file, user_id, achievement_id)
    
    if filename:
        print(f"✅ Achievement image processed: {filename}")
        return filename, url
    else:
        print("❌ Failed to process achievement image")
        return None, None

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
            if not user.is_verified:
                flash('Please verify your email address before logging in. Check your email for the verification link.', 'warning')
            else:
                login_user(user)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        
        # Check for existing username or email
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            if existing_user.username == username:
                flash('Username already exists', 'error')
            else:
                flash('Email address already registered', 'error')
        else:
            try:
                user = User(
                    username=username,
                    email=email,
                    password_hash=generate_password_hash(form.password.data),
                    created_at=datetime.utcnow(),
                    is_verified=False,  # Require email verification
                    is_active=True
                )
                db.session.add(user)
                db.session.commit()
                
                # Send verification email
                if email_service.send_verification_email(user):
                    flash('Registration successful! Please check your email to verify your account before logging in.', 'success')
                else:
                    flash('Registration successful, but we couldn\'t send the verification email. Please contact support.', 'warning')
                
                return redirect(url_for('login'))
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ Registration error: {e}")
                flash('Registration failed. Please try again.', 'error')
    
    return render_template('register.html', form=form)

@app.route('/verify-email/<token>')
def verify_email(token):
    """Verify email address using token"""
    verification_token = EmailVerificationToken.query.filter_by(token=token).first()
    
    if not verification_token:
        flash('Invalid verification link.', 'error')
        return redirect(url_for('login'))
    
    if not verification_token.is_valid:
        if verification_token.is_used:
            flash('This verification link has already been used.', 'info')
        else:
            flash('This verification link has expired. Please request a new one.', 'error')
        return redirect(url_for('login'))
    
    # Verify the user
    user = verification_token.user
    user.is_verified = True
    verification_token.mark_as_used()
    
    db.session.commit()
    
    flash('Email verified successfully! You can now log in.', 'success')
    return redirect(url_for('login'))

@app.route('/resend-verification')
def resend_verification():
    """Resend verification email (for logged out users)"""
    # We'll implement this if needed
    flash('Please contact support to resend verification email.', 'info')
    return redirect(url_for('login'))

@app.route('/confirm-email-change/<token>')
def confirm_email_change(token):
    """Confirm email change with token"""
    from models import EmailChangeToken
    
    # Find the token
    change_token = EmailChangeToken.query.filter_by(token=token).first()
    
    if not change_token:
        flash('Invalid or expired email change link.', 'error')
        return redirect(url_for('login'))
    
    if not change_token.is_valid:
        if change_token.is_used:
            flash('This email change link has already been used.', 'error')
        else:
            flash('This email change link has expired.', 'error')
        return redirect(url_for('login'))
    
    # Get the user
    user = change_token.user
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))
    
    # Update user's email
    old_email = user.email
    user.email = change_token.new_email
    user.updated_at = datetime.utcnow()
    
    # Mark token as used
    change_token.mark_as_used()
    
    db.session.commit()
    
    flash(f'Your email has been successfully changed to {change_token.new_email}!', 'success')
    
    # If user is logged in, redirect to profile, otherwise to login
    if current_user.is_authenticated and current_user.id == user.id:
        return redirect(url_for('profile'))
    else:
        return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password requests"""
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data
        user = User.query.filter_by(email=email).first()
        
        if user:
            try:
                # Get client IP for security logging
                client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                
                # Send password reset email
                if email_service.send_password_reset_email(user, client_ip):
                    flash('Password reset instructions have been sent to your email address.', 'success')
                else:
                    flash('Unable to send reset email at this time. Please try again later.', 'error')
            except Exception as e:
                print(f"❌ Password reset error: {e}")
                flash('An error occurred. Please try again later.', 'error')
        else:
            # Don't reveal whether email exists for security
            flash('Password reset instructions have been sent to your email address.', 'success')
        
        return redirect(url_for('login'))
    
    return render_template('forgot_password.html', form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset with token"""
    reset_token = PasswordResetToken.query.filter_by(token=token).first()
    
    if not reset_token:
        flash('Invalid reset link.', 'error')
        return redirect(url_for('login'))
    
    if not reset_token.is_valid:
        if reset_token.is_used:
            flash('This reset link has already been used.', 'info')
        else:
            flash('This reset link has expired. Please request a new one.', 'error')
        return redirect(url_for('forgot_password'))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            # Update user password
            user = reset_token.user
            user.password_hash = generate_password_hash(form.password.data)
            reset_token.mark_as_used()
            
            db.session.commit()
            
            flash('Your password has been reset successfully. You can now log in with your new password.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Password reset completion error: {e}")
            flash('An error occurred while resetting your password. Please try again.', 'error')
    
    return render_template('reset_password.html', form=form, token=token)

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
        # Handle email change
        new_email = form.email.data.strip() if form.email.data else None
        email_changed = False
        
        if new_email and new_email != current_user.email:
            # Check if email is already taken by another user
            existing_user = User.query.filter(User.email == new_email, User.id != current_user.id).first()
            if existing_user:
                flash('This email address is already in use by another account.', 'error')
                return redirect(url_for('profile'))
            
            # Send confirmation email to new address
            if email_service.send_email_change_confirmation(current_user, new_email):
                flash(f'A confirmation email has been sent to {new_email}. Please check your email and click the confirmation link to complete the email change.', 'info')
                email_changed = True
            else:
                flash('Failed to send confirmation email. Please try again later.', 'error')
                return redirect(url_for('profile'))
        
        # Encrypt and store Steam API key
        encrypted_api_key = encryption_manager.encrypt_steam_api_key(form.steam_api_key.data)
        
        # Update user in database
        current_user.steam_api_key_encrypted = encrypted_api_key
        current_user.steam_id = form.steam_id.data
        current_user.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        if email_changed:
            flash('Profile updated successfully! Your email change is pending confirmation.', 'success')
        else:
            flash('Profile updated successfully!', 'success')
        
        return redirect(url_for('profile'))
    
    # Pre-populate form with existing data
    if current_user.steam_api_key_encrypted:
        decrypted_key = encryption_manager.decrypt_steam_api_key(current_user.steam_api_key_encrypted)
        form.steam_api_key.data = decrypted_key
    if current_user.steam_id:
        form.steam_id.data = current_user.steam_id
    if current_user.email:
        form.email.data = current_user.email
    
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
        try:
            # Process image upload
            image_filename = None
            image_url = None
            if form.achievement_image.data:
                print(f"🖼️  Processing image upload for user {current_user.id}")
                # Create a unique filename
                achievement_id = f"custom_{current_user.id}_{int(time.time())}"
                image_filename, image_url = process_achievement_image(form.achievement_image.data, current_user.id, achievement_id)
                print(f"📄 Image upload result: filename={image_filename}, url={image_url}")
            
            # Only store image metadata if upload was successful
            if image_filename:
                achievement_image = AchievementImage(
                    filename=image_filename,
                    original_filename=form.achievement_image.data.filename,
                    file_size=0,  # Could calculate actual size
                    mime_type='image/jpeg',
                    uploaded_by=current_user.id,
                    uploaded_at=datetime.utcnow()
                )
                db.session.add(achievement_image)
            else:
                flash('Image upload failed. Achievement created without image.', 'warning')
            
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
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error creating achievement: {e}")
            flash(f'Error creating achievement: {str(e)}', 'error')
    
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
        # Check if this shared achievement is used in any collections
        collection_items = CollectionItem.query.filter_by(
            shared_achievement_id=shared_achievement.id
        ).all()
        
        if collection_items:
            # Cannot unshare if used in collections
            collection_names = [item.collection.name for item in collection_items]
            flash(f'Cannot unshare achievement! It is currently used in these collections: {", ".join(collection_names[:3])}{"..." if len(collection_names) > 3 else ""}', 'error')
        else:
            # Safe to unshare
            db.session.delete(shared_achievement)
            db.session.commit()
            flash('Achievement removed from community sharing!')
    else:
        flash('Achievement was not shared!')
    
    return redirect(url_for('custom_achievements'))

@app.route('/delete-shared-achievement/<int:shared_id>', methods=['POST'])
@login_required
def delete_shared_achievement(shared_id):
    """Delete a shared achievement (user can only delete their own)"""
    shared_achievement = SharedAchievement.query.filter_by(
        id=shared_id,
        creator_id=current_user.id
    ).first()
    
    if not shared_achievement:
        return jsonify({'success': False, 'error': 'Achievement not found or not owned by you'}), 404
    
    try:
        achievement_name = shared_achievement.name
        db.session.delete(shared_achievement)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted shared achievement "{achievement_name}"'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Failed to delete achievement: {str(e)}'}), 500

@app.route('/admin/delete-shared-achievement/<int:shared_id>', methods=['POST'])
@login_required
def admin_delete_shared_achievement(shared_id):
    """Admin delete any shared achievement"""
    if current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    
    shared_achievement = SharedAchievement.query.get(shared_id)
    
    if not shared_achievement:
        return jsonify({'success': False, 'error': 'Achievement not found'}), 404
    
    try:
        achievement_name = shared_achievement.name
        creator_name = shared_achievement.creator.username if shared_achievement.creator else 'Unknown'
        
        db.session.delete(shared_achievement)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted shared achievement "{achievement_name}" by {creator_name}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Failed to delete achievement: {str(e)}'}), 500

@app.route('/community-achievements')
@login_required
def community_achievements():
    """Display community shared achievements"""
    # Load shared achievements from database (include all active achievements)
    shared_achievements = SharedAchievement.query.filter(
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

@app.route('/admin/users')
@login_required
def admin_users():
    """Admin route to view all users"""
    if current_user.username != 'admin':  # Simple admin check
        flash('Access denied!')
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/json')
@login_required  
def admin_users_json():
    """Admin route to get users as JSON (for API calls)"""
    if current_user.username != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({
        'users': [
            {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'is_verified': user.is_verified,
                'is_active': user.is_active,
                'has_steam_api_key': bool(user.steam_api_key_encrypted),
                'games_count': user.user_games.count(),
                'custom_achievements_count': user.custom_achievements.count()
            }
            for user in users
        ],
        'total_users': len(users)
    })

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    """Admin route to delete a user and all their data"""
    if current_user.username != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    
    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot delete your own admin account'}), 400
    
    user_to_delete = User.query.get_or_404(user_id)
    
    try:
        username = user_to_delete.username
        
        # Delete all user data (CASCADE should handle most of this)
        # But let's be explicit about important tables
        
        # Delete custom achievements (this will cascade to shared achievements)
        CustomAchievement.query.filter_by(user_id=user_id).delete()
        
        # Delete shared achievements created by this user
        SharedAchievement.query.filter_by(creator_id=user_id).delete()
        
        # Delete activity feed entries
        ActivityFeed.query.filter_by(user_id=user_id).delete()
        
        # Delete achievement images uploaded by user
        AchievementImage.query.filter_by(uploaded_by=user_id).delete()
        
        # Delete email tokens
        try:
            EmailVerificationToken.query.filter_by(user_id=user_id).delete()
            PasswordResetToken.query.filter_by(user_id=user_id).delete()
        except:
            pass  # Tables might not exist yet
        
        # Delete user games and Steam achievements (CASCADE should handle this)
        UserGame.query.filter_by(user_id=user_id).delete()
        
        # Finally delete the user
        db.session.delete(user_to_delete)
        db.session.commit()
        
        print(f"🗑️  Admin deleted user: {username} (ID: {user_id})")
        
        return jsonify({
            'success': True,
            'message': f'User "{username}" and all their data have been permanently deleted.'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting user {user_id}: {e}")
        return jsonify({
            'error': f'Failed to delete user: {str(e)}'
        }), 500

@app.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
def admin_toggle_user_status(user_id):
    """Admin route to activate/deactivate a user"""
    if current_user.username != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    
    # Prevent admin from deactivating themselves
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot modify your own admin account'}), 400
    
    user = User.query.get_or_404(user_id)
    
    try:
        # Toggle active status
        user.is_active = not user.is_active
        db.session.commit()
        
        status = "activated" if user.is_active else "deactivated"
        print(f"👤 Admin {status} user: {user.username}")
        
        return jsonify({
            'success': True,
            'message': f'User "{user.username}" has been {status}.',
            'is_active': user.is_active
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': f'Failed to update user status: {str(e)}'
        }), 500

@app.route('/admin/fix-existing-users')
def admin_fix_existing_users():
    """Fix existing users to bypass email verification temporarily"""
    try:
        # Find users without proper email addresses
        users_fixed = 0
        users = User.query.all()
        
        for user in users:
            needs_fix = False
            
            # Fix users with placeholder emails or no verification
            if not user.email or '@temp.example.com' in user.email:
                user.email = f"{user.username}@temp-verified.local"
                needs_fix = True
            
            if not user.is_verified:
                user.is_verified = True  # Bypass verification for existing users
                needs_fix = True
            
            if needs_fix:
                users_fixed += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'✅ Fixed {users_fixed} existing users - they can now log in without email verification',
            'note': 'This is a temporary fix for existing users. New users will still need email verification.'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ Error fixing users: {str(e)}'
        }), 500

@app.route('/admin/create-email-tables')
def admin_create_email_tables():
    """Admin route to create email tables manually"""
    # Temporarily remove login requirement for setup
    
    try:
        # Drop tables if they exist (to avoid conflicts)
        db.session.execute(db.text('DROP TABLE IF EXISTS email_verification_tokens CASCADE'))
        db.session.execute(db.text('DROP TABLE IF EXISTS password_reset_tokens CASCADE'))
        db.session.execute(db.text('DROP TABLE IF EXISTS email_change_tokens CASCADE'))
        
        # Create tables with raw SQL to avoid sequence conflicts
        email_verification_sql = """
        CREATE TABLE email_verification_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            is_used BOOLEAN NOT NULL DEFAULT FALSE,
            used_at TIMESTAMP WITHOUT TIME ZONE
        );
        CREATE INDEX idx_email_verification_token ON email_verification_tokens(token);
        """
        
        password_reset_sql = """
        CREATE TABLE password_reset_tokens (
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
        CREATE INDEX idx_password_reset_token ON password_reset_tokens(token);
        """
        
        email_change_sql = """
        CREATE TABLE email_change_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token VARCHAR(255) UNIQUE NOT NULL,
            old_email VARCHAR(255),
            new_email VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            is_used BOOLEAN NOT NULL DEFAULT FALSE,
            used_at TIMESTAMP WITHOUT TIME ZONE
        );
        CREATE INDEX idx_email_change_token ON email_change_tokens(token);
        """
        
        db.session.execute(db.text(email_verification_sql))
        db.session.execute(db.text(password_reset_sql))
        db.session.execute(db.text(email_change_sql))
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '✅ Email tables created successfully!',
            'tables_created': ['email_verification_tokens', 'password_reset_tokens', 'email_change_tokens']
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ Error creating email tables: {str(e)}'
        }), 500


# ========================================
# ADMIN COLLECTION MANAGEMENT ROUTES
# ========================================

@app.route('/admin/collections')
@login_required
def admin_collections():
    """Admin page for managing achievement collections"""
    if current_user.username != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Get all collections with statistics
    collections = AchievementCollection.query.order_by(
        AchievementCollection.is_featured.desc(),
        AchievementCollection.created_at.desc()
    ).all()
    
    # Get collection statistics
    total_collections = len(collections)
    active_collections = len([c for c in collections if c.is_currently_active])
    featured_collections = len([c for c in collections if c.is_featured])
    total_participants = sum(c.participants_count for c in collections)
    
    stats = {
        'total_collections': total_collections,
        'active_collections': active_collections,
        'featured_collections': featured_collections,
        'total_participants': total_participants
    }
    
    return render_template('admin/collections.html', 
                         collections=collections, 
                         stats=stats)

@app.route('/admin/collections/create', methods=['GET', 'POST'])
@login_required
def admin_create_collection():
    """Admin route to create new achievement collection"""
    if current_user.username != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            collection_type = request.form.get('collection_type', 'seasonal')
            difficulty_level = request.form.get('difficulty_level', 'medium')
            estimated_time = request.form.get('estimated_time', '').strip()
            color_theme = request.form.get('color_theme', 'primary')
            is_featured = request.form.get('is_featured') == 'on'
            
            # Handle dates
            start_date = None
            end_date = None
            if request.form.get('start_date'):
                start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
            if request.form.get('end_date'):
                end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
            
            # Validation
            if not name or not description:
                flash('Name and description are required.', 'error')
                return redirect(request.url)
            
            # Create collection
            collection = AchievementCollection(
                name=name,
                description=description,
                collection_type=collection_type,
                difficulty_level=difficulty_level,
                estimated_time=estimated_time if estimated_time else None,
                color_theme=color_theme,
                is_featured=is_featured,
                start_date=start_date,
                end_date=end_date,
                created_by=current_user.id
            )
            
            db.session.add(collection)
            db.session.commit()
            
            flash(f'Collection "{name}" created successfully!', 'success')
            return redirect(url_for('admin_collections'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating collection: {str(e)}', 'error')
            return redirect(request.url)
    
    # GET request - show form
    return render_template('admin/create_collection.html')

@app.route('/admin/collections/<int:collection_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_collection(collection_id):
    """Admin route to edit achievement collection"""
    if current_user.username != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    collection = AchievementCollection.query.get_or_404(collection_id)
    
    if request.method == 'POST':
        try:
            # Update collection data
            collection.name = request.form.get('name', '').strip()
            collection.description = request.form.get('description', '').strip()
            collection.collection_type = request.form.get('collection_type', 'seasonal')
            collection.difficulty_level = request.form.get('difficulty_level', 'medium')
            collection.estimated_time = request.form.get('estimated_time', '').strip() or None
            collection.color_theme = request.form.get('color_theme', 'primary')
            collection.is_active = request.form.get('is_active') == 'on'
            collection.is_featured = request.form.get('is_featured') == 'on'
            
            # Handle dates
            if request.form.get('start_date'):
                collection.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
            else:
                collection.start_date = None
                
            if request.form.get('end_date'):
                collection.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
            else:
                collection.end_date = None
            
            collection.updated_at = datetime.utcnow()
            
            # Validation
            if not collection.name or not collection.description:
                flash('Name and description are required.', 'error')
                return redirect(request.url)
            
            db.session.commit()
            flash(f'Collection "{collection.name}" updated successfully!', 'success')
            return redirect(url_for('admin_collections'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating collection: {str(e)}', 'error')
            return redirect(request.url)
    
    # GET request - show edit form
    return render_template('admin/edit_collection.html', collection=collection)

@app.route('/admin/collections/<int:collection_id>/manage')
@login_required
def admin_manage_collection(collection_id):
    """Admin route to manage collection items and participants"""
    if current_user.username != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    collection = AchievementCollection.query.get_or_404(collection_id)
    
    # Get collection items with achievements
    items = CollectionItem.query.filter_by(collection_id=collection_id)\
        .join(SharedAchievement)\
        .order_by(CollectionItem.order_index).all()
    
    # Get user progress
    progress_records = UserCollectionProgress.query.filter_by(collection_id=collection_id)\
        .join(User)\
        .order_by(UserCollectionProgress.achievements_completed.desc()).all()
    
    # Get available shared achievements not in this collection
    existing_achievement_ids = [item.shared_achievement_id for item in items]
    available_shared_achievements = SharedAchievement.query.filter(
        ~SharedAchievement.id.in_(existing_achievement_ids),
        SharedAchievement.is_active == True
    ).order_by(SharedAchievement.name).all()
    
    # Also get custom achievements that could be promoted to shared
    available_custom_achievements = CustomAchievement.query.filter(
        ~CustomAchievement.id.in_(
            db.session.query(SharedAchievement.original_achievement_id)
            .filter(SharedAchievement.original_achievement_id.isnot(None))
        )
    ).order_by(CustomAchievement.name).limit(50).all()  # Limit to 50 for performance
    
    return render_template('admin/manage_collection.html',
                         collection=collection,
                         items=items,
                         progress_records=progress_records,
                         available_shared_achievements=available_shared_achievements,
                         available_custom_achievements=available_custom_achievements)

@app.route('/admin/collections/<int:collection_id>/add-achievement', methods=['POST'])
@login_required
def admin_add_achievement_to_collection(collection_id):
    """Admin route to add achievement to collection"""
    if current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        collection = AchievementCollection.query.get_or_404(collection_id)
        shared_achievement_id = request.json.get('shared_achievement_id')
        point_value = request.json.get('point_value', 10)
        is_required = request.json.get('is_required', True)
        
        if not shared_achievement_id:
            return jsonify({'success': False, 'error': 'Achievement ID required'}), 400
        
        # Check if achievement already in collection
        existing = CollectionItem.query.filter_by(
            collection_id=collection_id,
            shared_achievement_id=shared_achievement_id
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Achievement already in collection'}), 400
        
        # Get next order index
        max_order = db.session.query(db.func.max(CollectionItem.order_index))\
            .filter_by(collection_id=collection_id).scalar() or 0
        
        # Create collection item
        item = CollectionItem(
            collection_id=collection_id,
            shared_achievement_id=shared_achievement_id,
            order_index=max_order + 1,
            point_value=point_value,
            is_required=is_required,
            added_by=current_user.id
        )
        
        db.session.add(item)
        
        # Update user progress for all participants
        progress_records = UserCollectionProgress.query.filter_by(collection_id=collection_id).all()
        for progress in progress_records:
            progress.update_progress()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Achievement added to collection successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/collections/<int:collection_id>/add-custom-achievement', methods=['POST'])
@login_required
def admin_add_custom_achievement_to_collection(collection_id):
    """Admin route to promote custom achievement to shared and add to collection"""
    if current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        collection = AchievementCollection.query.get_or_404(collection_id)
        custom_achievement_id = request.json.get('custom_achievement_id')
        point_value = request.json.get('point_value', 10)
        is_required = request.json.get('is_required', True)
        
        if not custom_achievement_id:
            return jsonify({'success': False, 'error': 'Custom achievement ID required'}), 400
        
        custom_achievement = CustomAchievement.query.get_or_404(custom_achievement_id)
        
        # Check if this custom achievement is already promoted to shared
        existing_shared = SharedAchievement.query.filter_by(
            original_achievement_id=custom_achievement_id
        ).first()
        
        if existing_shared:
            # Use existing shared achievement
            shared_achievement = existing_shared
        else:
            # Promote custom achievement to shared
            shared_achievement = SharedAchievement(
                name=custom_achievement.name,
                description=custom_achievement.description,
                original_achievement_id=custom_achievement.id,
                creator_id=custom_achievement.user_id,
                original_creator_username=custom_achievement.user.username,
                condition_type=custom_achievement.condition_type,
                condition_data=custom_achievement.condition_data,
                image_filename=custom_achievement.image_filename,
                is_active=True,
                shared_at=db.func.current_timestamp()
            )
            db.session.add(shared_achievement)
            db.session.flush()  # Get the ID
        
        # Check if achievement already in collection
        existing_item = CollectionItem.query.filter_by(
            collection_id=collection_id,
            shared_achievement_id=shared_achievement.id
        ).first()
        
        if existing_item:
            return jsonify({'success': False, 'error': 'Achievement already in collection'}), 400
        
        # Get next order index
        max_order = db.session.query(db.func.max(CollectionItem.order_index))\
            .filter_by(collection_id=collection_id).scalar() or 0
        
        # Create collection item
        collection_item = CollectionItem(
            collection_id=collection_id,
            shared_achievement_id=shared_achievement.id,
            order_index=max_order + 1,
            points=point_value,
            is_required=is_required
        )
        
        db.session.add(collection_item)
        db.session.commit()
        
        action = "promoted and added" if not existing_shared else "added"
        return jsonify({
            'success': True,
            'message': f'Custom achievement "{custom_achievement.name}" {action} to collection successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/collections/<int:collection_id>/remove-achievement/<int:item_id>', methods=['POST'])
@login_required
def admin_remove_achievement_from_collection(collection_id, item_id):
    """Admin route to remove achievement from collection"""
    if current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        item = CollectionItem.query.filter_by(
            id=item_id,
            collection_id=collection_id
        ).first_or_404()
        
        db.session.delete(item)
        
        # Update user progress for all participants
        progress_records = UserCollectionProgress.query.filter_by(collection_id=collection_id).all()
        for progress in progress_records:
            progress.update_progress()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Achievement removed from collection successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/collections/items/<int:item_id>/move', methods=['POST'])
@login_required
def admin_reorder_collection_item(item_id):
    """Admin route to reorder collection items (move up/down)"""
    if current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        direction = data.get('direction')
        
        if direction not in ['up', 'down']:
            return jsonify({'success': False, 'error': 'Invalid direction'}), 400
        
        item = CollectionItem.query.get_or_404(item_id)
        collection_id = item.collection_id
        
        # Get all items in this collection ordered by order_index
        all_items = CollectionItem.query.filter_by(collection_id=collection_id)\
            .order_by(CollectionItem.order_index).all()
        
        # Find current item position
        current_index = None
        for i, collection_item in enumerate(all_items):
            if collection_item.id == item_id:
                current_index = i
                break
        
        if current_index is None:
            return jsonify({'success': False, 'error': 'Item not found'}), 404
        
        # Check if move is possible
        if direction == 'up' and current_index == 0:
            return jsonify({'success': False, 'error': 'Item is already at the top'}), 400
        
        if direction == 'down' and current_index == len(all_items) - 1:
            return jsonify({'success': False, 'error': 'Item is already at the bottom'}), 400
        
        # Swap positions
        if direction == 'up':
            swap_index = current_index - 1
        else:
            swap_index = current_index + 1
        
        # Swap order_index values
        current_item = all_items[current_index]
        swap_item = all_items[swap_index]
        
        temp_order = current_item.order_index
        current_item.order_index = swap_item.order_index
        swap_item.order_index = temp_order
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Achievement moved {direction} successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/collections/<int:collection_id>/delete', methods=['POST'])
@login_required
def admin_delete_collection(collection_id):
    """Admin route to delete achievement collection"""
    if current_user.username != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        collection = AchievementCollection.query.get_or_404(collection_id)
        collection_name = collection.name
        
        # Delete collection (cascades to items and progress)
        db.session.delete(collection)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Collection "{collection_name}" deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/create-collection-tables')
def admin_create_collection_tables():
    """Admin route to create collection tables manually"""
    try:
        # Create the new collection tables with raw SQL
        collection_sql = """
        CREATE TABLE IF NOT EXISTS achievement_collections (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            collection_type VARCHAR(50) NOT NULL DEFAULT 'seasonal',
            difficulty_level VARCHAR(20) NOT NULL DEFAULT 'medium',
            estimated_time VARCHAR(50),
            banner_image VARCHAR(255),
            icon_image VARCHAR(255),
            color_theme VARCHAR(20) DEFAULT 'primary',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_featured BOOLEAN NOT NULL DEFAULT FALSE,
            start_date TIMESTAMP WITHOUT TIME ZONE,
            end_date TIMESTAMP WITHOUT TIME ZONE,
            views_count INTEGER NOT NULL DEFAULT 0,
            participants_count INTEGER NOT NULL DEFAULT 0,
            completions_count INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_collection_name ON achievement_collections(name);
        CREATE INDEX IF NOT EXISTS idx_collection_active_featured ON achievement_collections(is_active, is_featured);
        CREATE INDEX IF NOT EXISTS idx_collection_type_active ON achievement_collections(collection_type, is_active);
        CREATE INDEX IF NOT EXISTS idx_collection_dates ON achievement_collections(start_date, end_date);
        """
        
        collection_items_sql = """
        CREATE TABLE IF NOT EXISTS collection_items (
            id SERIAL PRIMARY KEY,
            collection_id INTEGER NOT NULL REFERENCES achievement_collections(id) ON DELETE CASCADE,
            shared_achievement_id INTEGER NOT NULL REFERENCES shared_achievements(id) ON DELETE CASCADE,
            order_index INTEGER NOT NULL DEFAULT 0,
            is_required BOOLEAN NOT NULL DEFAULT TRUE,
            point_value INTEGER NOT NULL DEFAULT 10,
            unlock_condition VARCHAR(50),
            added_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            added_by INTEGER NOT NULL REFERENCES users(id),
            UNIQUE(collection_id, shared_achievement_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_collection_order ON collection_items(collection_id, order_index);
        """
        
        user_progress_sql = """
        CREATE TABLE IF NOT EXISTS user_collection_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            collection_id INTEGER NOT NULL REFERENCES achievement_collections(id) ON DELETE CASCADE,
            achievements_completed INTEGER NOT NULL DEFAULT 0,
            total_achievements INTEGER NOT NULL DEFAULT 0,
            points_earned INTEGER NOT NULL DEFAULT 0,
            total_points INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
            started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP WITHOUT TIME ZONE,
            last_activity TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            progress_data JSON,
            UNIQUE(user_id, collection_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_user_collection_status ON user_collection_progress(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_collection_progress ON user_collection_progress(collection_id, status);
        """
        
        # Execute all table creation statements
        db.session.execute(db.text(collection_sql))
        db.session.execute(db.text(collection_items_sql))
        db.session.execute(db.text(user_progress_sql))
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '✅ Collection tables created successfully!',
            'tables_created': ['achievement_collections', 'collection_items', 'user_collection_progress']
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ Error creating collection tables: {str(e)}'
        }), 500

@app.route('/admin/create-social-tables')
@login_required
def admin_create_social_tables():
    """Admin route to create social/friendship tables manually"""
    if current_user.username != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
    try:
        # Create the user_friendship table with raw SQL
        friendship_sql = """
        CREATE TABLE IF NOT EXISTS user_friendship (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            friend_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            accepted_at TIMESTAMP WITHOUT TIME ZONE,
            blocked_at TIMESTAMP WITHOUT TIME ZONE,
            UNIQUE(user_id, friend_id),
            CHECK (user_id != friend_id),
            CHECK (status IN ('pending', 'accepted', 'blocked', 'rejected'))
        );
        
        CREATE INDEX IF NOT EXISTS idx_friendship_user_status ON user_friendship(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_friendship_friend_status ON user_friendship(friend_id, status);
        CREATE INDEX IF NOT EXISTS idx_friendship_status ON user_friendship(status);
        CREATE INDEX IF NOT EXISTS idx_friendship_dates ON user_friendship(created_at, accepted_at);
        """
        
        # Execute table creation
        db.session.execute(db.text(friendship_sql))
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '✅ Social/friendship tables created successfully!',
            'tables_created': ['user_friendship'],
            'features_enabled': ['User profiles', 'Friend requests', 'Social discovery']
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ Error creating social tables: {str(e)}'
        }), 500


@app.route('/admin/create-rating-tables')
@login_required
def admin_create_rating_tables():
    """Admin route to create achievement rating and review tables"""
    if current_user.username != 'admin':
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
    try:
        # Create the achievement_ratings table
        ratings_sql = """
        CREATE TABLE IF NOT EXISTS achievement_ratings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            shared_achievement_id INTEGER NOT NULL REFERENCES shared_achievements(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            
            CONSTRAINT unique_user_achievement_rating UNIQUE (user_id, shared_achievement_id),
            CONSTRAINT valid_rating_range CHECK (rating >= 1 AND rating <= 5)
        );
        
        CREATE INDEX IF NOT EXISTS idx_rating_achievement ON achievement_ratings(shared_achievement_id, rating);
        CREATE INDEX IF NOT EXISTS idx_rating_user ON achievement_ratings(user_id);
        CREATE INDEX IF NOT EXISTS idx_rating_created ON achievement_ratings(created_at);
        """
        
        # Create the achievement_reviews table
        reviews_sql = """
        CREATE TABLE IF NOT EXISTS achievement_reviews (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            shared_achievement_id INTEGER NOT NULL REFERENCES shared_achievements(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            rating INTEGER NOT NULL,
            difficulty_vote VARCHAR(20),
            time_to_complete VARCHAR(50),
            tips_and_tricks TEXT,
            helpful_votes INTEGER NOT NULL DEFAULT 0,
            reported_count INTEGER NOT NULL DEFAULT 0,
            is_featured BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            
            CONSTRAINT unique_user_achievement_review UNIQUE (user_id, shared_achievement_id),
            CONSTRAINT valid_review_rating_range CHECK (rating >= 1 AND rating <= 5),
            CONSTRAINT valid_difficulty_vote CHECK (difficulty_vote IS NULL OR difficulty_vote IN ('easy', 'medium', 'hard', 'extreme'))
        );
        
        CREATE INDEX IF NOT EXISTS idx_review_achievement ON achievement_reviews(shared_achievement_id);
        CREATE INDEX IF NOT EXISTS idx_review_user ON achievement_reviews(user_id);
        CREATE INDEX IF NOT EXISTS idx_review_rating ON achievement_reviews(rating);
        CREATE INDEX IF NOT EXISTS idx_review_helpful ON achievement_reviews(helpful_votes DESC);
        """
        
        # Execute table creation
        db.session.execute(db.text(ratings_sql))
        db.session.execute(db.text(reviews_sql))
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '✅ Achievement rating and review tables created successfully!',
            'tables_created': ['achievement_ratings', 'achievement_reviews'],
            'features_enabled': ['Achievement ratings', 'Achievement reviews', 'Community feedback']
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'❌ Error creating rating/review tables: {str(e)}'
        }), 500


# ========================================
# USER COLLECTION ROUTES
# ========================================

@app.route('/collections')
@login_required
def collections():
    """User page to view and participate in achievement collections"""
    # Get active collections for users
    now = datetime.utcnow()
    active_collections = AchievementCollection.query.filter(
        AchievementCollection.is_active == True,
        db.or_(
            AchievementCollection.start_date.is_(None),
            AchievementCollection.start_date <= now
        ),
        db.or_(
            AchievementCollection.end_date.is_(None),
            AchievementCollection.end_date >= now
        )
    ).order_by(
        AchievementCollection.is_featured.desc(),
        AchievementCollection.created_at.desc()
    ).all()
    
    # Get user's progress for each collection
    user_progress = {}
    for collection in active_collections:
        progress = UserCollectionProgress.query.filter_by(
            user_id=current_user.id,
            collection_id=collection.id
        ).first()
        user_progress[collection.id] = progress
    
    # Get featured collections
    featured_collections = [c for c in active_collections if c.is_featured]
    
    return render_template('collections.html',
                         collections=active_collections,
                         featured_collections=featured_collections,
                         user_progress=user_progress)

@app.route('/collections/<int:collection_id>')
@login_required
def view_collection(collection_id):
    """View detailed collection page with achievements and progress"""
    collection = AchievementCollection.query.get_or_404(collection_id)
    
    if not collection.is_currently_active:
        flash('This collection is not currently active.', 'warning')
        return redirect(url_for('collections'))
    
    # Get collection items
    items = CollectionItem.query.filter_by(collection_id=collection_id)\
        .join(SharedAchievement)\
        .order_by(CollectionItem.order_index).all()
    
    # Get or create user progress
    user_progress = UserCollectionProgress.query.filter_by(
        user_id=current_user.id,
        collection_id=collection_id
    ).first()
    
    if not user_progress:
        user_progress = UserCollectionProgress(
            user_id=current_user.id,
            collection_id=collection_id
        )
        db.session.add(user_progress)
        
        # Update participant count
        collection.participants_count += 1
        db.session.commit()
    
    # Update progress
    user_progress.update_progress()
    
    # Update view count
    collection.views_count += 1
    db.session.commit()
    
    # Check which achievements user has completed
    user_achievements = {}
    for item in items:
        user_custom = CustomAchievement.query.filter_by(
            user_id=current_user.id,
            imported_from_shared_id=item.shared_achievement_id
        ).first()
        user_achievements[item.shared_achievement_id] = user_custom
    
    return render_template('collection_detail.html',
                         collection=collection,
                         items=items,
                         user_progress=user_progress,
                         user_achievements=user_achievements)

@app.route('/collections/<int:collection_id>/join', methods=['POST'])
@login_required
def join_collection(collection_id):
    """Join a collection and start tracking progress"""
    collection = AchievementCollection.query.get_or_404(collection_id)
    
    if not collection.is_currently_active:
        return jsonify({'success': False, 'error': 'Collection is not currently active'}), 400
    
    try:
        # Check if user already joined
        existing_progress = UserCollectionProgress.query.filter_by(
            user_id=current_user.id,
            collection_id=collection_id
        ).first()
        
        if existing_progress:
            return jsonify({'success': False, 'error': 'Already participating in this collection'}), 400
        
        # Create progress record
        user_progress = UserCollectionProgress(
            user_id=current_user.id,
            collection_id=collection_id
        )
        db.session.add(user_progress)
        
        # Update participant count
        collection.participants_count += 1
        
        # Update progress
        user_progress.update_progress()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully joined "{collection.name}"!'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ========================================
# SOCIAL FEATURES: USER PROFILES & FRIENDS
# ========================================

@app.route('/users')
@login_required
def browse_users():
    """Browse and discover other users"""
    search = request.args.get('search', '').strip()
    filter_by = request.args.get('filter', 'active')  # active, new, top_achievers
    
    # Base query for users (exclude current user)
    query = User.query.filter(User.id != current_user.id, User.is_active == True)
    
    # Apply search filter
    if search:
        query = query.filter(User.username.ilike(f'%{search}%'))
    
    # Apply sorting filters
    if filter_by == 'new':
        query = query.order_by(User.created_at.desc())
    elif filter_by == 'top_achievers':
        # Order by users with most custom achievements
        query = query.outerjoin(CustomAchievement).group_by(User.id)\
            .order_by(db.func.count(CustomAchievement.id).desc())
    else:  # active
        query = query.order_by(User.updated_at.desc())
    
    # Paginate results
    page = request.args.get('page', 1, type=int)
    users = query.paginate(page=page, per_page=20, error_out=False)
    
    # Get friendship status for each user
    user_friendships = {}
    friend_counts = {}
    achievement_counts = {}
    
    for user in users.items:
        # Friendship status
        user_friendships[user.id] = get_friendship_status(current_user.id, user.id)
        
        # Friend count
        friend_counts[user.id] = UserFriendship.query.filter_by(
            user_id=user.id, status='accepted'
        ).count()
        
        # Achievement count
        achievement_counts[user.id] = CustomAchievement.query.filter_by(
            user_id=user.id
        ).count()
    
    return render_template('social/browse_users.html',
                         users=users,
                         user_friendships=user_friendships,
                         friend_counts=friend_counts,
                         achievement_counts=achievement_counts,
                         search=search,
                         filter_by=filter_by)

@app.route('/user/<username>')
@login_required
def user_profile(username):
    """View a user's public profile"""
    user = User.query.filter_by(username=username).first_or_404()
    
    # Get friendship status
    friendship_status = None
    mutual_friends = []
    if user.id != current_user.id:
        friendship_status = get_friendship_status(current_user.id, user.id)
        mutual_friends = get_mutual_friends(current_user.id, user.id)
    
    # Get user's achievements
    achievements = CustomAchievement.query.filter_by(user_id=user.id)\
        .order_by(CustomAchievement.created_at.desc()).limit(12).all()
    
    # Get user's collection progress
    collections = UserCollectionProgress.query.filter_by(user_id=user.id)\
        .join(AchievementCollection)\
        .filter(AchievementCollection.is_active == True)\
        .order_by(UserCollectionProgress.achievements_completed.desc())\
        .limit(6).all()
    
    # Get recent activity
    recent_activity = get_recent_activities(limit=10, user_id=user.id)
    
    # Get friends
    friends = get_user_friends(user.id, status='accepted')[:12]  # Show first 12 friends
    
    # Calculate stats
    stats = {
        'total_achievements': CustomAchievement.query.filter_by(user_id=user.id).count(),
        'shared_achievements': SharedAchievement.query.filter_by(creator_id=user.id).count(),
        'collections_joined': UserCollectionProgress.query.filter_by(user_id=user.id).count(),
        'collections_completed': UserCollectionProgress.query.filter_by(
            user_id=user.id, status='completed'
        ).count(),
        'friend_count': len(friends),
        'join_date': user.created_at
    }
    
    return render_template('social/user_profile.html',
                         profile_user=user,
                         friendship_status=friendship_status,
                         mutual_friends=mutual_friends,
                         achievements=achievements,
                         collections=collections,
                         recent_activity=recent_activity,
                         friends=friends,
                         stats=stats,
                         is_own_profile=(user.id == current_user.id))

@app.route('/friends')
@login_required
def friends_list():
    """View user's friends and friend requests"""
    # Get accepted friends
    friends = get_user_friends(current_user.id, status='accepted')
    
    # Get pending friend requests (received)
    pending_requests = UserFriendship.query.filter_by(
        friend_id=current_user.id,
        status='pending'
    ).join(User, UserFriendship.user_id == User.id).all()
    
    # Get sent requests (waiting for response)
    sent_requests = UserFriendship.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).join(User, UserFriendship.friend_id == User.id).all()
    
    return render_template('social/friends.html',
                         friends=friends,
                         pending_requests=pending_requests,
                         sent_requests=sent_requests)

@app.route('/send-friend-request/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    """Send a friend request to another user"""
    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'Cannot send friend request to yourself'}), 400
    
    target_user = User.query.get_or_404(user_id)
    
    # Check if friendship already exists
    existing = UserFriendship.query.filter_by(
        user_id=current_user.id,
        friend_id=user_id
    ).first()
    
    if existing:
        if existing.status == 'accepted':
            return jsonify({'success': False, 'error': 'Already friends'}), 400
        elif existing.status == 'pending':
            return jsonify({'success': False, 'error': 'Friend request already sent'}), 400
        elif existing.status == 'blocked':
            return jsonify({'success': False, 'error': 'Cannot send friend request'}), 400
    
    try:
        # Create friend request
        friendship = UserFriendship(
            user_id=current_user.id,
            friend_id=user_id,
            status='pending'
        )
        
        db.session.add(friendship)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Friend request sent to {target_user.username}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/accept-friend-request/<int:friendship_id>', methods=['POST'])
@login_required
def accept_friend_request(friendship_id):
    """Accept a friend request"""
    friendship = UserFriendship.query.filter_by(
        id=friendship_id,
        friend_id=current_user.id,
        status='pending'
    ).first_or_404()
    
    try:
        friendship.accept_friendship()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'You are now friends with {friendship.user.username}!'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/decline-friend-request/<int:friendship_id>', methods=['POST'])
@login_required
def decline_friend_request(friendship_id):
    """Decline a friend request"""
    friendship = UserFriendship.query.filter_by(
        id=friendship_id,
        friend_id=current_user.id,
        status='pending'
    ).first_or_404()
    
    try:
        db.session.delete(friendship)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Friend request declined'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/remove-friend/<int:user_id>', methods=['POST'])
@login_required
def remove_friend(user_id):
    """Remove a friend"""
    # Find both friendship records
    friendship1 = UserFriendship.query.filter_by(
        user_id=current_user.id,
        friend_id=user_id,
        status='accepted'
    ).first()
    
    friendship2 = UserFriendship.query.filter_by(
        user_id=user_id,
        friend_id=current_user.id,
        status='accepted'
    ).first()
    
    if not friendship1 and not friendship2:
        return jsonify({'success': False, 'error': 'Friendship not found'}), 404
    
    try:
        if friendship1:
            db.session.delete(friendship1)
        if friendship2:
            db.session.delete(friendship2)
        
        db.session.commit()
        
        user = User.query.get(user_id)
        return jsonify({
            'success': True,
            'message': f'Removed {user.username} from friends'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)