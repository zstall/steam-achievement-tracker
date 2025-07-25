"""
AWS S3 file management utilities for achievement images
"""

import boto3
import os
import uuid
import time
from botocore.exceptions import NoCredentialsError, ClientError
from werkzeug.utils import secure_filename
from PIL import Image
import io
from flask import current_app

class S3Manager:
    """Manages file uploads and downloads to/from AWS S3"""
    
    def __init__(self):
        self.s3_client = None
        self.bucket_name = None
        self.cloudfront_domain = None
        self.use_s3 = False
        
    def init_app(self, app):
        """Initialize S3 manager with Flask app config"""
        self.bucket_name = app.config.get('AWS_S3_BUCKET')
        self.cloudfront_domain = app.config.get('CLOUDFRONT_DOMAIN')
        self.use_s3 = app.config.get('USE_S3', False)
        
        if self.use_s3:
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=app.config.get('AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=app.config.get('AWS_SECRET_ACCESS_KEY'),
                    region_name=app.config.get('AWS_S3_REGION', 'us-east-1')
                )
                print("✅ S3 client initialized successfully")
            except Exception as e:
                print(f"❌ Failed to initialize S3 client: {e}")
                self.use_s3 = False
    
    def upload_image(self, file, user_id, achievement_id):
        """
        Upload an image file to S3 or local storage
        Returns: (filename, url) tuple or (None, None) on error
        """
        if not file or not file.filename:
            return None, None
            
        try:
            # Generate secure filename
            timestamp = int(time.time())
            file_ext = os.path.splitext(secure_filename(file.filename))[1].lower()
            filename = f"custom_{user_id}_{timestamp}_{uuid.uuid4().hex[:8]}{file_ext}"
            
            if self.use_s3:
                return self._upload_to_s3(file, filename)
            else:
                return self._upload_locally(file, filename)
                
        except Exception as e:
            print(f"❌ Error uploading image: {e}")
            return None, None
    
    def _upload_to_s3(self, file, filename):
        """Upload file to S3 bucket"""
        try:
            # Read and process image
            file.seek(0)
            image = Image.open(file)
            
            # Convert to RGB if necessary (for JPEG compatibility)
            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # Resize if too large (max 800x600)
            if image.width > 800 or image.height > 600:
                image.thumbnail((800, 600), Image.Resampling.LANCZOS)
            
            # Save to bytes buffer
            buffer = io.BytesIO()
            image_format = 'JPEG' if filename.lower().endswith(('.jpg', '.jpeg')) else 'PNG'
            image.save(buffer, format=image_format, quality=85, optimize=True)
            buffer.seek(0)
            
            # Upload to S3
            s3_key = f"achievement_images/{filename}"
            self.s3_client.upload_fileobj(
                buffer,
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': f'image/{image_format.lower()}',
                    'CacheControl': 'max-age=31536000',  # 1 year cache
                    'ACL': 'public-read'
                }
            )
            
            # Return filename and CloudFront URL
            url = f"https://{self.cloudfront_domain}/{s3_key}"
            print(f"✅ Image uploaded to S3: {url}")
            return filename, url
            
        except Exception as e:
            print(f"❌ S3 upload failed: {e}")
            return None, None
    
    def _upload_locally(self, file, filename):
        """Upload file to local storage (fallback)"""
        try:
            import time
            
            # Create upload directory if it doesn't exist
            upload_path = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_path, exist_ok=True)
            
            # Save file
            file_path = os.path.join(upload_path, filename)
            
            # Process image
            image = Image.open(file)
            if image.width > 800 or image.height > 600:
                image.thumbnail((800, 600), Image.Resampling.LANCZOS)
            
            image.save(file_path, quality=85, optimize=True)
            
            # Return filename and local URL
            url = f"/static/achievement_images/{filename}"
            print(f"✅ Image saved locally: {url}")
            return filename, url
            
        except Exception as e:
            print(f"❌ Local upload failed: {e}")
            return None, None
    
    def delete_image(self, filename):
        """Delete an image from S3 or local storage"""
        if not filename:
            return True
            
        try:
            if self.use_s3:
                s3_key = f"achievement_images/{filename}"
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                print(f"✅ Deleted from S3: {s3_key}")
            else:
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"✅ Deleted locally: {file_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error deleting image: {e}")
            return False
    
    def get_image_url(self, filename):
        """Get the full URL for an image"""
        if not filename:
            return None
            
        if self.use_s3:
            return f"https://{self.cloudfront_domain}/achievement_images/{filename}"
        else:
            return f"/static/achievement_images/{filename}"

# Global instance
s3_manager = S3Manager()