"""
CRITICAL SECURITY FIXES FOR ZO-ZI MARKETPLACE
Apply these changes to app.py BEFORE production deployment

INSTRUCTIONS:
1. Read each section carefully
2. Apply fixes to app.py
3. Test locally
4. Deploy to Render

Author: Production Security Audit
Date: October 2025
"""

# ==========================================
# FIX 1: STRONG SECRET KEY
# ==========================================
# REMOVE THIS from app.py (Line 24):
# app.secret_key = os.getenv('SECRET_KEY', 'yaad2025')  # ❌ WEAK DEFAULT

# REPLACE WITH:
"""
import secrets
import os

# Generate secret key if not in environment (development only)
if os.getenv('FLASK_ENV') == 'production':
    # In production, SECRET_KEY must be set in environment
    SECRET_KEY = os.environ['SECRET_KEY']
else:
    # In development, generate a random key if not set
    SECRET_KEY = os.getenv('SECRET_KEY', secrets.token_hex(32))

app = Flask(__name__)
app.secret_key = SECRET_KEY
"""

# Generate a new secret key for production:
# Run this command and save output to .env:
# python3 -c "import secrets; print(secrets.token_hex(32))"


# ==========================================
# FIX 2: PRODUCTION LOGGING
# ==========================================
# REPLACE line 78 in app.py:
"""
# Secure logging configuration
log_level = logging.INFO if os.getenv('FLASK_ENV') == 'production' else logging.DEBUG
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('marketplace.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Don't log sensitive data in production
if os.getenv('FLASK_ENV') == 'production':
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
"""


# ==========================================
# FIX 3: RATE LIMITING
# ==========================================
# ADD at top of app.py with other imports:
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
"""

# ADD after csrf = CSRFProtect(app):
"""
# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)
"""

# APPLY to sensitive routes - example for login:
"""
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # Only 5 login attempts per minute
def login():
    # ... existing code
"""

# Other routes to rate limit:
# - /register - "10 per hour"
# - /checkout - "20 per hour"
# - /new_product - "30 per hour"
# - /admin/* - "100 per hour"


# ==========================================
# FIX 4: FILE UPLOAD SECURITY
# ==========================================
# ADD to app configuration (after line 32):
"""
# File upload security
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
ALLOWED_MIME_TYPES = {
    'image/png', 'image/jpeg', 'image/jpg',
    'image/webp', 'image/gif'
}
"""

# ADD this function before any upload route:
"""
import imghdr

def validate_image(stream):
    '''Validate that uploaded file is actually an image'''
    header = stream.read(512)
    stream.seek(0)
    format = imghdr.what(None, header)
    if not format:
        return None
    return '.' + (format if format != 'jpeg' else 'jpg')

def allowed_file(filename, check_mime=None):
    '''Check if file extension and MIME type are allowed'''
    if not filename or '.' not in filename:
        return False

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False

    # Additional MIME type check if provided
    if check_mime and check_mime not in ALLOWED_MIME_TYPES:
        return False

    return True
"""

# UPDATE your upload routes to use validation:
"""
@app.route('/new_product', methods=['POST'])
def new_product():
    if 'image' in request.files:
        file = request.files['image']

        # Validate file
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400

        # Validate actual file content
        if not validate_image(file.stream):
            return jsonify({'error': 'File is not a valid image'}), 400

        # ... rest of upload code
"""


# ==========================================
# FIX 5: HTTPS ENFORCEMENT
# ==========================================
# ADD after app initialization (around line 37):
"""
# Force HTTPS in production
if os.getenv('FLASK_ENV') == 'production':
    @app.before_request
    def enforce_https():
        if not request.is_secure:
            # Check if request came through a proxy (like Render)
            if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)
"""


# ==========================================
# FIX 6: SECURE CORS CONFIGURATION
# ==========================================
# REPLACE line 37 in app.py:
# socketio = SocketIO(app, cors_allowed_origins="*")  # ❌ TOO PERMISSIVE

# WITH:
"""
# Secure CORS configuration
if os.getenv('FLASK_ENV') == 'production':
    ALLOWED_ORIGINS = [
        'https://your-app.onrender.com',  # Replace with your actual domain
        'https://www.zozi-marketplace.com'  # Replace with your custom domain
    ]
else:
    ALLOWED_ORIGINS = ['http://localhost:5000', 'http://127.0.0.1:5000']

socketio = SocketIO(
    app,
    cors_allowed_origins=ALLOWED_ORIGINS,
    cors_credentials=True,
    async_mode='eventlet'
)
"""


# ==========================================
# FIX 7: STRONGER PASSWORD HASHING
# ==========================================
# FIND all instances of generate_password_hash() and UPDATE to:
"""
# Current (line 680 and others):
hashed_password = generate_password_hash(password)

# UPDATE TO:
hashed_password = generate_password_hash(
    password,
    method='pbkdf2:sha256',
    salt_length=16
)
"""


# ==========================================
# FIX 8: DATABASE CONNECTION (PRODUCTION)
# ==========================================
# ADD at top of app.py after imports:
"""
from dotenv import load_dotenv
load_dotenv()

# Database selection based on environment
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'sqlite')

if DATABASE_TYPE == 'postgresql':
    from database_postgres import get_db
    print("✅ Using PostgreSQL database")
