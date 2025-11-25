import sqlite3
import json
import re
import uuid
import random
import string
from flask_wtf.csrf import CSRFProtect, generate_csrf
import os
import logging  # Added logging import to fix NameError
import traceback
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from urllib.parse import unquote
# Simple admin protection decorator (use this for admin routes)
from functools import wraps
# Add these after your existing imports
from flask_socketio import SocketIO, emit, join_room, leave_room
import psycopg2
import psycopg2.extras

# PRODUCTION SECURITY FIX #1: Load environment variables securely
from dotenv import load_dotenv
load_dotenv()

# PRODUCTION SECURITY FIX #3: Rate Limiting
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# PAYMENT SYSTEM: Import payment calculation helpers
from payment_calculations import calculate_order_totals, calculate_seller_payouts

app = Flask(__name__)

# PRODUCTION SECURITY FIX #1: Strong Secret Key (NO DEFAULT FALLBACK)
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError("🚨 CRITICAL: SECRET_KEY not set in environment! Check your .env file")
app.secret_key = SECRET_KEY
# Only use secure cookies in production (HTTPS)
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # Disable CSRF token expiration
app.config['PERMANENT_SESSION_LIFETIME'] = 3600
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov'}

# WhatsApp Business Configuration
app.config['WHATSAPP_BUSINESS_NUMBER'] = os.getenv('WHATSAPP_BUSINESS_NUMBER', '18767962601')

csrf = CSRFProtect(app)

# Add this after: csrf = CSRFProtect(app)
socketio = SocketIO(app, cors_allowed_origins="*")


@app.template_filter('format_currency')
def format_currency(value):
    """Format currency values"""
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return "0.00"

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PARISHES = [
    'Clarendon', 'Hanover', 'Kingston', 'Manchester', 'Portland', 'Saint Andrew',
    'Saint Ann', 'Saint Catherine', 'Saint Elizabeth', 'Saint James', 'Saint Mary',
    'Saint Thomas', 'Trelawny', 'Westmoreland'
]

PARISH_POST_OFFICES = {
    'Clarendon': ['May Pen Post Office', 'Chapelton Post Office'],
    'Hanover': ['Lucea Post Office'],
    'Kingston': ['Half Way Tree Post Office'],
    'Manchester': ['Mandeville Post Office', 'Christiana Post Office'],
    'Portland': ['Port Antonio Post Office', 'Buff Bay Post Office'],
    'Saint Andrew': ['Constant Spring Post Office', 'Half Way Tree Post Office'],
    'Saint Ann': ['Ocho Rios Post Office', 'Browns Town Post Office', 'Saint Ann’s Bay Post Office'],
    'Saint Catherine': ['Spanish Town Post Office', 'Portmore Post Office', 'Linstead Post Office'],
    'Saint Elizabeth': ['Santa Cruz Post Office'],
    'Saint James': ['Montego Bay Post Office'],
    'Saint Mary': ['Port Maria Post Office', 'Highgate Post Office'],
    'Saint Thomas': ['Morant Bay Post Office'],
    'Trelawny': ['Falmouth Post Office'],
    'Westmoreland': ['Savanna-la-Mar Post Office', 'Negril Post Office'],
}

csrf = CSRFProtect(app)  # Initialize CSRF protection

# PRODUCTION SECURITY FIX #3: Initialize Rate Limiter (protects against spam/attacks)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["2000 per day", "500 per hour"],  # General limits for all routes (higher for development/testing)
    storage_uri="memory://",  # In-memory storage (good enough for single server)
    strategy="fixed-window"
)
print("✅ Rate limiting enabled - protecting against spam and attacks")

# PRODUCTION SECURITY FIX #2: Force PostgreSQL, block SQLite in production
# Auto-detect PostgreSQL from DATABASE_URL (used by Render, Heroku, etc.)
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'postgresql' if os.getenv('DATABASE_URL') else 'sqlite')
print(f"🔧 Database Type: {DATABASE_TYPE}")

if DATABASE_TYPE == 'postgresql':
    # Use PostgreSQL database
    from database_postgres import (
        get_db,
        track_product_view,
        get_last_viewed_product,
        get_personalized_products,
        init_db as init_postgres_db
    )
    print("✅ Using PostgreSQL database (PRODUCTION READY)")
else:
    # Use SQLite for development ONLY
    if os.getenv('FLASK_ENV') == 'production':
        raise RuntimeError("🚨 CRITICAL: Cannot use SQLite in production! Set DATABASE_TYPE=postgresql")
    print("⚠️  Using SQLite database (DEVELOPMENT ONLY)")

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

# Database connection helper
from contextlib import contextmanager

# Detect database type
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'postgresql' if os.getenv('DATABASE_URL') else 'sqlite')

@contextmanager
def get_db():
    """Database connection context manager - works with both PostgreSQL and SQLite"""
    conn = None
    try:
        if DATABASE_TYPE == 'postgresql':
            # PostgreSQL connection
            conn = psycopg2.connect(os.getenv('DATABASE_URL'))
            yield conn
            conn.commit()
        else:
            # SQLite connection
            import sqlite3
            conn = sqlite3.connect('zo-zi.db')
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    conn = sqlite3.connect('zo-zi.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT,
            first_name TEXT,
            last_name TEXT,
            is_seller BOOLEAN,
            is_support BOOLEAN DEFAULT FALSE,
            phone_number TEXT,
            address TEXT,
            parish TEXT,
            post_office TEXT,
            profile_picture TEXT,
            discount_used BOOLEAN DEFAULT FALSE,
            notification_preference TEXT,
            business_name TEXT,
            business_address TEXT,
            security_question TEXT,
            security_answer TEXT,
            discount_applied BOOLEAN DEFAULT FALSE,
            gender TEXT,
            delivery_address TEXT,
            billing_address TEXT,
            whatsapp_number TEXT,
            business_description TEXT,
            verification_status TEXT DEFAULT 'pending_documents',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # UPDATED: Conversations table
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_email TEXT NOT NULL,
                seller_email TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(buyer_email, seller_email),
                FOREIGN KEY (buyer_email) REFERENCES users(email),
                FOREIGN KEY (seller_email) REFERENCES users(email)
            )
        ''')

    # UPDATED: Messages table
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                sender_email TEXT NOT NULL,
                receiver_email TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_status BOOLEAN DEFAULT 0,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                FOREIGN KEY (sender_email) REFERENCES users(email),
                FOREIGN KEY (receiver_email) REFERENCES users(email)
            )
        ''')

    # Index for better query performance
    cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_messages_conversation 
            ON messages(conversation_id, timestamp)
        ''')

    cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_messages_unread 
            ON messages(receiver_email, read_status)
        ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            user_email TEXT,
            full_name TEXT,
            phone_number TEXT,
            address TEXT,
            parish TEXT,
            post_office TEXT,
            total REAL,
            discount REAL,
            payment_method TEXT,
            order_date DATETIME,
            status TEXT,
            shipping_option TEXT,
            shipping_fee REAL,
            tax REAL,
            lynk_reference TEXT,
            payment_verified BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_email) REFERENCES users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            admin_level TEXT DEFAULT 'admin',
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME,
            is_active BOOLEAN DEFAULT TRUE,
            permissions TEXT DEFAULT '{"users":true,"products":true,"orders":true,"analytics":true,"financials":true}',
            FOREIGN KEY (created_by) REFERENCES admin_users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            flag_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            flagged_by TEXT NOT NULL,
            flag_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            is_active BOOLEAN DEFAULT TRUE,
            notes TEXT,
            FOREIGN KEY (user_email) REFERENCES users(email),
            FOREIGN KEY (flagged_by) REFERENCES admin_users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_email TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            description TEXT,
            ip_address TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_email) REFERENCES admin_users(email)
        )
    ''')

    # Add these to your init_db() function after your existing tables

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            payment_type TEXT NOT NULL, -- 'bank', 'card', 'mobile'
            is_primary BOOLEAN DEFAULT FALSE,
            account_name TEXT,
            account_number TEXT, -- Will be encrypted in production
            bank_name TEXT,
            routing_number TEXT,
            card_last_four TEXT,
            card_brand TEXT,
            mobile_number TEXT,
            mobile_provider TEXT,
            payment_provider TEXT, -- 'stripe', 'paypal', 'local_bank'
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_verified BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (seller_email) REFERENCES users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT UNIQUE NOT NULL,
            order_id TEXT,
            seller_email TEXT,
            buyer_email TEXT,
            amount DECIMAL(10,2) NOT NULL,
            fee DECIMAL(10,2) DEFAULT 0,
            net_amount DECIMAL(10,2) NOT NULL,
            transaction_type TEXT, -- 'sale', 'withdrawal', 'refund'
            payment_method_id INTEGER,
            status TEXT DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed'
            processor_reference TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (seller_email) REFERENCES users(email),
            FOREIGN KEY (payment_method_id) REFERENCES seller_payment_methods(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS platform_financials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE UNIQUE NOT NULL,
            total_revenue DECIMAL(10,2) DEFAULT 0.00,
            platform_fees DECIMAL(10,2) DEFAULT 0.00,
            seller_payouts DECIMAL(10,2) DEFAULT 0.00,
            refunds_issued DECIMAL(10,2) DEFAULT 0.00,
            new_users INTEGER DEFAULT 0,
            new_sellers INTEGER DEFAULT 0,
            orders_count INTEGER DEFAULT 0,
            products_sold INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cancel_refund_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            user_email TEXT NOT NULL,
            reason TEXT NOT NULL,
            request_type TEXT DEFAULT 'cancel',
            request_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            admin_notes TEXT,
            processed_by TEXT,
            processed_date DATETIME,
            refund_amount DECIMAL(10,2),
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (user_email) REFERENCES users(email),
            FOREIGN KEY (processed_by) REFERENCES admin_users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_key TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            description TEXT,
            image_url TEXT,
            image_urls TEXT,
            shipping TEXT,
            brand TEXT,
            category TEXT,
            original_cost REAL,
            roi REAL,
            sizes TEXT,
            seller_email TEXT,
            sold INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            posted_date TEXT,
            amount INTEGER,
            FOREIGN KEY (seller_email) REFERENCES users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT,
            buyer_email TEXT,
            rating INTEGER CHECK(rating >= 1 AND rating <= 5),
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_email) REFERENCES users(email),
            FOREIGN KEY (buyer_email) REFERENCES users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_likes (
            user_email TEXT,
            product_key TEXT,
            created_at DATETIME,
            PRIMARY KEY (user_email, product_key),
            FOREIGN KEY (user_email) REFERENCES users(email),
            FOREIGN KEY (product_key) REFERENCES products(product_key)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_key TEXT NOT NULL,
            buyer_email TEXT NOT NULL,
            seller_email TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            review_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_verified_purchase BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (product_key) REFERENCES products(product_key),
            FOREIGN KEY (buyer_email) REFERENCES users(email),
            FOREIGN KEY (seller_email) REFERENCES users(email),
            UNIQUE(product_key, buyer_email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_email TEXT NOT NULL,
            session_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            unread INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            user_email TEXT NOT NULL,
            session_id TEXT NOT NULL,
            PRIMARY KEY (user_email, session_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            order_id TEXT,
            product_key TEXT,
            quantity INTEGER,
            price REAL,
            PRIMARY KEY (order_id, product_key),
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_key) REFERENCES products(product_key)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales_log (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT,
            product_key TEXT,
            quantity INTEGER,
            price REAL,
            sale_date DATETIME,
            buyer_email TEXT,
            FOREIGN KEY (product_key) REFERENCES products(product_key),
            FOREIGN KEY (seller_email) REFERENCES users(email),
            FOREIGN KEY (buyer_email) REFERENCES users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart_log (
            cart_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            product_key TEXT,
            quantity INTEGER,
            cart_date DATETIME,
            FOREIGN KEY (product_key) REFERENCES products(product_key),
            FOREIGN KEY (user_email) REFERENCES users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_finances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT UNIQUE NOT NULL,
            balance DECIMAL(10,2) DEFAULT 0.00,
            total_earnings DECIMAL(10,2) DEFAULT 0.00,
            pending_withdrawals DECIMAL(10,2) DEFAULT 0.00,
            last_withdrawal_date DATETIME,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_email) REFERENCES users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            product_key TEXT,
            buyer_email TEXT,
            description TEXT,
            transaction_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_email) REFERENCES users(email)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawal_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            fee DECIMAL(10,2) NOT NULL,
            net_amount DECIMAL(10,2) NOT NULL,
            method TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            request_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_date DATETIME,
            processing_time TEXT,
            reference_number TEXT,
            FOREIGN KEY (seller_email) REFERENCES users(email)
        )
    ''')

    # Create seller_verification table (only once)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL UNIQUE,
            verification_status TEXT DEFAULT 'pending_documents',
            id_document_path TEXT,
            id_document_type TEXT,
            trn_number TEXT,
            trn_document_path TEXT,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            reviewed_at DATETIME,
            reviewed_by TEXT,
            rejection_reason TEXT,
            notes TEXT,
            phone_verified BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (seller_email) REFERENCES users(email)
        )
    ''')

    # Create seller_notifications table for sale notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            product_key TEXT,
            product_name TEXT,
            buyer_email TEXT,
            quantity INTEGER,
            price REAL,
            sale_date DATETIME,
            order_id TEXT,
            is_read BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_email) REFERENCES users(email),
            FOREIGN KEY (product_key) REFERENCES products(product_key),
            FOREIGN KEY (buyer_email) REFERENCES users(email)
        )
    ''')

    # Insert default super admin - FIXED VERSION
    cursor.execute('''
           INSERT OR IGNORE INTO admin_users (email, password, admin_level, permissions, is_active, created_at)
           VALUES (%s, %s, %s, %s, %s,%s)
       ''', ('admin@zozi.com', generate_password_hash('adminpassword'), 'super_admin',

             '{"users":true,"products":true,"orders":true,"analytics":true,"financials":true,"admin_management":true}',
             1, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    # Insert default support agent with hashed password
    cursor.execute('''
           INSERT OR IGNORE INTO users (email, password, is_support, first_name, last_name, is_seller)
           VALUES (%s, %s, %s, %s, %s,%s)
       ''', ('support@yaad.com', generate_password_hash('supportpassword'), True, 'Support', 'Agent', False))

    conn.commit()
    conn.close()


def migrate_payment_tables():
    """Create payment-related tables if they don't exist"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if seller_payment_methods table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='seller_payment_methods'")
            if not cursor.fetchone():
                # Create the tables
                cursor.execute('''
                    CREATE TABLE seller_payment_methods (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        seller_email TEXT NOT NULL,
                        payment_type TEXT NOT NULL,
                        is_primary BOOLEAN DEFAULT FALSE,
                        account_name TEXT,
                        account_number TEXT,
                        bank_name TEXT,
                        routing_number TEXT,
                        card_last_four TEXT,
                        card_brand TEXT,
                        mobile_number TEXT,
                        mobile_provider TEXT,
                        payment_provider TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_verified BOOLEAN DEFAULT FALSE,
                        FOREIGN KEY (seller_email) REFERENCES users(email)
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE payment_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        transaction_id TEXT UNIQUE NOT NULL,
                        order_id TEXT,
                        seller_email TEXT,
                        buyer_email TEXT,
                        amount DECIMAL(10,2) NOT NULL,
                        fee DECIMAL(10,2) DEFAULT 0,
                        net_amount DECIMAL(10,2) NOT NULL,
                        transaction_type TEXT,
                        payment_method_id INTEGER,
                        status TEXT DEFAULT 'pending',
                        processor_reference TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME,
                        FOREIGN KEY (order_id) REFERENCES orders(order_id),
                        FOREIGN KEY (seller_email) REFERENCES users(email),
                        FOREIGN KEY (payment_method_id) REFERENCES seller_payment_methods(id)
                    )
                ''')

                conn.commit()
                logger.info("Created payment-related tables")
            else:
                logger.info("Payment tables already exist")

    except Exception as e:
        logger.error(f"Error creating payment tables: {e}")

def is_admin():
    """Check if current user is admin"""
    return 'admin_user' in session and session['admin_user'].get('is_active', False)


def admin_required(level='admin'):
    """Decorator to require admin authentication"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not is_admin():
                return redirect(url_for('login'))

            admin = session['admin_user']
            if level == 'super_admin' and admin.get('admin_level') != 'super_admin':
                return render_template('login.html', error="Super admin access required")

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def log_admin_activity(admin_email, action_type, target_type=None, target_id=None, description=None):
    """Log admin activities"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                   INSERT INTO admin_activity_log (admin_email, action_type, target_type, target_id, description, ip_address)
                   VALUES (%s, %s, %s, %s, %s,%s)
               ''', (admin_email, action_type, target_type, target_id, description, request.remote_addr))
            conn.commit()
    except Exception as e:
        logger.error(f"Error logging admin activity: {e}")


def reset_db():
    db_path = 'zo-zi.db'
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db()


# REMOVED: Old SQLite get_db() - now using PostgreSQL from database_postgres.py
# This function is imported at the top based on DATABASE_TYPE environment variable

INITIAL_PRODUCTS = {
    'Men Plaid Pants - 2400 JMD': {'name': 'Men Plaid Pants', 'price': 2400, 'description': 'Men Stylish Pants',
                                   'image_url': 'plaid pants.jpeg',
                                   'image_urls': ['plaid pants.jpeg', 'plaid pants 1.jpeg', 'plaid pants 3.jpeg'],
                                   'shipping': 'Kingston', 'seller_email': 'seller@example.com', 'sold': 5,
                                   'clicks': 20, 'likes': 10, 'amount': 15, 'category': 'Men Clothing',
                                   'sizes': {'Blue': 'M', 'Green': 'L'}},
    'Face Roll set - 1340 JMD': {'name': 'Face Roll Set', 'price': 1340, 'description': 'Comfortable Face Roll',
                                 'image_url': 'face roll 9.webp',
                                 'image_urls': ['face roll 9.webp', 'face roll 2.jpeg', 'face roll 3.webp',
                                                'face roll 4.webp', 'face roll 7.webp'], 'shipping': 'Saint_Ann',
                                 'seller_email': 'seller@example.com', 'sold': 2, 'clicks': 15, 'likes': 8,
                                 'amount': 10,
                                 'category': 'Beauty & Health', 'sizes': {'Silver': 'One Size'}},
    'Womens Plaid Pants - 2080 JMD': {'name': 'Womens Plaid Pants', 'price': 2080, 'description': 'Slim Fit Women',
                                      'image_url': 'women plaid pants 1.jpeg',
                                      'image_urls': ['women plaid pants 1.jpeg', 'women plaid pants.jpeg'],
                                      'shipping': 'Manchester', 'seller_email': 'seller2@example.com', 'sold': 0,
                                      'clicks': 5, 'likes': 3, 'amount': 20, 'category': 'Women Clothing',
                                      'sizes': {'Grey': 'S', 'Black': 'M'}},
    'Two Piece Hers - 3120 JMD': {'name': 'Two Piece Hers', 'price': 3120, 'description': 'Handmade Art',
                                  'image_url': 'two piece 3.jpeg',
                                  'image_urls': ['two piece 3.jpeg', 'two piece 2.jpeg', 'two piece 1.jpeg'],
                                  'shipping': 'Portland', 'seller_email': 'seller@example.com', 'sold': 3, 'clicks': 10,
                                  'likes': 7, 'amount': 12, 'category': 'Women Clothing',
                                  'sizes': {'Pink': 'M', 'Blue': 'L'}},
    'Womens Kini - 1560 JMD': {'name': 'Womens jamdung Kini', 'price': 1560, 'description': 'Sexy Bikini',
                               'image_url': 'kini 5.jpeg',
                               'image_urls': ['kini 5.jpeg', 'kini 1.jpeg', 'kini 2.webp', 'kini 3.jpeg',
                                              'kini 4.jpeg'], 'shipping': 'Trelawny',
                               'seller_email': 'seller2@example.com', 'sold': 1, 'clicks': 8, 'likes': 4, 'amount': 8,
                               'category': 'Beachwear', 'sizes': {'Green': 'S', 'Yellow': 'M'}},
    'Sewing Thread - 2000 JMD': {'name': 'Sewing Thread', 'price': 2000, 'description': 'Sewing Thread',
                                 'image_url': 'thread 1.webp',
                                 'image_urls': ['thread 1.webp', 'thread 2.webp', 'thread 3.webp', 'thread 4.webp',
                                                'thread 5.webp'], 'shipping': 'Saint Mary',
                                 'seller_email': 'seller@example.com', 'sold': 0, 'clicks': 3, 'likes': 2, 'amount': 50,
                                 'category': 'Home & Kitchen', 'sizes': {'Multicolor': 'One Size'}},
    'Womens Bodycon Dress - 2800 JMD': {'name': 'Womens Bodycon Dress', 'price': 2800,
                                        'description': 'Fitted Dress',
                                        'image_url': 'womens_bodycon_dress_2.jpeg',
                                        'image_urls': ['womens_bodycon_dress_2.jpeg', 'womens_bodycon_dress 1.jpeg',
                                                       'womens_bodycon_dress_4.jpeg', 'womens_bodycon_dress_5.jpeg'],
                                        'shipping': 'Saint James', 'seller_email': 'seller2@example.com', 'sold': 4,
                                        'clicks': 12, 'likes': 6, 'amount': 16, 'category': 'Women Clothing',
                                        'sizes': {'Red': 'S', 'Black': 'M'}},
    'Face Roll Vintage - 1800 JMD': {'name': 'Face Roll Vintage', 'price': 1800, 'description': 'Cultural Face Roll',
                                     'image_url': 'face roll 00.webp',
                                     'image_urls': ['face roll 00.webp', 'face roll 0.webp', 'face roll 01.webp'],
                                     'shipping': 'Westmoreland', 'seller_email': 'seller@example.com', 'sold': 2,
                                     'clicks': 7, 'likes': 5, 'amount': 9, 'category': 'Beauty & Health',
                                     'sizes': {'Gold': 'One Size'}},
    'Black Top Womens - 2500 JMD': {'name': 'Black Top Womens', 'price': 2500, 'description': 'Casual Top',
                                    'image_url': 'black top 2.jpeg',
                                    'image_urls': ['black top 2.jpeg', 'black top.jpeg', 'black top 1.jpeg'],
                                    'shipping': 'Hanover', 'seller_email': 'seller2@example.com', 'sold': 0,
                                    'clicks': 4, 'likes': 1, 'amount': 25, 'category': 'Women Clothing',
                                    'sizes': {'Black': 'M', 'White': 'L'}},
    'Red Lip Balm - 700 JMD': {'name': 'Red Lip Balm', 'price': 700, 'description': 'Moisturizing Lip Balm',
                               'image_url': 'red lip balm.jpeg',
                               'image_urls': ['red lip balm.jpeg', 'red lip balm 1.jpeg', 'red lip balm 77.jpeg',
                                              'red lip balm 2.jpeg'], 'shipping': 'Clarendon',
                               'seller_email': 'seller@example.com', 'sold': 1, 'clicks': 6, 'likes': 3, 'amount': 14,
                               'category': 'Beauty & Health', 'sizes': {'Red': 'One Size'}},
    'Brown Lip Gloss - 950 JMD': {'name': 'Brown Lip Gloss', 'price': 950, 'description': 'Shiny Lip Gloss',
                                  'image_url': 'brown lip gloss.jpeg',
                                  'image_urls': ['brown lip gloss.jpeg', 'brown lip gloss2.jpeg',
                                                 'brown lip gloss3.jpeg', 'brown lip gloss4.jpeg',
                                                 'brown lip gloss5.jpeg'], 'shipping': 'Saint Catherine',
                                  'seller_email': 'seller2@example.com', 'sold': 3, 'clicks': 9, 'likes': 4,
                                  'amount': 11, 'category': 'Beauty & Health', 'sizes': {'Brown': 'One Size'}},
    'jamaican bra- crochet - 1200 JMD': {'name': 'jamaican bra- crochet', 'price': 1200,
                                         'description': 'Jamaican Design Bra', 'image_url': 'bra-11.webp',
                                         'image_urls': ['bra-11.webp', 'bra 77.jpeg', 'bra22.webp'],
                                         'shipping': 'Saint Elizabeth', 'seller_email': 'seller@example.com', 'sold': 0,
                                         'clicks': 2, 'likes': 1, 'amount': 30, 'category': 'Underwear & Sleepwear',
                                         'sizes': {'Green': 'S', 'Yellow': 'M'}},
    'jamaica shirt-women - 500 JMD': {'name': 'jamaica-Shirt women', 'price': 500,
                                      'description': 'Cultural Shirt', 'image_url': 'jam shirt 1.jpeg',
                                      'image_urls': ['jam shirt 1.jpeg', 'jam shirt.jpeg'], 'shipping': 'Portland',
                                      'seller_email': 'seller2@example.com', 'sold': 2, 'clicks': 15, 'likes': 8,
                                      'amount': 18, 'category': 'Women Clothing',
                                      'sizes': {'Green': 'M', 'Black': 'L'}},
    'womens_two_piece- women - 2200 JMD': {'name': 'womens_two_piece- women', 'price': 2200,
                                           'description': 'Two Piece Set', 'image_url': 'womens_two_piece2.jpeg',
                                           'image_urls': ['womens_two_piece.jpeg', 'womens_two_piece4.jpeg',
                                                          'womens_two_piece_1.jpeg', 'womens_two_piece2.jpeg'],
                                           'shipping': 'Kingston', 'seller_email': 'seller@example.com', 'sold': 6,
                                           'clicks': 25, 'likes': 12, 'amount': 14, 'category': 'Women Clothing',
                                           'sizes': {'Blue': 'S', 'Pink': 'M'}},
    'Girl Sweater - 2100 JMD': {'name': 'Girl Sweater', 'price': 2100, 'description': 'Cozy Child Sweater',
                                'image_url': 'girl sweater.webp',
                                'image_urls': ['girl sweater 3.webp', 'island_hair_scarf2.webp',
                                               'island_hair_scarf3.webp', 'island_hair_scarf4.webp',
                                               'island_hair_scarf5.webp'], 'shipping': 'Saint Ann',
                                'seller_email': 'seller2@example.com', 'sold': 0, 'clicks': 3, 'likes': 2, 'amount': 20,
                                'category': 'Kids', 'sizes': {'Red': 'S', 'Blue': 'M'}},
    'Mens Jeans - 3000 JMD': {'name': 'Jeans Shirt pants', 'price': 3000, 'description': 'Casual Jeans',
                              'image_url': 'mens jeans .jpeg',
                              'image_urls': ['mens jeans fashion2.jpeg', 'mens jeans fashion6 .webp',
                                             'mens jeans fashion9.jpeg', 'mens jeans fashion.jpeg', 'mens jeans .jpeg'],
                              'shipping': 'Manchester', 'seller_email': 'seller@example.com', 'sold': 4, 'clicks': 18,
                              'likes': 9, 'amount': 16, 'category': 'Men Clothing',
                              'sizes': {'Blue': 'M', 'Black': 'L'}},
    'Mens Gray Jacket - 1900 JMD': {'name': 'Mens Gray Jacket', 'price': 1900, 'description': 'Mens Jacket',
                                    'image_url': 'jacket 5.jpeg',
                                    'image_urls': ['jacket 5.jpeg', 'gray jacket mens 6.webp',
                                                   'gray jacket mens 2.webp', 'gray jacket mens 3.webp'],
                                    'shipping': 'Saint Thomas', 'seller_email': 'seller2@example.com', 'sold': 1,
                                    'clicks': 5, 'likes': 3, 'amount': 25, 'category': 'Men Clothing',
                                    'sizes': {'Grey': 'M', 'Black': 'L'}},
    'All star - 2700 JMD': {'name': 'All Star Shoes', 'price': 2700, 'description': 'Casual Sneakers',
                            'image_url': 'all star shoes.jpeg',
                            'image_urls': ['all star shoes.jpeg', 'all star shoes 2.jpeg',
                                           'all star shoes.webp', 'all star shoes 5.jpeg'], 'shipping': 'Saint James',
                            'seller_email': 'seller@example.com', 'sold': 0, 'clicks': 4, 'likes': 2, 'amount': 30,
                            'category': 'Shoes', 'sizes': {'Black': ['7', '8', '9'], 'White': ['8', '9', '10']}},
    'baby gift set - 3800 JMD': {'name': 'Baby Gift Set', 'price': 3800, 'description': 'Baby Essentials',
                                 'image_url': 'baby gift set.jpeg',
                                 'image_urls': ['baby gift set 5.jpeg', 'baby gift set 1.jpeg',
                                                'baby gift set.jpeg'], 'shipping': 'Trelawny',
                                 'seller_email': 'seller2@example.com', 'sold': 3, 'clicks': 10, 'likes': 6,
                                 'amount': 17, 'category': 'Baby & Maternity', 'sizes': {'Blue': 'One Size'}},
    'ear ring jewelry - 1800 JMD': {'name': 'peridot ear ring', 'price': 1800, 'description': 'Elegant Earrings',
                                    'image_url': 'ear ring jewelry.jpeg',
                                    'image_urls': ['ear ring jewelry.jpeg'], 'shipping': 'Trelawny',
                                    'seller_email': 'seller2@example.com', 'sold': 3, 'clicks': 10, 'likes': 6,
                                    'amount': 17, 'category': 'Jewelry', 'sizes': {'Silver': 'One Size'}},
    'dumbell 10lbs - 3800 JMD': {'name': 'dumbell 10lbs', 'price': 3800, 'description': 'Fitness Weights',
                                 'image_url': 'dumbell 10lbs.webp',
                                 'image_urls': ['dumbell 10lbs.webp', 'dumbell 10lbs 2.webp'], 'shipping': 'Trelawny',
                                 'seller_email': 'seller2@example.com', 'sold': 3, 'clicks': 10, 'likes': 6,
                                 'amount': 17, 'category': 'Sports & Outdoors', 'sizes': {'Black': 'One Size'}}
}

FREE_PRODUCTS = {
    'Free knap-sack (bag) - 0 JMD': {
        'name': 'Zo-Zi School Bag',
        'price': 0,
        'description': 'Promotional Zo-Zi Gift School bag',
        'image_url': 'bag.jpeg',
        'image_urls': ['bag.jpeg', 'bag 1.jpeg', 'bag 2.jpeg', 'bag 3.jpeg'],
        'shipping': 'Kingston',
        'seller_email': 'seller@example.com',
        'sold': 0,
        'clicks': 0,
        'likes': 0,
        'amount': 100,
        'category': 'Promotional',
        'sizes': {'Multicolor': 'One Size'},
        'gift_key': 'gift_sticker'
    },
    'Free Zo-Zi Keychain - 0 JMD': {
        'name': 'Zo-Zi Keychain',
        'price': 0,
        'description': 'A free Zo-Zi keychain, perfect for your keys or bag.',
        'image_url': 'key chain.webp',
        'image_urls': ['key chain 1.webp', 'Key chain 3.webp', 'Key chain 5.webp', 'Key chain 2.webp'],
        'shipping': 'Saint Andrew',
        'seller_email': 'seller2@example.com',
        'sold': 0,
        'clicks': 0,
        'likes': 0,
        'amount': 50,
        'category': 'Promotional',
        'sizes': {'Silver': 'One Size'},
        'gift_key': 'gift_keychain'
    }
}


def migrate_products():
    with get_db() as conn:
        cursor = conn.cursor()
        for product_key, product in INITIAL_PRODUCTS.items():
            cursor.execute('SELECT product_key FROM products WHERE product_key = %s', (product_key,))
            if cursor.fetchone():
                continue
            cursor.execute('''
                INSERT INTO products (product_key, name, price, description, image_url, image_urls, shipping, brand, category,
                                    original_cost, roi, sizes, seller_email, sold, clicks, likes, posted_date, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                product_key,
                product['name'],
                product['price'],
                product['description'],
                product['image_url'],
                json.dumps(product['image_urls']),
                product['shipping'],
                product.get('brand', ''),
                product['category'],
                product.get('original_cost', 0),
                product.get('roi', 0),
                json.dumps(product.get('sizes', {})),
                product['seller_email'],
                product['sold'],
                product['clicks'],
                product['likes'],
                product.get('posted_date', datetime.now().strftime('%Y-%m-%d')),
                product['amount']
            ))
        for product_key, product in FREE_PRODUCTS.items():
            cursor.execute('SELECT product_key FROM products WHERE product_key = %s', (product_key,))
            if cursor.fetchone():
                continue
            cursor.execute('''
                INSERT INTO products (product_key, name, price, description, image_url, image_urls, shipping, brand, category,
                                    original_cost, roi, sizes, seller_email, sold, clicks, likes, posted_date, amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                product_key,
                product['name'],
                product['price'],
                product['description'],
                product['image_url'],
                json.dumps(product['image_urls']),
                product['shipping'],
                product.get('brand', ''),
                product['category'],
                product.get('original_cost', 0),
                product.get('roi', 0),
                json.dumps(product.get('sizes', {})),
                product['seller_email'],
                product['sold'],
                product['clicks'],
                product['likes'],
                product.get('posted_date', datetime.now().strftime('%Y-%m-%d')),
                product['amount']
            ))
        conn.commit()
        logger.info(f"Migrated {len(INITIAL_PRODUCTS)} initial products and {len(FREE_PRODUCTS)} free products")


def ensure_demo_seller():
    """Create demo seller accounts for initial products"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Create seller@example.com
            cursor.execute('SELECT email FROM users WHERE email = %s', ('seller@example.com',))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO users (email, password, first_name, last_name, is_seller, phone_number)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', ('seller@example.com', generate_password_hash('demo123'), 'Demo', 'Seller', True, '876-555-0100'))
                logger.info("✅ Created seller@example.com")

            # Create seller2@example.com
            cursor.execute('SELECT email FROM users WHERE email = %s', ('seller2@example.com',))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO users (email, password, first_name, last_name, is_seller, phone_number)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', ('seller2@example.com', generate_password_hash('demo123'), 'Demo', 'Seller 2', True, '876-555-0101'))
                logger.info("✅ Created seller2@example.com")

            conn.commit()
            logger.info("✅ All demo seller accounts ready")
    except Exception as e:
        logger.error(f"Error creating demo sellers: {e}")

def ensure_support_user():  # ✅ Now it's OUTSIDE migrate_products
    """Ensure the support user exists in the database"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if support user exists
            cursor.execute('SELECT email FROM users WHERE email = %s', ('support@yaad.com',))
            if not cursor.fetchone():
                # Create the support user
                cursor.execute('''
                    INSERT INTO users (email, password, is_support, first_name, last_name, is_seller,
                                     phone_number, address, parish, post_office, discount_applied, discount_used)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', ('support@yaad.com', 'supportpassword', True, 'Support', 'Agent', False,
                      '876-555-0000', 'Kingston Office', 'Kingston', 'Half Way Tree Post Office', False, False))
                conn.commit()
                logger.info("Support user created successfully")
            else:
                logger.info("Support user already exists")

    except Exception as e:
        logger.error(f"Error ensuring support user: {e}")


# REMOVED: Duplicate SQLite get_db() - using PostgreSQL version from import above

def is_user_flagged(user_email):
    """Check if a user has active flags"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as flag_count FROM user_flags
                WHERE user_email = %s AND is_active = true
                AND (expires_at IS NULL OR expires_at > NOW())
            ''', (user_email,))
            result = cursor.fetchone()
            return result['flag_count'] > 0
    except Exception as e:
        logger.error(f"Error checking if user flagged: {e}")
        return False

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def get_cart_items():
    try:
        cart = session.get('cart', {})
        if not cart:
            return {
                'items': [],
                'raw_total': 0.0,
                'discount': 0.0,
                'total': 0.0,
                'cart_item_count': 0
            }

        items = []
        raw_total = 0.0
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            for product_key, details in cart.items():
                base_product_key = re.sub(r'\s*\([^)]+\)$', '', product_key).strip()
                cursor.execute('''
                    SELECT name, price, image_url, amount, shipping_method, seller_email
                    FROM products WHERE product_key = %s
                ''', (base_product_key,))
                product = cursor.fetchone()
                if product:
                    quantity = min(details['quantity'], product['amount'])
                    items.append({
                        'product_key': product_key,
                        'name': product['name'],
                        'price': product['price'],
                        'quantity': quantity,
                        'stock': product['amount'],
                        'image_url': product['image_url'],
                        'shipping_method': product.get('shipping_method', 'jamaica_post'),
                        'seller_email': product.get('seller_email')
                    })
                    raw_total += product['price'] * quantity

        discount = 0.0
        if 'user' in session:
            email = session['user'].get('email')
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                cursor.execute('SELECT discount_applied, discount_used FROM users WHERE email = %s', (email,))
                user = cursor.fetchone()
                if user and not user['discount_used'] and items and not user['discount_applied']:
                    discount = min(500, raw_total)
                    cursor.execute('UPDATE users SET discount_applied = %s WHERE email = %s', (True, email))
                    conn.commit()
                    session['user']['discount_applied'] = True
                elif user and user['discount_applied'] and not user['discount_used']:
                    discount = min(500, raw_total)

        total = max(0, raw_total - discount)
        return {
            'items': items,
            'raw_total': raw_total,
            'discount': discount,
            'total': total,
            'cart_item_count': sum(item['quantity'] for item in items)
        }

    except sqlite3.Error as e:
        logger.error(f"Database error in get_cart_items: {e}\n{traceback.format_exc()}")
        return {
            'items': [],
            'raw_total': 0.0,
            'discount': 0.0,
            'total': 0.0,
            'cart_item_count': 0
        }
    except Exception as e:
        logger.error(f"Unexpected error in get_cart_items: {e}\n{traceback.format_exc()}")
        return {
            'items': [],
            'raw_total': 0.0,
            'discount': 0.0,
            'total': 0.0,
            'cart_item_count': 0
        }


