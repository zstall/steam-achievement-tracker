"""
Email service using SendGrid for email verification and password recovery
"""

import os
import secrets
from datetime import datetime, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, Subject, Content
from flask import current_app, url_for
from models import db, EmailVerificationToken, PasswordResetToken, EmailChangeToken

class EmailService:
    """Handles all email operations using SendGrid"""
    
    def __init__(self):
        self.client = None
        self.from_email = None
        self.from_name = None
        
    def init_app(self, app):
        """Initialize email service with Flask app config"""        
        api_key = app.config.get('SENDGRID_API_KEY')
        self.from_email = app.config.get('SENDGRID_FROM_EMAIL', 'noreply@steam-achievement-tracker.zstall.com')
        self.from_name = app.config.get('SENDGRID_FROM_NAME', 'Steam Achievement Tracker')
        
        if api_key:
            try:
                self.client = SendGridAPIClient(api_key)
                print("✅ SendGrid email service initialized successfully")
                print(f"✅ Using from email: {self.from_email}")
            except Exception as e:
                print(f"❌ Failed to initialize SendGrid: {e}")
                self.client = None
        else:
            print("⚠️  SendGrid API key not found - email service disabled")
            print(f"🔍 Available env vars starting with SEND: {[k for k in os.environ.keys() if k.startswith('SEND')]}")
    
    def _send_email(self, to_email, subject, html_content, text_content=None):
        """Send an email using SendGrid"""
        if not self.client:
            print("❌ Email service not initialized")
            return False
        
        try:
            # Create email
            from_addr = From(self.from_email, self.from_name)
            to_addr = To(to_email)
            subject_obj = Subject(subject)
            
            # Use HTML content as primary, fallback to text
            if text_content:
                content = Content("text/plain", text_content)
                html_content_obj = Content("text/html", html_content)
                mail = Mail(from_addr, to_addr, subject_obj, content)
                mail.add_content(html_content_obj)
            else:
                content = Content("text/html", html_content)
                mail = Mail(from_addr, to_addr, subject_obj, content)
            
            # Send email
            response = self.client.send(mail)
            
            if response.status_code in [200, 201, 202]:
                print(f"✅ Email sent to {to_email}: {subject}")
                return True
            else:
                print(f"❌ Failed to send email to {to_email}: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending email to {to_email}: {e}")
            return False
    
    def generate_verification_token(self, user):
        """Generate and store email verification token"""
        # Generate secure token
        token = secrets.token_urlsafe(32)
        
        # Set expiration (24 hours)
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        # Create token record
        verification_token = EmailVerificationToken(
            user_id=user.id,
            token=token,
            email=user.email,
            expires_at=expires_at
        )
        
        db.session.add(verification_token)
        db.session.commit()
        
        return token
    
    def generate_reset_token(self, user, request_ip=None):
        """Generate and store password reset token"""
        # Generate secure token
        token = secrets.token_urlsafe(32)
        
        # Set expiration (15 minutes for security)
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        # Create token record
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token,
            email=user.email,
            expires_at=expires_at,
            request_ip=request_ip
        )
        
        db.session.add(reset_token)
        db.session.commit()
        
        return token
    
    def send_verification_email(self, user):
        """Send email verification email to user"""
        if not user.email:
            print(f"❌ User {user.username} has no email address")
            return False
        
        # Generate verification token
        token = self.generate_verification_token(user)
        
        # Create verification URL
        verification_url = url_for('verify_email', token=token, _external=True)
        
        # Email content
        subject = "Verify your Steam Achievement Tracker account"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">🏆 Steam Achievement Tracker</h1>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa;">
                <h2 style="color: #2a5298;">Welcome, {user.username}!</h2>
                
                <p>Thanks for joining Steam Achievement Tracker! To complete your registration and start tracking your Steam achievements, please verify your email address.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_url}" 
                       style="background: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                        ✅ Verify Email Address
                    </a>
                </div>
                
                <p style="color: #6c757d; font-size: 14px;">
                    This verification link will expire in 24 hours. If you didn't create this account, you can safely ignore this email.
                </p>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #dee2e6;">
                
                <p style="color: #6c757d; font-size: 12px; text-align: center;">
                    Steam Achievement Tracker<br>
                    <a href="{url_for('index', _external=True)}" style="color: #2a5298;">Visit our website</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Welcome to Steam Achievement Tracker!
        
        Hi {user.username},
        
        Thanks for joining! To complete your registration, please verify your email address by clicking this link:
        
        {verification_url}
        
        This verification link will expire in 24 hours.
        
        If you didn't create this account, you can safely ignore this email.
        
        Best regards,
        Steam Achievement Tracker Team
        """
        
        return self._send_email(user.email, subject, html_content, text_content)
    
    def send_password_reset_email(self, user, request_ip=None):
        """Send password reset email to user"""
        if not user.email:
            print(f"❌ User {user.username} has no email address")
            return False
        
        # Generate reset token
        token = self.generate_reset_token(user, request_ip)
        
        # Create reset URL
        reset_url = url_for('reset_password', token=token, _external=True)
        
        # Email content
        subject = "Reset your Steam Achievement Tracker password"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #dc3545 0%, #c82333 100%); padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">🔐 Password Reset</h1>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa;">
                <h2 style="color: #dc3545;">Reset Your Password</h2>
                
                <p>Hi {user.username},</p>
                
                <p>We received a request to reset your password for your Steam Achievement Tracker account. If you made this request, click the button below to reset your password:</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" 
                       style="background: #dc3545; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                        🔑 Reset Password
                    </a>
                </div>
                
                <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;">
                        <strong>Security Notice:</strong> This reset link will expire in 15 minutes for your security.
                    </p>
                </div>
                
                <p style="color: #6c757d; font-size: 14px;">
                    If you didn't request this password reset, you can safely ignore this email. Your password will remain unchanged.
                </p>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #dee2e6;">
                
                <p style="color: #6c757d; font-size: 12px; text-align: center;">
                    Steam Achievement Tracker<br>
                    <a href="{url_for('index', _external=True)}" style="color: #2a5298;">Visit our website</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Password Reset Request
        
        Hi {user.username},
        
        We received a request to reset your password for your Steam Achievement Tracker account.
        
        To reset your password, click this link:
        {reset_url}
        
        This reset link will expire in 15 minutes for your security.
        
        If you didn't request this password reset, you can safely ignore this email.
        
        Best regards,
        Steam Achievement Tracker Team
        """
        
        return self._send_email(user.email, subject, html_content, text_content)
    
    def generate_email_change_token(self, user, new_email):
        """Generate and store email change token"""
        # Generate secure token
        token = secrets.token_urlsafe(32)
        
        # Set expiration (24 hours)
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        # Create token record
        change_token = EmailChangeToken(
            user_id=user.id,
            token=token,
            old_email=user.email,
            new_email=new_email,
            expires_at=expires_at
        )
        
        db.session.add(change_token)
        db.session.commit()
        
        return token
    
    def send_email_change_confirmation(self, user, new_email):
        """Send email change confirmation to new email address"""
        # Generate change token
        token = self.generate_email_change_token(user, new_email)
        
        # Create confirmation URL
        confirmation_url = url_for('confirm_email_change', token=token, _external=True)
        
        # Email content
        subject = "Confirm your new email address - Steam Achievement Tracker"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">📧 Email Change Request</h1>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa;">
                <h2 style="color: #2a5298;">Confirm Your New Email</h2>
                
                <p>Hi {user.username},</p>
                
                <p>You requested to change your email address for your Steam Achievement Tracker account:</p>
                
                <div style="background: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Current email:</strong> {user.email or 'Not set'}</p>
                    <p style="margin: 5px 0 0 0;"><strong>New email:</strong> {new_email}</p>
                </div>
                
                <p>To confirm this change, click the button below:</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{confirmation_url}" 
                       style="background: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                        ✅ Confirm Email Change
                    </a>
                </div>
                
                <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;">
                        <strong>Security Note:</strong> This confirmation link will expire in 24 hours. If you didn't request this change, you can safely ignore this email.
                    </p>
                </div>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #dee2e6;">
                
                <p style="color: #6c757d; font-size: 12px; text-align: center;">
                    Steam Achievement Tracker<br>
                    <a href="{url_for('index', _external=True)}" style="color: #2a5298;">Visit our website</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Email Change Confirmation
        
        Hi {user.username},
        
        You requested to change your email address for your Steam Achievement Tracker account.
        
        Current email: {user.email or 'Not set'}
        New email: {new_email}
        
        To confirm this change, click this link:
        {confirmation_url}
        
        This confirmation link will expire in 24 hours.
        
        If you didn't request this change, you can safely ignore this email.
        
        Best regards,
        Steam Achievement Tracker Team
        """
        
        return self._send_email(new_email, subject, html_content, text_content)

# Global instance
email_service = EmailService()