else:
    from database import get_db
    print("⚠️  Using SQLite database (development only)")

# Ensure PostgreSQL in production
if os.getenv('FLASK_ENV') == 'production' and DATABASE_TYPE != 'postgresql':
    raise RuntimeError("❌ CRITICAL: Must use PostgreSQL in production!")
"""


# ==========================================
# FIX 9: ERROR HANDLING (PRODUCTION)
# ==========================================
# ADD these error handlers before if __name__ == '__main__':
"""
# Custom error pages for production
@app.errorhandler(404)
def page_not_found(e):
    if os.getenv('FLASK_ENV') == 'production':
        return render_template('404.html'), 404
    return f"404 Error: {e}", 404

@app.errorhandler(500)
def internal_error(e):
    # Log the error
    logger.error(f"Internal error: {e}")

    if os.getenv('FLASK_ENV') == 'production':
        return render_template('500.html'), 500
    return f"500 Error: {e}", 500

@app.errorhandler(403)
def forbidden(e):
    if os.getenv('FLASK_ENV') == 'production':
        return render_template('403.html'), 403
    return f"403 Error: {e}", 403

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'error': 'Rate limit exceeded',
        'message': 'Too many requests. Please try again later.'
    }), 429
"""


# ==========================================
# FIX 10: SECURE SESSION CONFIGURATION
# ==========================================
# UPDATE session configuration (after line 26):
"""
# Secure session configuration
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
app.config['SESSION_COOKIE_NAME'] = 'zozi_session'

# Additional security headers
@app.after_request
def add_security_headers(response):
    if os.getenv('FLASK_ENV') == 'production':
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response
"""


# ==========================================
# BONUS: INPUT VALIDATION HELPER
# ==========================================
"""
import re

def validate_email(email):
    '''Validate email format'''
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    '''Validate Jamaican phone number'''
    # Jamaica format: (876) XXX-XXXX or 876XXXXXXX
    pattern = r'^(\(876\)|876)[\s-]?\d{3}[\s-]?\d{4}$'
    return re.match(pattern, phone) is not None

def sanitize_input(text, max_length=1000):
    '''Sanitize user input'''
    if not text:
        return ''
    # Remove potential XSS
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    # Limit length
    return text[:max_length].strip()
"""


# ==========================================
# UPDATE REQUIREMENTS.TXT
# ==========================================
"""
Add these to requirements.txt:

Flask-Limiter==3.5.0
python-dotenv==1.0.0
email-validator==2.1.0
gunicorn==21.2.0
psycopg2-binary==2.9.10

Then run:
pip install -r requirements.txt
"""


# ==========================================
# ENVIRONMENT VARIABLES (.env file)
# ==========================================
"""
Create/Update .env file with:

# Security
SECRET_KEY=<generate_with_command_above>
FLASK_ENV=production

# Database
DATABASE_TYPE=postgresql
DATABASE_URL=<render_will_provide_this>

# Application
DEBUG=False
FLASK_APP=app.py
"""


# ==========================================
# TESTING CHECKLIST
# ==========================================
"""
Before deploying, test:

1. Login/Logout
   - Try wrong password 6 times (should be rate limited)
   - Login successfully
   - Session should expire after 1 hour

2. File Upload
   - Try uploading .exe file (should fail)
   - Try uploading renamed .exe as .jpg (should fail)
   - Upload real image (should work)

3. Database
   - Create user
   - Create product
   - Make order
   - Check admin dashboard

4. Security Headers
   - Use https://securityheaders.com to scan your site

5. Performance
   - Test with 10 simultaneous users
   - Check page load times

6. Error Handling
   - Visit /nonexistent-page (should show custom 404)
   - Trigger an error (should show custom 500)
"""


# ==========================================
# DEPLOYMENT COMMAND
# ==========================================
"""
After applying all fixes:

# 1. Test locally
python app.py

# 2. Commit changes
git add .
git commit -m "Security fixes for production"
git push origin main

# 3. Deploy to Render
# (Render will auto-deploy when you push to main)

# 4. Monitor logs
# View logs on Render dashboard
"""

print("""
╔═══════════════════════════════════════════════════╗
║  ZO-ZI MARKETPLACE - CRITICAL SECURITY FIXES      ║
╠═══════════════════════════════════════════════════╣
║                                                   ║
║  ⚠️  APPLY ALL FIXES ABOVE BEFORE PRODUCTION     ║
║                                                   ║
║  Priority Order:                                  ║
║  1. Fix secret key (5 minutes)                   ║
║  2. Add rate limiting (15 minutes)               ║
║  3. Migrate to PostgreSQL (30 minutes)           ║
║  4. Add HTTPS enforcement (5 minutes)            ║
║  5. Secure file uploads (20 minutes)             ║
║  6. Update CORS (5 minutes)                      ║
║  7. Add error handlers (15 minutes)              ║
║  8. Add security headers (10 minutes)            ║
║  9. Test everything (2 hours)                    ║
║                                                   ║
║  Total Time: ~4 hours                            ║
║                                                   ║
║  🚀 Then you're ready for Render deployment!     ║
║                                                   ║
╚═══════════════════════════════════════════════════╝
""")