def save_cart_to_db(user_email, cart_data):
    """Save user's cart to database before logout"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Clear existing cart data for this user
            cursor.execute('DELETE FROM cart_log WHERE user_email = %s', (user_email,))

            # Save current cart items
            for product_key, details in cart_data.items():
                base_product_key = re.sub(r'\s*\([^)]+\)$', '', product_key).strip()
                cursor.execute('''
                    INSERT INTO cart_log (user_email, product_key, quantity, cart_date)
                    VALUES (%s, %s, %s,%s)
                ''', (user_email, base_product_key, details['quantity'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

            conn.commit()
            logger.info(f"Saved cart to database for user: {user_email}")
    except Exception as e:
        logger.error(f"Error saving cart to DB: {e}")


def add_purchase_count_column():
    """Add purchase_count column to users table"""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS purchase_count INTEGER DEFAULT 0')
            conn.commit()
            logger.info("✅ Added purchase_count column to users table")
        except Exception as e:
            if "already exists" in str(e) or "duplicate column" in str(e).lower():
                logger.info("✅ purchase_count column already exists")
            else:
                logger.error(f"❌ Error adding column: {e}")


# STEP 2: Add this function to calculate purchase count from existing orders

def update_purchase_counts_from_orders():
    """Update purchase counts based on existing orders"""
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

        # Get all users who have placed orders
        cursor.execute('''
            SELECT user_email, COUNT(*) as order_count 
            FROM orders 
            WHERE status NOT IN ('cancelled', 'refunded')
            GROUP BY user_email
        ''')

        for row in cursor.fetchall():
            user_email = row['user_email']
            order_count = row['order_count']

            # Update user's purchase count
            cursor.execute('''
                UPDATE users 
                SET purchase_count = %s 
                WHERE email = %s
            ''', (order_count, user_email))

            # If they have 5+ orders, mark them as eligible for free gift
            if order_count >= 5 and order_count % 5 == 0:
                cursor.execute('''
                    UPDATE users 
                    SET discount_applied = true, discount_used = 0 
                    WHERE email = %s
                ''', (user_email,))

        conn.commit()
        logger.info("✅ Updated purchase counts from existing orders")

def restore_cart_from_db(user_email):
    """Restore user's cart from database after login"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get saved cart items
            cursor.execute('''
                SELECT cl.product_key, cl.quantity, p.name, p.price, p.image_url
                FROM cart_log cl
                JOIN products p ON cl.product_key = p.product_key
                WHERE cl.user_email = %s
                ORDER BY cl.cart_date DESC
            ''', (user_email,))

            saved_items = cursor.fetchall()
            restored_cart = {}

            for item in saved_items:
                product_key = item['product_key']
                restored_cart[product_key] = {
                    'name': item['name'],
                    'price': item['price'],
                    'quantity': item['quantity'],
                    'image_url': item['image_url']
                }

            if restored_cart:
                logger.info(f"Restored {len(restored_cart)} items to cart for user: {user_email}")

            return restored_cart

    except Exception as e:
        logger.error(f"Error restoring cart from DB: {e}")
        return {}

def send_notification(identifier, message, method):
    with get_db() as conn:
        cursor = conn.cursor()
        if method == 'email':
            cursor.execute('SELECT email FROM users WHERE email = %s', (identifier,))
        elif method == 'phone':
            cursor.execute('SELECT phone_number FROM users WHERE phone_number = %s', (identifier,))
        elif method == 'whatsapp':
            cursor.execute('SELECT whatsapp_number FROM users WHERE whatsapp_number = %s', (identifier,))
        user = cursor.fetchone()
        if user:
            logger.info(f"Sending {method} notification to {identifier}: {message}")
        else:
            logger.warning(f"No {method} found for {identifier}")

def generate_reset_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))



def get_postgres_connection():
    """Connection to PostgreSQL for chat messages"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            database=os.getenv('POSTGRES_DB', 'zozi_chat'),
            user=os.getenv('POSTGRES_USER', 'zozi_user'),
            password=os.getenv('POSTGRES_PASSWORD', 'yourpassword'),
            port=os.getenv('POSTGRES_PORT', '5432')
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to PostgreSQL: {e}")
        return None

def init_chat_db():
    """Create the messages table in PostgreSQL"""
    conn = get_postgres_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    sender_id VARCHAR(255) NOT NULL,
                    receiver_id VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_read BOOLEAN DEFAULT FALSE,
                    conversation_id VARCHAR(255)
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation 
                ON messages(conversation_id, timestamp);
            """)
            conn.commit()
            cur.close()
            conn.close()
            logger.info("Chat database initialized")
        except Exception as e:
            logger.error(f"Error initializing chat database: {e}")

def get_conversation_id(user1_id, user2_id):
    """Generate consistent conversation ID for two users"""
    return f"{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"

@app.errorhandler(400)
def bad_request(e):
    if request.path == '/cart' and request.method == 'POST':
        return jsonify({
            'success': False,
            'message': 'Bad request: Invalid or missing JSON payload'
        }), 400
    return render_template('404.html', error=str(e)), 400

@app.errorhandler(500)
def internal_error(e):
    if request.path == '/cart' and request.method == 'POST':
        return jsonify({
            'success': False,
            'message': 'Internal server error'
        }), 500
    return render_template('404.html', error="Internal server error"), 500


@app.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    """Serve uploaded files (verification documents, etc.)"""
    # Only allow admin and support agents to access verification documents
    if '/verifications/' in filename:
        is_admin = 'admin' in session or 'admin_user' in session
        is_support = 'user' in session and session['user'].get('is_support')

        if not (is_admin or is_support):
            return "Unauthorized", 403

    # Serve from static/uploads directory
    return send_from_directory(os.path.join(app.root_path, 'static', 'uploads'), filename)


@app.route('/free')
def free():
    if 'user' not in session:
        return redirect(url_for('login'))

    cart_data = get_cart_items()
    error = None
    user_email = session['user']['email']

    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

        # Calculate purchase count from actual orders
        cursor.execute('''
            SELECT COUNT(*) as order_count 
            FROM orders 
            WHERE user_email = %s AND status NOT IN ('cancelled', 'refunded')
        ''', (user_email,))

        order_result = cursor.fetchone()
        purchase_count = order_result['order_count'] if order_result else 0

        # Update user's purchase count in database
        cursor.execute('''
            UPDATE users SET purchase_count = %s WHERE email = %s
        ''', (purchase_count, user_email))

        # Get user's gift eligibility
        cursor.execute('''
            SELECT discount_applied, discount_used 
            FROM users WHERE email = %s
        ''', (user_email,))
        user_data = cursor.fetchone()

        discount_applied = user_data['discount_applied'] if user_data else False
        discount_used = user_data['discount_used'] if user_data else False

        # Update session
        session['user']['purchase_count'] = purchase_count
        session.modified = True

        # Get available free gifts
        cursor.execute('SELECT * FROM products WHERE price = 0')
        gifts = [
            dict(row,
                 image_urls=json.loads(row['image_urls']),
                 sizes=json.loads(row['sizes'])
                 )
            for row in cursor.fetchall()
        ]

        # Check eligibility based on actual order count
        if purchase_count < 5:
            error = f"Yuh nuh reach 5 purchases yet, mi fren. Yuh have {purchase_count} order{'s' if purchase_count != 1 else ''}. Shop more to qualify!"
        elif purchase_count >= 5:
            # Check if they've earned a gift they haven't claimed
            gifts_earned = purchase_count // 5

            if not discount_applied and gifts_earned > 0:
                # They earned a gift but it's not marked - fix this
                cursor.execute('''
                    UPDATE users 
                    SET discount_applied = true, discount_used = 0 
                    WHERE email = %s
                ''', (user_email,))
                session['user']['discount_applied'] = True
                session['user']['discount_used'] = False
                conn.commit()
            elif discount_used:
                # They used their last gift, check if they earned a new one
                next_milestone = ((purchase_count // 5)) * 5
                if purchase_count > next_milestone:
                    cursor.execute('''
                        UPDATE users 
                        SET discount_applied = true, discount_used = 0 
                        WHERE email = %s
                    ''', (user_email,))
                    session['user']['discount_applied'] = True
                    session['user']['discount_used'] = False
                    conn.commit()
                else:
                    remaining = (gifts_earned + 1) * 5 - purchase_count
                    error = f"Yuh already claim yuh gift! Make {remaining} more purchase{'s' if remaining > 1 else ''} fi yuh next free gift!"

        if not error and not gifts:
            error = "No free gifts deh yah right now, mi fren. Check back later, yuh hear!"

        conn.commit()

    return render_template(
        'free.html',
        gifts=gifts,
        error=error,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        user=session['user'],
        cart_item_count=cart_data['cart_item_count'],
        purchase_count=purchase_count
    )


@app.route('/cart/data', methods=['GET'])
def cart_data():
    try:
        cart_data = get_cart_items()
        return jsonify({
            'success': True,
            'cart_items': cart_data['items'],
            'cart_total': cart_data['total'],
            'discount': cart_data['discount'],
            'cart_item_count': cart_data['cart_item_count']
        })
    except Exception as e:
        logger.error(f"Error fetching cart data: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': 'Error loading cart'}), 500


# Autocomplete route for search suggestions
@app.route('/autocomplete')
def autocomplete():
    query = request.args.get('query', '').strip()
    if len(query) < 2:
        return jsonify([])

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            # Split query into keywords for partial matching
            keywords = query.lower().split()
            conditions = []
            params = []

            for keyword in keywords:
                conditions.append("LOWER(name) LIKE %s")
                params.append(f'%{keyword}%')

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor.execute(f'''
                SELECT product_key, name, image_url
                FROM products
                WHERE {where_clause}
                ORDER BY clicks DESC, likes DESC
                LIMIT 5
            ''', params)

            suggestions = []
            for row in cursor.fetchall():
                suggestions.append({
                    'product_key': row['product_key'],
                    'name': row['name'],
                    'image_url': row['image_url']
                })

            return jsonify(suggestions)
    except Exception as e:
        logger.error(f"Error in autocomplete: {e}")
        return jsonify([])

@app.route('/select_gift', methods=['POST'])
def select_gift():
    if 'user' not in session:
        return redirect(url_for('login'))

    gift_key = request.form.get('gift_key')
    if not gift_key:
        return redirect(url_for('free', error="No gift selected, mi fren!"))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM products WHERE product_key = %s', (gift_key,))
        gift = cursor.fetchone()
        if not gift or gift['price'] != 0:
            return redirect(url_for('free', error="Invalid gift selected, mi fren!"))

        if gift['amount'] < 1:
            return redirect(url_for('free', error="Gift out of stock, mi fren! Try another one."))

        if 'cart' not in session:
            session['cart'] = {}

        cart = session['cart']
        if gift_key in cart:
            return redirect(
                url_for('free', error="Yuh already pick dis gift, mi fren! Choose another or check yuh cart."))

        cart[gift_key] = {
            'name': gift['name'],
            'price': 0,
            'quantity': 1,
            'image_url': gift['image_url']
        }
        session['cart'] = cart
        session.modified = True
        logger.info(f"User {session['user']['email']} added free gift {gift_key} to cart")

    return redirect(url_for('checkout'))


@app.route('/')
def index():
    user = session.get('user')
    cart_data = get_cart_items()
    context = {
        'cart_items': cart_data['items'],
        'cart_total': cart_data['total'],
        'discount': cart_data['discount'],
        'user': user,
        'cart_item_count': cart_data['cart_item_count'],
        'categories': [
            'Accessories', 'Baby & Maternity', 'Beachwear', 'Beauty & Health', 'Home & Kitchen',
            'Jewelry', 'Kids', 'Men Clothing', 'Shoes', 'Sports & Outdoors',
            'Underwear & Sleepwear', 'Women Clothing'
        ]
    }
    try:
        # Get list of flagged sellers to exclude
        flagged_sellers = []
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            # Get all flagged sellers
            if DATABASE_TYPE == 'postgresql':
                cursor.execute('''
                    SELECT DISTINCT user_email FROM user_flags
                    WHERE is_active = true
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ''')
            else:
                cursor.execute('''
                    SELECT DISTINCT user_email FROM user_flags
                    WHERE is_active = 1
                    AND (expires_at IS NULL OR expires_at > datetime('now'))
                ''')
            flagged_sellers = [row['user_email'] if isinstance(row, dict) else row[0] for row in cursor.fetchall()]

        # Use personalized products if user is logged in and PostgreSQL is enabled
        if DATABASE_TYPE == 'postgresql' and user and user.get('email'):
            try:
                # Get personalized products based on viewing history
                products = get_personalized_products(user['email'], excluded_seller_emails=flagged_sellers)
                context['products'] = products
            except Exception as e:
                logger.error(f"Error getting personalized products, falling back to default: {e}")
                # Fallback to default product loading
                with get_db() as conn:
                    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                    cursor.execute('SELECT * FROM products ORDER BY RANDOM()')
                    products = {}
                    for row in cursor.fetchall():
                        product = dict(row, image_urls=json.loads(row['image_urls']), sizes=json.loads(row['sizes']))
                        if is_user_flagged(product['seller_email']) is None:
                            products[product['product_key']] = product
                    context['products'] = products
        else:
            # User not logged in or SQLite - show products ordered by popularity
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                if DATABASE_TYPE == 'postgresql':
                    cursor.execute('SELECT * FROM products ORDER BY (clicks + likes * 2) DESC, RANDOM()')
                else:
                    cursor.execute('SELECT * FROM products ORDER BY (clicks + likes * 2) DESC')
                products = {}
                for row in cursor.fetchall():
                    product = dict(row, image_urls=json.loads(row['image_urls']), sizes=json.loads(row['sizes']))
                    # Check if seller is flagged - completely hide product from homepage
                    if is_user_flagged(product['seller_email']) is None:
                        products[product['product_key']] = product
                context['products'] = products

        # Get review averages for all products
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                SELECT product_key, AVG(rating) as avg_rating, COUNT(*) as review_count
                FROM product_reviews
                GROUP BY product_key
            ''')
            review_stats = {row['product_key']: {'avg_rating': row['avg_rating'], 'review_count': row['review_count']} for row in cursor.fetchall()}

        # Attach review averages to products
        for product_key, product in context['products'].items():
            if product_key in review_stats:
                product['avg_rating'] = round(review_stats[product_key]['avg_rating'], 1)
                product['review_count'] = review_stats[product_key]['review_count']
            else:
                product['avg_rating'] = product.get('rating', 5.0)
                product['review_count'] = 0

        # Check if user is support agent and redirect to enhanced dashboard
        is_support = user and user.get('is_support', False)
        if is_support:
            return render_template('index_agent.html', **context)  # Your new enhanced template
        else:
            return render_template('index.html', **context)

    except Exception as e:
        context['error'] = f"An error occurred: {str(e)}"
        context['products'] = {}  # Ensure products is always defined
        return render_template('index.html', **context)


#
# Fix for the orders route in app.py
# Replace your existing orders route with this corrected version

# Debug the orders route to fix image display issue
# Add this debugging to your orders route in app.py

@app.route('/orders', methods=['GET'])
def orders():
    if 'user' not in session:
        return redirect(url_for('login'))

    user_email = session['user']['email']
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    per_page = 10

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get orders for the user with optional status filter
            base_query = '''
                SELECT order_id, user_email, full_name, phone_number, address, parish, post_office,
                       total, discount, payment_method, order_date, status, shipping_option, 
                       shipping_fee, tax
                FROM orders 
                WHERE user_email = %s
            '''
            params = [user_email]

            if status_filter:
                base_query += ' AND status = %s'
                params.append(status_filter)

            base_query += ' ORDER BY order_date DESC'

            cursor.execute(base_query, params)
            orders_data = cursor.fetchall()

            # Get unique statuses for filter dropdown
            cursor.execute('''
                SELECT DISTINCT status FROM orders 
                WHERE user_email = %s AND status IS NOT NULL
                ORDER BY status
            ''', (user_email,))
            available_statuses = [row['status'] for row in cursor.fetchall()]

            orders = []

            for order in orders_data:
                order_dict = dict(order)

                # IMPROVED: Get order items with better image handling
                cursor.execute('''
                    SELECT oi.product_key, oi.quantity, oi.price, 
                           COALESCE(p.name, oi.product_key) as name, 
                           COALESCE(p.image_url, 'placeholder.jpg') as image_url, 
                           COALESCE(p.category, 'Unknown') as category
                    FROM order_items oi
                    LEFT JOIN products p ON oi.product_key = p.product_key
                    WHERE oi.order_id = %s
                ''', (order_dict['order_id'],))

                order_items = cursor.fetchall()
                items_list = []

                for item in order_items:
                    # DEBUG: Print image URL to console
                    logger.info(f"DEBUG - Item: {item['name']}, Image URL: {item['image_url']}")

                    # Fix image URL path
                    image_url = item['image_url']
                    if image_url and image_url != 'placeholder.jpg':
                        # If image_url doesn't start with 'uploads/', add static path properly
                        if not image_url.startswith('uploads/') and not image_url.startswith('static/'):
                            # Image is just filename, use directly
                            final_image_url = image_url
                        else:
                            # Image already has path
                            final_image_url = image_url
                    else:
                        final_image_url = 'placeholder.jpg'

                    items_list.append({
                        'product_key': item['product_key'],
                        'product_name': item['name'],
                        'quantity': item['quantity'],
                        'price': float(item['price']) if item['price'] else 0.0,
                        'total_price': float(item['price'] * item['quantity']) if item['price'] else 0.0,
                        'image_url': final_image_url,  # Use the fixed image URL
                        'category': item['category']
                    })

                # Parse order date
                order_date_str = order_dict['order_date'] or ''
                if order_date_str:
                    try:
                        if ' ' in order_date_str:
                            date_part, time_part = order_date_str.split(' ', 1)
                        else:
                            date_part = order_date_str
                            time_part = '00:00:00'
                    except:
                        date_part = order_date_str
                        time_part = '00:00:00'
                else:
                    date_part = 'Unknown'
                    time_part = '00:00:00'

                # Determine order status with colors and descriptions
                status = order_dict['status'] or 'pending'
                status_info = {
                    'pending': {'color': '#ffc107', 'text': 'Order Pending'},
                    'confirmed': {'color': '#17a2b8', 'text': 'Order Confirmed'},
                    'shipped': {'color': '#6f42c1', 'text': 'Shipped'},
                    'delivered': {'color': '#28a745', 'text': 'Delivered'},
                    'cancelled': {'color': '#dc3545', 'text': 'Cancelled'},
                    'refunded': {'color': '#6c757d', 'text': 'Refunded'}
                }

                current_status = status_info.get(status, status_info['pending'])

                # Calculate days since order
                try:
                    from datetime import datetime
                    order_datetime = datetime.strptime(order_date_str.split(' ')[0], '%Y-%m-%d')
                    days_ago = (datetime.now() - order_datetime).days
                except:
                    days_ago = 0

                # Create simple order object
                order_formatted = {
                    'order_id': order_dict['order_id'],
                    'date': date_part,
                    'time': time_part,
                    'full_name': order_dict['full_name'] or 'N/A',
                    'phone_number': order_dict['phone_number'] or 'N/A',
                    'address': order_dict['address'] or 'N/A',
                    'parish': order_dict['parish'] or 'N/A',
                    'post_office': order_dict['post_office'] or 'N/A',
                    'subtotal': float(order_dict['total']) - float(order_dict['shipping_fee'] or 0) - float(
                        order_dict['tax'] or 0) + float(order_dict['discount'] or 0),
                    'total': float(order_dict['total']) if order_dict['total'] else 0.0,
                    'discount': float(order_dict['discount']) if order_dict['discount'] else 0.0,
                    'shipping_fee': float(order_dict['shipping_fee']) if order_dict['shipping_fee'] else 0.0,
                    'tax': float(order_dict['tax']) if order_dict['tax'] else 0.0,
                    'status': status,
                    'status_color': current_status['color'],
                    'status_text': current_status['text'],
                    'payment_method': order_dict['payment_method'] or 'N/A',
                    'shipping_option': order_dict['shipping_option'] or 'regular',
                    'shipping_type': 'Overnight Shipping' if order_dict[
                                                                 'shipping_option'] == 'overnight' else 'Regular Shipping',
                    'items': items_list,  # This contains the fixed image URLs
                    'item_count': len(items_list),
                    'days_ago': days_ago
                }

                orders.append(order_formatted)

            # Pagination
            total_orders = len(orders)
            total_pages = max(1, (total_orders + per_page - 1) // per_page)
            start = (page - 1) * per_page
            orders_paginated = orders[start:start + per_page]

            logger.info(f"Retrieved {len(orders_paginated)} orders for user {user_email}")

    except Exception as e:
        logger.error(f"Error in orders route: {e}\n{traceback.format_exc()}")
        orders_paginated = []
        total_pages = true
        available_statuses = []

    cart_data = get_cart_items()
    return render_template(
        'orders.html',
        user=session.get('user'),
        orders=orders_paginated,
        parishes=PARISHES,
        page=page,
        total_pages=total_pages,
        status_filter=status_filter,
        available_statuses=available_statuses,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )
#Debgging situation- trying to fid the problem.even IF IT WORKS. EVEN IF IT WORKS- THE THE PROBLEM STILL REMAIN#
@app.route('/debug_orders')
def debug_orders():
    """See which products exist vs don't exist"""
    if 'user' not in session:
        return "Please log in first"

    user_email = session['user']['email']

    with get_db() as conn:
        cursor = conn.cursor()

        # Check what's in your order_items vs products
        cursor.execute('''
            SELECT 
                oi.order_id,
                oi.product_key,
                p.name as product_name,
                p.image_url,
                CASE WHEN p.product_key IS NULL THEN 'DELETED' ELSE 'EXISTS' END as status
            FROM order_items oi
            LEFT JOIN products p ON oi.product_key = p.product_key
            WHERE oi.order_id IN (
                SELECT order_id FROM orders WHERE user_email = %s
            )
            ORDER BY oi.order_id DESC
        ''', (user_email,))

        results = cursor.fetchall()

        html = "<h2>Order Items Debug</h2><table border='1'>"
        html += "<tr><th>Order ID</th><th>Product Key</th><th>Product Name</th><th>Image URL</th><th>Status</th></tr>"

        for row in results:
            html += f"<tr><td>{row['order_id']}</td><td>{row['product_key']}</td><td>{row['product_name'] or 'N/A'}</td><td>{row['image_url'] or 'N/A'}</td><td>{row['status']}</td></tr>"

        html += "</table>"
        return html

@app.route('/receipt/<order_id>', methods=['GET'])
def receipt(order_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    user_email = session['user']['email']
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
        cursor.execute(
            "SELECT order_id, user_email, full_name, address, parish, post_office, total, discount, payment_method, order_date, status "
            "FROM orders WHERE order_id = %s AND user_email = %s",
            (order_id, user_email)
        )
        order_data = cursor.fetchone()
        if not order_data:
            return render_template(
                'receipt.html',
                error="Order not found or unauthorized",
                user=session.get('user'),
                cart_items=[],
                cart_total=0,
                discount=0,
                cart_item_count=0
            )
        cursor.execute(
            "SELECT oi.product_key, oi.quantity, oi.price, p.name, p.image_url "
            "FROM order_items oi JOIN products p ON oi.product_key = p.product_key WHERE oi.order_id = %s",
            (order_id,)
        )
        items = [{
            'product_key': item['product_key'],
            'product_name': item['name'],
            'quantity': item['quantity'],
            'price': item['price'],
            'image_url': item['image_url']
        } for item in cursor.fetchall()]
        order = {
            'order_id': order_data['order_id'],
            'user_email': order_data['user_email'],
            'full_name': order_data['full_name'],
            'address': order_data['address'],
            'parish': order_data['parish'],
            'post_office': order_data['post_office'],
            'total': order_data['total'],
            'discount': order_data['discount'],
            'payment_method': order_data['payment_method'],
            'order_date': order_data['order_date'],
            'status': order_data['status'],
            'items': items
        }
    cart_data = get_cart_items()
    return render_template(
        'receipt.html',
        user=session.get('user'),
        order=order,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )


# Add these routes to your app.py file
@app.route('/agent/orders/all', methods=['GET'])
def agent_get_all_orders():
    """Get all orders for agent dashboard"""
    if 'user' not in session or not session['user'].get('is_support'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all orders with customer info and items
            cursor.execute('''
                SELECT 
                    o.order_id, o.user_email, o.full_name, o.phone_number,
                    o.address, o.parish, o.post_office, o.total, o.discount,
                    o.payment_method, o.order_date, o.status, o.shipping_option,
                    o.shipping_fee, o.tax
                FROM orders o
                ORDER BY o.order_date DESC
            ''')

            orders = []
            for row in cursor.fetchall():
                order = dict(row)
                order['total'] = float(order['total'] or 0)
                order['discount'] = float(order['discount'] or 0)
                order['shipping_fee'] = float(order['shipping_fee'] or 0)
                order['tax'] = float(order['tax'] or 0)

                # Get seller info from order items
                cursor.execute('''
                    SELECT DISTINCT p.seller_email, u.business_name, u.first_name, u.last_name
                    FROM order_items oi
                    JOIN products p ON oi.product_key = p.product_key
                    LEFT JOIN users u ON p.seller_email = u.email
                    WHERE oi.order_id = %s
                ''', (order['order_id'],))

                sellers = cursor.fetchall()

                if sellers:
                    if len(sellers) == 1:
                        seller = sellers[0]
                        order['seller_info'] = {
                            'email': seller['seller_email'],
                            'business_name': seller['business_name'],
                            'name': f"{seller['first_name'] or ''} {seller['last_name'] or ''}".strip()
                        }
                    else:
                        # Multiple sellers
                        order['seller_info'] = None
                        order['multiple_sellers'] = True
                else:
                    order['seller_info'] = {'email': 'Unknown', 'business_name': 'Unknown', 'name': 'Unknown'}

                orders.append(order)

            return jsonify({
                'success': True,
                'orders': orders,
                'total_count': len(orders)
            })

    except Exception as e:
        logger.error(f"Error getting all orders for agent: {e}")
        return jsonify({'success': False, 'message': 'Error loading orders'}), 500


@app.route('/agent/orders/search', methods=['GET'])
def agent_search_orders():
    """Search orders for agent dashboard"""
    if 'user' not in session or not session['user'].get('is_support'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    search_query = request.args.get('q', '').strip()
    if not search_query:
        return jsonify({'success': False, 'message': 'Search query required'}), 400

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Search orders
            cursor.execute('''
                SELECT 
                    o.order_id, o.user_email, o.full_name, o.phone_number,
                    o.address, o.parish, o.post_office, o.total, o.discount,
                    o.payment_method, o.order_date, o.status, o.shipping_option,
                    o.shipping_fee, o.tax
                FROM orders o
                WHERE 
                    o.order_id LIKE ? OR 
                    o.user_email LIKE ? OR 
                    o.full_name LIKE ? OR
                    o.phone_number LIKE ?
                ORDER BY o.order_date DESC
            ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))

            orders = []
            for row in cursor.fetchall():
                order = dict(row)
                order['total'] = float(order['total'] or 0)
                order['discount'] = float(order['discount'] or 0)
                order['shipping_fee'] = float(order['shipping_fee'] or 0)
                order['tax'] = float(order['tax'] or 0)

                # Get seller info
                cursor.execute('''
                    SELECT DISTINCT p.seller_email, u.business_name, u.first_name, u.last_name
                    FROM order_items oi
                    JOIN products p ON oi.product_key = p.product_key
                    LEFT JOIN users u ON p.seller_email = u.email
                    WHERE oi.order_id = %s
                ''', (order['order_id'],))

                sellers = cursor.fetchall()

                if sellers:
                    if len(sellers) == 1:
                        seller = sellers[0]
                        order['seller_info'] = {
                            'email': seller['seller_email'],
                            'business_name': seller['business_name'],
                            'name': f"{seller['first_name'] or ''} {seller['last_name'] or ''}".strip()
                        }
                    else:
                        order['seller_info'] = None
                        order['multiple_sellers'] = True
                else:
                    order['seller_info'] = {'email': 'Unknown', 'business_name': 'Unknown', 'name': 'Unknown'}

                orders.append(order)

            return jsonify({
                'success': True,
                'orders': orders,
                'search_query': search_query,
                'total_count': len(orders)
            })

    except Exception as e:
        logger.error(f"Error searching orders for agent: {e}")
        return jsonify({'success': False, 'message': 'Error searching orders'}), 500


@app.route('/agent/orders/<order_id>', methods=['GET'])
def agent_get_order_details(order_id):
    """Get detailed order information for agent dashboard"""
    if 'user' not in session or not session['user'].get('is_support'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get order details
            cursor.execute('''
                SELECT 
                    order_id, user_email, full_name, phone_number, address, 
                    parish, post_office, total, discount, payment_method, 
                    order_date, status, shipping_option, shipping_fee, tax
                FROM orders 
                WHERE order_id = %s
            ''', (order_id,))

            order_data = cursor.fetchone()
            if not order_data:
                return jsonify({'success': False, 'message': 'Order not found'}), 404

            order = dict(order_data)
            order['total'] = float(order['total'] or 0)
            order['discount'] = float(order['discount'] or 0)
            order['shipping_fee'] = float(order['shipping_fee'] or 0)
            order['tax'] = float(order['tax'] or 0)

            # Get order items
            cursor.execute('''
                SELECT 
                    oi.product_key, oi.quantity, oi.price,
                    COALESCE(p.name, oi.product_key) as product_name,
                    COALESCE(p.image_url, 'placeholder.jpg') as image_url,
                    COALESCE(p.category, 'Unknown') as category
                FROM order_items oi
                LEFT JOIN products p ON oi.product_key = p.product_key
                WHERE oi.order_id = %s
            ''', (order_id,))

            items = []
            for item_row in cursor.fetchall():
                item = dict(item_row)
                item['price'] = float(item['price'] or 0)
                item['total_price'] = item['price'] * item['quantity']
                items.append(item)

            order['items'] = items

            # ADD SELLER INFO - This was missing!
            cursor.execute('''
                SELECT DISTINCT p.seller_email, u.business_name, u.first_name, u.last_name
                FROM order_items oi
                JOIN products p ON oi.product_key = p.product_key
                LEFT JOIN users u ON p.seller_email = u.email
                WHERE oi.order_id = %s
            ''', (order_id,))

            sellers = cursor.fetchall()

            if sellers:
                if len(sellers) == 1:
                    seller = sellers[0]
                    # Handle null values and prioritize business name
                    business_name = seller['business_name'] if seller['business_name'] else ''
                    first_name = seller['first_name'] if seller['first_name'] else ''
                    last_name = seller['last_name'] if seller['last_name'] else ''
                    full_name = f"{first_name} {last_name}".strip()

                    # Priority: business_name > full_name > email > default
                    if business_name:
                        display_name = business_name
                    elif full_name:
                        display_name = full_name
                    elif seller['seller_email']:
                        display_name = seller['seller_email']
                    else:
                        display_name = 'Unknown Seller'

                    order['seller_info'] = {
                        'email': seller['seller_email'] or 'Unknown',
                        'business_name': business_name or 'No Business Name',
                        'name': display_name,
                        'first_name': first_name,
                        'last_name': last_name
                    }
                    order['multiple_sellers'] = False
                else:
                    # Multiple sellers
                    order['seller_info'] = None
                    order['multiple_sellers'] = True
            else:
                order['seller_info'] = {
                    'email': 'No Seller Found',
                    'business_name': 'No Business',
                    'name': 'Unknown Seller',
                    'first_name': '',
                    'last_name': ''
                }
                order['multiple_sellers'] = False

            return jsonify({
                'success': True,
                'order': order
            })

    except Exception as e:
        logger.error(f"Error getting order details for agent: {e}")
        return jsonify({'success': False, 'message': f'Error loading order details: {str(e)}'}), 500


@app.route('/agent/orders/update-status', methods=['POST'])
def agent_update_order_status():
    """Update order status from agent dashboard"""
    if 'user' not in session or not session['user'].get('is_support'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        order_id = data.get('order_id')
        new_status = data.get('status')

        if not order_id or not new_status:
            return jsonify({'success': False, 'message': 'Order ID and status required'}), 400

        # Valid status options
        valid_statuses = ['pending', 'preparing', 'on-the-way', 'delivered', 'cancelled', 'refunded']
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if order exists
            cursor.execute('SELECT order_id, status FROM orders WHERE order_id = %s', (order_id,))
            order = cursor.fetchone()
            if not order:
                return jsonify({'success': False, 'message': 'Order not found'}), 404

            old_status = order['status']

            # Update order status
            cursor.execute('UPDATE orders SET status = %s WHERE order_id = %s', (new_status, order_id))

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Failed to update order'}), 500

            conn.commit()

            # Log the status change
            logger.info(
                f"Agent {session['user']['email']} updated order {order_id} status from {old_status} to {new_status}")

            return jsonify({
                'success': True,
                'message': f'Order status updated successfully',
                'order_id': order_id,
                'old_status': old_status,
                'new_status': new_status
            })

    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return jsonify({'success': False, 'message': 'Error updating order status'}), 500


@app.route('/subscriptions')
def subscriptions():
    cart_data = get_cart_items()
    return render_template(
        'subscriptions.html',
        user=session.get('user'),
        cart_item_count=cart_data['cart_item_count']
    )

@app.route('/subscribe/<plan>')
def subscribe(plan):
    if plan not in ['basic', 'pro', 'growth']:
        return render_template('404.html', error="Invalid subscription plan"), 404
    if 'user' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('payment', plan=plan))

@app.route('/payment/<plan>')
def payment(plan):
    cart_data = get_cart_items()
    return render_template(
        'payment.html',
        user=session.get('user'),
        cart_item_count=cart_data['cart_item_count'],
        plan=plan,
        error="Payment processing not yet implemented"
    )

@app.route('/zozi_assistant', methods=['GET', 'POST'])
def zozi_assistant():
    user = session.get('user')
    cart_data = get_cart_items()
    if 'chat_history' not in session:
        session['chat_history'] = []
    chat_history = session['chat_history']
    if request.method == 'POST':
        user_message = request.form.get('message', '').lower().strip()
        if not user_message:
            return render_template(
                'zozi_assistant.html',
                user=user,
                cart_items=cart_data['items'],
                cart_total=cart_data['total'],
                discount=cart_data['discount'],
                cart_item_count=cart_data['cart_item_count'],
                chat_history=chat_history,
                error="Please type a message, dear!"
            )
        zozi_response = ""
        if any(greeting in user_message for greeting in ['hi', 'hello', 'hey', 'good morning', 'good afternoon']):
            zozi_response = "Good day, my dear! How can I assist you today? It’s always nice to hear from you."
        elif 'math' in user_message or 'fraction' in user_message or 'subtract' in user_message:
            if 'subtract' in user_message and 'from' in user_message:
                try:
                    numbers = re.findall(r'\d+/\d+', user_message)
                    if len(numbers) == 2:
                        num1, den1 = map(int, numbers[0].split('/'))
                        num2, den2 = map(int, numbers[1].split('/'))
                        common_den = den1 * den2
                        new_num1 = num1 * den2
                        new_num2 = num2 * den1
                        result_num = new_num2 - new_num1
                        result_den = common_den
                        zozi_response = (
                            f"Let’s sort this out nice and easy. To subtract {num1}/{den1} from {num2}/{den2}, "
                            f"we need a common denominator, which is {common_den}. So, {num1}/{den1} becomes {new_num1}/{common_den}, "
                            f"and {num2}/{den2} becomes {new_num2}/{common_den}. Now, subtract: {new_num2}/{common_den} minus {new_num1}/{common_den} "
                            f"is {result_num}/{result_den}. You see how we did that? Let’s try another one if you’d like!")
                    else:
                        zozi_response = "I see you’re working with fractions, but I need two fractions to subtract, like 3/4 from 5/6. Can you give me those numbers again, please?"
                except Exception:
                    zozi_response = "That’s a likkle tricky one! Can you write the fractions clearly, like 3/4 or 5/6, so I can help you better?"
            else:
                zozi_response = "Maths, eh? I love helping with that! Can you tell me the specific problem you’re working on? Maybe something with fractions or addition?"
        elif any(q in user_message for q in ['what can you do', 'how can you help']):
            zozi_response = "I’m here to assist with a whole heap of things, my dear! I can help with maths problems, answer questions, or even chat about what’s on your mind. What would you like to do today?"
        elif 'struggle' in user_message or 'hard' in user_message or 'difficult' in user_message:
            zozi_response = "No need to get vex, alright? Let’s break it down together. What part are you finding difficult? Tell me more, and we’ll sort it out nice and easy."
        else:
            zozi_response = "I’m not quite sure how to answer that just yet, but I’m here to help! Can you tell me a bit more, or maybe ask in a different way?"
        timestamp = datetime.now().strftime('%B %d - %I:%M%p')
        chat_history.append({'timestamp': timestamp, 'messages': [{'user': user_message, 'zozi': zozi_response}]})
        session['chat_history'] = chat_history
    return render_template(
        'zozi_assistant.html',
        user=user,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count'],
        chat_history=chat_history
    )

@app.route('/save_chat', methods=['POST'])
def save_chat():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'User not logged in'}), 401
    data = request.get_json()
    messages = data.get('messages', [])
    if messages:
        timestamp = datetime.now().strftime('%B %d - %I:%M%p')
        if 'chat_history' not in session:
            session['chat_history'] = []
        session['chat_history'].append({'timestamp': timestamp, 'messages': messages})
    return jsonify({'success': True})


@app.route('/find_sellers')
def find_sellers():
    """Enhanced sellers directory with store links"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get user's parish (default to Kingston if not logged in)
            user_parish = 'Kingston'
            if 'user' in session and session['user'].get('parish'):
                user_parish = session['user']['parish']

            # Get sellers in user's parish with enhanced info
            cursor.execute('''
                SELECT u.email, u.first_name, u.last_name, u.business_name, u.business_address, 
                       u.profile_picture, COUNT(p.product_key) as product_count,
                       AVG(sr.rating) as avg_rating, COUNT(sr.rating) as rating_count,
                       SUM(p.sold) as total_sales
                FROM users u
                LEFT JOIN products p ON u.email = p.seller_email
                LEFT JOIN seller_ratings sr ON u.email = sr.seller_email
                WHERE u.is_seller = true AND u.business_address = %s
                GROUP BY u.email
                ORDER BY total_sales DESC, product_count DESC
            ''', (user_parish,))

            local_sellers = []
            for row in cursor.fetchall():
                seller_data = dict(row)
                seller_data['avg_rating'] = round(seller_data['avg_rating'], 1) if seller_data['avg_rating'] else 0
                seller_data['total_sales'] = seller_data['total_sales'] or 0
                seller_data['product_count'] = seller_data['product_count'] or 0
                seller_data['rating_count'] = seller_data['rating_count'] or 0
                local_sellers.append(seller_data)

            # Get sellers from other parishes
            cursor.execute('''
                SELECT u.email, u.first_name, u.last_name, u.business_name, u.business_address, 
                       u.profile_picture, COUNT(p.product_key) as product_count,
                       AVG(sr.rating) as avg_rating, COUNT(sr.rating) as rating_count,
                       SUM(p.sold) as total_sales
                FROM users u
                LEFT JOIN products p ON u.email = p.seller_email
                LEFT JOIN seller_ratings sr ON u.email = sr.seller_email
                WHERE u.is_seller = true AND u.business_address != ?
                GROUP BY u.email
                ORDER BY total_sales DESC, product_count DESC
            ''', (user_parish,))

            other_sellers = []
            for row in cursor.fetchall():
                seller_data = dict(row)
                seller_data['avg_rating'] = round(seller_data['avg_rating'], 1) if seller_data['avg_rating'] else 0
                seller_data['total_sales'] = seller_data['total_sales'] or 0
                seller_data['product_count'] = seller_data['product_count'] or 0
                seller_data['rating_count'] = seller_data['rating_count'] or 0
                other_sellers.append(seller_data)

        cart_data = get_cart_items()
        return render_template(
            'find_sellers.html',
            local_sellers=local_sellers,
            other_sellers=other_sellers,
            user_parish=user_parish,
            cart_items=cart_data['items'],
            cart_total=cart_data['total'],
            discount=cart_data['discount'],
            user=session.get('user'),
            cart_item_count=cart_data['cart_item_count']
        )
    except Exception as e:
        logger.error(f"Error in find_sellers: {e}")
        cart_data = get_cart_items()
        return render_template(
            'find_sellers.html',
            local_sellers=[],
            other_sellers=[],
            user_parish='Kingston',
            cart_items=cart_data['items'],
            cart_total=cart_data['total'],
            discount=cart_data['discount'],
            user=session.get('user'),
            cart_item_count=cart_data['cart_item_count']
        )


@app.route('/customer_service_login', methods=['GET', 'POST'])
def customer_service_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('SELECT * FROM users WHERE email = %s AND is_support = %s', (username, True))
            user = cursor.fetchone()

            if user:
                # Check if password is hashed
                password_valid = False
                if user['password'] and ('pbkdf2:' in user['password'] or 'scrypt:' in user['password'] or '$' in user['password']):
                    password_valid = check_password_hash(user['password'], password)
                else:
                    # Plain text password - check and update
                    password_valid = (user['password'] == password)
                    if password_valid:
                        # Update to hashed password
                        hashed_password = generate_password_hash(password)
                        cursor.execute('UPDATE users SET password = %s WHERE email = %s', (hashed_password, user['email']))
                        conn.commit()

                if password_valid:
                    session['support_user'] = {'email': username, 'is_support': True}
                    return redirect(url_for('customer_service'))

            return render_template('customer_service_login.html', error="Invalid credentials")
    return render_template('customer_service_login.html')



@app.route('/customer_service', methods=['GET'])
def customer_service():
    if 'support_user' not in session or not session['support_user'].get('is_support'):
        return redirect(url_for('customer_service_login'))
    with get_db() as conn:
        cursor = conn.cursor()
        selected_user = request.args.get('user_id')
        selected_session = request.args.get('session_id')

        cursor.execute('''
            SELECT DISTINCT user_email, session_id, MAX(timestamp) as last_message
            FROM contact_messages
            WHERE sender = 'user'
            GROUP BY user_email, session_id
            ORDER BY last_message DESC
        ''')
        conversations = []
        for row in cursor.fetchall():
            user_email = row['user_email']
            session_id = row['session_id']
            cursor.execute('''
                SELECT COUNT(*) as unread_count
                FROM contact_messages
                WHERE user_email = %s AND session_id = %s AND unread = true
            ''', (user_email, session_id))
            unread_result = cursor.fetchone()
            unread_count = unread_result['unread_count'] if unread_result else 0
            conversations.append({
                'user_id': user_email,
                'session_id': session_id,
                'last_message': datetime.strptime(row['last_message'], '%Y-%m-%d %H:%M:%S'),
                'unread_count': unread_count
            })

        if not selected_user or not selected_session:
            if conversations:
                selected_user = conversations[0]['user_id']
                selected_session = conversations[0]['session_id']
            else:
                selected_user = None
                selected_session = None

        contact_history = []
        can_respond = False
        if selected_user:
            cursor.execute('''
                SELECT sender, message, timestamp
                FROM contact_messages
                WHERE user_email = %s AND session_id = %s
                ORDER BY timestamp
            ''', (selected_user, selected_session))
            contact_history = [
                {
                    'sender': row['sender'],
                    'text': row['message'],
                    'timestamp': datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
                } for row in cursor.fetchall()
            ]
            cursor.execute('''
                SELECT COUNT(*) FROM contact_messages
                WHERE user_email = %s AND session_id = %s AND sender = 'user'
            ''', (selected_user, selected_session))
            can_respond = cursor.fetchone()[0] > 0

        cursor.execute('SELECT COUNT(*) as unread_count FROM contact_messages WHERE unread = true')
        unread_result = cursor.fetchone()
        total_unread_count = unread_result['unread_count'] if unread_result else 0

    cart_data = get_cart_items()
    return render_template(
        'customer_service.html',
        conversations=conversations,
        selected_user=selected_user,
        selected_session=selected_session,
        contact_history=contact_history,
        can_respond=can_respond,
        unread_count=total_unread_count,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )

@app.route('/respond', methods=['POST'])
def respond():
    user = session.get('user')
    if not user or not user.get('is_support', False):
        return redirect(url_for('index'))
    session_id = request.form.get('session_id')
    response = request.form.get('response', '').strip()
    if response:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                INSERT INTO contact_messages (user_id, user_email, session_id, sender, message, timestamp, unread)
                VALUES (%s, %s, %s, %s, %s, %s,%s)
            ''', ('support', 'support@yaad.com', session_id, 'support', response, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 1))
            conn.commit()
    return redirect(url_for('contact'))

@app.route('/customer_service/check_new_messages')
def check_new_messages():
    if 'support_user' not in session or not session['support_user'].get('is_support'):
        return jsonify({'error': 'Unauthorized'}), 401
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_email, session_id, sender, message, timestamp FROM contact_messages WHERE sender = %s AND unread = true ORDER BY timestamp DESC',
                       ('user',))
        new_messages = [{'user_id': row['user_email'], 'session_id': row['session_id'], 'sender': row['sender'], 'text': row['message'], 'timestamp': row['timestamp']} for row in cursor.fetchall()]
    return jsonify({'new_messages': new_messages})

@app.route('/agent_respond', methods=['POST'])
def agent_respond():
    if 'support_user' not in session or not session['support_user'].get('is_support'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    user_email = request.form.get('user_email')
    session_id = request.form.get('session_id')
    response = request.form.get('response')

    if not user_email or not session_id or not response:
        return jsonify({'success': False, 'message': 'Missing response, user email, or session ID'}), 400

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                INSERT INTO contact_messages (user_id, user_email, session_id, sender, message, timestamp, unread)
                VALUES (%s, %s, %s, %s, %s, %s,%s)
            ''', ('support', user_email, session_id, 'support', response, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 1))
            conn.commit()
        return jsonify({'success': True, 'user_email': user_email, 'session_id': session_id})
    except Exception as e:
        logger.error(f"Error in agent_respond: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error saving response: {str(e)}'}), 500

@app.route('/track_order')
def tracking():
    cart_data = get_cart_items()
    return render_template(
        'track_order.html',
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        user=session.get('user'),
        cart_item_count=cart_data['cart_item_count']
    )


from werkzeug.security import generate_password_hash

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        notification_preference = request.form.get('notification_preference', 'sms')
        if not form_type:
            return render_template('signup.html', error="Form type missing!")

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            if form_type == 'buyer':
                email = request.form['email']
                phone_number = request.form['phone_number']
                if not phone_number:
                    return render_template('signup.html', error="Phone number is required!")
                cursor.execute('SELECT phone_number FROM users WHERE phone_number = %s', (phone_number,))
                if cursor.fetchone():
                    return render_template('signup.html', error="Phone number already registered!")
                if email:
                    cursor.execute('SELECT email FROM users WHERE email = %s', (email,))
                    if cursor.fetchone():
                        return render_template('signup.html', error="Email already registered!")

                password = request.form['password']
                hashed_password = generate_password_hash(password)

                user_data = {
                    'first_name': request.form.get('first_name', ''),
                    'last_name': request.form.get('last_name', ''),
                    'email': email,
                    'phone_number': phone_number,
                    'password': hashed_password,
                    'address': request.form.get('address', ''),
                    'security_question': request.form.get('security_question', ''),
                    'security_answer': request.form.get('security_answer', ''),
                    'notification_preference': notification_preference,
                    'is_seller': False,
                    'discount_applied': False,
                    'discount_used': False,
                    'gender': '',
                    'delivery_address': '',
                    'billing_address': ''
                }
                cursor.execute('''
                    INSERT INTO users (email, first_name, last_name, phone_number, notification_preference, password, address,
                                    security_question, security_answer, is_seller, discount_applied, discount_used, gender,
                                    delivery_address, billing_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)
                ''', (
                    email, user_data['first_name'], user_data['last_name'], phone_number, notification_preference,
                    user_data['password'], user_data['address'], user_data['security_question'],
                    user_data['security_answer'], user_data['is_seller'], user_data['discount_applied'],
                    user_data['discount_used'], user_data['gender'], user_data['delivery_address'],
                    user_data['billing_address']
                ))
                conn.commit()

                user_data['password'] = '[PROTECTED]'
                session.clear()  # Clear all session data
                session['user'] = user_data
                logger.info(f"New buyer signed up: {email}")
                return redirect(url_for('verification', email=email, first_name=user_data['first_name']))

            elif form_type == 'seller':
                email = request.form['business_email']
                phone_number = request.form['business_phone']
                if not phone_number:
                    return render_template('signup.html', error="Business phone number is required!")
                cursor.execute('SELECT phone_number FROM users WHERE phone_number = %s', (phone_number,))
                if cursor.fetchone():
                    return render_template('signup.html', error="Phone number already registered!")
                if email:
                    cursor.execute('SELECT email FROM users WHERE email = %s', (email,))
                    if cursor.fetchone():
                        return render_template('signup.html', error="Email already registered!")

                password = request.form['business_password']
                hashed_password = generate_password_hash(password)

                user_data = {
                    'first_name': request.form.get('owner_name', ''),
                    'email': email,
                    'phone_number': phone_number,
                    'password': hashed_password,
                    'business_name': request.form.get('business_name', ''),
                    'business_address': request.form.get('business_address', ''),
                    'notification_preference': notification_preference,
                    'is_seller': True,
                    'discount_applied': False,
                    'discount_used': False,
                    'gender': '',
                    'delivery_address': '',
                    'billing_address': ''
                }
                cursor.execute('''
                    INSERT INTO users (email, first_name, phone_number, notification_preference, password, business_name,
                                    business_address, is_seller, discount_applied, discount_used, gender, delivery_address,
                                    billing_address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    email, user_data['first_name'], phone_number, notification_preference, user_data['password'],
                    user_data['business_name'], user_data['business_address'], user_data['is_seller'],
                    user_data['discount_applied'], user_data['discount_used'], user_data['gender'],
                    user_data['delivery_address'], user_data['billing_address']
                ))

                # Create seller_finances record
                cursor.execute('''
                    INSERT INTO seller_finances
                    (seller_email, balance, total_earnings, pending_withdrawals)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (seller_email) DO NOTHING
                ''', (email, 0, 0, 0))

                # Create initial verification record for new seller
                cursor.execute('''
                    INSERT INTO seller_verification (seller_email, verification_status)
                    VALUES (%s, 'pending_documents')
                    ON CONFLICT (seller_email) DO NOTHING
                ''', (email,))

                conn.commit()

                user_data['password'] = '[PROTECTED]'
                session.clear()  # Clear all session data
                session['user'] = user_data
                logger.info(f"New seller signed up: {email}, is_seller: {user_data['is_seller']}")
                return redirect(url_for('seller_verification'))
            else:
                return render_template('signup.html', error="Invalid form type!")
    return render_template('signup.html', error=None)




@app.route('/contact', methods=['GET', 'POST'])
def contact():
    user = session.get('user')
    user_email = user['email'] if user else 'anonymous_' + str(uuid.uuid4())
    user_id = user_email
    cart_data = get_cart_items()
    context = {
        'cart_items': cart_data['items'],
        'cart_total': cart_data['total'],
        'discount': cart_data['discount'],
        'user': user,
        'cart_item_count': cart_data['cart_item_count'],
        'contact_history': [],
        'conversations': [],
        'selected_session': ''
    }
    try:
        if 'contact_session_id' not in session:
            session['contact_session_id'] = str(uuid.uuid4())
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                cursor.execute('''
                    INSERT INTO user_sessions (user_email, session_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_email, session_id) DO NOTHING
                ''', (user_email, session['contact_session_id']))
                conn.commit()
        session_id = session.get('contact_session_id')

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('SELECT session_id FROM user_sessions WHERE user_email = %s', (user_email,))
            session_ids = [row['session_id'] for row in cursor.fetchall()]
            if not session_ids:
                session_ids = [session_id]

        if request.method == 'POST':
            message = request.form.get('message', '').strip()
            if not message:
                return render_template('contact.html', error="Message cannot be empty", **context)
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                cursor.execute('''
                    INSERT INTO contact_messages (user_id, user_email, session_id, sender, message, timestamp, unread)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (user_id, user_email, session_id, 'user', message, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 1))
                conn.commit()
            return redirect(url_for('contact', session_id=session_id, success="Message sent successfully"))

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            selected_session = request.args.get('session_id', session_id)
            cursor.execute('''
                SELECT sender, message, timestamp
                FROM contact_messages
                WHERE user_email = %s AND session_id = %s
                ORDER BY timestamp
            ''', (user_email, selected_session))
            context['contact_history'] = [
                {
                    'sender': row['sender'],
                    'text': row['message'],
                    'timestamp': datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
                } for row in cursor.fetchall()
            ]
            cursor.execute('''
                SELECT DISTINCT session_id, MAX(timestamp) as last_message, SUM(CASE WHEN unread = true THEN 1 ELSE 0 END) as unread_count
                FROM contact_messages
                WHERE user_email = %s AND session_id IN ({})
                GROUP BY session_id
                ORDER BY last_message DESC
            '''.format(','.join(['%s'] * len(session_ids))), [user_email] + session_ids)
            context['conversations'] = [
                {
                    'session_id': row['session_id'],
                    'last_message': datetime.strptime(row['last_message'], '%Y-%m-%d %H:%M:%S'),
                    'unread_count': row['unread_count'],
                    'user_id': user_email
                } for row in cursor.fetchall()
            ]
            context['selected_session'] = selected_session

        error = request.args.get('error')
        success = request.args.get('success')
        if error: context['error'] = error
        if success: context['success'] = success
        if user and user.get('is_support', False):
            return redirect(url_for('customer_service'))
        return render_template('contact.html', **context)
    except Exception as e:
        return render_template('contact.html', error=f"An error occurred: {str(e)}", **context)


@app.route('/admin_login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # SECURITY: Max 5 login attempts per minute
def admin_login():
    """Separate admin login route - only checks admin_users table"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        try:
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

                # Check admin_users table ONLY
                cursor.execute('SELECT * FROM admin_users WHERE email = %s', (email,))
                admin = cursor.fetchone()

                if admin and check_password_hash(admin['password'], password):
                    # Admin login successful
                    session['admin_user'] = dict(admin)
                    session['user'] = dict(admin)

                    # Update last login
                    cursor.execute('UPDATE admin_users SET last_login = %s WHERE email = %s',
                                   (datetime.now(), email))
                    conn.commit()

                    # Log admin activity
                    log_admin_activity(email, 'login', description='Admin logged in')

                    logger.info(f"✅ Admin login successful: {email}")
                    return redirect(url_for('admin_dashboard_page'))
                else:
                    logger.warning(f"❌ Failed admin login attempt: {email}")
                    return render_template('admin_login.html',
                                           error="Invalid admin credentials. Please try again.")

        except Exception as e:
            logger.error(f"Admin login error: {e}")
            return render_template('admin_login.html',
                                   error="An error occurred during login. Please try again.")

    return render_template('admin_login.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # SECURITY: Max 5 login attempts per minute (prevents brute force)
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']

        try:
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

                # FIRST - Check if it's an admin user
                cursor.execute('SELECT * FROM admin_users WHERE email = %s', (identifier,))
                admin = cursor.fetchone()

                if admin and check_password_hash(admin['password'], password):
                    # Admin login successful
                    session['admin_user'] = dict(admin)
                    session['user'] = dict(admin)

                    cursor.execute('UPDATE admin_users SET last_login = %s WHERE email = %s',
                                   (datetime.now(), identifier))
                    conn.commit()

                    log_admin_activity(identifier, 'login', description='Admin logged in')
                    logger.info(f"✅ Admin login successful: {identifier}")
                    return redirect(url_for('admin_dashboard_page'))

                # SECOND - Check regular users and support agents
                cursor.execute('SELECT * FROM users WHERE (email = %s OR phone_number = %s)',
                               (identifier, identifier))
                user = cursor.fetchone()

                if user:
                    logger.info(f"User found: {user['email']}, checking password...")

                    # Check if user is flagged/banned
                    flag = is_user_flagged(user['email'])
                    if flag:
                        if flag['flag_type'] == 'banned':
                            return render_template('login.html',
                                                   error=f"Your account has been banned. Reason: {flag['reason']}")
                        # For suspended sellers, allow login but they'll see "Under Review" message

                    # Check password - FIXED VERSION
                    password_valid = False

                    # Check if password is hashed (supports pbkdf2, scrypt, argon2, etc.)
                    if user['password'] and (
                            'pbkdf2:' in user['password'] or 'scrypt:' in user['password'] or 'argon2:' in user[
                        'password'] or '$' in user['password']):
                        # Any hashed password format
                        try:
                            password_valid = check_password_hash(user['password'], password)
                            logger.info(f"Hashed password check result: {password_valid}")
                        except Exception as hash_error:
                            logger.warning(f"Hash verification failed: {hash_error}")
                            password_valid = False
                    else:
                        # Plain text password (for support agent)
                        password_valid = (user['password'] == password)
                        logger.info(f"Plain text password check result: {password_valid}")

                        if password_valid:
                            # Update to hashed password
                            hashed_password = generate_password_hash(password)
                            cursor.execute('UPDATE users SET password = %s WHERE email = %s',
                                           (hashed_password, user['email']))
                            conn.commit()
                            logger.info(f"Updated password to hashed for user: {user['email']}")

                    if password_valid:
                        # Create clean user session data
                        user_data = dict(user)
                        if 'password' in user_data:
                            del user_data['password']

                        session['user'] = user_data

                        # *** SUPPORT AGENT CHECK: Redirect support agents to their dashboard ***
                        if user['is_support']:
                            session['support_user'] = user_data
                            logger.info(f"Support agent logged in: {user['email']}")
                            return redirect(url_for('agent_dashboard'))  # ✅ Changed from 'customer_service'

                        # *** REGULAR USER: RESTORE CART FROM DATABASE ***
                        session_cart = session.get('cart', {})
                        restored_cart = restore_cart_from_db(user['email'])

                        if restored_cart and session_cart:
                            # Merge carts - prioritize session cart for conflicts
                            for product_key, details in restored_cart.items():
                                if product_key not in session_cart:
                                    session_cart[product_key] = details
                            session['cart'] = session_cart
                        elif restored_cart and not session_cart:
                            # No session cart, restore from DB
                            session['cart'] = restored_cart
                        elif session_cart and not restored_cart:
                            # Keep session cart as-is
                            pass

                        session.modified = True
                        logger.info(f"Login successful for user: {user['email']}")

                        # Redirect based on user type
                        if user['is_seller']:
                            return redirect(url_for('seller_dashboard'))
                        else:
                            return redirect(url_for('index'))
                    else:
                        logger.warning(f"Password check failed for user: {user['email']}")
                        return render_template('login.html',
                                               error="Invalid email/phone or password. Please try again.")
                else:
                    logger.warning(f"No user found with identifier: {identifier}")
                    return render_template('login.html',
                                           error="Invalid email/phone or password. Please try again.")

        except Exception as e:
            logger.error(f"Login error: {e}")
            return render_template('login.html',
                                   error="An error occurred during login. Please try again.")

    return render_template('login.html')


@app.route('/agent_dashboard')
def agent_dashboard():
    """Agent dashboard with enhanced features"""
    if 'user' not in session or not session['user'].get('is_support'):
        return redirect(url_for('login'))

    # The template should be the HTML file you showed me
    return render_template('index_agent.html', user=session['user'])


@app.route('/debug_login', methods=['POST'])
def debug_login():
    identifier = request.form['identifier']
    password = request.form['password']

    with get_db() as conn:
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute(
            'SELECT email, phone_number, password, is_seller FROM users WHERE (email = %s OR phone_number = %s)',
            (identifier, identifier))
        user = cursor.fetchone()

        if not user:
            return f"❌ User not found with identifier: {identifier}"

        # Check password format
        stored_password = user['password']
        if stored_password.startswith('pbkdf2:'):
            # Hashed password
            password_check = check_password_hash(stored_password, password)
            return f"""
            ✅ User found: {user['email']}<br>
            📱 Phone: {user['phone_number']}<br>
            🔐 Password format: Hashed (pbkdf2)<br>
            🔍 Password check result: {password_check}<br>
            👤 Is seller: {user['is_seller']}<br>
            """
        else:
            # Plain text password
            password_check = (stored_password == password)
            return f"""
            ✅ User found: {user['email']}<br>
            📱 Phone: {user['phone_number']}<br>
            🔐 Password format: Plain text<br>
            🔍 Password check result: {password_check}<br>
            👤 Is seller: {user['is_seller']}<br>
            """

def is_user_flagged(email):
    """Check if a user is currently flagged/banned"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                SELECT flag_type, reason, expires_at FROM user_flags
                WHERE user_email = %s AND is_active = true
                AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY flag_date DESC
                LIMIT 1
            ''', (email,))
            flag = cursor.fetchone()
            return dict(flag) if flag else None
    except Exception as e:
        logger.error(f"Error checking if user flagged: {e}")
        return None


def log_admin_activity(admin_email, action_type, target_type=None, target_id=None, description=None):
    """Log admin activities"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                INSERT INTO admin_activity_log (admin_email, action_type, target_type, target_id, description, ip_address)
                VALUES (%s, %s, %s, %s, %s,%s)
            ''', (admin_email, action_type, target_type, target_id, description, request.remote_addr))
            conn.commit()
    except Exception as e:
        logger.error(f"Error logging admin activity: {e}")

@app.route('/logout')
def logout():
    """User logout route"""
    if 'user' in session and 'cart' in session:
        user_email = session['user']['email']
        cart_data = session.get('cart', {})
        if cart_data:
            save_cart_to_db(user_email, cart_data)
        logger.info(f"User logged out: {user_email}")
    session.clear()  # Clear all session data
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """User profile management"""
    if 'user' not in session:
        logger.info("Profile: User not logged in, redirecting to login")
        return redirect(url_for('login'))
    user = session['user']
    error = None
    success = None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (user['email'],))
        db_user = cursor.fetchone()
        if not db_user:
            logger.warning(f"Profile: User email {user['email']} not found in database")
            return redirect(url_for('login'))
        if request.method == 'POST':
            if request.form.get('action') == 'continue_shopping':
                logger.info(f"Profile POST: Continue to shopping for user {user['email']}")
                return redirect(url_for('index'))
            try:
                if 'profile_picture' not in request.files:
                    logger.warning("Profile POST: No file part in request")
                    error = "No file selected. Please choose an image."
                else:
                    file = request.files['profile_picture']
                    if file.filename == '':
                        logger.warning("Profile POST: No file selected")
                        error = "No file selected. Please choose an image."
                    elif not allowed_file(file.filename):
                        logger.warning(f"Profile POST: Invalid file extension for {file.filename}")
                        error = "Invalid file type. Please upload a PNG, JPG, JPEG, or WEBP image."
                    else:
                        ext = file.filename.rsplit('.', 1)[1].lower()
                        unique_filename = f"{uuid.uuid4().hex}.{ext}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        file.save(file_path)
                        db_path = f"uploads/{unique_filename}"
                        cursor.execute('UPDATE users SET profile_picture = %s WHERE email = %s', (db_path, user['email']))
                        conn.commit()
                        cursor.execute('SELECT * FROM users WHERE email = %s', (user['email'],))
                        session['user'] = dict(cursor.fetchone())
                        session.modified = True
                        logger.info(f"Profile POST: Updated profile picture to {db_path} for user {user['email']}")
                        success = "Profile picture uploaded successfully!"
            except Exception as e:
                logger.error(f"Profile POST: Unexpected error: {str(e)}")
                error = "An unexpected error occurred. Please try again."
    logger.info(f"Profile GET: Rendering with user.profile_picture = {session['user'].get('profile_picture', 'None')}")
    cart_data = get_cart_items()
    return render_template(
        'upload_profile.html',
        user=session['user'],
        error=error,
        success=success,
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )

@app.route('/personal_info', methods=['GET', 'POST'])
def personal_info():
    """User personal information management"""
    if 'user' not in session:
        logger.info("Personal Info: User not logged in, redirecting to login")
        return redirect(url_for('login'))
    user = session['user']
    error = None
    success = None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE phone_number = %s', (user['phone_number'],))
        db_user = cursor.fetchone()
        if not db_user:
            logger.warning(f"Personal Info: User phone_number {user['phone_number']} not found in database")
            return redirect(url_for('login'))
        if request.method == 'POST':
            try:
                first_name = request.form.get('first_name', '').strip()
                last_name = request.form.get('last_name', '').strip()
                new_email = request.form.get('email', '').strip()
                new_phone = request.form.get('phone_number', '').strip()
                gender = request.form.get('gender', '').strip()
                address = request.form.get('address', '').strip()
                whatsapp_number = request.form.get('whatsapp_number', '').strip()
                if not all([first_name, last_name, new_email, new_phone, gender, address, whatsapp_number]):
                    error = "All fields are required."
                    logger.warning(f"Personal Info POST: Missing required fields for {user['phone_number']}")
                elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', new_email):
                    error = "Invalid email format."
                    logger.warning(f"Personal Info POST: Invalid email format {new_email} for {user['phone_number']}")
                elif not re.match(r'^[+\d\s-]{7,15}$', new_phone):
                    error = "Phone number must be 7-15 digits."
                    logger.warning(f"Personal Info POST: Invalid phone number {new_phone} for {user['phone_number']}")
                elif not re.match(r'^[+\d\s-]{7,20}$', whatsapp_number):
                    error = "WhatsApp number must be 7-20 characters (including country code)."
                    logger.warning(f"Personal Info POST: Invalid WhatsApp number {whatsapp_number} for {user['phone_number']}")
                elif gender not in ['Male', 'Female', 'Other']:
                    error = "Invalid gender selection."
                    logger.warning(f"Personal Info POST: Invalid gender {gender} for {user['phone_number']}")
                else:
                    cursor.execute('SELECT email FROM users WHERE email = %s AND phone_number != ?',
                                   (new_email, user['phone_number']))
                    if cursor.fetchone():
                        error = "Email already in use."
                        logger.warning(f"Personal Info POST: Email {new_email} already in use for {user['phone_number']}")
                    elif cursor.execute('SELECT phone_number FROM users WHERE phone_number = %s AND phone_number != ?',
                                       (new_phone, user['phone_number'])).fetchone():
                        error = "Phone number already in use."
                        logger.warning(f"Personal Info POST: Phone number {new_phone} already in use for {user['phone_number']}")
                    elif cursor.execute('SELECT whatsapp_number FROM users WHERE whatsapp_number = %s AND phone_number != ?',
                                       (whatsapp_number, user['phone_number'])).fetchone():
                        error = "WhatsApp number already in use."
                        logger.warning(f"Personal Info POST: WhatsApp number {whatsapp_number} already in use for {user['phone_number']}")
                    else:
                        cursor.execute('''
                            UPDATE users SET first_name = %s, last_name = %s, email = %s, phone_number = %s, 
                                            gender = %s, address = %s, whatsapp_number = %s
                            WHERE phone_number = %s
                        ''', (first_name, last_name, new_email, new_phone, gender, address, whatsapp_number, user['phone_number']))
                        conn.commit()
                        cursor.execute('SELECT * FROM users WHERE phone_number = %s', (new_phone,))
                        updated_user = cursor.fetchone()
                        if not updated_user:
                            error = "Failed to update details. Please try again."
                            logger.error(f"Personal Info POST: Failed to verify update for phone_number {new_phone}")
                        else:
                            session['user'] = dict(updated_user)
                            session.modified = True
                            success = "Details saved successfully."
                            logger.info(f"Personal Info POST: Updated details for phone_number {new_phone}")
                if error:
                    cart_data = get_cart_items()
                    return render_template(
                        'personal_info.html',
                        user=user,
                        error=error,
                        success=success,
                        cart_total=cart_data['total'],
                        discount=cart_data['discount'],
                        cart_item_count=cart_data['cart_item_count']
                    )
            except Exception as e:
                logger.error(f"Personal Info POST: Unexpected error: {str(e)}")
                error = "An unexpected error occurred. Please try again."
        cart_data = get_cart_items()
        return render_template(
            'personal_info.html',
            user=session['user'],
            error=error,
            success=success,
            cart_total=cart_data['total'],
            discount=cart_data['discount'],
            cart_item_count=cart_data['cart_item_count']
        )

@app.route('/password_reset', methods=['GET', 'POST'])
def password_reset():
    """Password reset request"""
    if request.method == 'POST':
        reset_method = request.form['reset_method']
        identifier = request.form['identifier']
        try:
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                user = None
                if reset_method == 'email':
                    cursor.execute('SELECT * FROM users WHERE email = %s', (identifier,))
                    user = cursor.fetchone()
                elif reset_method == 'phone':
                    cursor.execute('SELECT * FROM users WHERE phone_number = %s', (identifier,))
                    user = cursor.fetchone()
                elif reset_method == 'whatsapp':
                    cursor.execute('SELECT * FROM users WHERE whatsapp_number = %s', (identifier,))
                    user = cursor.fetchone()
                if user:
                    reset_code = generate_reset_code()
                    session['reset_code'] = reset_code
                    session['reset_identifier'] = identifier
                    session['reset_method'] = reset_method
                    send_notification(identifier, f"Your reset code is {reset_code}. Keep it safe!", reset_method)
                    return redirect(url_for('verify_reset'))
                else:
                    logger.warning(f"Password reset: No user found for {reset_method} = {identifier}")
                    return render_template('password_reset.html', error="No user found with that information.")
        except Exception as e:
            logger.error(f"Password reset: Error processing request: {str(e)}")
            return render_template('password_reset.html', error="An error occurred. Please try again.")
    cart_data = get_cart_items()
    return render_template(
        'password_reset.html',
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )


@app.route('/start_chat/<seller_email>')
def start_chat(seller_email):
    """Start a chat with a seller"""
    if 'user' not in session:
        return redirect(url_for('login'))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT email, first_name, last_name, business_name FROM users WHERE email = %s AND is_seller = %s',
            (seller_email, True))
        seller = cursor.fetchone()

        if not seller:
            return render_template('404.html', error="Seller not found"), 404

    cart_data = get_cart_items()
    return render_template('buyer_seller_chat.html',
                           seller=dict(seller),
                           buyer=session['user'],
                           cart_items=cart_data['items'],
                           cart_total=cart_data['total'],
                           discount=cart_data['discount'],
                           cart_item_count=cart_data['cart_item_count'])


@app.route('/seller/update_description', methods=['POST'])
def update_seller_description():
    if 'user' not in session or not session['user'].get('is_seller'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        description = data.get('description', '')

        seller_email = session['user']['email']

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if business_description column exists, if not add it
            try:
                cursor.execute('ALTER TABLE users ADD COLUMN business_description TEXT')
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Update description
            cursor.execute('''
                UPDATE users SET business_description = %s WHERE email = %s
            ''', (description, seller_email))

            conn.commit()

            # Log for debugging
            logger.info(f"Updated description for {seller_email}: {description}")

        return jsonify({'success': True, 'message': 'Description updated successfully'})

    except Exception as e:
        logger.error(f"Error updating description: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/seller/upload_store_logo', methods=['POST'])
def upload_store_logo():
    """Upload and update seller's store logo"""
    if 'user' not in session or not session['user'].get('is_seller'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        if 'store_logo' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'}), 400

        file = request.files['store_logo']

        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400

        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'message': 'Invalid file type. Please upload PNG, JPG, or GIF'}), 400

        # Generate unique filename
        seller_email = session['user']['email']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_email = seller_email.replace('@', '_').replace('.', '_')
        filename = f"store_logo_{safe_email}_{timestamp}.{file_ext}"

        # Save file to uploads directory
        upload_folder = os.path.join(app.static_folder, 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)

        # Update database
        logo_path = f'uploads/{filename}'

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            cursor.execute('''
                UPDATE users SET store_logo = %s WHERE email = %s
            ''', (logo_path, seller_email))

            conn.commit()

            # Update session
            session['user']['store_logo'] = logo_path
            session.modified = True

        logger.info(f"Store logo uploaded for {seller_email}: {logo_path}")

        return jsonify({
            'success': True,
            'message': 'Store logo updated successfully',
            'logo_path': logo_path
        })

    except Exception as e:
        logger.error(f"Error uploading store logo: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': 'Error uploading logo. Please try again.'}), 500


@app.route('/get_seller_info/<email>')
def get_seller_info(email):
    try:
                with get_db() as conn:
                    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                    cursor.execute('''
                        SELECT email, first_name, business_name, profile_picture
                        FROM users
                        WHERE email = %s AND is_seller = true
                    ''', (email,))
                    seller = cursor.fetchone()
                    if not seller:
                        return jsonify({'success': False, 'message': 'Seller not found'}), 404
                    return jsonify({
                        'success': True,
                        'seller': {
                            'email': seller['email'],
                            'first_name': seller['first_name'],
                            'business_name': seller['business_name'],
                            'profile_picture': seller['profile_picture']
                        }
                    })
    except Exception as e:
        logger.error(f"Error getting seller info: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500



    @app.route('/buyer/messages', endpoint='buyer_messages')
    def buyer_messages():
            if 'user' not in session:
                return redirect(url_for('login'))

            buyer_email = session['user']['email']

            try:
                with get_db() as conn:
                    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

                    # Get all conversations for this buyer
                    cursor.execute('''
                        SELECT c.id, c.seller_email, c.last_message_at,
                               u.first_name, u.last_name, u.business_name,
                               (SELECT COUNT(*) FROM messages m 
                                WHERE m.conversation_id = c.id 
                                AND m.receiver_email = %s 
                                AND m.read_status = false) as unread_count,
                               (SELECT message FROM messages m2 
                                WHERE m2.conversation_id = c.id 
                                ORDER BY m2.timestamp DESC LIMIT 1) as last_message
                        FROM conversations c
                        JOIN users u ON c.seller_email = u.email
                        WHERE c.buyer_email = %s
                        ORDER BY c.last_message_at DESC
                    ''', (buyer_email, buyer_email))

                    conversations = []
                    for row in cursor.fetchall():
                        conversations.append({
                            'id': row['id'],
                            'seller_email': row['seller_email'],
                            'seller_name': row['business_name'] or f"{row['first_name']} {row['last_name']}",
                            'last_message': row['last_message'],
                            'last_message_at': row['last_message_at'],
                            'unread_count': row['unread_count'] or 0
                        })

                cart_data = get_cart_items()
                return render_template(
                    'buyer_messages.html',
                    conversations=conversations,
                    user=session['user'],
                    cart_items=cart_data['items'],
                    cart_total=cart_data['total'],
                    discount=cart_data['discount'],
                    cart_item_count=cart_data['cart_item_count']
                )
            except Exception as e:
                logger.error(f"Error in buyer_messages: {e}")
                return redirect(url_for('index'))


@app.route('/api/unread_messages_count')
def unread_messages_count():
    """Get total unread message count for current user"""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    current_user_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM messages m
                WHERE m.receiver_email = %s AND m.read_status = false
            ''', (current_user_email,))

            count = cursor.fetchone()['count']
            return jsonify({'success': True, 'count': count})

    except Exception as e:
        logger.error(f"Error getting unread messages count: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# Add these missing routes to your app.py file

@app.route('/send_message', methods=['POST'])
def send_message():
    """Send a message between buyer and seller"""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    try:
        data = request.get_json()
        receiver_email = data.get('receiver_email')
        message = data.get('message', '').strip()

        if not receiver_email:
            return jsonify({'success': False, 'message': 'Missing receiver'}), 400

        current_user_email = session['user']['email']

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Determine who is buyer and who is seller
            cursor.execute('SELECT is_seller FROM users WHERE email = %s', (current_user_email,))
            sender_user = cursor.fetchone()
            cursor.execute('SELECT is_seller FROM users WHERE email = %s', (receiver_email,))
            receiver_user = cursor.fetchone()

            if not sender_user or not receiver_user:
                return jsonify({'success': False, 'message': 'User not found'}), 404

            # Set buyer/seller emails correctly
            if sender_user['is_seller']:
                seller_email = current_user_email
                buyer_email = receiver_email
            else:
                buyer_email = current_user_email
                seller_email = receiver_email

            # Get or create conversation
            cursor.execute('''
                SELECT id FROM conversations 
                WHERE (buyer_email = %s AND seller_email = %s) 
                OR (buyer_email = %s AND seller_email = %s)
            ''', (buyer_email, seller_email, seller_email, buyer_email))

            conversation = cursor.fetchone()

            if not conversation:
                # Create new conversation
                cursor.execute('''
                    INSERT INTO conversations (buyer_email, seller_email, created_at, last_message_at)
                    VALUES (%s, %s, %s,%s)
                    RETURNING id
                ''', (buyer_email, seller_email,
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conversation_id = cursor.fetchone()['id']
            else:
                conversation_id = conversation['id']
                # Update last message time only if sending a message
                if message:
                    cursor.execute('''
                        UPDATE conversations
                        SET last_message_at = %s
                        WHERE id = %s
                    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), conversation_id))

            # Insert message only if not empty
            if message:
                cursor.execute('''
                    INSERT INTO messages (conversation_id, sender_email, receiver_email, message, timestamp, read_status)
                    VALUES (%s, %s, %s, %s, %s,%s)
                ''', (conversation_id, current_user_email, receiver_email, message,
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S'), False))

            conn.commit()

            return jsonify({
                'success': True,
                'message': 'Message sent successfully' if message else 'Conversation created',
                'conversation_id': conversation_id
            })

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return jsonify({'success': False, 'message': 'Error sending message'}), 500


@app.route('/get_messages/<other_email>')
def get_messages_fixed(other_email):
    """Get messages between current user and another user - FIXED VERSION"""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    current_user_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Find conversation between users
            cursor.execute('''
                SELECT id FROM conversations 
                WHERE (buyer_email = %s AND seller_email = %s) 
                OR (buyer_email = %s AND seller_email = %s)
            ''', (current_user_email, other_email, other_email, current_user_email))

            conversation = cursor.fetchone()

            if not conversation:
                return jsonify({'success': True, 'messages': []})

            # Get all messages for this conversation
            cursor.execute('''
                SELECT sender_email, receiver_email, message, timestamp, read_status
                FROM messages
                WHERE conversation_id = %s
                ORDER BY timestamp ASC
            ''', (conversation['id'],))

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'sender_email': row['sender_email'],
                    'receiver_email': row['receiver_email'],
                    'message': row['message'],
                    'timestamp': row['timestamp'],
                    'read_status': row['read_status']
                })

            # Mark messages as read for current user
            cursor.execute('''
                UPDATE messages 
                SET read_status = true 
                WHERE conversation_id = %s AND receiver_email = %s AND read_status = false
            ''', (conversation['id'], current_user_email))
            conn.commit()

            return jsonify({'success': True, 'messages': messages})

    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/get_conversations')
def get_conversations_fixed():
    """Get all conversations for current user - FIXED VERSION"""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    current_user_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get user's seller status
            cursor.execute('SELECT is_seller FROM users WHERE email = %s', (current_user_email,))
            user_info = cursor.fetchone()
            is_seller = user_info['is_seller'] if user_info else False

            if is_seller:
                # If current user is seller, get conversations where they are the seller
                cursor.execute('''
                    SELECT DISTINCT
                        c.buyer_email as other_email,
                        c.last_message_at,
                        u.first_name,
                        u.last_name,
                        u.business_name,
                        (SELECT COUNT(*) FROM messages m 
                         WHERE m.conversation_id = c.id 
                         AND m.receiver_email = %s 
                         AND m.read_status = false) as unread_count
                    FROM conversations c
                    JOIN users u ON c.buyer_email = u.email
                    WHERE c.seller_email = %s
                    ORDER BY c.last_message_at DESC
                ''', (current_user_email, current_user_email))
            else:
                # If current user is buyer, get conversations where they are the buyer
                cursor.execute('''
                    SELECT DISTINCT
                        c.seller_email as other_email,
                        c.last_message_at,
                        u.first_name,
                        u.last_name,
                        u.business_name,
                        (SELECT COUNT(*) FROM messages m 
                         WHERE m.conversation_id = c.id 
                         AND m.receiver_email = %s 
                         AND m.read_status = false) as unread_count
                    FROM conversations c
                    JOIN users u ON c.seller_email = u.email
                    WHERE c.buyer_email = %s
                    ORDER BY c.last_message_at DESC
                ''', (current_user_email, current_user_email))

            conversations = []
            for row in cursor.fetchall():
                seller_name = row['business_name'] or f"{row['first_name']} {row['last_name']}" or row['other_email']
                conversations.append({
                    'seller_email': row['other_email'],  # For compatibility
                    'seller_name': seller_name,
                    'unread_count': row['unread_count'] or 0,
                    'last_message_at': row['last_message_at']
                })

            return jsonify({'success': True, 'conversations': conversations})

    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/conversations')
def get_all_conversations():
    """Get all conversations for current user"""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    current_user_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all conversations where user is either buyer or seller
            cursor.execute('''
                SELECT c.id, c.buyer_email, c.seller_email, c.last_message_at,
                       u1.first_name as buyer_first_name, u1.last_name as buyer_last_name,
                       u1.business_name as buyer_business_name,
                       u2.first_name as seller_first_name, u2.last_name as seller_last_name,
                       u2.business_name as seller_business_name,
                       (SELECT COUNT(*) FROM messages m
                        WHERE m.conversation_id = c.id
                        AND m.receiver_email = %s
                        AND m.read_status = false) as unread_count,
                       (SELECT message FROM messages m2
                        WHERE m2.conversation_id = c.id
                        ORDER BY m2.timestamp DESC LIMIT 1) as last_message
                FROM conversations c
                LEFT JOIN users u1 ON c.buyer_email = u1.email
                LEFT JOIN users u2 ON c.seller_email = u2.email
                WHERE c.buyer_email = %s OR c.seller_email = %s
                ORDER BY c.last_message_at DESC
            ''', (current_user_email, current_user_email, current_user_email))

            conversations = []
            for row in cursor.fetchall():
                # Determine the other person in the conversation
                if row['buyer_email'] == current_user_email:
                    other_email = row['seller_email']
                    other_name = row['seller_business_name'] or f"{row['seller_first_name'] or ''} {row['seller_last_name'] or ''}".strip() or other_email
                else:
                    other_email = row['buyer_email']
                    other_name = row['buyer_business_name'] or f"{row['buyer_first_name'] or ''} {row['buyer_last_name'] or ''}".strip() or other_email

                conversations.append({
                    'id': row['id'],
                    'other_email': other_email,
                    'other_name': other_name,
                    'last_message': row['last_message'],
                    'last_message_at': row['last_message_at'],
                    'unread_count': row['unread_count'] or 0
                })

            return jsonify({
                'success': True,
                'conversations': conversations
            })

    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/mark_messages_read', methods=['POST'])
def mark_messages_read():
    """Mark all messages in a conversation as read"""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    try:
        data = request.get_json()
        conversation_id = data.get('conversation_id')

        if not conversation_id:
            return jsonify({'success': False, 'message': 'Missing conversation_id'}), 400

        current_user_email = session['user']['email']

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Mark all messages in this conversation as read for current user
            cursor.execute('''
                UPDATE messages
                SET read_status = true
                WHERE conversation_id = %s AND receiver_email = %s
            ''', (conversation_id, current_user_email))

            conn.commit()

            return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error marking messages as read: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# Socket.IO event handlers for real-time chat
@socketio.on('join_conversation')
def on_join_conversation(data):
    """Join a conversation room for real-time updates"""
    # Support both old and new parameter names
    user1_email = data.get('user1_email') or data.get('buyer_email')
    user2_email = data.get('user2_email') or data.get('seller_email')

    if user1_email and user2_email:
        room = f"chat_{min(user1_email, user2_email)}_{max(user1_email, user2_email)}"
        join_room(room)
        logger.info(f"User joined chat room: {room}")

@socketio.on('leave_conversation')
def on_leave_conversation(data=None):
    """Leave a conversation room"""
    if data:
        user1_email = data.get('user1_email') or data.get('buyer_email')
        user2_email = data.get('user2_email') or data.get('seller_email')

        if user1_email and user2_email:
            room = f"chat_{min(user1_email, user2_email)}_{max(user1_email, user2_email)}"
            leave_room(room)
            logger.info(f"User left chat room: {room}")

@socketio.on('send_message')
def handle_send_message(data):
    """Handle real-time message sending"""
    sender_email = data.get('sender_email')
    receiver_email = data.get('receiver_email')
    if sender_email and receiver_email:
        room = f"chat_{min(sender_email, receiver_email)}_{max(sender_email, receiver_email)}"
        emit('receive_message', data, room=room)
        logger.info(f"Real-time message sent in room: {room}")

@socketio.on('typing')
def handle_typing(data):
    """Handle typing indicators"""
    sender_email = data.get('sender_email')
    receiver_email = data.get('receiver_email')
    if sender_email and receiver_email:
        room = f"chat_{min(sender_email, receiver_email)}_{max(sender_email, receiver_email)}"
        emit('user_typing', data, room=room, include_self=False)


# Fix for the indentation error around line 2672
# Replace the problematic buyer_messages function with this corrected version:

@app.route('/buyer/messages')
def buyer_messages():
    """Buyer messages page"""
    if 'user' not in session:
        return redirect(url_for('login'))

    buyer_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all conversations for this buyer
            cursor.execute('''
                SELECT c.id, c.seller_email, c.last_message_at,
                       u.first_name, u.last_name, u.business_name,
                       (SELECT COUNT(*) FROM messages m 
                        WHERE m.conversation_id = c.id 
                        AND m.receiver_email = %s 
                        AND m.read_status = false) as unread_count,
                       (SELECT message FROM messages m2 
                        WHERE m2.conversation_id = c.id 
                        ORDER BY m2.timestamp DESC LIMIT 1) as last_message
                FROM conversations c
                JOIN users u ON c.seller_email = u.email
                WHERE c.buyer_email = %s
                ORDER BY c.last_message_at DESC
            ''', (buyer_email, buyer_email))

            conversations = []
            for row in cursor.fetchall():
                conversations.append({
                    'id': row['id'],
                    'seller_email': row['seller_email'],
                    'seller_name': row['business_name'] or f"{row['first_name']} {row['last_name']}",
                    'last_message': row['last_message'],
                    'last_message_at': row['last_message_at'],
                    'unread_count': row['unread_count'] or 0
                })

        cart_data = get_cart_items()
        return render_template(
            'buyer_messages.html',
            conversations=conversations,
            user=session['user'],
            cart_items=cart_data['items'],
            cart_total=cart_data['total'],
            discount=cart_data['discount'],
            cart_item_count=cart_data['cart_item_count']
        )
    except Exception as e:
        logger.error(f"Error in buyer_messages: {e}")
        return redirect(url_for('index'))


# The issue was that the function definition was improperly nested.
# Make sure this function is at the proper indentation level (no extra spaces before @app.route)


@app.route('/seller/messages')
def seller_messages():
    """Seller messages page"""
    if 'user' not in session or not session['user'].get('is_seller'):
        return redirect(url_for('login'))

    seller_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all conversations for this seller
            cursor.execute('''
                SELECT c.id, c.buyer_email, c.last_message_at,
                       u.first_name, u.last_name,
                       (SELECT COUNT(*) FROM messages m 
                        WHERE m.conversation_id = c.id 
                        AND m.receiver_email = %s 
                        AND m.read_status = false) as unread_count,
                       (SELECT message FROM messages m2 
                        WHERE m2.conversation_id = c.id 
                        ORDER BY m2.timestamp DESC LIMIT 1) as last_message
                FROM conversations c
                JOIN users u ON c.buyer_email = u.email
                WHERE c.seller_email = %s
                ORDER BY c.last_message_at DESC
            ''', (seller_email, seller_email))

            conversations = []
            for row in cursor.fetchall():
                conversations.append({
                    'id': row['id'],
                    'buyer_email': row['buyer_email'],
                    'buyer_name': f"{row['first_name']} {row['last_name']}",
                    'last_message': row['last_message'],
                    'last_message_at': row['last_message_at'],
                    'unread_count': row['unread_count'] or 0
                })

        cart_data = get_cart_items()
        return render_template(
            'seller_messages.html',
            conversations=conversations,
            user=session['user'],
            cart_items=cart_data['items'],
            cart_total=cart_data['total'],
            discount=cart_data['discount'],
            cart_item_count=cart_data['cart_item_count']
        )

    except Exception as e:
        logger.error(f"Error in seller_messages: {e}")
        return redirect(url_for('seller_dashboard'))


# Add navigation links to your templates
@app.context_processor
def inject_messaging_links():
    """Add messaging navigation links"""
    messaging_links = {}
    if 'user' in session:
        if session['user'].get('is_seller'):
            messaging_links['seller_messages'] = url_for('seller_messages')
        else:
            messaging_links['buyer_messages'] = url_for('buyer_messages')
    return messaging_links

@app.route('/track_store_view', methods=['POST'])
def track_store_view():
    """Track store page views (optional analytics)"""
    try:
        data = request.get_json()
        # You can log this data or save to database
        logger.info(f"Store view tracked: {data}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error tracking store view: {e}")
        return jsonify({'success': False}), 500

@app.route('/verify_reset', methods=['GET', 'POST'])
def verify_reset():
    """Verify password reset code"""
    if request.method == 'POST':
        code = request.form['code']
        if 'reset_code' in session and code == session['reset_code']:
            session.pop('reset_code', None)
            session.pop('reset_identifier', None)
            session.pop('reset_method', None)
            return redirect(url_for('login'))
        else:
            logger.warning("Verify reset: Invalid reset code entered")
            return render_template('verify_reset.html', error="Invalid reset code. Please try again.")
    cart_data = get_cart_items()
    return render_template(
        'verify_reset.html',
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )


# ========================================
# COMPLETE ADMIN ROUTES FOR ZOZI MARKETPLACE
# ========================================

@app.route('/admin_dashboard')
@admin_required()
def admin_dashboard_page():
    """Main admin dashboard page"""
    if not is_admin():
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html', admin=session['admin_user'])


# ========================================
# DASHBOARD & ANALYTICS ENDPOINTS
# ========================================

@app.route('/admin/api/dashboard_stats')
@admin_required()
def dashboard_stats():
    """Real-time dashboard statistics"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Total users
            cursor.execute('SELECT COUNT(*) as total FROM users')
            total_users_result = cursor.fetchone()
            total_users = total_users_result['total'] if total_users_result else 0

            # Total sellers
            cursor.execute('SELECT COUNT(*) as total FROM users WHERE is_seller = true')
            total_sellers_result = cursor.fetchone()
            total_sellers = total_sellers_result['total'] if total_sellers_result else 0

            # Total products
            cursor.execute('SELECT COUNT(*) as total FROM products')
            total_products_result = cursor.fetchone()
            total_products = total_products_result['total'] if total_products_result else 0

            # Total orders
            cursor.execute('SELECT COUNT(*) as total FROM orders')
            total_orders_result = cursor.fetchone()
            total_orders = total_orders_result['total'] if total_orders_result else 0

            # Total revenue
            cursor.execute(
                "SELECT COALESCE(SUM(total), 0) as revenue FROM orders WHERE status NOT IN ('cancelled', 'refunded')")
            total_revenue_result = cursor.fetchone()
            total_revenue = float(total_revenue_result['revenue']) if total_revenue_result and total_revenue_result[
                'revenue'] else 0.0

            # Platform fees (5% of revenue)
            platform_fees = total_revenue * 0.05

            # Growth calculations with safe date handling
            try:
                if DATABASE_TYPE == 'postgresql':
                    cursor.execute("SELECT COUNT(*) as recent_users FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'")
                else:
                    cursor.execute('SELECT COUNT(*) as recent_users FROM users WHERE created_at >= date("now", "-30 days")')
                recent_users_result = cursor.fetchone()
                recent_users_count = recent_users_result['recent_users'] if recent_users_result else 0
            except:
                recent_users_count = 0

            try:
                if DATABASE_TYPE == 'postgresql':
                    cursor.execute(
                        "SELECT COUNT(*) as recent_sellers FROM users WHERE is_seller = true AND created_at >= CURRENT_DATE - INTERVAL '30 days'")
                else:
                    cursor.execute(
                        'SELECT COUNT(*) as recent_sellers FROM users WHERE is_seller = true AND created_at >= date("now", "-30 days")')
                recent_sellers_result = cursor.fetchone()
                recent_sellers_count = recent_sellers_result['recent_sellers'] if recent_sellers_result else 0
            except:
                recent_sellers_count = 0

            try:
                if DATABASE_TYPE == 'postgresql':
                    cursor.execute(
                        "SELECT COUNT(*) as recent_products FROM products WHERE posted_date >= CURRENT_DATE - INTERVAL '30 days'")
                else:
                    cursor.execute(
                        'SELECT COUNT(*) as recent_products FROM products WHERE posted_date >= date("now", "-30 days")')
                recent_products_result = cursor.fetchone()
                recent_products_count = recent_products_result['recent_products'] if recent_products_result else 0
            except:
                recent_products_count = 0

            try:
                if DATABASE_TYPE == 'postgresql':
                    cursor.execute(
                        "SELECT COUNT(*) as recent_orders FROM orders WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'")
                else:
                    cursor.execute(
                        'SELECT COUNT(*) as recent_orders FROM orders WHERE order_date >= date("now", "-30 days")')
                recent_orders_result = cursor.fetchone()
                recent_orders_count = recent_orders_result['recent_orders'] if recent_orders_result else 0
            except:
                recent_orders_count = 0

            # Calculate growth percentages
            user_growth = f"+{min(100, recent_users_count * 5)}%" if recent_users_count > 0 else "+0%"
            seller_growth = f"+{min(100, recent_sellers_count * 10)}%" if recent_sellers_count > 0 else "+0%"
            product_growth = f"+{min(100, recent_products_count * 3)}%" if recent_products_count > 0 else "+0%"
            order_growth = f"+{min(100, recent_orders_count * 15)}%" if recent_orders_count > 0 else "+0%"
            revenue_growth = f"+{min(100, int(total_revenue / 1000))}%" if total_revenue > 0 else "+0%"

            return jsonify({
                'success': True,
                'totalUsers': total_users,
                'totalSellers': total_sellers,
                'totalProducts': total_products,
                'totalOrders': total_orders,
                'totalRevenue': f"J${total_revenue:,.2f}",
                'platformFees': f"J${platform_fees:,.2f}",
                'userGrowth': user_growth,
                'sellerGrowth': seller_growth,
                'productGrowth': product_growth,
                'orderGrowth': order_growth,
                'revenueGrowth': revenue_growth
            })
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        return jsonify({
            'success': True,
            'totalUsers': 0,
            'totalSellers': 0,
            'totalProducts': 0,
            'totalOrders': 0,
            'totalRevenue': 'J$0.00',
            'platformFees': 'J$0.00',
            'userGrowth': '+0%',
            'sellerGrowth': '+0%',
            'productGrowth': '+0%',
            'orderGrowth': '+0%',
            'revenueGrowth': '+0%'
        })


@app.route('/admin/api/analytics')
@admin_required()
def admin_api_analytics():
    """General analytics data for charts"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Category sales data
            cursor.execute('''
                SELECT 
                    COALESCE(p.category, 'Uncategorized') as category, 
                    COUNT(p.product_key) as products_count,
                    COALESCE(SUM(p.sold), 0) as total_sold,
                    COALESCE(SUM(p.sold * p.price), 0) as revenue
                FROM products p
                WHERE p.category IS NOT NULL AND p.category != ''
                GROUP BY p.category
                ORDER BY products_count DESC
            ''')
            category_data = cursor.fetchall()

            # Daily sales (last 30 days)
            cursor.execute('''
                SELECT DATE(order_date) as date,
                       COUNT(*) as orders,
                       COALESCE(SUM(total), 0) as revenue
                FROM orders o
                WHERE order_date >= date('now', '-30 days')
                AND status != 'cancelled'
                GROUP BY date
                ORDER BY date
            ''')
            daily_sales = cursor.fetchall()

            # Top products
            cursor.execute('''
                SELECT p.name, p.seller_email, p.category, p.price,
                       u.first_name as seller_first_name,
                       u.last_name as seller_last_name,
                       u.business_name as seller_business_name,
                       COALESCE(p.sold, 0) as total_sold,
                       COALESCE(p.sold * p.price, 0) as revenue,
                       COALESCE(p.clicks, 0) as clicks,
                       COALESCE(p.likes, 0) as likes
                FROM products p
                LEFT JOIN users u ON p.seller_email = u.email
                ORDER BY p.sold DESC, p.clicks DESC, p.likes DESC
                LIMIT 10
            ''')
            top_products = cursor.fetchall()

            return jsonify({
                'success': True,
                'category_data': [dict(row) for row in category_data],
                'daily_sales': [dict(row) for row in daily_sales],
                'top_products': [dict(row) for row in top_products]
            })
    except Exception as e:
        logger.error(f"Error getting analytics data: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/parish_analytics')
@admin_required()
def admin_api_parish_analytics():
    """Parish-based analytics for Jamaica"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Buyers by parish
            cursor.execute('''
                SELECT COALESCE(parish, 'Unknown') as parish, COUNT(*) as buyer_count
                FROM users 
                WHERE is_seller = 0 
                GROUP BY COALESCE(parish, 'Unknown')
                HAVING buyer_count > 0
                ORDER BY buyer_count DESC
            ''')
            buyers_by_parish = cursor.fetchall()

            # Sellers by parish
            cursor.execute('''
                SELECT COALESCE(business_address, parish, 'Unknown') as parish, COUNT(*) as seller_count
                FROM users 
                WHERE is_seller = true 
                GROUP BY COALESCE(business_address, parish, 'Unknown')
                HAVING seller_count > 0
                ORDER BY seller_count DESC
            ''')
            sellers_by_parish = cursor.fetchall()

            # Orders by parish
            cursor.execute('''
                SELECT COALESCE(parish, 'Unknown') as parish, 
                       COUNT(*) as order_count, 
                       COALESCE(SUM(total), 0) as revenue
                FROM orders 
                WHERE status != 'cancelled'
                GROUP BY COALESCE(parish, 'Unknown')
                HAVING order_count > 0
                ORDER BY order_count DESC
            ''')
            orders_by_parish = cursor.fetchall()

            # Combined parish stats
            parish_stats = {}

            # Initialize with buyers
            for row in buyers_by_parish:
                parish = row['parish']
                parish_stats[parish] = {
                    'parish': parish,
                    'buyers': row['buyer_count'],
                    'sellers': 0,
                    'orders': 0,
                    'revenue': 0
                }

            # Add sellers
            for row in sellers_by_parish:
                parish = row['parish']
                if parish in parish_stats:
                    parish_stats[parish]['sellers'] = row['seller_count']
                else:
                    parish_stats[parish] = {
                        'parish': parish,
                        'buyers': 0,
                        'sellers': row['seller_count'],
                        'orders': 0,
                        'revenue': 0
                    }

            # Add orders and revenue
            for row in orders_by_parish:
                parish = row['parish']
                if parish in parish_stats:
                    parish_stats[parish]['orders'] = row['order_count']
                    parish_stats[parish]['revenue'] = float(row['revenue'] or 0)
                else:
                    parish_stats[parish] = {
                        'parish': parish,
                        'buyers': 0,
                        'sellers': 0,
                        'orders': row['order_count'],
                        'revenue': float(row['revenue'] or 0)
                    }

            # Create revenue by parish data
            revenue_by_parish = []
            for parish, stats in parish_stats.items():
                revenue_by_parish.append({
                    'parish': parish,
                    'revenue': stats['revenue']
                })
            revenue_by_parish.sort(key=lambda x: x['revenue'], reverse=True)

            return jsonify({
                'success': True,
                'buyers_by_parish': [dict(row) for row in buyers_by_parish],
                'sellers_by_parish': [dict(row) for row in sellers_by_parish],
                'orders_by_parish': [dict(row) for row in orders_by_parish],
                'parish_stats': list(parish_stats.values()),
                'revenue_by_parish': revenue_by_parish
            })

    except Exception as e:
        logger.error(f"Error getting parish analytics: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/revenue_data')
@admin_required()
def admin_api_revenue_data():
    """Revenue chart data with different timeframes"""
    try:
        timeframe = request.args.get('timeframe', '1y')
        chart_type = request.args.get('chart_type', 'line')

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if we have any orders first
            cursor.execute('SELECT COUNT(*) as order_count FROM orders')
            order_count_result = cursor.fetchone()
            total_orders = order_count_result['order_count'] if order_count_result else 0

            if total_orders == 0:
                return jsonify({
                    'success': True,
                    'data': [],
                    'summary': {
                        'total_revenue': 0,
                        'total_orders': 0,
                        'avg_order_value': 0
                    }
                })

            # Calculate date range based on timeframe
            if timeframe == '7d':
                days_back = 7
                group_by = 'DATE(order_date)'
            elif timeframe == '1m':
                days_back = 30
                group_by = 'DATE(order_date)'
            elif timeframe == '3m':
                days_back = 90
                group_by = 'DATE(order_date)'
            elif timeframe == '6m':
                days_back = true80
                group_by = 'strftime("%Y-%W", order_date)'
            elif timeframe == '1y':
                days_back = 365
                group_by = 'strftime("%Y-%m", order_date)'
            else:  # 'all'
                days_back = 3650
                group_by = 'strftime("%Y-%m", order_date)'

            start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

            # Get revenue data from orders table
            cursor.execute(f'''
                SELECT 
                    {group_by} as period,
                    COALESCE(SUM(total), 0) as revenue,
                    COUNT(*) as order_count,
                    COALESCE(AVG(total), 0) as avg_order_value,
                    COALESCE(MIN(total), 0) as min_order,
                    COALESCE(MAX(total), 0) as max_order
                FROM orders 
                WHERE order_date >= ? 
                AND status NOT IN ('cancelled', 'refunded')
                GROUP BY period
                ORDER BY period
            ''', (start_date,))

            db_results = cursor.fetchall()
            chart_data = []

            for row in db_results:
                try:
                    if timeframe in ['7d', '1m', '3m']:
                        date_obj = datetime.strptime(row['period'], '%Y-%m-%d')
                    elif timeframe == '6m':
                        year, week = row['period'].split('-')
                        date_obj = datetime.strptime(f'{year}-W{week}-1', '%Y-W%W-%w')
                    else:
                        date_obj = datetime.strptime(row['period'] + '-01', '%Y-%m-%d')

                    timestamp = int(date_obj.timestamp() * 1000)

                    if chart_type == 'candlestick':
                        chart_data.append({
                            'x': timestamp,
                            'y': [
                                float(row['min_order'] or 0),
                                float(row['max_order'] or 0),
                                float(row['min_order'] or 0),
                                float(row['avg_order_value'] or 0)
                            ]
                        })
                    else:
                        chart_data.append({
                            'x': timestamp,
                            'y': float(row['revenue'] or 0)
                        })

                except Exception as e:
                    logger.error(f"Error parsing date {row['period']}: {e}")
                    continue

            return jsonify({
                'success': True,
                'data': chart_data,
                'summary': {
                    'total_revenue': sum(float(row['revenue'] or 0) for row in db_results),
                    'total_orders': sum(row['order_count'] or 0 for row in db_results),
                    'avg_order_value': sum(float(row['avg_order_value'] or 0) for row in db_results) / len(
                        db_results) if db_results else 0
                }
            })

    except Exception as e:
        logger.error(f"Error getting revenue chart data: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/recent_activity')
@admin_required()
def recent_activity():
    """Recent platform activity for dashboard"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            activities = []

            # Get recent user registrations
            try:
                cursor.execute('''
                    SELECT email, first_name, last_name, is_seller, 
                           COALESCE(created_at, 'Recently') as created_at
                    FROM users 
                    ORDER BY email DESC
                    LIMIT 5
                ''')
                users = cursor.fetchall()

                for user in users:
                    activities.append({
                        'time': user['created_at'],
                        'action': 'seller_register' if user['is_seller'] else 'user_register',
                        'action_type': 'New Seller Registration' if user['is_seller'] else 'New User Registration',
                        'user': user['email'],
                        'description': f"{user['first_name'] or ''} {user['last_name'] or ''} joined as {'seller' if user['is_seller'] else 'buyer'}".strip()
                    })
            except Exception as e:
                logger.error(f"Error getting user activity: {e}")

            # Get recent product uploads
            try:
                cursor.execute('''
                    SELECT product_key, name, seller_email, 
                           COALESCE(posted_date, 'Recently') as posted_date
                    FROM products 
                    ORDER BY posted_date DESC
                    LIMIT 5
                ''')
                products = cursor.fetchall()

                for product in products:
                    activities.append({
                        'time': product['posted_date'],
                        'action': 'product_upload',
                        'action_type': 'Product Listed',
                        'user': product['seller_email'],
                        'description': f"New product: {product['name']}"
                    })
            except Exception as e:
                logger.error(f"Error getting product activity: {e}")

            # Get recent orders
            try:
                cursor.execute('''
                    SELECT order_id, user_email, total, 
                           COALESCE(order_date, 'Recently') as order_date
                    FROM orders 
                    ORDER BY order_date DESC
                    LIMIT 5
                ''')
                orders = cursor.fetchall()

                for order in orders:
                    activities.append({
                        'time': order['order_date'],
                        'action': 'order_placed',
                        'action_type': 'Order Placed',
                        'user': order['user_email'],
                        'description': f"Order #{order['order_id'][:8]} - J${order['total']}"
                    })
            except Exception as e:
                logger.error(f"Error getting order activity: {e}")

            # Get recent admin activity
            try:
                cursor.execute('''
                    SELECT admin_email, action_type, description, timestamp
                    FROM admin_activity_log
                    ORDER BY timestamp DESC
                    LIMIT 5
                ''')
                admin_activities = cursor.fetchall()

                for activity in admin_activities:
                    activities.append({
                        'time': activity['timestamp'],
                        'action': 'admin_action',
                        'action_type': activity['action_type'],
                        'user': activity['admin_email'],
                        'description': activity['description'] or 'Admin action performed'
                    })
            except Exception as e:
                logger.error(f"Error getting admin activity: {e}")

            # Sort activities and format times
            activities.sort(key=lambda x: str(x['time']), reverse=True)
            activities = activities[:15]

            # Format times safely
            for activity in activities:
                if activity['time'] and activity['time'] != 'Recently':
                    try:
                        if ' ' in str(activity['time']):
                            time_obj = datetime.strptime(activity['time'], '%Y-%m-%d %H:%M:%S')
                        else:
                            time_obj = datetime.strptime(activity['time'], '%Y-%m-%d')

                        time_diff = datetime.now() - time_obj

                        if time_diff.days > 0:
                            activity['time'] = f"{time_diff.days} days ago"
                        elif time_diff.seconds > 3600:
                            activity['time'] = f"{time_diff.seconds // 3600} hrs ago"
                        elif time_diff.seconds > 60:
                            activity['time'] = f"{time_diff.seconds // 60} mins ago"
                        else:
                            activity['time'] = "Just now"
                    except:
                        activity['time'] = 'Recently'

            return jsonify({
                'success': True,
                'activities': activities
            })

    except Exception as e:
        logger.error(f"Error getting recent activity: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========================================
# USER MANAGEMENT ENDPOINTS
# ========================================

@app.route('/admin/api/users')
@admin_required()
def admin_api_users():
    """FIXED: Users API - handles missing created_at column"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all users with their stats including seller revenue
            cursor.execute('''
                SELECT
                    u.email, u.first_name, u.last_name, u.phone_number, u.whatsapp_number,
                    u.parish, u.business_address, u.business_name, u.is_seller,
                    u.profile_picture,
                    COUNT(DISTINCT o.order_id) as order_count,
                    COUNT(DISTINCT p.product_key) as products_listed,
                    COALESCE(SUM(CASE WHEN o.user_email = u.email THEN o.total ELSE 0 END), 0) as total_spent,
                    COALESCE(SUM(p.price * COALESCE(p.sold, 0)), 0) as seller_revenue,
                    COUNT(DISTINCT uf.id) as flag_count
                FROM users u
                LEFT JOIN orders o ON u.email = o.user_email
                LEFT JOIN products p ON u.email = p.seller_email
                LEFT JOIN user_flags uf ON u.email = uf.user_email AND uf.is_active = true
                GROUP BY u.email, u.first_name, u.last_name, u.phone_number, u.whatsapp_number,
                    u.parish, u.business_address, u.business_name, u.is_seller, u.profile_picture
                ORDER BY seller_revenue DESC, u.email DESC
            ''')

            users_raw = cursor.fetchall()
            users = []

            for row in users_raw:
                user = dict(row)
                # Clean up data
                user['order_count'] = user['order_count'] or 0
                user['products_listed'] = user['products_listed'] or 0
                user['total_spent'] = float(user['total_spent'] or 0)
                user['seller_revenue'] = float(user['seller_revenue'] or 0)
                user['flag_count'] = user['flag_count'] or 0
                users.append(user)

            logger.info(f"Found {len(users)} users for admin dashboard")
            return jsonify({
                'success': True,
                'users': users
            })

    except Exception as e:
        logger.error(f"Error getting users API data: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/flag_user', methods=['POST'])
@admin_required()
def flag_user():
    """Flag or ban a user"""
    try:
        data = request.get_json()
        user_email = data.get('user_email')
        flag_type = data.get('flag_type', 'warning')  # warning, suspended, banned
        reason = data.get('reason')
        expires_days = data.get('expires_days')

        if not user_email or not reason:
            return jsonify({'success': False, 'message': 'User email and reason required'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if user exists
            cursor.execute('SELECT email FROM users WHERE email = %s', (user_email,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': 'User not found'}), 404

            # Calculate expiry date if provided
            expires_at = None
            if expires_days:
                expires_at = (datetime.now() + timedelta(days=int(expires_days))).strftime('%Y-%m-%d %H:%M:%S')

            # Create flag record
            cursor.execute('''
                INSERT INTO user_flags (user_email, flag_type, reason, flagged_by, expires_at)
                VALUES (%s, %s, %s, %s,%s)
            ''', (user_email, flag_type, reason, session['admin_user']['email'], expires_at))

            conn.commit()

            # Log admin activity
            log_admin_activity(
                session['admin_user']['email'],
                f'user_{flag_type}',
                'user',
                user_email,
                f'{flag_type.title()} user: {reason}'
            )

            return jsonify({'success': True, 'message': f'User {flag_type} successfully'})

    except Exception as e:
        logger.error(f"Error flagging user: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/user_details/<email>')
@admin_required()
def get_user_details(email):
    """Get detailed information about a specific user"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get user basic info
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            user = cursor.fetchone()

            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404

            user_data = dict(user)

            # Get user flags
            cursor.execute('''
                SELECT * FROM user_flags
                WHERE user_email = %s AND is_active = true
                ORDER BY flag_date DESC
            ''', (email,))
            flags = [dict(row) for row in cursor.fetchall()]

            # Get orders if buyer
            cursor.execute('''
                SELECT o.*, COUNT(oi.id) as item_count
                FROM orders o
                LEFT JOIN order_items oi ON o.order_id = oi.order_id
                WHERE o.user_email = %s
                GROUP BY o.order_id
                ORDER BY o.order_date DESC
            ''', (email,))
            orders = [dict(row) for row in cursor.fetchall()]

            # Get products if seller
            products = []
            if user_data.get('is_seller'):
                cursor.execute('''
                    SELECT p.*,
                           COALESCE((SELECT COUNT(*) FROM user_flags
                                    WHERE user_email = p.seller_email AND is_active = true), 0) as seller_flagged
                    FROM products p
                    WHERE p.seller_email = %s
                    ORDER BY p.posted_date DESC
                ''', (email,))
                products_raw = cursor.fetchall()
                for row in products_raw:
                    product = dict(row)
                    # Parse JSON fields
                    try:
                        product['image_urls'] = json.loads(product['image_urls']) if product['image_urls'] else []
                    except:
                        product['image_urls'] = []
                    try:
                        product['sizes'] = json.loads(product['sizes']) if product['sizes'] else {}
                    except:
                        product['sizes'] = {}
                    products.append(product)

            return jsonify({
                'success': True,
                'user': user_data,
                'flags': flags,
                'orders': orders,
                'products': products
            })

    except Exception as e:
        logger.error(f"Error getting user details: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/unflag_user', methods=['POST'])
@admin_required()
def unflag_user():
    """Unflag/unpause a user account"""
    try:
        data = request.get_json()
        user_email = data.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'message': 'User email required'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Deactivate all active flags for this user
            cursor.execute('''
                UPDATE user_flags
                SET is_active = 0
                WHERE user_email = %s AND is_active = true
            ''', (user_email,))

            conn.commit()

            # Log admin activity
            log_admin_activity(
                session['admin_user']['email'],
                'user_unflagged',
                'user',
                user_email,
                'User account unpaused/unflagged'
            )

            return jsonify({'success': True, 'message': 'User unflagged successfully'})

    except Exception as e:
        logger.error(f"Error unflagging user: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========================================
# SELLER MANAGEMENT ENDPOINTS
# ========================================

@app.route('/admin/api/sellers')
@admin_required()
def admin_api_sellers():
    """Get all sellers for seller analytics section"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all sellers with detailed info
            cursor.execute('''
                SELECT
                    u.email, u.first_name, u.last_name, u.business_name,
                    u.business_address, u.phone_number, u.profile_picture, u.parish,
                    u.cod_enabled,
                    COUNT(DISTINCT p.product_key) as products_listed,
                    COALESCE(SUM(p.sold), 0) as total_sales,
                    COALESCE(SUM(p.sold * p.price), 0) as total_revenue,
                    AVG(sr.rating) as avg_rating,
                    COUNT(sr.rating) as rating_count,
                    COUNT(DISTINCT uf.id) as flag_count
                FROM users u
                LEFT JOIN products p ON u.email = p.seller_email
                LEFT JOIN seller_ratings sr ON u.email = sr.seller_email
                LEFT JOIN user_flags uf ON u.email = uf.user_email AND uf.is_active = true
                WHERE u.is_seller = true
                GROUP BY u.email, u.cod_enabled
                ORDER BY total_revenue DESC
            ''')

            sellers_raw = cursor.fetchall()
            sellers = []

            for row in sellers_raw:
                seller = dict(row)
                # Clean up data
                seller['products_listed'] = seller['products_listed'] or 0
                seller['total_sales'] = seller['total_sales'] or 0
                seller['total_revenue'] = float(seller['total_revenue'] or 0)
                seller['avg_rating'] = round(float(seller['avg_rating'] or 0), 1)
                seller['rating_count'] = seller['rating_count'] or 0
                seller['flag_count'] = seller['flag_count'] or 0
                sellers.append(seller)

            logger.info(f"Found {len(sellers)} sellers for admin dashboard")
            return jsonify({
                'success': True,
                'sellers': sellers
            })

    except Exception as e:
        logger.error(f"Error getting sellers API data: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/seller/<seller_email>')
@admin_required()
def admin_api_seller_details(seller_email):
    """Get detailed seller information for admin view"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get seller info with verification status
            cursor.execute('''
                SELECT
                    u.email, u.first_name, u.last_name, u.business_name,
                    u.business_address, u.phone_number, u.profile_picture, u.parish,
                    u.business_description,
                    sv.verification_status, sv.submitted_at as verification_date,
                    COUNT(DISTINCT p.product_key) as products_listed,
                    COALESCE(SUM(p.sold), 0) as total_sales,
                    COALESCE(SUM(p.sold * p.price), 0) as total_revenue,
                    AVG(sr.rating) as avg_rating,
                    COUNT(sr.rating) as rating_count,
                    COUNT(DISTINCT uf.id) as flag_count
                FROM users u
                LEFT JOIN seller_verification sv ON u.email = sv.seller_email
                LEFT JOIN products p ON u.email = p.seller_email
                LEFT JOIN seller_ratings sr ON u.email = sr.seller_email
                LEFT JOIN user_flags uf ON u.email = uf.user_email AND uf.is_active = true
                WHERE u.email = %s AND u.is_seller = true
                GROUP BY u.email
            ''', (seller_email,))

            seller = cursor.fetchone()
            if not seller:
                return jsonify({'success': False, 'message': 'Seller not found'}), 404

            seller_data = dict(seller)
            # Clean up data
            seller_data['products_listed'] = seller_data['products_listed'] or 0
            seller_data['total_sales'] = seller_data['total_sales'] or 0
            seller_data['total_revenue'] = float(seller_data['total_revenue'] or 0)
            seller_data['avg_rating'] = round(float(seller_data['avg_rating'] or 0), 1)
            seller_data['rating_count'] = seller_data['rating_count'] or 0
            seller_data['flag_count'] = seller_data['flag_count'] or 0

            return jsonify({
                'success': True,
                'seller': seller_data
            })

    except Exception as e:
        logger.error(f"Error getting seller details for {seller_email}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/toggle_cod', methods=['POST'])
@admin_required()
def admin_toggle_cod():
    """Toggle COD (Cash on Delivery) access for a seller"""
    try:
        data = request.get_json()
        seller_email = data.get('seller_email')
        cod_enabled = data.get('cod_enabled', False)

        if not seller_email:
            return jsonify({'success': False, 'message': 'Seller email required'}), 400

        with get_db() as conn:
            cursor = conn.cursor()

            # Update seller's COD access
            cursor.execute('''
                UPDATE users
                SET cod_enabled = %s
                WHERE email = %s AND is_seller = true
            ''', (cod_enabled, seller_email))

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Seller not found'}), 404

            conn.commit()

            logger.info(f"Admin toggled COD for {seller_email}: {cod_enabled}")
            return jsonify({
                'success': True,
                'message': f"COD {'enabled' if cod_enabled else 'disabled'} for {seller_email}"
            })

    except Exception as e:
        logger.error(f"Error toggling COD for seller: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========================================
# PRODUCT MANAGEMENT ENDPOINTS
# ========================================

@app.route('/admin/api/products')
@admin_required()
def admin_api_products():
    """Get all products for product management"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all products with seller info
            cursor.execute('''
                SELECT p.product_key, p.name, p.price, p.description, p.image_url, 
                       p.image_urls, p.shipping, p.brand, p.category, p.original_cost, 
                       p.roi, p.sizes, p.seller_email, p.sold, p.clicks, p.likes, 
                       p.posted_date, p.amount,
                       u.first_name as seller_first_name,
                       u.last_name as seller_last_name,
                       u.business_name as seller_business_name,
                       COALESCE(p.sold, 0) as total_sold,
                       COALESCE(p.sold * p.price, 0) as total_revenue
                FROM products p
                LEFT JOIN users u ON p.seller_email = u.email
                ORDER BY p.posted_date DESC
            ''')

            products_raw = cursor.fetchall()
            products = []

            for row in products_raw:
                product = dict(row)
                # Parse JSON fields safely
                try:
                    product['image_urls'] = json.loads(product['image_urls']) if product['image_urls'] else []
                except:
                    product['image_urls'] = []

                try:
                    product['sizes'] = json.loads(product['sizes']) if product['sizes'] else {}
                except:
                    product['sizes'] = {}

                products.append(product)

            logger.info(f"Found {len(products)} products in database")
            return jsonify({
                'success': True,
                'products': products
            })
    except Exception as e:
        logger.error(f"Error getting products API data: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/remove_product', methods=['POST'])
@admin_required()
def remove_product():
    """Remove/hide a product"""
    try:
        data = request.get_json()
        product_key = data.get('product_key')
        reason = data.get('reason', 'Admin removal')

        if not product_key:
            return jsonify({'success': False, 'message': 'Product key required'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if product exists
            cursor.execute('SELECT * FROM products WHERE product_key = %s', (product_key,))
            product = cursor.fetchone()
            if not product:
                return jsonify({'success': False, 'message': 'Product not found'}), 404

            # Remove the product
            cursor.execute('DELETE FROM products WHERE product_key = %s', (product_key,))
            conn.commit()

            # Log admin activity
            log_admin_activity(
                session['admin_user']['email'],
                'product_removed',
                'product',
                product_key,
                f'Removed product: {reason}'
            )

            return jsonify({'success': True, 'message': 'Product removed successfully'})

    except Exception as e:
        logger.error(f"Error removing product: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========================================
# ORDER MANAGEMENT ENDPOINTS
# ========================================

@app.route('/admin/api/orders')
@admin_required()
def admin_api_orders():
    """Get all orders for order management"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all orders with user info
            cursor.execute('''
                SELECT
                    o.order_id, o.user_email, o.full_name, o.phone_number,
                    o.parish, o.total, o.payment_method, o.order_date, o.status,
                    o.payment_verified, o.lynk_reference,
                    u.first_name, u.last_name,
                    COUNT(oi.product_key) as item_count
                FROM orders o
                LEFT JOIN users u ON o.user_email = u.email
                LEFT JOIN order_items oi ON o.order_id = oi.order_id
                GROUP BY o.order_id, o.user_email, o.full_name, o.phone_number,
                    o.parish, o.total, o.payment_method, o.order_date, o.status,
                    o.payment_verified, o.lynk_reference,
                    u.first_name, u.last_name
                ORDER BY o.order_date DESC
            ''')

            orders_raw = cursor.fetchall()
            orders = []

            for row in orders_raw:
                order = dict(row)
                # Clean up data
                order['item_count'] = order['item_count'] or 0
                order['total'] = float(order['total'] or 0)
                orders.append(order)

            logger.info(f"Found {len(orders)} orders for admin dashboard")
            return jsonify({
                'success': True,
                'orders': orders
            })

    except Exception as e:
        logger.error(f"Error getting orders API data: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/update_order_status', methods=['POST'])
@admin_required()
def update_order_status():
    """Update order status"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        new_status = data.get('status')

        if not order_id or not new_status:
            return jsonify({'success': False, 'message': 'Order ID and status required'}), 400

        valid_statuses = ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled', 'refunded']
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Update order status
            cursor.execute('UPDATE orders SET status = %s WHERE order_id = %s', (new_status, order_id))

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Order not found'}), 404

            conn.commit()

            # Log admin activity
            log_admin_activity(
                session['admin_user']['email'],
                'order_status_updated',
                'order',
                order_id,
                f'Updated order status to: {new_status}'
            )

            return jsonify({'success': True, 'message': f'Order status updated to {new_status}'})

    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========================================
# FINANCIAL MANAGEMENT ENDPOINTS
# ========================================

@app.route('/admin/api/financials')
@admin_required()
def admin_api_financials():
    """Get financial data for financial dashboard"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Calculate financial metrics
            cursor.execute('''
                SELECT 
                    COALESCE(SUM(total), 0) as total_revenue,
                    COUNT(*) as total_orders,
                    COALESCE(AVG(total), 0) as avg_order_value
                FROM orders 
                WHERE status NOT IN ('cancelled', 'refunded')
            ''')
            revenue_data = cursor.fetchone()

            total_revenue = float(revenue_data['total_revenue'] or 0)
            platform_fees = total_revenue * 0.05  # 5% platform fee
            seller_payouts = total_revenue * 0.95  # 95% to sellers

            # Get refunds
            cursor.execute('''
                SELECT COALESCE(SUM(total), 0) as total_refunds
                FROM orders 
                WHERE status = 'refunded'
            ''')
            refunds_data = cursor.fetchone()
            total_refunds = float(refunds_data['total_refunds'] or 0)

            # Calculate net profit
            net_profit = platform_fees - total_refunds

            # Get monthly data for charts
            cursor.execute('''
                SELECT 
                    strftime('%Y-%m', order_date) as month,
                    COALESCE(SUM(total), 0) as revenue,
                    COUNT(*) as orders
                FROM orders 
                WHERE order_date >= date('now', '-12 months')
                AND status NOT IN ('cancelled', 'refunded')
                GROUP BY month
                ORDER BY month
            ''')
            monthly_data = [dict(row) for row in cursor.fetchall()]

            return jsonify({
                'success': True,
                'total_revenue': total_revenue,
                'platform_fees': platform_fees,
                'seller_payouts': seller_payouts,
                'total_refunds': total_refunds,
                'net_profit': net_profit,
                'monthly_data': monthly_data
            })

    except Exception as e:
        logger.error(f"Error getting financial data: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========================================
# ADMIN PAYOUT MANAGEMENT
# ========================================

@app.route('/admin/api/pending_payouts')
@admin_required()
def admin_pending_payouts():
    """Get all pending seller payout requests"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            cursor.execute('''
                SELECT
                    wr.id,
                    wr.seller_email,
                    wr.amount,
                    wr.fee,
                    wr.net_amount,
                    wr.method,
                    wr.status,
                    wr.request_date,
                    wr.processing_time,
                    u.first_name,
                    u.last_name,
                    spm.account_number,
                    spm.account_name,
                    spm.bank_name
                FROM withdrawal_requests wr
                JOIN users u ON wr.seller_email = u.email
                LEFT JOIN seller_payment_methods spm ON wr.seller_email = spm.seller_email
                    AND spm.payment_type = wr.method
                WHERE wr.status = 'pending'
                ORDER BY wr.request_date DESC
            ''')

            pending_payouts = [dict(row) for row in cursor.fetchall()]

            # Get summary
            cursor.execute('''
                SELECT
                    COUNT(*) as total_pending,
                    COALESCE(SUM(amount), 0) as total_amount
                FROM withdrawal_requests
                WHERE status = 'pending'
            ''')
            summary = cursor.fetchone()

            return jsonify({
                'success': True,
                'payouts': pending_payouts,
                'summary': {
                    'total_pending': int(summary['total_pending']),
                    'total_amount': float(summary['total_amount'])
                }
            })

    except Exception as e:
        logger.error(f"Error getting pending payouts: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/approve_payout', methods=['POST'])
@admin_required()
def admin_approve_payout():
    """Manually approve and mark payout as completed"""
    try:
        data = request.get_json()
        payout_id = data.get('payout_id')

        if not payout_id:
            return jsonify({'success': False, 'message': 'Payout ID required'})

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get payout details
            cursor.execute('''
                SELECT seller_email, amount, net_amount
                FROM withdrawal_requests
                WHERE id = %s AND status = 'pending'
            ''', (payout_id,))

            payout = cursor.fetchone()
            if not payout:
                return jsonify({'success': False, 'message': 'Payout not found or already processed'})

            # Update withdrawal request to completed
            cursor.execute('''
                UPDATE withdrawal_requests
                SET status = 'completed',
                    completed_date = %s
                WHERE id = %s
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), payout_id))

            # Update seller finances - remove from pending
            cursor.execute('''
                UPDATE seller_finances
                SET pending_withdrawals = GREATEST(pending_withdrawals - %s, 0)
                WHERE seller_email = %s
            ''', (payout['amount'], payout['seller_email']))

            # Find and update transaction
            cursor.execute('''
                UPDATE payment_transactions
                SET status = 'completed',
                    completed_at = %s
                WHERE seller_email = %s
                AND transaction_type = 'withdrawal'
                AND amount = %s
                AND status = 'processing'
                ORDER BY created_at DESC
                LIMIT 1
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), payout['seller_email'], payout['amount']))

            # Send seller notification
            cursor.execute('''
                INSERT INTO seller_notifications (seller_email, notification_type, title, message, created_at)
                VALUES (%s, %s, %s, %s, %s)
            ''', (
                payout['seller_email'],
                'payout_approved',
                '✅ Payout Approved!',
                f"Your withdrawal request of J${payout['net_amount']:,.2f} has been approved and processed. Funds should arrive within the specified processing time.",
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

            conn.commit()

            logger.info(f"Admin approved payout {payout_id} for {payout['seller_email']}: J${payout['net_amount']}")

            return jsonify({
                'success': True,
                'message': f"Payout of J${payout['net_amount']:,.2f} approved successfully!"
            })

    except Exception as e:
        logger.error(f"Error approving payout: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/payout_history')
@admin_required()
def admin_payout_history():
    """Get completed payout history"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            cursor.execute('''
                SELECT
                    wr.id,
                    wr.seller_email,
                    wr.amount,
                    wr.fee,
                    wr.net_amount,
                    wr.method,
                    wr.status,
                    wr.request_date,
                    wr.completed_date,
                    u.first_name,
                    u.last_name
                FROM withdrawal_requests wr
                JOIN users u ON wr.seller_email = u.email
                WHERE wr.status IN ('completed', 'failed')
                ORDER BY wr.completed_date DESC
                LIMIT 100
            ''')

            history = [dict(row) for row in cursor.fetchall()]

            return jsonify({
                'success': True,
                'history': history
            })

    except Exception as e:
        logger.error(f"Error getting payout history: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========================================
# ADMIN USER MANAGEMENT ENDPOINTS
# ========================================

@app.route('/admin/api/admin_users')
@admin_required()
def admin_api_admin_users():
    """Get all admin users for settings"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            cursor.execute('''
                SELECT email, admin_level, created_by, created_at, last_login, is_active
                FROM admin_users
                ORDER BY created_at DESC
            ''')

            admin_users = [dict(row) for row in cursor.fetchall()]

            return jsonify({
                'success': True,
                'admin_users': admin_users
            })

    except Exception as e:
        logger.error(f"Error getting admin users: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/create_admin', methods=['POST'])
@admin_required('super_admin')  # Only super admins can create admins
def create_admin_user():
    """Create new admin user"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        admin_level = data.get('admin_level', 'admin')

        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password required'}), 400

        # Hash the password
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash(password)

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if admin already exists
            cursor.execute('SELECT email FROM admin_users WHERE email = %s', (email,))
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'Admin user already exists'}), 400

            # Create admin user
            cursor.execute('''
                INSERT INTO admin_users (email, password, admin_level, created_by)
                VALUES (%s, %s, %s,%s)
            ''', (email, hashed_password, admin_level, session['admin_user']['email']))
            conn.commit()

            # Log activity
            log_admin_activity(
                session['admin_user']['email'],
                'admin_created',
                'admin',
                email,
                f'Created {admin_level} user: {email}'
            )

            return jsonify({'success': True, 'message': 'Admin user created successfully'})

    except Exception as e:
        logger.error(f"Error creating admin user: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/deactivate_admin', methods=['POST'])
@admin_required('super_admin')
def deactivate_admin():
    """Deactivate an admin user"""
    try:
        data = request.get_json()
        admin_email = data.get('admin_email')

        if not admin_email:
            return jsonify({'success': False, 'message': 'Admin email required'}), 400

        if admin_email == session['admin_user']['email']:
            return jsonify({'success': False, 'message': 'Cannot deactivate yourself'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Deactivate admin
            cursor.execute('UPDATE admin_users SET is_active = 0 WHERE email = %s', (admin_email,))

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Admin user not found'}), 404

            conn.commit()

            # Log activity
            log_admin_activity(
                session['admin_user']['email'],
                'admin_deactivated',
                'admin',
                admin_email,
                f'Deactivated admin user: {admin_email}'
            )

            return jsonify({'success': True, 'message': 'Admin user deactivated'})

    except Exception as e:
        logger.error(f"Error deactivating admin: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========================================
# TESTING & DEBUG ENDPOINTS
# ========================================

@app.route('/admin/test-data')
@admin_required()
def test_admin_data():
    """Test endpoint to verify data (temporary for debugging)"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Count users
            cursor.execute('SELECT COUNT(*) as count FROM users')
            user_count = cursor.fetchone()['count']

            # Count sellers
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_seller = true')
            seller_count = cursor.fetchone()['count']

            # Count products
            cursor.execute('SELECT COUNT(*) as count FROM products')
            product_count = cursor.fetchone()['count']

            # Count orders
            cursor.execute('SELECT COUNT(*) as count FROM orders')
            order_count = cursor.fetchone()['count']

            # Get sample user data
            cursor.execute('SELECT email, first_name, is_seller FROM users LIMIT 5')
            sample_users = [dict(row) for row in cursor.fetchall()]

            # Get sample seller data
            cursor.execute('SELECT email, business_name FROM users WHERE is_seller = true LIMIT 3')
            sample_sellers = [dict(row) for row in cursor.fetchall()]

            return jsonify({
                'success': True,
                'counts': {
                    'users': user_count,
                    'sellers': seller_count,
                    'products': product_count,
                    'orders': order_count
                },
                'sample_users': sample_users,
                'sample_sellers': sample_sellers,
                'message': 'Database test successful!'
            })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/verification')
def verification():
    email = request.args.get('email', 'your email')
    first_name = request.args.get('first_name', 'User')
    cart_data = get_cart_items()
    return render_template(
        'verification.html',
        email=email,
        first_name=first_name,
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )

@app.route('/verify')
def verify():
    token = request.args.get('token')
    email = request.args.get('email')
    first_name = request.args.get('first_name', 'User')
    if token:
        return redirect(url_for('welcome', first_name=first_name))
    return "Invalid verification link", 400

@app.route('/welcome')
def welcome():
    first_name = request.args.get('first_name', 'User')
    cart_data = get_cart_items()
    return render_template(
        'welcome.html',
        first_name=first_name,
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )

@app.route('/handmade')
def handmade():
    cart_data = get_cart_items()
    return render_template(
        'handmade.html',
        user=session.get('user'),
        cart_item_count=cart_data['cart_item_count']
    )


# Add these routes to your app.py
@app.route('/seller_verification', methods=['GET', 'POST'])
def seller_verification():
    """Seller ID and TRN verification page"""
    if 'user' not in session or not session['user'].get('is_seller'):
        return redirect(url_for('login'))

    user_email = session['user']['email']

    if request.method == 'POST':
        try:
            # Get form data
            id_document_type = request.form.get('id_document_type')
            trn_number = request.form.get('trn_number', '').strip()
            notes = request.form.get('notes', '').strip()

            # Validate TRN format (9 digits)
            if not re.match(r'^\d{9}$', trn_number):
                from flask_wtf.csrf import generate_csrf
                return render_template('seller_verification.html',
                                       error="TRN must be exactly 9 digits",
                                       csrf_token=generate_csrf())

            # Check for uploaded files
            if 'id_document' not in request.files or 'trn_document' not in request.files:
                from flask_wtf.csrf import generate_csrf
                return render_template('seller_verification.html',
                                       error="Both ID document and TRN document are required",
                                       csrf_token=generate_csrf())

            id_file = request.files['id_document']
            trn_file = request.files['trn_document']

            if not id_file.filename or not trn_file.filename:
                from flask_wtf.csrf import generate_csrf
                return render_template('seller_verification.html',
                                       error="Please upload both required documents",
                                       csrf_token=generate_csrf())

            # Validate file types
            allowed_extensions = {'png', 'jpg', 'jpeg', 'pdf'}

            def allowed_file(filename):
                return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

            if not allowed_file(id_file.filename) or not allowed_file(trn_file.filename):
                from flask_wtf.csrf import generate_csrf
                return render_template('seller_verification.html',
                                       error="Only PNG, JPG, JPEG, and PDF files are allowed",
                                       csrf_token=generate_csrf())

            # Create verification documents directory
            verification_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'verifications')
            os.makedirs(verification_dir, exist_ok=True)

            # Save files with secure names
            verification_id = str(uuid.uuid4())[:8]

            id_filename = f"{verification_id}_id.{id_file.filename.rsplit('.', 1)[1].lower()}"
            trn_filename = f"{verification_id}_trn.{trn_file.filename.rsplit('.', 1)[1].lower()}"

            id_path = os.path.join(verification_dir, id_filename)
            trn_path = os.path.join(verification_dir, trn_filename)

            id_file.save(id_path)
            trn_file.save(trn_path)

            # Store in database
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

                # Check if verification already exists
                cursor.execute('''
                    SELECT id FROM seller_verification WHERE seller_email = %s
                ''', (user_email,))

                existing = cursor.fetchone()

                if existing:
                    # Update existing verification
                    cursor.execute('''
                        UPDATE seller_verification
                        SET id_document_path = %s, id_document_type = %s, trn_number = %s,
                            trn_document_path = %s, notes = %s, verification_status = 'pending_review',
                            submitted_at = CURRENT_TIMESTAMP
                        WHERE seller_email = %s
                    ''', (f"uploads/verifications/{id_filename}", id_document_type, trn_number,
                          f"uploads/verifications/{trn_filename}", notes, user_email))
                else:
                    # Create new verification
                    cursor.execute('''
                        INSERT INTO seller_verification
                        (seller_email, id_document_path, id_document_type, trn_number,
                         trn_document_path, notes, verification_status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending_review')
                    ''', (user_email, f"uploads/verifications/{id_filename}", id_document_type,
                          trn_number, f"uploads/verifications/{trn_filename}", notes))

                conn.commit()

            # Update session
            session['user']['verification_status'] = 'pending_review'
            session.modified = True

            logger.info(f"Verification documents submitted for seller: {user_email}")

            return redirect(url_for('seller_verification_pending'))

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Error in seller verification: {e}")
            logger.error(f"Full traceback: {error_details}")
            from flask_wtf.csrf import generate_csrf
            return render_template('seller_verification.html',
                                   error=f"An error occurred: {str(e)}",
                                   csrf_token=generate_csrf())

    # GET request - check current verification status
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
        cursor.execute('''
            SELECT verification_status FROM seller_verification WHERE seller_email = %s
        ''', (user_email,))
        verification = cursor.fetchone()

        if verification:
            status = verification['verification_status']
            if status == 'approved':
                return redirect(url_for('seller_dashboard'))
            elif status == 'pending_review':
                return redirect(url_for('seller_verification_pending'))
            elif status == 'rejected':
                return redirect(url_for('seller_verification_rejected'))

    # Generate CSRF token for the form
    from flask_wtf.csrf import generate_csrf
    return render_template('seller_verification.html', csrf_token=generate_csrf())


@app.route('/seller_verification_pending')
def seller_verification_pending():
    """Pending verification status page"""
    if 'user' not in session or not session['user'].get('is_seller'):
        return redirect(url_for('login'))

    return render_template('seller_verification_pending.html', user=session['user'])


@app.route('/seller_verification_rejected')
def seller_verification_rejected():
    """Rejected verification status page"""
    if 'user' not in session or not session['user'].get('is_seller'):
        return redirect(url_for('login'))

    user_email = session['user']['email']

    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
        cursor.execute('''
            SELECT rejection_reason, reviewed_at
            FROM seller_verification
            WHERE seller_email = %s
        ''', (user_email,))
        verification = cursor.fetchone()

    return render_template('seller_verification_rejected.html',
                           user=session['user'],
                           verification=verification)

# Replace your existing seller_dashboard route with this complete version
@app.route('/seller_dashboard')
def seller_dashboard():
    if 'user' not in session or not session['user'].get('is_seller', False):
        return redirect(url_for('login'))

    seller_email = session['user']['email']

    # Check if seller is flagged
    flag_status = is_user_flagged(seller_email)

    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
        # Check verification status from seller_verification table
        cursor.execute('''
            SELECT verification_status FROM seller_verification WHERE seller_email = %s
        ''', (seller_email,))
        verification_record = cursor.fetchone()

        if verification_record:
            verification_status = verification_record['verification_status']
            if verification_status == 'pending_review':
                return redirect(url_for('seller_verification_pending'))
            elif verification_status == 'rejected':
                return redirect(url_for('seller_verification_rejected'))
            # If approved, continue to dashboard
        else:
            # No verification record exists, redirect to verification
            return redirect(url_for('seller_verification'))

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Verify seller exists
            cursor.execute('SELECT * FROM users WHERE email = %s AND is_seller = %s', (seller_email, True))
            seller = cursor.fetchone()
            if not seller:
                logger.warning(f"Seller not found or not authorized: {seller_email}")
                return redirect(url_for('login'))

            # Get seller's products with calculated revenue
            cursor.execute('''
                SELECT product_key, name, category, price, posted_date, sold, clicks, likes, 
                       image_url, description, amount
                FROM products 
                WHERE seller_email = %s
                ORDER BY posted_date DESC
            ''', (seller_email,))

            products_raw = cursor.fetchall()
            logger.info(f"DEBUG: Found {len(products_raw)} products for seller {seller_email}")
            products = []
            total_calculated_earnings = 0.0

            for row in products_raw:
                product_revenue = float(row['price']) * (row['sold'] or 0)
                total_calculated_earnings += product_revenue

                products.append({
                    'product_key': row['product_key'],
                    'name': row['name'],
                    'category': row['category'] or 'Uncategorized',
                    'price': float(row['price']),
                    'posted_date': row['posted_date'] or 'N/A',
                    'sold': row['sold'] or 0,
                    'clicks': row['clicks'] or 0,
                    'likes': row['likes'] or 0,
                    'image_url': row['image_url'] or 'placeholder.jpg',
                    'description': row['description'] or 'No description available',
                    'amount': row['amount'] or 0,
                    'revenue': product_revenue
                })

            # Calculate actual earnings from sales_log table
            cursor.execute('''
                SELECT COALESCE(SUM(quantity * price), 0) as actual_earnings
                FROM sales_log 
                WHERE seller_email = %s
            ''', (seller_email,))

            sales_result = cursor.fetchone()
            actual_sales_earnings = float(sales_result['actual_earnings']) if sales_result else 0.0

            # Use the higher value between calculated and actual earnings
            total_earnings = max(total_calculated_earnings, actual_sales_earnings)

            # Get total withdrawals (completed)
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) as completed_withdrawals
                FROM withdrawal_requests 
                WHERE seller_email = %s AND status = 'completed'
            ''', (seller_email,))

            completed_withdrawals_result = cursor.fetchone()
            completed_withdrawals = float(
                completed_withdrawals_result['completed_withdrawals']) if completed_withdrawals_result else 0.0

            # Get pending withdrawals
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) as pending_withdrawals
                FROM withdrawal_requests 
                WHERE seller_email = %s AND status = 'pending'
            ''', (seller_email,))

            pending_withdrawals_result = cursor.fetchone()
            pending_withdrawals = float(
                pending_withdrawals_result['pending_withdrawals']) if pending_withdrawals_result else 0.0

            # Calculate available balance
            available_balance = total_earnings - completed_withdrawals - pending_withdrawals

            # Get or create financial data for this seller
            cursor.execute('''
                SELECT balance, total_earnings, pending_withdrawals 
                FROM seller_finances 
                WHERE seller_email = %s
            ''', (seller_email,))

            financial_data = cursor.fetchone()

            # Update or create seller_finances with correct calculated values
            cursor.execute('''
                INSERT INTO seller_finances
                (seller_email, balance, total_earnings, pending_withdrawals)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (seller_email)
                DO UPDATE SET
                    balance = EXCLUDED.balance,
                    total_earnings = EXCLUDED.total_earnings,
                    pending_withdrawals = EXCLUDED.pending_withdrawals
            ''', (seller_email, available_balance, total_earnings, pending_withdrawals))
            conn.commit()

            # Get withdrawal history
            cursor.execute('''
                SELECT id, method, amount, fee, net_amount, status, request_date, processing_time 
                FROM withdrawal_requests 
                WHERE seller_email = %s
                ORDER BY request_date DESC
                LIMIT 20
            ''', (seller_email,))

            withdrawal_history = []
            for row in cursor.fetchall():
                withdrawal_history.append({
                    'id': row['id'],
                    'method': row['method'].title() if row['method'] else 'Unknown',
                    'amount': float(row['amount']),
                    'fee': float(row['fee'] or 0),
                    'net_amount': float(row['net_amount'] or 0),
                    'status': row['status'],
                    'request_date': row['request_date'],
                    'processing_time': row['processing_time'] or 'Unknown'
                })

            # Get transaction history from multiple sources
            transactions = []

            # Add sales transactions
            for product in products:
                if product['sold'] > 0:
                    transactions.append({
                        'type': 'sale',
                        'description': f"Sale: {product['name']} (x{product['sold']})",
                        'amount': product['revenue'],
                        'transaction_date': product['posted_date'],
                        'product_key': product['product_key']
                    })

            # Add withdrawal transactions
            for withdrawal in withdrawal_history:
                transactions.append({
                    'type': 'withdrawal',
                    'description': f"{withdrawal['method']} Withdrawal - {withdrawal['status'].title()}",
                    'amount': -withdrawal['amount'],
                    'transaction_date': withdrawal['request_date'],
                    'product_key': None
                })

            # Sort transactions by date (newest first)
            transactions.sort(key=lambda x: x['transaction_date'], reverse=True)

            # Calculate summary stats
            total_products = len(products)
            total_sold = sum(product['sold'] for product in products)

            # Prepare financial data object with correct values
            financial_summary = {
                'total_earnings': total_earnings,
                'available_balance': available_balance,
                'pending_withdrawals': pending_withdrawals,
                'completed_withdrawals': completed_withdrawals,
                'withdrawal_history': withdrawal_history,
                'transactions': transactions[:20],  # Limit to 20 most recent
                'total_products': total_products,
                'total_sold': total_sold,
                'total_revenue': total_earnings
            }

            logger.info(
                f"Seller dashboard loaded for {seller_email}: {total_products} products, {total_sold} sold, earnings: J${total_earnings:,.2f}")

    except Exception as e:
        import traceback
        logger.error(f"Error loading seller dashboard for {seller_email}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return empty dashboard on error
        products = []
        financial_summary = {
            'total_earnings': 0.0,
            'available_balance': 0.0,
            'pending_withdrawals': 0.0,
            'completed_withdrawals': 0.0,
            'withdrawal_history': [],
            'transactions': [],
            'total_products': 0,
            'total_sold': 0,
            'total_revenue': 0.0
        }

    # Get cart data for template
    cart_data = get_cart_items()

    return render_template(
        'seller_dashboard.html',
        user=session['user'],
        seller_products=products,
        financial_data=financial_summary,
        flag_status=flag_status,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )


# Helper functions for encryption (basic version - use proper encryption in production)
def encrypt_data(data):
    """Basic encryption - replace with proper encryption in production"""
    import base64
    return base64.b64encode(data.encode()).decode()


def decrypt_data(data):
    """Basic decryption - replace with proper decryption in production"""
    import base64
    try:
        return base64.b64decode(data.encode()).decode()
    except:
        return data


def detect_card_brand(card_number):
    """Detect card brand from card number"""
    card_number = card_number.replace(' ', '').replace('-', '')
    if card_number.startswith('4'):
        return 'Visa'
    elif card_number.startswith(('51', '52', '53', '54', '55')):
        return 'Mastercard'
    elif card_number.startswith(('34', '37')):
        return 'American Express'
    else:
        return 'Unknown'


@app.route('/seller/payment_methods', methods=['GET', 'POST'])
def seller_payment_methods():
    if 'user' not in session or not session['user'].get('is_seller'):
        return redirect(url_for('login'))

    seller_email = session['user']['email']

    if request.method == 'POST':
        try:
            data = request.get_json()
            payment_type = data.get('payment_type')
            is_primary = data.get('is_primary') == 'true'

            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

                # If setting as primary, remove primary flag from others
                if is_primary:
                    cursor.execute('''
                        UPDATE seller_payment_methods 
                        SET is_primary = FALSE 
                        WHERE seller_email = %s
                    ''', (seller_email,))

                if payment_type == 'bank':
                    cursor.execute('''
                        INSERT INTO seller_payment_methods 
                        (seller_email, payment_type, account_name, account_number, 
                         bank_name, routing_number, is_primary)
                        VALUES (%s, %s, %s, %s, %s, %s,%s)
                    ''', (
                        seller_email, payment_type,
                        data.get('account_name'),
                        encrypt_data(data.get('account_number')),
                        data.get('bank_name'),
                        data.get('routing_number', ''),
                        is_primary
                    ))

                elif payment_type == 'card':
                    card_number = data.get('card_number', '').replace(' ', '')
                    cursor.execute('''
                        INSERT INTO seller_payment_methods 
                        (seller_email, payment_type, account_name, card_last_four, card_brand, 
                         payment_provider, is_primary)
                        VALUES (%s, %s, %s, %s, %s, %s,%s)
                    ''', (
                        seller_email, payment_type,
                        data.get('cardholder_name'),
                        card_number[-4:] if len(card_number) >= 4 else card_number,
                        detect_card_brand(card_number),
                        'stripe',
                        is_primary
                    ))

                elif payment_type == 'mobile':
                    cursor.execute('''
                        INSERT INTO seller_payment_methods 
                        (seller_email, payment_type, account_name, mobile_number, 
                         mobile_provider, is_primary)
                        VALUES (%s, %s, %s, %s, %s,%s)
                    ''', (
                        seller_email, payment_type,
                        data.get('account_name'),
                        data.get('mobile_number'),
                        data.get('mobile_provider'),
                        is_primary
                    ))

                conn.commit()
                return jsonify({'success': True, 'message': 'Payment method added successfully'})

        except Exception as e:
            logger.error(f"Error adding payment method: {e}")
            return jsonify({'success': False, 'message': 'Error adding payment method'})

    # GET request - return payment methods as JSON
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('''
                SELECT id, payment_type, account_name, account_number, bank_name,
                       routing_number, card_last_four, card_brand, mobile_number, 
                       mobile_provider, is_primary, is_verified, created_at
                FROM seller_payment_methods 
                WHERE seller_email = %s
                ORDER BY is_primary DESC, created_at DESC
            ''', (seller_email,))

            payment_methods = []
            for row in cursor.fetchall():
                method = dict(row)
                # Decrypt sensitive data for display
                if method['account_number']:
                    method['account_number'] = decrypt_data(method['account_number'])
                payment_methods.append(method)

        return jsonify({'success': True, 'payment_methods': payment_methods})

    except Exception as e:
        logger.error(f"Error getting payment methods: {e}")
        return jsonify({'success': False, 'message': 'Error loading payment methods'})


@app.route('/seller/payment_methods/<int:method_id>/delete', methods=['POST'])
def delete_payment_method(method_id):
    if 'user' not in session or not session['user'].get('is_seller'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    seller_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Check if this method is being used in pending withdrawals
            cursor.execute('''
                SELECT COUNT(*) as count FROM withdrawal_requests 
                WHERE seller_email = %s AND status = 'pending'
            ''', (seller_email,))

            pending_count = cursor.fetchone()['count']
            if pending_count > 0:
                return jsonify({
                    'success': False,
                    'message': 'Cannot delete payment method while you have pending withdrawals'
                })

            cursor.execute('''
                DELETE FROM seller_payment_methods 
                WHERE id = %s AND seller_email = %s
            ''', (method_id, seller_email))

            if cursor.rowcount > 0:
                conn.commit()
                return jsonify({'success': True, 'message': 'Payment method deleted'})
            else:
                return jsonify({'success': False, 'message': 'Payment method not found'})

    except Exception as e:
        logger.error(f"Error deleting payment method: {e}")
        return jsonify({'success': False, 'message': 'Error deleting payment method'})


@app.route('/seller/payment_methods/<int:method_id>/set_primary', methods=['POST'])
def set_primary_payment_method(method_id):
    if 'user' not in session or not session['user'].get('is_seller'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    seller_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Remove primary from all methods
            cursor.execute('''
                UPDATE seller_payment_methods 
                SET is_primary = FALSE 
                WHERE seller_email = %s
            ''', (seller_email,))

            # Set the selected method as primary
            cursor.execute('''
                UPDATE seller_payment_methods 
                SET is_primary = TRUE 
                WHERE id = %s AND seller_email = %s
            ''', (method_id, seller_email))

            if cursor.rowcount > 0:
                conn.commit()
                return jsonify({'success': True, 'message': 'Primary payment method updated'})
            else:
                return jsonify({'success': False, 'message': 'Payment method not found'})

    except Exception as e:
        logger.error(f"Error setting primary payment method: {e}")
        return jsonify({'success': False, 'message': 'Error updating payment method'})


@app.route('/seller_withdraw', methods=['POST'])
def seller_withdraw():
    """Enhanced withdrawal with payment method selection"""
    if 'user' not in session or not session['user'].get('email'):
        return jsonify({'success': False, 'message': 'Not logged in'})

    user_email = session['user']['email']

    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        payment_method_id = data.get('payment_method_id')

        if amount < 500:
            return jsonify({'success': False, 'message': 'Minimum withdrawal is J$500'})

        if not payment_method_id:
            return jsonify({'success': False, 'message': 'Please select a payment method'})

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Verify user is a seller
            cursor.execute('SELECT is_seller FROM users WHERE email = %s', (user_email,))
            user = cursor.fetchone()
            if not user or not user['is_seller']:
                return jsonify({'success': False, 'message': 'Unauthorized'})

            # Get payment method details
            cursor.execute('''
                SELECT * FROM seller_payment_methods 
                WHERE id = %s AND seller_email = %s
            ''', (payment_method_id, user_email))

            payment_method = cursor.fetchone()
            if not payment_method:
                return jsonify({'success': False, 'message': 'Invalid payment method'})

            # Get current available balance
            cursor.execute('''
                SELECT balance FROM seller_finances WHERE seller_email = %s
            ''', (user_email,))

            balance_row = cursor.fetchone()
            if not balance_row:
                return jsonify({'success': False, 'message': 'No financial record found'})

            current_balance = float(balance_row['balance'])

            if current_balance < amount:
                return jsonify({
                    'success': False,
                    'message': f'Insufficient balance. Available: J${current_balance:,.2f}'
                })

            # Calculate fees based on payment method type
            fee = 0.0
            processing_time = ''

            if payment_method['payment_type'] == 'card':
                fee = amount * 0.02  # 2% for cards
                processing_time = 'Instant'
            elif payment_method['payment_type'] == 'mobile':
                fee = amount * 0.01  # 1% for mobile money
                processing_time = 'Within minutes'
            else:  # bank
                fee = 0.0  # Free for bank transfers
                processing_time = '1-3 business days'

            net_amount = amount - fee

            # Create transaction record
            transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

            cursor.execute('''
                INSERT INTO payment_transactions 
                (transaction_id, seller_email, amount, fee, net_amount, transaction_type, 
                 payment_method_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s,%s)
            ''', (transaction_id, user_email, amount, fee, net_amount, 'withdrawal',
                  payment_method_id, 'processing'))

            # Create withdrawal request
            cursor.execute('''
                INSERT INTO withdrawal_requests 
                (seller_email, amount, fee, net_amount, method, status, request_date, processing_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s,%s)
            ''', (user_email, amount, fee, net_amount, payment_method['payment_type'], 'pending',
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S'), processing_time))

            # Update seller balance
            new_balance = current_balance - amount
            cursor.execute('''
                UPDATE seller_finances 
                SET balance = %s, pending_withdrawals = pending_withdrawals + ?
                WHERE seller_email = %s
            ''', (new_balance, amount, user_email))

            conn.commit()

            # Simulate processing completion after 5 seconds
            def complete_withdrawal():
                import time
                time.sleep(5)

                try:
                    with get_db() as conn:
                        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                        cursor.execute('''
                            UPDATE withdrawal_requests 
                            SET status = 'completed' 
                            WHERE seller_email = %s AND amount = %s AND status = 'pending'
                            ORDER BY request_date DESC LIMIT 1
                        ''', (user_email, amount))

                        cursor.execute('''
                            UPDATE payment_transactions 
                            SET status = 'completed', completed_at = %s
                            WHERE transaction_id = %s
                        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), transaction_id))

                        cursor.execute('''
                            UPDATE seller_finances 
                            SET pending_withdrawals = pending_withdrawals - ?
                            WHERE seller_email = %s
                        ''', (amount, user_email))

                        conn.commit()
                        logger.info(f"Completed withdrawal for {user_email}: J${amount}")
                except Exception as e:
                    logger.error(f"Error completing withdrawal: {e}")

            # Start background task
            import threading
            threading.Thread(target=complete_withdrawal, daemon=True).start()

            return jsonify({
                'success': True,
                'message': f'Withdrawal of J${net_amount:,.2f} initiated successfully! Processing time: {processing_time}',
                'transaction_id': transaction_id,
                'withdrawal_info': {
                    'amount': amount,
                    'fee': fee,
                    'net_amount': net_amount,
                    'method': payment_method['payment_type'],
                    'processing_time': processing_time
                }
            })

    except Exception as e:
        logger.error(f"Error in seller_withdraw for {user_email}: {e}")
        return jsonify({'success': False, 'message': 'Withdrawal request failed'})


# Updated seller_financials route
@app.route('/seller_financials')
def seller_financials():
    """Get seller's financial data via AJAX"""
    if 'user' not in session or not session['user'].get('email'):
        return jsonify({'success': False, 'message': 'Not logged in'}), 401

    user_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Verify user is a seller
            cursor.execute('SELECT is_seller FROM users WHERE email = %s', (user_email,))
            user = cursor.fetchone()
            if not user or not user['is_seller']:
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403

            # Get current financial data
            cursor.execute('''
                SELECT balance, total_earnings, pending_withdrawals
                FROM seller_finances WHERE seller_email = %s
            ''', (user_email,))
            financial_data = cursor.fetchone()

            if not financial_data:
                return jsonify({'success': False, 'message': 'No financial data found'}), 404

            # Get products
            cursor.execute('''
                SELECT product_key, name, category, price, posted_date, sold, clicks, likes, image_url, description, amount
                FROM products 
                WHERE seller_email = %s
                ORDER BY posted_date DESC
            ''', (user_email,))
            products = []
            for row in cursor.fetchall():
                products.append({
                    'product_key': row['product_key'],
                    'name': row['name'],
                    'category': row['category'] or 'N/A',
                    'price': float(row['price']),
                    'posted_date': row['posted_date'] or 'N/A',
                    'sold': row['sold'] or 0,
                    'clicks': row['clicks'] or 0,
                    'likes': row['likes'] or 0,
                    'image_url': row['image_url'] or 'placeholder.jpg',
                    'description': row['description'] or 'No description available',
                    'amount': row['amount'] or 0,
                    'revenue': float(row['price']) * (row['sold'] or 0)
                })

            # Get withdrawal history
            cursor.execute('''
                SELECT id, method, amount, fee, net_amount, status, request_date, processing_time
                FROM withdrawal_requests 
                WHERE seller_email = %s
                ORDER BY request_date DESC
            ''', (user_email,))
            withdrawal_history = []
            for row in cursor.fetchall():
                withdrawal_history.append({
                    'id': row['id'],
                    'method': row['method'],
                    'amount': float(row['amount']),
                    'fee': float(row['fee'] or 0),
                    'net_amount': float(row['net_amount'] or 0),
                    'status': row['status'],
                    'request_date': row['request_date'],
                    'processing_time': row['processing_time']
                })

            # Get transactions
            transactions = []
            for product in products:
                if product['sold'] > 0:
                    transactions.append({
                        'type': 'sale',
                        'description': f"Sale: {product['name']} (x{product['sold']})",
                        'amount': product['revenue'],
                        'transaction_date': product['posted_date'],
                        'product_key': product['product_key']
                    })

            return jsonify({
                'success': True,
                'financial_data': {
                    'balance': float(financial_data['balance']),
                    'total_earnings': float(financial_data['total_earnings']),
                    'pending_withdrawals': float(financial_data['pending_withdrawals']),
                    'withdrawal_history': withdrawal_history,
                    'transactions': transactions
                },
                'products': products
            })

    except Exception as e:
        logger.error(f"Error in seller_financials for {user_email}: {e}")
        return jsonify({'success': False, 'message': 'Error fetching financial data'}), 500

@app.route('/seller_dashboard/data')
def seller_dashboard_data():
    try:
        if 'user' not in session or not session['user'].get('email') or not session['user'].get('is_seller'):
            logger.warning("Unauthorized access to seller_dashboard/data")
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401

        seller_email = session['user']['email']
        logger.info(f"Accessing seller_dashboard/data for {seller_email}")

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Verify user is a seller (redundant but safe)
            cursor.execute('SELECT is_seller FROM users WHERE email = %s', (seller_email,))
            user = cursor.fetchone()
            if not user or not user['is_seller']:
                logger.warning(f"User {seller_email} is not a seller")
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401

        period = request.args.get('period', 'daily')
        product_key = request.args.get('product_key')

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            if period == 'yearly':
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
                date_format = '%Y'
                group_by = 'strftime("%Y", sale_date)'
                cart_group_by = 'strftime("%Y", cart_date)'
                likes_group_by = 'strftime("%Y", created_at)'
            elif period == 'monthly':
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
                date_format = '%Y-%m'
                group_by = 'strftime("%Y-%m", sale_date)'
                cart_group_by = 'strftime("%Y-%m", cart_date)'
                likes_group_by = 'strftime("%Y-%m", created_at)'
            else:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                date_format = '%Y-%m-%d'
                group_by = 'DATE(sale_date)'
                cart_group_by = 'DATE(cart_date)'
                likes_group_by = 'DATE(created_at)'

            periods = []
            if period == 'yearly':
                for i in range(1):
                    periods.append((datetime.now() - timedelta(days=365*i)).strftime('%Y'))
            elif period == 'monthly':
                for i in range(12):
                    periods.append((datetime.now() - timedelta(days=30*i)).strftime('%Y-%m'))
            else:
                for i in range(30):
                    periods.append((datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'))
            periods.sort()

            cursor.execute(f'''
                SELECT {group_by} as period, SUM(quantity) as units_sold
                FROM sales_log
                WHERE seller_email = %s AND sale_date >= ? {'AND product_key = %s' if product_key else ''}
                GROUP BY period
                ORDER BY period
            ''', (seller_email, start_date, product_key) if product_key else (seller_email, start_date))
            sales_rows = cursor.fetchall()
            sales_data = {row['period']: row['units_sold'] or 0 for row in sales_rows}
            sales_labels = periods
            sales_data_list = [sales_data.get(period, 0) for period in periods]

            cursor.execute(f'''
                SELECT {cart_group_by} as period, SUM(quantity) as cart_count
                FROM cart_log cl
                JOIN products p ON cl.product_key = p.product_key
                WHERE p.seller_email = %s AND cl.cart_date >= ? {'AND cl.product_key = %s' if product_key else ''}
                GROUP BY period
                ORDER BY period
            ''', (seller_email, start_date, product_key) if product_key else (seller_email, start_date))
            cart_rows = cursor.fetchall()
            cart_data = {row['period']: row['cart_count'] or 0 for row in cart_rows}
            cart_labels = periods
            cart_data_list = [cart_data.get(period, 0) for period in periods]
            logger.info(f"Cart data for {period}: labels={cart_labels}, data={cart_data_list}")

            cursor.execute(f'''
                SELECT strftime("{date_format}", posted_date) as period, clicks as click_count
                FROM products
                WHERE seller_email = %s AND posted_date >= ? {'AND product_key = %s' if product_key else ''}
                GROUP BY period
                ORDER BY period
            ''', (seller_email, start_date, product_key) if product_key else (seller_email, start_date))
            clicks_rows = cursor.fetchall()
            clicks_data = {row['period']: row['click_count'] or 0 for row in clicks_rows}
            clicks_labels = periods
            clicks_data_list = [clicks_data.get(period, 0) for period in periods]

            cursor.execute(f'''
                SELECT {likes_group_by} as period, COUNT(ul.user_email) as like_count
                FROM user_likes ul
                JOIN products p ON ul.product_key = p.product_key
                WHERE p.seller_email = %s AND ul.created_at >= ? {'AND ul.product_key = %s' if product_key else ''}
                GROUP BY period
                ORDER BY period
            ''', (seller_email, start_date, product_key) if product_key else (seller_email, start_date))
            likes_rows = cursor.fetchall()
            likes_data = {row['period']: row['like_count'] or 0 for row in likes_rows}
            likes_labels = periods
            likes_data_list = [likes_data.get(period, 0) for period in periods]
            logger.info(f"Likes data for {period}: labels={likes_labels}, data={likes_data_list}")

            cursor.execute(f'''
                SELECT strftime("{date_format}", posted_date) as period, sold as sold_count
                FROM products
                WHERE seller_email = %s AND posted_date >= ? {'AND product_key = %s' if product_key else ''}
                GROUP BY period
                ORDER BY period
            ''', (seller_email, start_date, product_key) if product_key else (seller_email, start_date))
            sold_rows = cursor.fetchall()
            sold_data = {row['period']: row['sold_count'] or 0 for row in sold_rows}
            sold_labels = periods
            sold_data_list = [sold_data.get(period, 0) for period in periods]

            return jsonify({
                'success': True,
                'sales': {'labels': sales_labels, 'data': sales_data_list},
                'cart': {'labels': cart_labels, 'data': cart_data_list},
                'clicks': {'labels': clicks_labels, 'data': clicks_data_list},
                'likes': {'labels': likes_labels, 'data': likes_data_list},
                'sold': {'labels': sold_labels, 'data': sold_data_list}
            })
    except Exception as e:
        logger.error(f"Error in seller_dashboard_data for {seller_email}: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/seller_statistics')
def seller_statistics():
    """Get detailed statistics for seller analytics dashboard"""
    if 'user' not in session or not session['user'].get('is_seller', False):
        return jsonify({'success': False, 'message': 'Not authorized'}), 401

    seller_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all products with their stats
            cursor.execute('''
                SELECT product_key, name, price, sold, clicks, likes, image_url, posted_date
                FROM products
                WHERE seller_email = %s
                ORDER BY sold DESC
            ''', (seller_email,))

            products_raw = cursor.fetchall()
            products = []
            total_views = 0
            total_likes = 0
            total_sales = 0
            total_revenue = 0.0

            for row in products_raw:
                clicks = row['clicks'] or 0
                likes = row['likes'] or 0
                sold = row['sold'] or 0
                price = float(row['price'])
                revenue = sold * price

                total_views += clicks
                total_likes += likes
                total_sales += sold
                total_revenue += revenue

                # Handle posted_date - it might be a string or datetime object
                posted_date = row['posted_date']
                if posted_date:
                    if hasattr(posted_date, 'strftime'):
                        posted_date_str = posted_date.strftime('%Y-%m-%d')
                    else:
                        posted_date_str = str(posted_date)
                else:
                    posted_date_str = 'N/A'

                products.append({
                    'product_key': row['product_key'],
                    'name': row['name'],
                    'price': price,
                    'sold': sold,
                    'clicks': clicks,
                    'likes': likes,
                    'image_url': row['image_url'] or 'product-placeholder.svg',
                    'posted_date': posted_date_str
                })

            # Get sales over time (last 7 days)
            cursor.execute('''
                SELECT
                    DATE(sale_date) as date,
                    COUNT(*) as sales
                FROM sales_log
                WHERE seller_email = %s
                AND sale_date >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY DATE(sale_date)
                ORDER BY date ASC
            ''', (seller_email,))

            sales_over_time_raw = cursor.fetchall()

            # Fill in missing days with 0 sales
            from datetime import datetime, timedelta

            # Build sales dictionary handling both date objects and strings
            sales_dict = {}
            for row in sales_over_time_raw:
                date_val = row['date']
                if hasattr(date_val, 'strftime'):
                    date_key = date_val.strftime('%m/%d')
                else:
                    # If it's already a string, try to parse it
                    try:
                        date_obj = datetime.strptime(str(date_val), '%Y-%m-%d')
                        date_key = date_obj.strftime('%m/%d')
                    except:
                        date_key = str(date_val)
                sales_dict[date_key] = row['sales']

            sales_over_time = []
            for i in range(6, -1, -1):
                date = datetime.now() - timedelta(days=i)
                date_str = date.strftime('%m/%d')
                sales_over_time.append({
                    'date': date_str,
                    'sales': sales_dict.get(date_str, 0)
                })

            return jsonify({
                'success': True,
                'total_views': total_views,
                'total_likes': total_likes,
                'total_sales': total_sales,
                'total_revenue': total_revenue,
                'products': products,
                'sales_over_time': sales_over_time
            })

    except Exception as e:
        logger.error(f"Error in seller_statistics for {seller_email}: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/seller/notifications')
def get_seller_notifications():
    """Get notifications for the current seller"""
    if 'user' not in session or not session['user'].get('is_seller', False):
        return jsonify({'success': False, 'message': 'Not authorized'}), 401

    seller_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get unread notifications
            cursor.execute('''
                SELECT id, notification_type, product_key, product_name, buyer_email,
                       quantity, price, sale_date, order_id, is_read, created_at
                FROM seller_notifications
                WHERE seller_email = %s
                ORDER BY created_at DESC
                LIMIT 50
            ''', (seller_email,))

            notifications = []
            for row in cursor.fetchall():
                notifications.append({
                    'id': row['id'],
                    'type': row['notification_type'],
                    'product_key': row['product_key'],
                    'product_name': row['product_name'],
                    'buyer_email': row['buyer_email'],
                    'quantity': row['quantity'],
                    'price': row['price'],
                    'sale_date': row['sale_date'],
                    'order_id': row['order_id'],
                    'is_read': row['is_read'],
                    'created_at': row['created_at']
                })

            # Count unread notifications
            cursor.execute('SELECT COUNT(*) as unread_count FROM seller_notifications WHERE seller_email = %s AND is_read = FALSE', (seller_email,))
            unread_count = cursor.fetchone()['unread_count']

            return jsonify({
                'success': True,
                'notifications': notifications,
                'unread_count': unread_count
            })

    except Exception as e:
        logger.error(f"Error getting notifications for {seller_email}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/seller/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    if 'user' not in session or not session['user'].get('is_seller', False):
        return jsonify({'success': False, 'message': 'Not authorized'}), 401

    seller_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Update notification as read (verify it belongs to the seller)
            cursor.execute('''
                UPDATE seller_notifications
                SET is_read = true
                WHERE id = %s AND seller_email = %s
            ''', (notification_id, seller_email))

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Notification not found'}), 404

            conn.commit()
            return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error marking notification {notification_id} as read for {seller_email}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/seller/update_stock', methods=['POST'])
def update_product_stock():
    """Update product stock level"""
    if 'user' not in session or not session['user'].get('is_seller', False):
        return jsonify({'success': False, 'message': 'Not authorized'}), 401

    seller_email = session['user']['email']

    try:
        data = request.get_json()
        product_key = data.get('product_key')
        new_stock = data.get('stock')

        if not product_key or new_stock is None:
            return jsonify({'success': False, 'message': 'Product key and stock amount required'}), 400

        if new_stock < 0:
            return jsonify({'success': False, 'message': 'Stock cannot be negative'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Verify product belongs to seller
            cursor.execute('SELECT product_key, name FROM products WHERE product_key = %s AND seller_email = %s',
                          (product_key, seller_email))
            product = cursor.fetchone()

            if not product:
                return jsonify({'success': False, 'message': 'Product not found or not authorized'}), 404

            # Update stock
            cursor.execute('UPDATE products SET amount = %s WHERE product_key = %s AND seller_email = %s',
                          (new_stock, product_key, seller_email))

            conn.commit()

            logger.info(f"Seller {seller_email} updated stock for {product_key} to {new_stock}")

            return jsonify({'success': True, 'message': 'Stock updated successfully', 'new_stock': new_stock})

    except Exception as e:
        logger.error(f"Error updating stock for {seller_email}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/seller/check_low_stock', methods=['POST'])
def check_all_low_stock():
    """Check all products for low stock and create notifications"""
    if 'user' not in session or not session['user'].get('is_seller', False):
        return jsonify({'success': False, 'message': 'Not authorized'}), 401

    seller_email = session['user']['email']

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all products with low stock (2 or less) for this seller
            cursor.execute('''
                SELECT product_key, name, amount, seller_email
                FROM products
                WHERE seller_email = %s AND amount <= 2
            ''', (seller_email,))

            low_stock_products = cursor.fetchall()
            notifications_created = 0

            for product in low_stock_products:
                # Check if notification already exists for this product
                cursor.execute('''
                    SELECT id FROM seller_notifications
                    WHERE seller_email = %s AND product_key = %s AND notification_type = 'low_stock' AND is_read = FALSE
                ''', (seller_email, product['product_key']))

                existing_notification = cursor.fetchone()

                if not existing_notification:
                    # Create low stock notification
                    cursor.execute('''
                        INSERT INTO seller_notifications
                        (seller_email, notification_type, product_key, product_name, quantity, sale_date)
                        VALUES (%s, %s, %s, %s, %s,%s)
                    ''', (
                        seller_email,
                        'low_stock',
                        product['product_key'],
                        product['name'],
                        product['amount'],
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ))
                    notifications_created += 1

            conn.commit()

            return jsonify({
                'success': True,
                'message': f'Checked all products. Created {notifications_created} new low stock notifications.',
                'notifications_created': notifications_created
            })

    except Exception as e:
        logger.error(f"Error checking low stock for {seller_email}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/seller/<seller_email>')
def seller_store(seller_email):
    """Individual seller's store page"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get seller info - with safe column handling
            cursor.execute('''
                SELECT u.email, u.first_name, u.last_name, u.business_name, u.business_address,
                       u.profile_picture, u.store_logo, u.phone_number, u.parish,
                       sv.verification_status
                FROM users u
                LEFT JOIN seller_verification sv ON u.email = sv.seller_email
                WHERE u.email = %s AND u.is_seller = true
            ''', (seller_email,))

            seller = cursor.fetchone()
            if not seller:
                return render_template('404.html', error="Seller not found"), 404

            # Convert row to dict and handle None/NULL values properly
            seller_data = {}
            for key in seller.keys():
                value = seller[key]
                # Convert any Undefined or None to proper Python None
                seller_data[key] = value if value is not None else None

            # Try to get business_description separately (column might not exist)
            try:
                cursor.execute('''
                    SELECT business_description FROM users WHERE email = %s
                ''', (seller_email,))
                desc_result = cursor.fetchone()
                seller_data['business_description'] = desc_result['business_description'] if desc_result and \
                                                                                             desc_result[
                                                                                                 'business_description'] else 'Discover amazing products carefully curated just for you. We\'re committed to providing the highest quality items with exceptional customer service. Browse our collection and find exactly what you\'re looking for!'
            except Exception as e:
                # Column doesn't exist or error - use default
                logger.warning(f"Could not get business_description: {e}")
                seller_data[
                    'business_description'] = 'Discover amazing products carefully curated just for you. We\'re committed to providing the highest quality items with exceptional customer service. Browse our collection and find exactly what you\'re looking for!'

            # Get seller stats
            cursor.execute('''
                SELECT 
                    AVG(sr.rating) as avg_rating, 
                    COUNT(sr.rating) as rating_count,
                    COUNT(DISTINCT p.product_key) as product_count,
                    SUM(p.sold) as total_sales
                FROM users u
                LEFT JOIN seller_ratings sr ON u.email = sr.seller_email
                LEFT JOIN products p ON u.email = p.seller_email
                WHERE u.email = %s
                GROUP BY u.email
            ''', (seller_email,))

            stats = cursor.fetchone()
            if stats:
                seller_data['avg_rating'] = round(float(stats['avg_rating'] or 0), 1)
                seller_data['rating_count'] = stats['rating_count'] or 0
                seller_data['product_count'] = stats['product_count'] or 0
                seller_data['total_sales'] = stats['total_sales'] or 0
            else:
                seller_data['avg_rating'] = 0
                seller_data['rating_count'] = 0
                seller_data['product_count'] = 0
                seller_data['total_sales'] = 0

            seller_data['join_date'] = '2024'

            # Ensure all required fields exist with safe defaults
            seller_data['first_name'] = seller_data.get('first_name') or ''
            seller_data['last_name'] = seller_data.get('last_name') or ''
            seller_data['business_name'] = seller_data.get('business_name') or 'Seller Store'
            seller_data['profile_picture'] = seller_data.get('profile_picture') or None
            seller_data['phone_number'] = seller_data.get('phone_number') or ''
            seller_data['parish'] = seller_data.get('parish') or ''
            seller_data['business_address'] = seller_data.get('business_address') or ''
            # Check verification status - only 'approved' shows verified badge
            actual_verification_status = seller_data.get('verification_status')
            seller_data['verification_status'] = actual_verification_status or 'unverified'
            seller_data['is_verified'] = actual_verification_status == 'approved'

            # Get seller's products
            cursor.execute('''
                SELECT * FROM products
                WHERE seller_email = %s
                ORDER BY posted_date DESC, clicks DESC
            ''', (seller_email,))

            products = []
            categories = set()

            # Check if seller is flagged
            seller_is_flagged = is_user_flagged(seller_email)

            # Get all product rows
            all_products = cursor.fetchall()

            # If seller is NOT flagged, show products (is_user_flagged returns None if not flagged, dict if flagged)
            if seller_is_flagged is None:
                for row in all_products:
                    product_data = dict(row)
                    try:
                        product_data['image_urls'] = json.loads(product_data['image_urls']) if product_data.get(
                            'image_urls') else []
                        product_data['sizes'] = json.loads(product_data['sizes']) if product_data.get('sizes') else {}
                    except:
                        product_data['image_urls'] = [product_data['image_url']] if product_data.get(
                            'image_url') else []
                        product_data['sizes'] = {}

                    products.append(product_data)
                    if product_data.get('category'):
                        categories.add(product_data['category'])

            product_categories = sorted(list(categories))

        # Get cart data safely - handle case where user might not have a cart (e.g., admin viewing)
        try:
            cart_data = get_cart_items()
        except Exception as cart_error:
            logger.warning(f"Could not load cart data: {cart_error}")
            cart_data = {
                'items': [],
                'total': 0,
                'discount': 0,
                'cart_item_count': 0
            }

        return render_template(
            'seller_store_page.html',
            seller=seller_data,
            products=products,
            product_categories=product_categories,
            cart_items=cart_data['items'],
            cart_total=cart_data['total'],
            discount=cart_data['discount'],
            user=session.get('user'),
            cart_item_count=cart_data['cart_item_count']
        )
    except Exception as e:
        logger.error(f"Error in seller_store: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return render_template('404.html', error=f"Error loading store: {str(e)}"), 500


@app.route('/product_listing')
def product_listing():
    if 'user' not in session:
        return redirect(url_for('login'))
    seller_email = session['user']['email']
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s AND is_seller = %s', (seller_email, True))
        if not cursor.fetchone():
            return redirect(url_for('login'))
        cursor.execute('SELECT * FROM products WHERE seller_email = %s', (seller_email,))
        seller_products = {
            row['product_key']: dict(row, image_urls=json.loads(row['image_urls']), sizes=json.loads(row['sizes']))
            for row in cursor.fetchall()}
    cart_data = get_cart_items()
    return render_template(
        'product_listing.html',
        seller_products=seller_products,
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )


@app.route('/seller/new_product', methods=['GET', 'POST'])
def new_product():
    if 'user' not in session:
        return redirect(url_for('login'))

    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s AND is_seller = %s', (session['user']['email'], True))
        user = cursor.fetchone()
        if not user:
            return redirect(url_for('login'))

        # Check if seller is verified from seller_verification table
        cursor.execute('SELECT verification_status FROM seller_verification WHERE seller_email = %s', (session['user']['email'],))
        verification = cursor.fetchone()

        if not verification:
            flash('You must complete seller verification before posting products.', 'error')
            return redirect(url_for('seller_verification'))

        if verification['verification_status'] != 'approved':
            if verification['verification_status'] == 'pending_review':
                return redirect(url_for('seller_verification_pending'))
            elif verification['verification_status'] == 'rejected':
                return redirect(url_for('seller_verification_rejected'))
            else:
                flash('You must complete seller verification before posting products.', 'error')
                return redirect(url_for('seller_verification'))

        if request.method == 'POST':
            try:
                name = request.form['name']
                category = request.form['category']
                description = request.form['description']
                brand = request.form['brand']
                parish = request.form['parish']
                original_cost = float(request.form['original_cost'])
                selling_price = float(request.form['selling_price'])

                # SHIPPING: Get shipping method and add cost to price
                shipping_method = request.form.get('shipping_method', 'jamaica_post')
                shipping_costs = {
                    'knutsford': 650,
                    'jamaica_post': 400,
                    'local_delivery': 300
                }
                shipping_cost = shipping_costs.get(shipping_method, 400)

                # Add shipping to selling price (buyers see "FREE SHIPPING")
                final_price = selling_price + shipping_cost

                # COD: Check if seller enabled COD for this product
                # Only allow if admin has enabled COD for this seller
                cod_available = False
                if user.get('cod_enabled', False):
                    cod_available = request.form.get('cod_available') == 'true'

                colors = request.form.getlist('colors[]')
                sizes = {}

                # DEBUG: Log what we received
                logger.info(f"DEBUG - Colors received: {colors}")
                logger.info(f"DEBUG - Category: {category}")

                for color in colors:
                    if color and color.strip():  # Check if color is not empty or whitespace
                        color = color.strip()  # Remove any whitespace
                        if category == 'Shoes':
                            size_list = request.form.getlist(f'sizes_{color}[]')
                            logger.info(f"DEBUG - Sizes for {color}: {size_list}")
                            if size_list:
                                sizes[color] = [size.strip() for size in size_list if size and size.strip()]
                        else:
                            size = request.form.get(f'sizes_{color}', '')
                            logger.info(f"DEBUG - Size for {color}: {size}")
                            if size and size.strip():
                                sizes[color] = size.strip()

                # DEBUG: Log final sizes dictionary
                logger.info(f"DEBUG - Final sizes dict: {sizes}")

                # If no colors/sizes were added, create a default entry
                if not sizes:
                    logger.warning("No colors/sizes provided - using default 'One Size'")
                    sizes = {"Default": "One Size"}

                image_urls = []
                video_urls = []
                video_url = None

                # Validate first upload is an image
                first_file = request.files.get('image_0')
                if first_file and first_file.filename:
                    if allowed_video(first_file.filename):
                        cart_data = get_cart_items()
                        return render_template('new_product.html',
                                               user=session.get('user'),
                                               parishes=PARISHES,
                                               error="First upload must be an image, not a video",
                                               cart_total=cart_data['total'],
                                               discount=cart_data['discount'],
                                               cart_item_count=cart_data['cart_item_count'])

                for i in range(5):
                    file_key = f'image_{i}'
                    if file_key in request.files and request.files[file_key].filename:
                        file = request.files[file_key]
                        if file:
                            filename = secure_filename(file.filename)
                            # Check if it's a video or image
                            if allowed_video(file.filename):
                                # It's a video - save it and store as video_url (only first video)
                                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                                if not video_url:  # Only save first video
                                    video_url = f"uploads/{filename}"
                                video_urls.append(f"uploads/{filename}")
                            elif allowed_file(file.filename):
                                # It's an image
                                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                                image_urls.append(f"uploads/{filename}")

                # Combine: images first, then videos at the end (like Amazon)
                all_media = image_urls + video_urls

                if not all_media:
                    cart_data = get_cart_items()
                    return render_template('new_product.html',
                                           user=session.get('user'),
                                           parishes=PARISHES,
                                           error="At least one image is required",
                                           cart_total=cart_data['total'],
                                           discount=cart_data['discount'],
                                           cart_item_count=cart_data['cart_item_count'])

                # Ensure image_url is always an image (never a video)
                main_image = all_media[0]
                for media in all_media:
                    if not media.endswith(('.mp4', '.webm', '.mov')):
                        main_image = media
                        break

                roi = ((final_price - original_cost) / original_cost) * 100 if original_cost > 0 else 0
                product_key = f"{name} - {final_price} JMD"

                cursor.execute('SELECT product_key FROM products WHERE product_key = %s', (product_key,))
                if cursor.fetchone():
                    product_key = f"{name} - {final_price} JMD - {datetime.now().strftime('%s')}"

                # Add shipping columns if they don't exist (migration)
                try:
                    cursor.execute('''
                        ALTER TABLE products
                        ADD COLUMN IF NOT EXISTS shipping_method VARCHAR(50),
                        ADD COLUMN IF NOT EXISTS base_price DECIMAL(10,2),
                        ADD COLUMN IF NOT EXISTS shipping_cost DECIMAL(10,2)
                    ''')
                except:
                    pass  # Columns might already exist

                # New products start with 0 sold, 0 views, 0 likes
                # These will increment as people view, like, and purchase

                cursor.execute('''
                    INSERT INTO products (product_key, name, price, description, image_url, image_urls, shipping, brand, category,
                                        original_cost, roi, sizes, seller_email, sold, clicks, likes, posted_date, amount,
                                        shipping_method, base_price, shipping_cost, video_url, cod_available)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    product_key, name, final_price, description, main_image, json.dumps(all_media),
                    parish, brand, category, original_cost, roi, json.dumps(sizes),
                    session['user']['email'], 0, 0, 0, datetime.now().strftime('%Y-%m-%d'), 10,
                    shipping_method, selling_price, shipping_cost, video_url, cod_available
                ))
                conn.commit()
                return redirect(url_for('seller_dashboard'))

            except Exception as e:
                logger.error(f"Error in new_product POST: {e}")
                cart_data = get_cart_items()
                return render_template('new_product.html',
                                       user=session.get('user'),
                                       parishes=PARISHES,
                                       error="An error occurred while creating the product. Please try again.",
                                       cart_total=cart_data['total'],
                                       discount=cart_data['discount'],
                                       cart_item_count=cart_data['cart_item_count'])

    # GET request - render the form
    cart_data = get_cart_items()
    return render_template(
        'new_product.html',
        user=dict(user) if user else session.get('user'),
        parishes=PARISHES,
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )


@app.route('/agent/verifications/all')
def agent_get_all_verifications():
    """Get all seller verifications for agent dashboard"""
    if 'user' not in session or not session['user'].get('is_support'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            cursor.execute('''
                   SELECT sv.*, u.first_name, u.last_name, u.business_name, u.phone_number,
                          COALESCE(
                              CASE
                                  WHEN u.last_name IS NULL OR u.last_name = 'None' OR u.last_name = ''
                                  THEN u.first_name
                                  ELSE u.first_name || ' ' || u.last_name
                              END,
                              u.business_name,
                              'N/A'
                          ) as seller_name
                   FROM seller_verification sv
                   JOIN users u ON sv.seller_email = u.email
                   ORDER BY sv.submitted_at DESC
               ''')

            verifications = []
            for row in cursor.fetchall():
                verification = dict(row)
                verifications.append(verification)

            return jsonify({
                'success': True,
                'verifications': verifications
            })

    except Exception as e:
        logger.error(f"Error getting verifications for agent: {e}")
        return jsonify({'success': False, 'message': 'Error loading verifications'}), 500


@app.route('/agent/verifications/pending')
def agent_get_pending_verifications():
    """Get pending seller verifications"""
    if 'user' not in session or not session['user'].get('is_support'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            cursor.execute('''
                   SELECT sv.*, u.first_name, u.last_name, u.business_name, u.phone_number,
                          COALESCE(
                              CASE
                                  WHEN u.last_name IS NULL OR u.last_name = 'None' OR u.last_name = ''
                                  THEN u.first_name
                                  ELSE u.first_name || ' ' || u.last_name
                              END,
                              u.business_name,
                              'N/A'
                          ) as seller_name
                   FROM seller_verification sv
                   JOIN users u ON sv.seller_email = u.email
                   WHERE sv.verification_status = 'pending_review'
                   ORDER BY sv.submitted_at ASC
               ''')

            verifications = []
            for row in cursor.fetchall():
                verification = dict(row)
                verifications.append(verification)

            return jsonify({
                'success': True,
                'verifications': verifications
            })

    except Exception as e:
        logger.error(f"Error getting pending verifications: {e}")
        return jsonify({'success': False, 'message': 'Error loading verifications'}), 500


@app.route('/agent/verifications/<seller_email>')
def agent_get_verification_details(seller_email):
    """Get detailed verification information"""
    if 'user' not in session or not session['user'].get('is_support'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            cursor.execute('''
                   SELECT sv.*, u.first_name, u.last_name, u.business_name, u.phone_number,
                          COALESCE(
                              CASE
                                  WHEN u.last_name IS NULL OR u.last_name = 'None' OR u.last_name = ''
                                  THEN u.first_name
                                  ELSE u.first_name || ' ' || u.last_name
                              END,
                              u.business_name,
                              'N/A'
                          ) as seller_name
                   FROM seller_verification sv
                   JOIN users u ON sv.seller_email = u.email
                   WHERE sv.seller_email = %s
               ''', (seller_email,))

            verification = cursor.fetchone()
            if not verification:
                return jsonify({'success': False, 'message': 'Verification not found'}), 404

            return jsonify({
                'success': True,
                'verification': dict(verification)
            })

    except Exception as e:
        logger.error(f"Error getting verification details: {e}")
        return jsonify({'success': False, 'message': 'Error loading verification details'}), 500


@app.route('/admin/verifications/approve', methods=['POST'])
def approve_seller_verification():
    """Approve a seller verification - ADMIN or SUPPORT AGENT"""
    # Allow both admin and support agents
    is_admin = 'admin' in session or 'admin_user' in session
    is_support = 'user' in session and session['user'].get('is_support')

    if not (is_admin or is_support):
        return jsonify({'success': False, 'message': 'Unauthorized - Admin or Support access required'}), 401

    try:
        data = request.get_json()
        seller_email = data.get('seller_email')

        if not seller_email:
            return jsonify({'success': False, 'message': 'Seller email required'}), 400

        # Get reviewer email
        if is_admin:
            reviewer_email = session.get('admin_user', {}).get('email') or session.get('admin', {}).get('email')
        else:
            reviewer_email = session['user']['email']

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Update verification status
            cursor.execute('''
                   UPDATE seller_verification
                   SET verification_status = 'approved',
                       reviewed_at = CURRENT_TIMESTAMP,
                       reviewed_by = %s
                   WHERE seller_email = %s
               ''', (reviewer_email, seller_email))

            conn.commit()

            logger.info(f"Seller verification approved: {seller_email} by {reviewer_email}")

            return jsonify({
                'success': True,
                'message': 'Seller verification approved successfully'
            })

    except Exception as e:
        logger.error(f"Error approving verification: {e}")
        return jsonify({'success': False, 'message': 'Error approving verification'}), 500


@app.route('/admin/verifications/reject', methods=['POST'])
def reject_seller_verification():
    """Reject a seller verification - ADMIN or SUPPORT AGENT"""
    # Allow both admin and support agents
    is_admin = 'admin' in session or 'admin_user' in session
    is_support = 'user' in session and session['user'].get('is_support')

    if not (is_admin or is_support):
        return jsonify({'success': False, 'message': 'Unauthorized - Admin or Support access required'}), 401

    try:
        data = request.get_json()
        seller_email = data.get('seller_email')
        reason = data.get('reason')

        if not seller_email or not reason:
            return jsonify({'success': False, 'message': 'Seller email and reason required'}), 400

        # Get reviewer email
        if is_admin:
            reviewer_email = session.get('admin_user', {}).get('email') or session.get('admin', {}).get('email')
        else:
            reviewer_email = session['user']['email']

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Update verification status
            cursor.execute('''
                   UPDATE seller_verification
                   SET verification_status = 'rejected',
                       reviewed_at = CURRENT_TIMESTAMP,
                       reviewed_by = %s,
                       rejection_reason = %s
                   WHERE seller_email = %s
               ''', (reviewer_email, reason, seller_email))

            conn.commit()

            logger.info(f"Seller verification rejected: {seller_email} by {reviewer_email}")

            return jsonify({
                'success': True,
                'message': 'Seller verification rejected'
            })

    except Exception as e:
        logger.error(f"Error rejecting verification: {e}")
        return jsonify({'success': False, 'message': 'Error rejecting verification'}), 500

@app.route('/seller/edit_product/<product_key>', methods=['GET', 'POST'])
def edit_product(product_key):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s AND is_seller = %s', (session['user']['email'], True))
        if not cursor.fetchone():
            return redirect(url_for('login'))
        cursor.execute('SELECT * FROM products WHERE product_key = %s AND seller_email = %s',
                       (product_key, session['user']['email']))
        product = cursor.fetchone()
        if not product:
            return render_template('404.html', error="Product not found or unauthorized"), 404
        product = dict(product, image_urls=json.loads(product['image_urls']), sizes=json.loads(product['sizes']))
        if request.method == 'POST':
            name = request.form['name']
            category = request.form['category']
            description = request.form['description']
            brand = request.form['brand']
            parish = request.form['parish']
            original_cost = float(request.form['original_cost'])
            selling_price = float(request.form['selling_price'])

            # SHIPPING: Get shipping method and add cost to price
            shipping_method = request.form.get('shipping_method', product.get('shipping_method', 'jamaica_post'))
            shipping_costs = {
                'knutsford': 650,
                'jamaica_post': 400,
                'local_delivery': 300
            }
            shipping_cost = shipping_costs.get(shipping_method, 400)

            # Add shipping to selling price (buyers see "FREE SHIPPING")
            final_price = selling_price + shipping_cost

            colors = request.form.getlist('colors[]')
            sizes = {}

            # DEBUG: Log what we received for edit
            logger.info(f"DEBUG EDIT - Colors received: {colors}")
            logger.info(f"DEBUG EDIT - Category: {category}")

            for color in colors:
                if color and color.strip():  # Check if color is not empty or whitespace
                    color = color.strip()  # Remove any whitespace
                    if category == 'Shoes':
                        size_list = request.form.getlist(f'sizes_{color}[]')
                        logger.info(f"DEBUG EDIT - Sizes for {color}: {size_list}")
                        if size_list:
                            sizes[color] = [size.strip() for size in size_list if size and size.strip()]
                    else:
                        size = request.form.get(f'sizes_{color}', '')
                        logger.info(f"DEBUG EDIT - Size for {color}: {size}")
                        if size and size.strip():
                            sizes[color] = size.strip()

            # DEBUG: Log final sizes dictionary
            logger.info(f"DEBUG EDIT - Final sizes dict: {sizes}")

            # If no colors/sizes, keep existing or use default
            if not sizes and product.get('sizes'):
                logger.warning("No new colors/sizes - keeping existing")
                sizes = product['sizes']
            elif not sizes:
                logger.warning("No colors/sizes - using default")
                sizes = {"Default": "One Size"}
            # Handle image/video updates - merge old and new uploads
            old_image_urls = product['image_urls']
            all_media = []
            video_url = product.get('video_url')  # Keep existing video if no new one uploaded
            new_video_found = False

            # Validate first upload is an image (if a new file is uploaded)
            first_file = request.files.get('image_0')
            if first_file and first_file.filename:
                if allowed_video(first_file.filename):
                    cart_data = get_cart_items()
                    return render_template(
                        'new_product.html',
                        user=session.get('user'),
                        parishes=PARISHES,
                        product=product,
                        product_key=product_key,
                        error="First upload must be an image, not a video",
                        cart_total=cart_data['total'],
                        discount=cart_data['discount'],
                        cart_item_count=cart_data['cart_item_count']
                    )

            # Process each upload slot - keep old if no new file uploaded
            for i in range(5):
                file_key = f'image_{i}'
                if file_key in request.files and request.files[file_key].filename:
                    # New file uploaded in this slot
                    file = request.files[file_key]
                    if file:
                        filename = secure_filename(file.filename)
                        if allowed_video(file.filename):
                            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                            if not new_video_found:  # Only set first video as main video_url
                                video_url = f"uploads/{filename}"
                                new_video_found = True
                            all_media.append(f"uploads/{filename}")
                        elif allowed_file(file.filename):
                            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                            all_media.append(f"uploads/{filename}")
                else:
                    # No new file - keep existing file from this slot if it exists
                    if i < len(old_image_urls):
                        all_media.append(old_image_urls[i])

            if not all_media:
                cart_data = get_cart_items()
                return render_template(
                    'new_product.html',
                    user=session.get('user'),
                    parishes=PARISHES,
                    product=product,
                    product_key=product_key,
                    error="At least one image is required",
                    cart_total=cart_data['total'],
                    discount=cart_data['discount'],
                    cart_item_count=cart_data['cart_item_count']
                )

            # Ensure image_url is always an image (never a video)
            main_image = all_media[0]
            for media in all_media:
                if not media.endswith(('.mp4', '.webm', '.mov')):
                    main_image = media
                    break

            roi = ((final_price - original_cost) / original_cost) * 100 if original_cost > 0 else 0
            cursor.execute('''
                UPDATE products SET name = %s, price = %s, description = %s, image_url = %s, image_urls = %s, video_url = %s, shipping = %s,
                                  brand = %s, category = %s, original_cost = %s, roi = %s, sizes = %s, amount = %s,
                                  shipping_method = %s, base_price = %s, shipping_cost = %s
                WHERE product_key = %s AND seller_email = %s
            ''', (
                name, final_price, description, main_image, json.dumps(all_media), video_url, parish, brand, category,
                original_cost, roi, json.dumps(sizes), request.form.get('amount', product['amount'], type=int),
                shipping_method, selling_price, shipping_cost,
                product_key, session['user']['email']
            ))
            conn.commit()
            return redirect(url_for('seller_dashboard'))
    cart_data = get_cart_items()
    return render_template(
        'new_product.html',
        user=session.get('user'),
        parishes=PARISHES,
        product=product,
        product_key=product_key,
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )

@app.route('/seller/delete_product/<product_key>', methods=['POST'])
def delete_product(product_key):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s AND is_seller = %s', (session['user']['email'], True))
        if not cursor.fetchone():
            return redirect(url_for('login'))
        cursor.execute('DELETE FROM products WHERE product_key = %s AND seller_email = %s',
                       (product_key, session['user']['email']))
        conn.commit()
    return redirect(url_for('seller_dashboard'))

@app.route('/product/<product_key>')
def product(product_key):
    product_key = unquote(product_key.replace('+', ' ')).strip()
    with get_db() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
        cursor.execute('SELECT * FROM products WHERE product_key = %s', (product_key,))
        product = cursor.fetchone()
        if not product:
            cursor.execute('SELECT * FROM products WHERE LOWER(product_key) = LOWER(%s)', (product_key,))
            product = cursor.fetchone()
        if not product:
            return redirect(url_for('index'))
        product = dict(product, image_urls=json.loads(product['image_urls']), sizes=json.loads(product['sizes']))

        # Check if seller is flagged - if so, completely hide product
        # is_user_flagged returns None if not flagged, dict if flagged
        seller_flagged = is_user_flagged(product['seller_email'])
        if seller_flagged is not None:
            # Product is hidden - redirect to homepage
            return redirect(url_for('index'))

        cursor.execute('UPDATE products SET clicks = clicks + 1 WHERE product_key = %s', (product['product_key'],))

        # Track product view for personalization (PostgreSQL only, logged-in users)
        if DATABASE_TYPE == 'postgresql' and 'user' in session and session.get('user', {}).get('email'):
            try:
                track_product_view(
                    user_email=session['user']['email'],
                    product_key=product['product_key'],
                    category=product.get('category')
                )
            except Exception as e:
                logger.error(f"Error tracking product view: {e}")
                # Don't block the page if tracking fails
                pass

        cursor.execute('''
            SELECT u.business_name, u.business_address, sv.verification_status
            FROM users u
            LEFT JOIN seller_verification sv ON u.email = sv.seller_email
            WHERE u.email = %s
        ''', (product['seller_email'],))
        seller = cursor.fetchone()
        cursor.execute('''
            SELECT AVG(rating) as avg_rating, COUNT(rating) as rating_count
            FROM seller_ratings
            WHERE seller_email = %s
        ''', (product['seller_email'],))
        rating_info = cursor.fetchone()
        avg_rating = round(rating_info['avg_rating'], 1) if rating_info['avg_rating'] else 0
        rating_count = rating_info['rating_count'] if rating_info['rating_count'] else 0

        # Get product reviews
        cursor.execute('''
            SELECT pr.*, u.first_name, u.last_name
            FROM product_reviews pr
            JOIN users u ON pr.buyer_email = u.email
            WHERE pr.product_key = %s
            ORDER BY pr.created_at DESC
        ''', (product['product_key'],))
        product_reviews = cursor.fetchall()

        # Get average product rating
        cursor.execute('''
            SELECT AVG(rating) as avg_product_rating, COUNT(*) as product_review_count
            FROM product_reviews
            WHERE product_key = %s
        ''', (product['product_key'],))
        product_rating_info = cursor.fetchone()
        avg_product_rating = round(product_rating_info['avg_product_rating'], 1) if product_rating_info['avg_product_rating'] else 0
        product_review_count = product_rating_info['product_review_count'] or 0
        cursor.execute('''
            SELECT * FROM products
            WHERE category = %s AND product_key != %s
            ORDER BY clicks DESC
            LIMIT 4
        ''', (product['category'], product['product_key']))
        related_products = [
            dict(row, image_urls=json.loads(row['image_urls']), sizes=json.loads(row['sizes']))
            for row in cursor.fetchall()
        ]
        user_liked = False
        if 'user' in session:
            cursor.execute('''
                SELECT * FROM user_likes
                WHERE user_email = %s AND product_key = %s
            ''', (session['user']['email'], product['product_key']))
            user_liked = cursor.fetchone() is not None
        conn.commit()
    cart_data = get_cart_items()
    return render_template(
        'product.html',
        product=product,
        seller=seller,
        avg_rating=avg_rating,
        rating_count=rating_count,
        product_reviews=product_reviews,
        avg_product_rating=avg_product_rating,
        product_review_count=product_review_count,
        related_products=related_products,
        user_liked=user_liked,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        user=session.get('user'),
        cart_item_count=cart_data['cart_item_count']
    )


@app.route('/cart', methods=['GET', 'POST'])
def cart():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No JSON data provided'}), 400
            product_key = data.get('product_key')
            quantity = data.get('quantity', 1)
            size = data.get('size')
            color = data.get('color')
            if not product_key or quantity < 1:
                return jsonify({'success': False, 'message': 'Invalid product key or quantity'}), 400

            # Initialize cart in session if it doesn't exist
            if 'cart' not in session:
                session['cart'] = {}
            cart = session['cart']
            base_product_key = re.sub(r'\s*\([^)]+\)$', '', product_key).strip()

            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                cursor.execute('SELECT name, price, image_url, amount FROM products WHERE product_key = %s',
                               (base_product_key,))
                product = cursor.fetchone()
                if not product:
                    return jsonify({'success': False, 'message': 'Product not found'}), 404
                if product['amount'] < quantity:
                    return jsonify({'success': False, 'message': 'Not enough stock'}), 400

                cart_key = f"{product_key}"
                if size and color:
                    cart_key = f"{product_key} ({color}, {size})"
                elif color:
                    cart_key = f"{product_key} ({color})"

                if cart_key in cart:
                    cart[cart_key]['quantity'] = min(cart[cart_key]['quantity'] + quantity, product['amount'])
                else:
                    cart[cart_key] = {
                        'name': product['name'],
                        'price': product['price'],
                        'quantity': min(quantity, product['amount']),
                        'image_url': product['image_url'],
                        'size': size,
                        'color': color
                    }
                session['cart'] = cart
                session.modified = True

                # Log to cart_log if user is logged in
                if 'user' in session:
                    cursor.execute('''
                        INSERT INTO cart_log (user_email, product_key, quantity, cart_date)
                        VALUES (%s, %s, %s,%s)
                    ''', (session['user']['email'], base_product_key, quantity, datetime.now().strftime('%Y-%m-%d')))
                    conn.commit()

                cart_data = get_cart_items()
                return jsonify({
                    'success': True,
                    'cart_items': cart_data['items'],
                    'cart_total': cart_data['total'],
                    'discount': cart_data['discount'],
                    'cart_item_count': cart_data['cart_item_count']
                })
        except Exception as e:
            logger.error(f"Error in cart POST: {e}\n{traceback.format_exc()}")
            return jsonify({'success': False, 'message': 'Error adding to cart'}), 500

    cart_data = get_cart_items()
    return render_template(
        'cart.html',
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        user=session.get('user'),
        cart_item_count=cart_data['cart_item_count']
    )


@app.route('/toggle_like/<path:product_key>', methods=['POST'])
def toggle_like(product_key):
    if 'user' not in session:
        logger.warning("Toggle like: User not logged in")
        return jsonify({'success': False, 'message': 'Login required'}), 401

    try:
        # Validate CSRF token
        from flask_wtf.csrf import validate_csrf

        csrf_token = request.headers.get('X-CSRFToken')
        if csrf_token:
            try:
                validate_csrf(csrf_token)
            except Exception as e:
                logger.warning(f"CSRF validation failed: {e}")
                return jsonify({'success': False, 'message': 'CSRF token invalid'}), 400

        product_key = unquote(product_key.replace('+', ' ')).strip()
        logger.info(f"Toggle like for product: {product_key} by user: {session['user']['email']}")

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('SELECT * FROM products WHERE product_key = %s', (product_key,))
            product = cursor.fetchone()
            if not product:
                logger.warning(f"Product not found: {product_key}")
                return jsonify({'success': False, 'message': 'Product not found'}), 404

            cursor.execute('''
                SELECT * FROM user_likes
                WHERE user_email = %s AND product_key = %s
            ''', (session['user']['email'], product_key))
            existing_like = cursor.fetchone()

            if existing_like:
                # Unlike
                logger.info(f"Unliking product: {product_key}")
                cursor.execute('''
                    DELETE FROM user_likes
                    WHERE user_email = %s AND product_key = %s
                ''', (session['user']['email'], product_key))
                cursor.execute(
                    'UPDATE products SET likes = CASE WHEN likes > 0 THEN likes - 1 ELSE 0 END WHERE product_key = %s',
                    (product_key,))
                conn.commit()

                # Get updated like count
                cursor.execute('SELECT likes FROM products WHERE product_key = %s', (product_key,))
                updated_product = cursor.fetchone()
                likes_count = updated_product['likes'] if updated_product else 0
                logger.info(f"Unlike successful. New count: {likes_count}")

                return jsonify({'success': True, 'liked': False, 'likes': likes_count})
            else:
                # Like
                logger.info(f"Liking product: {product_key}")
                cursor.execute('''
                    INSERT INTO user_likes (user_email, product_key, created_at)
                    VALUES (%s, %s, %s)
                ''', (session['user']['email'], product_key, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                cursor.execute('UPDATE products SET likes = likes + 1 WHERE product_key = %s', (product_key,))
                conn.commit()

                # Get updated like count
                cursor.execute('SELECT likes FROM products WHERE product_key = %s', (product_key,))
                updated_product = cursor.fetchone()
                likes_count = updated_product['likes'] if updated_product else 0
                logger.info(f"Like successful. New count: {likes_count}")

                return jsonify({'success': True, 'liked': True, 'likes': likes_count})

    except Exception as e:
        logger.error(f"Error in toggle_like: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': 'Error processing like'}), 500


@app.route('/cart/remove/<product_key>', methods=['POST'])
def remove_from_cart(product_key):
    product_key = unquote(product_key.replace('+', ' ')).strip()
    if 'cart' in session and product_key in session['cart']:
        del session['cart'][product_key]
        session.modified = True
    return redirect(url_for('cart'))


@app.route('/update_cart', methods=['POST'])
def update_cart():
    try:
        # Validate CSRF token
        from flask_wtf.csrf import validate_csrf

        csrf_token = request.headers.get('X-CSRFToken')
        if csrf_token:
            try:
                validate_csrf(csrf_token)
            except Exception as e:
                return jsonify({'success': False, 'message': 'CSRF token invalid'}), 400

        data = request.get_json()
        if not data or 'product_key' not in data or 'quantity' not in data:
            return jsonify({'success': False, 'message': 'Invalid or missing data'}), 400

        product_key = data['product_key']
        quantity = data['quantity']

        if quantity < 1:
            if product_key in session.get('cart', {}):
                del session['cart'][product_key]
                session.modified = True
            cart_data = get_cart_items()
            return jsonify({
                'success': True,
                'cart_items': cart_data['items'],
                'cart_total': cart_data['total'],
                'discount': cart_data['discount'],
                'cart_item_count': cart_data['cart_item_count']
            })

        base_product_key = re.sub(r'\s*\([^)]+\)$', '', product_key).strip()
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('SELECT amount FROM products WHERE product_key = %s', (base_product_key,))
            product = cursor.fetchone()
            if not product:
                return jsonify({'success': False, 'message': 'Product not found'}), 404

            if product['amount'] < quantity:
                return jsonify({'success': False, 'message': 'Not enough stock'}), 400

            if 'cart' in session and product_key in session['cart']:
                session['cart'][product_key]['quantity'] = min(quantity, product['amount'])
                session.modified = True

            cart_data = get_cart_items()
            return jsonify({
                'success': True,
                'cart_items': cart_data['items'],
                'cart_total': cart_data['total'],
                'discount': cart_data['discount'],
                'cart_item_count': cart_data['cart_item_count']
            })

    except Exception as e:
        logger.error(f"Error in update_cart: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': 'Error updating cart'}), 500


# Replace your existing checkout route with this fixed version

@app.route('/checkout', methods=['GET', 'POST'])
@limiter.limit("20 per hour")  # SECURITY: Max 20 checkouts per hour (prevents spam orders)
def checkout():
    import re
    import uuid
    from datetime import datetime, timedelta

    cart_data = get_cart_items()
    if not cart_data['items']:
        return redirect(url_for('cart'))

    if request.method == 'POST':
        try:
            # Check if this is a guest checkout
            is_guest = request.form.get('user_type') == 'guest'

            # LYNK INTEGRATION: Check if this is a Lynk payment
            is_lynk_payment = request.form.get('is_lynk_payment') == 'true'
            lynk_reference = request.form.get('lynk_reference', '').strip()

            if is_guest:
                # Guest checkout processing
                guest_email = request.form.get('guest_email')
                guest_first_name = request.form.get('guest_first_name')
                guest_last_name = request.form.get('guest_last_name')
                guest_phone = request.form.get('guest_phone')
                guest_address = request.form.get('guest_address')
                guest_parish = request.form.get('guest_parish')
                guest_post_office = request.form.get('guest_post_office')
                payment_method = request.form.get('payment_method')
                shipping_option = request.form.get('shipping_option', 'regular')

                # Validate guest data
                if not all([guest_email, guest_first_name, guest_last_name, guest_phone,
                            guest_address, guest_parish, guest_post_office, payment_method]):
                    return render_template(
                        'checkout.html',
                        error="All fields are required for guest checkout",
                        cart_items=cart_data['items'],
                        cart_total=cart_data['total'],
                        discount=cart_data['discount'],
                        user=None,
                        cart_item_count=cart_data['cart_item_count'],
                        parishes=PARISHES,
                        parish_post_offices=PARISH_POST_OFFICES,
                        post_offices=PARISH_POST_OFFICES.get(guest_parish, [])
                    )

                # LYNK VALIDATION: Check Lynk payment requirements
                if payment_method == 'lynk':
                    if not lynk_reference:
                        return render_template(
                            'checkout.html',
                            error="Lynk transaction reference is required for Lynk payments. Please complete the Lynk transfer and enter your transaction ID.",
                            cart_items=cart_data['items'],
                            cart_total=cart_data['total'],
                            discount=cart_data['discount'],
                            user=None,
                            cart_item_count=cart_data['cart_item_count'],
                            parishes=PARISHES,
                            parish_post_offices=PARISH_POST_OFFICES,
                            post_offices=PARISH_POST_OFFICES.get(guest_parish, [])
                        )

                    # Validate Lynk reference format (basic validation)
                    if len(lynk_reference) < 5:
                        return render_template(
                            'checkout.html',
                            error="Please enter a valid Lynk transaction reference (at least 5 characters)",
                            cart_items=cart_data['items'],
                            cart_total=cart_data['total'],
                            discount=cart_data['discount'],
                            user=None,
                            cart_item_count=cart_data['cart_item_count'],
                            parishes=PARISHES,
                            parish_post_offices=PARISH_POST_OFFICES,
                            post_offices=PARISH_POST_OFFICES.get(guest_parish, [])
                        )

                # Validate email format
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_pattern, guest_email):
                    return render_template(
                        'checkout.html',
                        error="Please enter a valid email address",
                        cart_items=cart_data['items'],
                        cart_total=cart_data['total'],
                        discount=cart_data['discount'],
                        user=None,
                        cart_item_count=cart_data['cart_item_count'],
                        parishes=PARISHES,
                        parish_post_offices=PARISH_POST_OFFICES,
                        post_offices=PARISH_POST_OFFICES.get(guest_parish, [])
                    )

                # Calculate totals using new payment system (NO SHIPPING - included in product price)
                totals = calculate_order_totals(cart_data['total'], payment_method)
                final_total = totals['final_total'] - cart_data['discount']

                # LYNK LOGGING: Log Lynk payment for verification
                if payment_method == 'lynk':
                    logger.info(
                        f"LYNK PAYMENT - Guest Order - Reference: {lynk_reference}, Amount: J${final_total}, Email: {guest_email}")

                # Calculate estimated delivery (3-5 business days standard)
                delivery_days = 5
                estimated_delivery = (datetime.now() + timedelta(days=delivery_days)).strftime('%B %d, %Y')

                # Define shipping and tax (shipping is included in product prices, tax is platform fee)
                shipping_fee = 0  # Shipping is FREE and included in product prices
                shipping_option = 'standard'  # Default shipping option
                tax = totals['platform_fee']  # Platform fee acts as "tax"

                with get_db() as conn:
                    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                    order_id = f"GUEST-{str(uuid.uuid4())[:8].upper()}"

                    # UPDATED: Create guest order with new payment system fields
                    cursor.execute('''
                        INSERT INTO orders (order_id, user_email, full_name, phone_number, address, parish, post_office,
                                          total, discount, payment_method, order_date, status,
                                          subtotal, platform_fee, payment_gateway_fee, total_before_gateway_fee,
                                          lynk_reference, payment_verified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        order_id, guest_email, f"{guest_first_name} {guest_last_name}", guest_phone,
                        guest_address, guest_parish, guest_post_office, final_total, cart_data['discount'],
                        payment_method, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'pending_payment' if payment_method in ['lynk', 'whatsapp'] else 'pending',
                        totals['subtotal'], totals['platform_fee'], totals['payment_gateway_fee'], totals['total_before_gateway_fee'],
                        lynk_reference if payment_method == 'lynk' else None,
                        False  # Will be verified manually or via API later
                    ))


                    # Add order items and update inventory
                    for item in cart_data['items']:
                        # Strip variations from product_key before inserting
                        base_product_key = re.sub(r'\s*\([^)]+\)$', '', item['product_key']).strip()

                        cursor.execute('''
                            INSERT INTO order_items (order_id, product_key, quantity, price)
                            VALUES (%s, %s, %s, %s)
                        ''', (order_id, base_product_key, item['quantity'], item['price']))

                        # Update product inventory
                        cursor.execute('UPDATE products SET amount = amount - %s, sold = sold + %s WHERE product_key = %s',
                                       (item['quantity'], item['quantity'], base_product_key))

                        # Check for low stock and create notification (guest checkout)
                        cursor.execute('SELECT amount, name, seller_email FROM products WHERE product_key = %s', (base_product_key,))
                        product_info = cursor.fetchone()
                        if product_info and product_info['amount'] <= 2:
                            # Create low stock notification
                            cursor.execute('''
                                INSERT INTO seller_notifications
                                (seller_email, notification_type, product_key, product_name, quantity, sale_date)
                                VALUES (%s, %s, %s, %s, %s,%s)
                            ''', (
                                product_info['seller_email'],
                                'low_stock',
                                base_product_key,
                                product_info['name'],
                                product_info['amount'],  # Current stock level
                                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            ))

                        # LYNK: Add to sales log for Lynk payments too
                        if payment_method == 'lynk':
                            # Get seller email for this product
                            cursor.execute('SELECT seller_email FROM products WHERE product_key = %s',
                                           (base_product_key,))
                            product_info = cursor.fetchone()
                            seller_email = product_info['seller_email'] if product_info else 'unknown@example.com'

                            cursor.execute('''
                                INSERT INTO sales_log (seller_email, product_key, quantity, price, sale_date, buyer_email)
                                VALUES (%s, %s, %s, %s, %s,%s)
                            ''', (
                                seller_email,
                                base_product_key,
                                item['quantity'],
                                item['price'],
                                datetime.now().strftime('%Y-%m-%d'),
                                guest_email
                            ))

                            # Create notification for the seller (guest purchase)
                            cursor.execute('''
                                INSERT INTO seller_notifications
                                (seller_email, notification_type, product_key, product_name, buyer_email, quantity, price, sale_date, order_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s,%s)
                            ''', (
                                seller_email,
                                'sale',
                                base_product_key,
                                item['name'],
                                guest_email,
                                item['quantity'],
                                item['price'],
                                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                order_id
                            ))

                    # NEW: Update seller finances and platform finances
                    seller_payouts = calculate_seller_payouts(cart_data['items'])

                    for seller_email, amount in seller_payouts.items():
                        # Check if seller_finances record exists
                        cursor.execute('SELECT seller_email FROM seller_finances WHERE seller_email = %s', (seller_email,))
                        if cursor.fetchone():
                            # Update existing record
                            cursor.execute('''
                                UPDATE seller_finances
                                SET balance = COALESCE(balance, 0) + %s,
                                    total_earnings = COALESCE(total_earnings, 0) + %s
                                WHERE seller_email = %s
                            ''', (amount, amount, seller_email))
                        else:
                            # Create new record
                            cursor.execute('''
                                INSERT INTO seller_finances (seller_email, balance, total_earnings)
                                VALUES (%s, %s, %s)
                            ''', (seller_email, amount, amount))

                        # Log seller transaction
                        cursor.execute('''
                            INSERT INTO seller_transactions (seller_email, transaction_type, amount, order_id, buyer_email, description)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        ''', (seller_email, 'sale', amount, order_id, guest_email, f'Sale from order {order_id}'))

                    # Record platform revenue
                    cursor.execute('''
                        INSERT INTO platform_finances (order_id, revenue_from_fees, gateway_fees_paid, net_revenue, payment_method)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (
                        order_id,
                        totals['platform_fee'],
                        totals['payment_gateway_fee'],
                        totals['platform_fee'] - totals['payment_gateway_fee'],
                        payment_method
                    ))

                    conn.commit()

                    # Store order info for confirmation page
                    session['confirmation_data'] = {
                        'order_id': order_id,
                        'customer_name': f"{guest_first_name} {guest_last_name}",
                        'customer_email': guest_email,
                        'total_amount': final_total,
                        'shipping_fee': shipping_fee,
                        'tax': tax,
                        'shipping_option': shipping_option,
                        'subtotal': totals['subtotal'],
                        'platform_fee': totals['platform_fee'],
                        'payment_gateway_fee': totals['payment_gateway_fee'],
                        'discount': cart_data['discount'],
                        'estimated_delivery': estimated_delivery,
                        'order_date': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
                        'items': cart_data['items'],
                        'is_guest': True,
                        'payment_method': payment_method,
                        'lynk_reference': lynk_reference if payment_method == 'lynk' else None,
                        'lynk_success_message': f"✅ Lynk payment received! Reference: {lynk_reference}" if payment_method == 'lynk' else None
                    }

                    # Clear cart
                    session.pop('cart', None)
                    session.modified = True

                    return redirect(url_for('order_confirmation'))

            else:
                # Logged-in user checkout
                if 'user' not in session:
                    return redirect(url_for('login'))

                full_name = request.form.get('full_name')
                phone_number = request.form.get('phone_number')
                address = request.form.get('address')
                parish = request.form.get('parish')
                post_office = request.form.get('post_office')
                payment_method = request.form.get('payment_method')
                shipping_option = request.form.get('shipping_option', 'regular')

                if not all([full_name, phone_number, address, parish, post_office, payment_method]):
                    return render_template(
                        'checkout.html',
                        error="All fields are required",
                        cart_items=cart_data['items'],
                        cart_total=cart_data['total'],
                        discount=cart_data['discount'],
                        user=session['user'],
                        cart_item_count=cart_data['cart_item_count'],
                        parishes=PARISHES,
                        parish_post_offices=PARISH_POST_OFFICES,
                        post_offices=PARISH_POST_OFFICES.get(parish, [])
                    )

                # LYNK VALIDATION: Check Lynk payment requirements for logged-in users
                if payment_method == 'lynk':
                    if not lynk_reference:
                        return render_template(
                            'checkout.html',
                            error="Lynk transaction reference is required for Lynk payments. Please complete the Lynk transfer and enter your transaction ID.",
                            cart_items=cart_data['items'],
                            cart_total=cart_data['total'],
                            discount=cart_data['discount'],
                            user=session['user'],
                            cart_item_count=cart_data['cart_item_count'],
                            parishes=PARISHES,
                            parish_post_offices=PARISH_POST_OFFICES,
                            post_offices=PARISH_POST_OFFICES.get(parish, [])
                        )

                    # Validate Lynk reference format
                    if len(lynk_reference) < 5:
                        return render_template(
                            'checkout.html',
                            error="Please enter a valid Lynk transaction reference (at least 5 characters)",
                            cart_items=cart_data['items'],
                            cart_total=cart_data['total'],
                            discount=cart_data['discount'],
                            user=session['user'],
                            cart_item_count=cart_data['cart_item_count'],
                            parishes=PARISHES,
                            parish_post_offices=PARISH_POST_OFFICES,
                            post_offices=PARISH_POST_OFFICES.get(parish, [])
                        )

                # Calculate totals using new payment system (NO SHIPPING - included in product price)
                totals = calculate_order_totals(cart_data['total'], payment_method)
                final_total = totals['final_total'] - cart_data['discount']

                # LYNK LOGGING: Log Lynk payment for verification
                if payment_method == 'lynk':
                    logger.info(
                        f"LYNK PAYMENT - User Order - Reference: {lynk_reference}, Amount: J${final_total}, User: {session['user']['email']}")

                # Calculate estimated delivery (3-5 business days standard)
                delivery_days = 5
                estimated_delivery = (datetime.now() + timedelta(days=delivery_days)).strftime('%B %d, %Y')

                # Define shipping and tax (shipping is included in product prices, tax is platform fee)
                shipping_fee = 0  # Shipping is FREE and included in product prices
                tax = totals['platform_fee']  # Platform fee acts as "tax"
                # shipping_option is already defined from form at line 8003

                with get_db() as conn:
                    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                    order_id = str(uuid.uuid4())[:8].upper()

                    # UPDATED: Create user order with new payment system fields
                    cursor.execute('''
                        INSERT INTO orders (order_id, user_email, full_name, phone_number, address, parish, post_office,
                                          total, discount, payment_method, order_date, status,
                                          subtotal, platform_fee, payment_gateway_fee, total_before_gateway_fee,
                                          lynk_reference, payment_verified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        order_id, session['user']['email'], full_name, phone_number, address, parish, post_office,
                        final_total, cart_data['discount'], payment_method,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'pending_payment' if payment_method in ['lynk', 'whatsapp'] else 'pending',
                        totals['subtotal'], totals['platform_fee'], totals['payment_gateway_fee'], totals['total_before_gateway_fee'],
                        lynk_reference if payment_method == 'lynk' else None,
                        False  # Will be verified manually or via API later
                    ))

                    # Add order items and update inventory
                    for item in cart_data['items']:
                        # Strip variations from product_key before inserting
                        base_product_key = re.sub(r'\s*\([^)]+\)$', '', item['product_key']).strip()

                        cursor.execute('''
                            INSERT INTO order_items (order_id, product_key, quantity, price)
                            VALUES (%s, %s, %s, %s)
                        ''', (order_id, base_product_key, item['quantity'], item['price']))

                        # Update product inventory
                        cursor.execute('UPDATE products SET amount = amount - %s, sold = sold + %s WHERE product_key = %s',
                                       (item['quantity'], item['quantity'], base_product_key))

                        # Check for low stock and create notification
                        cursor.execute('SELECT amount, name, seller_email FROM products WHERE product_key = %s', (base_product_key,))
                        product_info = cursor.fetchone()
                        if product_info and product_info['amount'] <= 2:
                            # Create low stock notification
                            cursor.execute('''
                                INSERT INTO seller_notifications
                                (seller_email, notification_type, product_key, product_name, quantity, sale_date)
                                VALUES (%s, %s, %s, %s, %s,%s)
                            ''', (
                                product_info['seller_email'],
                                'low_stock',
                                base_product_key,
                                product_info['name'],
                                product_info['amount'],  # Current stock level
                                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            ))

                        # Add to sales log
                        cursor.execute('''
                            INSERT INTO sales_log (seller_email, product_key, quantity, price, sale_date, buyer_email)
                            VALUES (%s, %s, %s, %s, %s,%s)
                        ''', (
                            item.get('seller_email', session['user']['email']),
                            base_product_key,
                            item['quantity'],
                            item['price'],
                            datetime.now().strftime('%Y-%m-%d'),
                            session['user']['email']
                        ))

                        # Create notification for the seller
                        seller_email = item.get('seller_email', session['user']['email'])
                        if seller_email != session['user']['email']:  # Don't notify if seller is buying their own item
                            cursor.execute('''
                                INSERT INTO seller_notifications
                                (seller_email, notification_type, product_key, product_name, buyer_email, quantity, price, sale_date, order_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s,%s)
                            ''', (
                                seller_email,
                                'sale',
                                base_product_key,
                                item['name'],
                                session['user']['email'],
                                item['quantity'],
                                item['price'],
                                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                order_id
                            ))

                    # 🔥 NEW: Increment purchase count for logged-in users
                    cursor.execute('''
                        UPDATE users 
                        SET purchase_count = COALESCE(purchase_count, 0) + 1 
                        WHERE email = %s
                    ''', (session['user']['email'],))

                    # Get updated purchase count
                    cursor.execute('SELECT purchase_count FROM users WHERE email = %s', (session['user']['email'],))
                    user_data = cursor.fetchone()
                    updated_purchase_count = user_data['purchase_count'] if user_data else 1

                    # Update session with new purchase count
                    session['user']['purchase_count'] = updated_purchase_count

                    # Check if user qualifies for free gift (every 5 purchases)
                    if updated_purchase_count > 0 and updated_purchase_count % 5 == 0:
                        # Mark as eligible for free gift
                        cursor.execute('''
                            UPDATE users 
                            SET discount_applied = true, discount_used = 0 
                            WHERE email = %s
                        ''', (session['user']['email'],))
                        session['user']['discount_applied'] = True
                        session['user']['discount_used'] = False

                        logger.info(
                            f"User {session['user']['email']} earned free gift after {updated_purchase_count} purchases")

                    # Check if cart contains any free items (indicating a gift was claimed)
                    has_free_item = any(item['price'] == 0 for item in cart_data['items'])

                    if has_free_item:
                        # Mark discount as used and reset for next cycle
                        cursor.execute('UPDATE users SET discount_used = %s WHERE email = %s',
                                       (True, session['user']['email']))
                        logger.info(f"User {session['user']['email']} claimed free gift - discount marked as used")

                    # NEW: Update seller finances and platform finances
                    seller_payouts = calculate_seller_payouts(cart_data['items'])

                    for seller_email, amount in seller_payouts.items():
                        # Check if seller_finances record exists
                        cursor.execute('SELECT seller_email FROM seller_finances WHERE seller_email = %s', (seller_email,))
                        if cursor.fetchone():
                            # Update existing record
                            cursor.execute('''
                                UPDATE seller_finances
                                SET balance = COALESCE(balance, 0) + %s,
                                    total_earnings = COALESCE(total_earnings, 0) + %s
                                WHERE seller_email = %s
                            ''', (amount, amount, seller_email))
                        else:
                            # Create new record
                            cursor.execute('''
                                INSERT INTO seller_finances (seller_email, balance, total_earnings)
                                VALUES (%s, %s, %s)
                            ''', (seller_email, amount, amount))

                        # Log seller transaction
                        cursor.execute('''
                            INSERT INTO seller_transactions (seller_email, transaction_type, amount, order_id, buyer_email, description)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        ''', (seller_email, 'sale', amount, order_id, session['user']['email'], f'Sale from order {order_id}'))

                    # Record platform revenue
                    cursor.execute('''
                        INSERT INTO platform_finances (order_id, revenue_from_fees, gateway_fees_paid, net_revenue, payment_method)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (
                        order_id,
                        totals['platform_fee'],
                        totals['payment_gateway_fee'],
                        totals['platform_fee'] - totals['payment_gateway_fee'],
                        payment_method
                    ))

                    conn.commit()

                    # 🔥 UPDATE PURCHASE COUNT
                    cursor.execute('''
                                            UPDATE users 
                                            SET purchase_count = (
                                                SELECT COUNT(*) 
                                                FROM orders 
                                                WHERE user_email = %s AND status NOT IN ('cancelled', 'refunded')
                                            )
                                            WHERE email = %s
                                        ''', (session['user']['email'], session['user']['email']))

                    # Get updated purchase count
                    cursor.execute('SELECT purchase_count FROM users WHERE email = %s', (session['user']['email'],))
                    user_data = cursor.fetchone()
                    updated_purchase_count = user_data['purchase_count'] if user_data else 0

                    # Update session
                    session['user']['purchase_count'] = updated_purchase_count

                    # Check if eligible for free gift (every 5 purchases)
                    if updated_purchase_count >= 5 and updated_purchase_count % 5 == 0:
                        cursor.execute('''
                                                UPDATE users 
                                                SET discount_applied = true, discount_used = 0 
                                                WHERE email = %s
                                            ''', (session['user']['email'],))
                        session['user']['discount_applied'] = True
                        session['user']['discount_used'] = False
                        logger.info(
                            f"🎁 User {session['user']['email']} earned free gift after {updated_purchase_count} purchases")

                    conn.commit()

                    # Store order info for confirmation page
                    session['confirmation_data'] = {
                        'order_id': order_id,
                        'customer_name': full_name,
                        'customer_email': session['user']['email'],
                        'total_amount': final_total,
                        'shipping_fee': shipping_fee,
                        'tax': tax,
                        'discount': cart_data['discount'],
                        'estimated_delivery': estimated_delivery,
                        'shipping_option': shipping_option,
                        'order_date': datetime.now().strftime('%B %d, %Y at %I:%M %p'),
                        'items': cart_data['items'],
                        'is_guest': False,
                        'payment_method': payment_method,
                        'lynk_reference': lynk_reference if payment_method == 'lynk' else None,
                        'lynk_success_message': f"✅ Lynk payment received! Reference: {lynk_reference}" if payment_method == 'lynk' else None
                    }

                    # Update user session
                    if has_free_item:
                        session['user']['discount_used'] = True
                    session.pop('cart', None)
                    session.modified = True

                    return redirect(url_for('order_confirmation'))

        except Exception as e:
            logger.error(f"Error in checkout: {e}\n{traceback.format_exc()}")
            return render_template(
                'checkout.html',
                error="An error occurred during checkout. Please try again.",
                cart_items=cart_data['items'],
                cart_total=cart_data['total'],
                discount=cart_data['discount'],
                user=session.get('user'),
                cart_item_count=cart_data['cart_item_count'],
                parishes=PARISHES,
                parish_post_offices=PARISH_POST_OFFICES,
                post_offices=PARISH_POST_OFFICES.get(session.get('user', {}).get('parish', 'Kingston'), [])
            )

    # GET request - render the checkout form

    # Check if ALL cart items support COD
    # COD is only available if every product in cart has cod_available = True
    cod_available = False
    if cart_data['items']:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get product keys from cart
            product_keys = [item['product_key'] for item in cart_data['items']]

            # Check if all products have cod_available = True
            placeholders = ','.join(['%s'] * len(product_keys))
            cursor.execute(f'''
                SELECT COUNT(*) as total_products,
                       SUM(CASE WHEN cod_available = TRUE THEN 1 ELSE 0 END) as cod_products
                FROM products
                WHERE product_key IN ({placeholders})
            ''', product_keys)

            result = cursor.fetchone()
            if result:
                # COD available only if ALL products support it
                cod_available = result['total_products'] == result['cod_products'] and result['total_products'] > 0

    return render_template(
        'checkout.html',
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        user=session.get('user'),
        cart_item_count=cart_data['cart_item_count'],
        parishes=PARISHES,
        parish_post_offices=PARISH_POST_OFFICES,
        post_offices=PARISH_POST_OFFICES.get(session.get('user', {}).get('parish', 'Kingston'), []),
        cod_available=cod_available
    )


@app.route('/order-confirmation')
def order_confirmation():
    """Universal order confirmation page for both guests and logged-in users"""

    # Get confirmation data from session
    confirmation_data = session.get('confirmation_data')
    if not confirmation_data:
        # If no confirmation data, redirect to home
        return redirect(url_for('index'))

    # Clear the confirmation data from session after retrieving it
    session.pop('confirmation_data', None)
    session.modified = True

    # Get current cart data for template
    cart_data = get_cart_items()

    return render_template(
        'order_confirmation.html',
        order=confirmation_data,
        items=confirmation_data['items'],
        user=session.get('user') if not confirmation_data['is_guest'] else None,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        cart_item_count=cart_data['cart_item_count']
    )


@app.route('/guest-order-confirmation')
def guest_order_confirmation():
    order_id = session.get('guest_order_id')
    if not order_id:
        return redirect(url_for('index'))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE order_id = %s', (order_id,))
        order = cursor.fetchone()

        if not order:
            return redirect(url_for('index'))

        # Get order items
        cursor.execute('''
            SELECT oi.product_key, oi.quantity, oi.price, p.name, p.image_url
            FROM order_items oi
            LEFT JOIN products p ON oi.product_key = p.product_key
            WHERE oi.order_id = %s
        ''', (order_id,))
        order_items = cursor.fetchall()

    # Clear the session order ID
    session.pop('guest_order_id', None)

    cart_data = get_cart_items()
    return render_template(
        'guest_order_confirmation.html',
        order=dict(order),
        order_items=order_items,
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        user=None,
        cart_item_count=cart_data['cart_item_count']
    )

@app.route('/cancel_refund', methods=['GET', 'POST'])
def cancel_refund():
    if request.method == 'POST':
        if 'user' not in session:
            return redirect(url_for('login'))
        try:
            order_id = request.form.get('order_id')
            reason = request.form.get('reason')
            if not order_id or not reason:
                return render_template('cancel_refund.html', error="Order ID and reason are required", user=session.get('user'))
            with get_db() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
                cursor.execute('SELECT * FROM orders WHERE order_id = %s AND user_email = %s', (order_id, session['user']['email']))
                order = cursor.fetchone()
                if not order:
                    return render_template('cancel_refund.html', error="Order not found or not authorized", user=session.get('user'))
                cursor.execute('''
                    INSERT INTO cancel_refund_requests (order_id, user_email, reason, request_date, status)
                    VALUES (%s, %s, %s, %s,%s)
                ''', (order_id, session['user']['email'], reason, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'pending'))
                conn.commit()
                return render_template('cancel_refund.html', success="Cancellation/Refund request submitted", user=session.get('user'))
        except Exception as e:
            logger.error(f"Error in cancel_refund: {e}\n{traceback.format_exc()}")
            return render_template('cancel_refund.html', error="Error submitting request", user=session.get('user'))
    return render_template('cancel_refund.html', user=session.get('user'))

@app.route('/like/<product_key>', methods=['POST'])
def like_product(product_key):
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401
    product_key = unquote(product_key.replace('+', ' ')).strip()
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('SELECT * FROM products WHERE product_key = %s', (product_key,))
            product = cursor.fetchone()
            if not product:
                return jsonify({'success': False, 'message': 'Product not found'}), 404
            cursor.execute('''
                SELECT * FROM user_likes
                WHERE user_email = %s AND product_key = %s
            ''', (session['user']['email'], product_key))
            existing_like = cursor.fetchone()
            if existing_like:
                cursor.execute('''
                    DELETE FROM user_likes
                    WHERE user_email = %s AND product_key = %s
                ''', (session['user']['email'], product_key))
                cursor.execute('UPDATE products SET likes = likes - 1 WHERE product_key = %s', (product_key,))
                conn.commit()
                return jsonify({'success': True, 'liked': False, 'likes': product['likes'] - 1})
            else:
                cursor.execute('''
                    INSERT INTO user_likes (user_email, product_key, created_at)
                    VALUES (%s, %s, %s)
                ''', (session['user']['email'], product_key, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                cursor.execute('UPDATE products SET likes = likes + 1 WHERE product_key = %s', (product_key,))
                conn.commit()
                return jsonify({'success': True, 'liked': True, 'likes': product['likes'] + 1})
    except Exception as e:
        logger.error(f"Error in like_product: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': 'Error processing like'}), 500


@app.route('/make_admin')
def make_admin():
    from werkzeug.security import generate_password_hash
    from datetime import datetime

    try:
        conn = sqlite3.connect('zo-zi.db')
        cursor = conn.cursor()

        # Clear any existing admin
        cursor.execute('DELETE FROM admin_users')

        # Create admin
        cursor.execute('''
            INSERT INTO admin_users (email, password, admin_level, is_active, created_at)
            VALUES (%s, %s, %s, %s,%s)
        ''', (
            'admin@test.com',
            generate_password_hash('admin123'),
            'super_admin',
            1,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))

        conn.commit()
        conn.close()

        return "ADMIN CREATED. Email: admin@test.com Password: admin123"

    except Exception as e:
        return f"ERROR: {str(e)}"

@app.route('/rate_seller', methods=['POST'])
def rate_seller():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401

    try:
        # Validate CSRF token
        from flask_wtf.csrf import validate_csrf

        csrf_token = request.headers.get('X-CSRFToken')
        if csrf_token:
            try:
                validate_csrf(csrf_token)
            except Exception as e:
                return jsonify({'success': False, 'message': 'CSRF token invalid'}), 400

        data = request.get_json()
        seller_email = data.get('seller_email')
        rating = data.get('rating')

        if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({'success': False, 'message': 'Invalid rating'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()
            cursor.execute('SELECT * FROM users WHERE email = %s AND is_seller = %s', (seller_email, True))
            seller = cursor.fetchone()
            if not seller:
                return jsonify({'success': False, 'message': 'Seller not found'}), 404

            cursor.execute('''
                INSERT OR REPLACE INTO seller_ratings (buyer_email, seller_email, rating)
                VALUES (%s, %s, %s)
            ''', (session['user']['email'], seller_email, rating))
            conn.commit()

            cursor.execute('''
                SELECT AVG(rating) as avg_rating, COUNT(rating) as rating_count
                FROM seller_ratings
                WHERE seller_email = %s
            ''', (seller_email,))
            rating_info = cursor.fetchone()

            return jsonify({
                'success': True,
                'avg_rating': round(rating_info['avg_rating'], 1) if rating_info['avg_rating'] else 0,
                'rating_count': rating_info['rating_count'] if rating_info['rating_count'] else 0
            })

    except Exception as e:
        logger.error(f"Error in rate_seller: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': 'Error processing rating'}), 500


@app.route('/submit_product_review', methods=['POST'])
def submit_product_review():
    """Submit or update a product review"""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Login required'}), 401

    try:
        # Validate CSRF token
        from flask_wtf.csrf import validate_csrf
        csrf_token = request.headers.get('X-CSRFToken')
        if csrf_token:
            try:
                validate_csrf(csrf_token)
            except Exception as e:
                return jsonify({'success': False, 'message': 'CSRF token invalid'}), 400

        data = request.get_json()
        product_key = data.get('product_key')
        rating = data.get('rating')
        review_text = data.get('review_text', '').strip()

        if not product_key:
            return jsonify({'success': False, 'message': 'Product key required'}), 400

        if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({'success': False, 'message': 'Invalid rating (1-5)'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get product and seller info
            cursor.execute('SELECT seller_email FROM products WHERE product_key = %s', (product_key,))
            product = cursor.fetchone()
            if not product:
                return jsonify({'success': False, 'message': 'Product not found'}), 404

            seller_email = product['seller_email']
            buyer_email = session['user']['email']

            # Check if buyer has purchased this product (verified purchase)
            cursor.execute('''
                SELECT COUNT(*) as purchase_count
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                WHERE oi.product_key = %s AND o.user_email = %s
            ''', (product_key, buyer_email))
            purchase_check = cursor.fetchone()
            is_verified_purchase = purchase_check['purchase_count'] > 0

            # Insert or update review
            cursor.execute('''
                INSERT INTO product_reviews (product_key, buyer_email, seller_email, rating, review_text, is_verified_purchase)
                VALUES (%s, %s, %s, %s, %s,%s)
                ON CONFLICT(product_key, buyer_email)
                DO UPDATE SET rating = %s, review_text = %s, updated_at = CURRENT_TIMESTAMP
            ''', (product_key, buyer_email, seller_email, rating, review_text, is_verified_purchase, rating, review_text))

            conn.commit()

            # Get updated review stats
            cursor.execute('''
                SELECT AVG(rating) as avg_rating, COUNT(*) as review_count
                FROM product_reviews
                WHERE product_key = %s
            ''', (product_key,))
            stats = cursor.fetchone()

            return jsonify({
                'success': True,
                'message': 'Review submitted successfully',
                'avg_rating': round(stats['avg_rating'], 1) if stats['avg_rating'] else 0,
                'review_count': stats['review_count'] or 0,
                'is_verified_purchase': is_verified_purchase
            })

    except Exception as e:
        logger.error(f"Error submitting product review: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': 'Error submitting review'}), 500


@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '').strip()
    category = request.args.get('category', '').strip()
    cart_data = get_cart_items()
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Split query into keywords for partial matching
            keywords = query.lower().split() if query else []
            keyword_conditions = []
            params = []

            for keyword in keywords:
                keyword_conditions.append("LOWER(p.name) LIKE %s")
                params.append(f'%{keyword}%')

            keyword_clause = " AND ".join(keyword_conditions) if keyword_conditions else "1=1"

            # Exclude products from flagged sellers
            sql = f'''
                SELECT p.* FROM products p
                LEFT JOIN user_flags uf ON p.seller_email = uf.user_email AND uf.is_active = true
                WHERE uf.id IS NULL AND ({keyword_clause})
            '''

            if category:
                sql += ' AND p.category = %s'
                params.append(category)

            cursor.execute(sql, params)
            products_list = [
                dict(row, image_urls=json.loads(row['image_urls']), sizes=json.loads(row['sizes']))
                for row in cursor.fetchall()
            ]
            # Convert list to dictionary with product_key as key (matching index route format)
            products = {product['product_key']: product for product in products_list}

            return render_template(
                'index.html',
                products=products,
                cart_items=cart_data['items'],
                cart_total=cart_data['total'],
                discount=cart_data['discount'],
                user=session.get('user'),
                cart_item_count=cart_data['cart_item_count'],
                categories=[
                    'Accessories', 'Baby & Maternity', 'Beachwear', 'Beauty & Health', 'Home & Kitchen',
                    'Jewelry', 'Kids', 'Men Clothing', 'Shoes', 'Sports & Outdoors',
                    'Underwear & Sleepwear', 'Women Clothing'
                ],
                search_query=query,
                selected_category=category
            )
    except Exception as e:
        logger.error(f"Error in search: {e}\n{traceback.format_exc()}")
        return render_template(
            'index.html',
            error="Error performing search",
            products={},
            cart_items=cart_data['items'],
            cart_total=cart_data['total'],
            discount=cart_data['discount'],
            user=session.get('user'),
            cart_item_count=cart_data['cart_item_count'],
            categories=[
                'Accessories', 'Baby & Maternity', 'Beachwear', 'Beauty & Health', 'Home & Kitchen',
                'Jewelry', 'Kids', 'Men Clothing', 'Shoes', 'Sports & Outdoors',
                'Underwear & Sleepwear', 'Women Clothing'
            ]
        )


# ==================================================
# LYNK PAYMENT VERIFICATION ROUTES
# ==================================================

@app.route('/admin/verify_lynk_payment', methods=['POST'])
@admin_required()
def verify_lynk_payment():
    """Verify Lynk payment manually (until API is available)"""
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        verified = data.get('verified', False)

        if not order_id:
            return jsonify({'success': False, 'message': 'Order ID required'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Update payment verification status
            cursor.execute('''
                UPDATE orders 
                SET payment_verified = %s, status = %s
                WHERE order_id = %s
            ''', (verified, 'confirmed' if verified else 'pending_payment', order_id))

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Order not found'}), 404

            conn.commit()

            # Log admin activity
            log_admin_activity(
                session['admin_user']['email'],
                'lynk_payment_verified' if verified else 'lynk_payment_rejected',
                'order',
                order_id,
                f'Lynk payment {"verified" if verified else "rejected"} for order {order_id}'
            )

            return jsonify({
                'success': True,
                'message': f'Lynk payment {"verified" if verified else "rejected"} successfully'
            })

    except Exception as e:
        logger.error(f"Error verifying Lynk payment: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/lynk_info')
def lynk_info():
    """Information about Lynk digital wallet"""
    cart_data = get_cart_items()
    return render_template(
        'lynk_info.html',
        cart_items=cart_data['items'],
        cart_total=cart_data['total'],
        discount=cart_data['discount'],
        user=session.get('user'),
        cart_item_count=cart_data['cart_item_count']
    )


@app.route('/admin/api/lynk_orders')
@admin_required()
def admin_api_lynk_orders():
    """Get all Lynk orders for admin dashboard"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all Lynk orders with verification status
            cursor.execute('''
                SELECT 
                    o.order_id, o.user_email, o.full_name, o.total, o.order_date,
                    o.lynk_reference, o.payment_verified, o.status,
                    COUNT(oi.product_key) as item_count
                FROM orders o
                LEFT JOIN order_items oi ON o.order_id = oi.order_id
                WHERE o.payment_method = 'lynk'
                GROUP BY o.order_id
                ORDER BY o.order_date DESC
            ''')

            lynk_orders = []
            for row in cursor.fetchall():
                order = dict(row)
                order['total'] = float(order['total'] or 0)
                order['item_count'] = order['item_count'] or 0
                lynk_orders.append(order)

            return jsonify({
                'success': True,
                'lynk_orders': lynk_orders,
                'total_count': len(lynk_orders)
            })

    except Exception as e:
        logger.error(f"Error getting Lynk orders: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/conversations')
@admin_required()
def admin_api_conversations():
    """Get all customer conversations for admin dashboard"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Get all conversation sessions with stats
            cursor.execute('''
                SELECT
                    session_id,
                    user_email,
                    MAX(timestamp) as last_message_time,
                    COUNT(*) as message_count,
                    SUM(CASE WHEN unread = true AND sender = 'user' THEN 1 ELSE 0 END) as unread_count
                FROM contact_messages
                GROUP BY session_id, user_email
                ORDER BY last_message_time DESC
            ''')

            conversations = []
            for row in cursor.fetchall():
                conversations.append({
                    'session_id': row[0],
                    'user_email': row[1],
                    'last_message_time': row[2],
                    'message_count': row[3],
                    'unread_count': row[4] or 0
                })

            return jsonify({
                'success': True,
                'conversations': conversations
            })

    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/conversation/<session_id>/messages')
@admin_required()
def admin_api_conversation_messages(session_id):
    """Get all messages for a specific conversation"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            cursor.execute('''
                SELECT sender, message, timestamp
                FROM contact_messages
                WHERE session_id = %s
                ORDER BY timestamp ASC
            ''', (session_id,))

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'sender': row[0],
                    'message': row[1],
                    'timestamp': row[2]
                })

            # Mark user messages as read
            cursor.execute('''
                UPDATE contact_messages
                SET unread = 0
                WHERE session_id = %s AND sender = 'user'
            ''', (session_id,))
            conn.commit()

            return jsonify({
                'success': True,
                'messages': messages
            })

    except Exception as e:
        logger.error(f"Error getting conversation messages: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/api/send_reply', methods=['POST'])
@admin_required()
def admin_api_send_reply():
    """Send admin reply to customer"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        user_email = data.get('user_email')
        message = data.get('message', '').strip()

        if not session_id or not user_email or not message:
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if DATABASE_TYPE == 'postgresql' else conn.cursor()

            # Insert admin reply
            cursor.execute('''
                INSERT INTO contact_messages (user_id, user_email, session_id, sender, message, timestamp, unread)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (user_email, user_email, session_id, 'support', message, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 1))

            conn.commit()

            logger.info(f"Admin sent reply to {user_email} in session {session_id}")

            return jsonify({
                'success': True,
                'message': 'Reply sent successfully'
            })

    except Exception as e:
        logger.error(f"Error sending admin reply: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


def fix_messaging_tables():
    """Run this once to fix existing database schema"""
    conn = sqlite3.connect('zo-zi.db')
    cursor = conn.cursor()

    try:
        # Check if conversations table exists, create if not
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_email TEXT NOT NULL,
                    seller_email TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(buyer_email, seller_email),
                    FOREIGN KEY (buyer_email) REFERENCES users(email),
                    FOREIGN KEY (seller_email) REFERENCES users(email)
                )
            ''')
            print("✅ Created conversations table")

        # Check if messages table exists, create if not
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    sender_email TEXT NOT NULL,
                    receiver_email TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    read_status BOOLEAN DEFAULT 0,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                    FOREIGN KEY (sender_email) REFERENCES users(email),
                    FOREIGN KEY (receiver_email) REFERENCES users(email)
                )
            ''')
            print("✅ Created messages table")

        # Add missing columns if they don't exist
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'created_at' not in columns:
            cursor.execute('ALTER TABLE conversations ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            print("✅ Added created_at column")

        if 'last_message_at' not in columns:
            cursor.execute('ALTER TABLE conversations ADD COLUMN last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
            print("✅ Added last_message_at column")

        # Create all necessary indexes
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_messages_conversation 
            ON messages(conversation_id, timestamp)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_messages_unread 
            ON messages(receiver_email, read_status)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversations_buyer
            ON conversations(buyer_email)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversations_seller
            ON conversations(seller_email)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversations_last_message
            ON conversations(last_message_at DESC)
        ''')

        conn.commit()
        print("✅ Database schema updated successfully!")
        print("✅ All indexes created for optimal performance")
    except Exception as e:
        print(f"❌ Error updating database: {e}")
        conn.rollback()
    finally:
        conn.close()


def reset_database_fresh():
    """Reset the entire database - WARNING: This deletes all data!"""
    import os

    # Remove old database
    db_path = 'zo-zi.db'
    if os.path.exists(db_path):
        os.remove(db_path)
        print("🗑️ Old database deleted")

    # Create fresh database with all tables
    init_db()
    migrate_products()  # Add your initial products
    print("✅ Fresh database created with all tables")
    print("✅ Initial products migrated")

    print("\n" + "=" * 50)
    print("🎉 FRESH DATABASE READY!")
    print("=" * 50)
    print("✅ Database reset complete!")
    print("📝 You can now create your own accounts:")
    print("   • Go to /signup to create buyer/seller accounts")
    print("   • Go to /login to access your accounts")
    print("🔗 Admin Dashboard: http://localhost:5000/admin_dashboard")
    print("   (Create admin account first, then access)")
    print("=" * 50)







if __name__ == '__main__':
    # Initialize PostgreSQL database if using PostgreSQL
    if DATABASE_TYPE == 'postgresql':
        init_postgres_db()

    add_purchase_count_column()              # ADD THIS
    update_purchase_counts_from_orders()     # ADD THIS
    fix_messaging_tables()
    ensure_demo_seller()                     # Create demo sellers FIRST
    migrate_products()                       # Now add all dummy products!
    ensure_support_user()
    port = int(os.environ.get('PORT', 8080))
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True, port=port)