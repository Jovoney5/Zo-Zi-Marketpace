# database_postgres.py - PostgreSQL database manager for ZoZi Marketplace
import os
import json
import logging
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlparse
from werkzeug.security import generate_password_hash, check_password_hash

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or default"""
    return os.getenv('DATABASE_URL', 'postgresql://username:password@localhost:5432/zozi_marketplace')


def parse_database_url(database_url):
    """Parse database URL into connection parameters"""
    url = urlparse(database_url)
    return {
        'host': url.hostname,
        'port': url.port or 5432,
        'database': url.path[1:] if url.path else 'zozi_marketplace',
        'user': url.username,
        'password': url.password
    }


@contextmanager
def get_db():
    """
    PostgreSQL context manager for database connections
    Usage:
        with get_db() as conn:
            cursor = conn.cursor()
            # do database operations
    """
    conn = None
    try:
        database_url = get_database_url()

        # Handle both postgres:// and postgresql:// URLs
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)

        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def get_db_connection():
    """
    Alternative method - simple connection getter
    Remember to close the connection when done!
    """
    database_url = get_database_url()
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    conn = psycopg2.connect(database_url)
    return conn


# =============================================================================
# DATABASE MIGRATION SYSTEM
# =============================================================================

def run_migrations(cursor=None, conn=None):
    """
    Run all database migrations to ensure schema is up to date.
    This handles adding missing tables and columns to existing databases.
    Safe to run multiple times - uses IF NOT EXISTS and checks.

    Args:
        cursor: Optional cursor to use (if None, creates new connection)
        conn: Optional connection (used with cursor)
    """
    # If no cursor provided, create new connection
    if cursor is None:
        try:
            with get_db() as new_conn:
                new_cursor = new_conn.cursor()
                logger.info("🔄 Running database migrations...")
                return _run_migrations_impl(new_cursor, new_conn)
        except Exception as e:
            logger.error(f"❌ Migration error: {e}")
            return False
    else:
        # Use provided cursor
        logger.info("🔄 Running database migrations...")
        return _run_migrations_impl(cursor, conn)


def _run_migrations_impl(cursor, conn):
    """Implementation of migrations using provided cursor and connection"""
    try:
        logger.info("  Starting migration 1: user_flags")
        # Migration 1: Ensure user_flags table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_flags (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) NOT NULL,
                flag_type VARCHAR(50) NOT NULL,
                reason TEXT,
                flagged_by VARCHAR(255) NOT NULL,
                flag_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ user_flags table checked")

        logger.info("  Starting migration 2: product_reviews")
        # Migration: Ensure product_reviews table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_reviews (
                id SERIAL PRIMARY KEY,
                product_key VARCHAR(255) NOT NULL,
                buyer_email VARCHAR(255) NOT NULL,
                seller_email VARCHAR(255) NOT NULL,
                rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                review_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_verified_purchase BOOLEAN DEFAULT FALSE,
                UNIQUE(product_key, buyer_email)
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ product_reviews table checked")

        logger.info("  Starting migration 2b: seller_ratings")
        # Migration: Ensure seller_ratings table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seller_ratings (
                id SERIAL PRIMARY KEY,
                seller_email VARCHAR(255) NOT NULL,
                buyer_email VARCHAR(255) NOT NULL,
                rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                review_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(seller_email, buyer_email)
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ seller_ratings table checked")

        logger.info("  Starting migration 2c: user_likes")
        # Migration: Ensure user_likes table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_likes (
                user_email VARCHAR(255) NOT NULL,
                product_key VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_email, product_key)
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ user_likes table checked")

        logger.info("  Starting migration 3: messages conversation_id")
        # Migration 2: Ensure messages table has conversation_id
        cursor.execute('''
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'messages' AND column_name = 'conversation_id'
        ''')
        if not cursor.fetchone():
            # Check if messages table exists at all
            cursor.execute('''
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'messages'
                )
            ''')
            if cursor.fetchone()[0]:
                # Table exists but missing column - add it
                cursor.execute('ALTER TABLE messages ADD COLUMN conversation_id INTEGER DEFAULT 0')
                cursor.execute(
                    'UPDATE messages SET conversation_id = id WHERE conversation_id IS NULL OR conversation_id = 0')
                logger.info("  ✓ Added conversation_id to messages table")
            else:
                # Create full messages table
                cursor.execute('''
                    CREATE TABLE messages (
                        id SERIAL PRIMARY KEY,
                        conversation_id INTEGER NOT NULL DEFAULT 0,
                        sender_email VARCHAR(255) NOT NULL,
                        receiver_email VARCHAR(255) NOT NULL,
                        message TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        read_status BOOLEAN DEFAULT FALSE
                    )
                ''')
                logger.info("  ✓ Created messages table")
        else:
            logger.info("  ✓ messages.conversation_id exists")

        logger.info("  Starting migration 4: admin_activity_log")
        # Migration 3: Ensure admin_activity_log table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_activity_log (
                id SERIAL PRIMARY KEY,
                admin_email VARCHAR(255) NOT NULL,
                action_type VARCHAR(100) NOT NULL,
                target_type VARCHAR(50),
                target_id VARCHAR(255),
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address INET
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ admin_activity_log table checked")

        logger.info("  Starting migration 5: seller_finances")
        # Migration 4: Ensure seller_finances table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seller_finances (
                id SERIAL PRIMARY KEY,
                seller_email VARCHAR(255) UNIQUE NOT NULL,
                balance DECIMAL(10,2) DEFAULT 0,
                total_sales DECIMAL(10,2) DEFAULT 0,
                pending_withdrawals DECIMAL(10,2) DEFAULT 0,
                total_withdrawn DECIMAL(10,2) DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                commission_rate DECIMAL(5,4) DEFAULT 0.05
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ seller_finances table checked")

        logger.info("  Starting migration 6: seller_transactions")
        # Migration 5: Ensure seller_transactions table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seller_transactions (
                id SERIAL PRIMARY KEY,
                seller_email VARCHAR(255) NOT NULL,
                transaction_type VARCHAR(50) NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                description TEXT,
                order_id VARCHAR(255),
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ seller_transactions table checked")

        logger.info("  Starting migration 7: withdrawal_requests")
        # Migration 6: Ensure withdrawal_requests table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id SERIAL PRIMARY KEY,
                seller_email VARCHAR(255) NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_date TIMESTAMP,
                bank_details JSONB,
                notes TEXT
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ withdrawal_requests table checked")

        logger.info("  Starting migration 8: seller_verification")
        # Migration 7: Ensure seller_verification table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seller_verification (
                id SERIAL PRIMARY KEY,
                seller_email VARCHAR(255) UNIQUE NOT NULL,
                business_name VARCHAR(255),
                business_address TEXT,
                phone_number VARCHAR(20),
                id_document_path VARCHAR(255),
                business_document_path VARCHAR(255),
                bank_statement_path VARCHAR(255),
                verification_status VARCHAR(50) DEFAULT 'pending_review',
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                reviewed_by VARCHAR(255),
                rejection_reason TEXT
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ seller_verification table checked")

        logger.info("  Starting migration 9: payment_transactions")
        # Migration 8: Ensure payment_transactions table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_transactions (
                id SERIAL PRIMARY KEY,
                transaction_id VARCHAR(255) UNIQUE NOT NULL,
                order_id VARCHAR(255),
                user_email VARCHAR(255) NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                payment_method VARCHAR(50) NOT NULL,
                transaction_type VARCHAR(50) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                gateway_response JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ payment_transactions table checked")

        logger.info("  Starting migration 10: contact_sessions")
        # Migration 9: Ensure contact_sessions table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contact_sessions (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) NOT NULL,
                session_id VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ contact_sessions table checked")

        logger.info("  Starting migration 11: user_product_views")
        # Migration 10: Ensure user_product_views table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_product_views (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) NOT NULL,
                product_key VARCHAR(255) NOT NULL,
                category VARCHAR(100),
                viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ user_product_views table checked")

        logger.info("  Starting migration 11b: products table amount column")
        # Migration: Add amount column to products table if missing
        cursor.execute('''
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'products' AND column_name = 'amount'
        ''')
        if not cursor.fetchone():
            cursor.execute('ALTER TABLE products ADD COLUMN amount INTEGER DEFAULT 1')
            logger.info("  ✓ Added products.amount column")
        else:
            logger.info("  ✓ products.amount column exists")
        if conn:
            conn.commit()  # Force commit so column is visible to other connections

        logger.info("  Starting migration 11c: products table shipping_method column")
        # Migration: Add shipping_method column to products table if missing
        cursor.execute('''
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'products' AND column_name = 'shipping_method'
        ''')
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE products ADD COLUMN shipping_method VARCHAR(50) DEFAULT 'standard'")
            logger.info("  ✓ Added products.shipping_method column")
        else:
            logger.info("  ✓ products.shipping_method column exists")
        if conn:
            conn.commit()  # Force commit so column is visible to other connections

        logger.info("  Starting migration 12: user table columns")
        # Migration 11: Add any missing columns to users table
        user_columns_to_add = [
            ('discount_used', 'BOOLEAN DEFAULT FALSE'),
            ('notification_preference', 'VARCHAR(10)'),
            ('business_name', 'VARCHAR(255)'),
            ('business_address', 'TEXT'),
            ('security_question', 'TEXT'),
            ('security_answer', 'TEXT'),
            ('discount_applied', 'BOOLEAN DEFAULT FALSE'),
            ('gender', 'VARCHAR(20)'),
            ('delivery_address', 'TEXT'),
            ('billing_address', 'TEXT'),
            ('whatsapp_number', 'VARCHAR(20)'),
            ('business_description', 'TEXT'),
            ('verification_status', "VARCHAR(50) DEFAULT 'pending_documents'"),
            ('purchase_count', 'INTEGER DEFAULT 0'),
            ('store_logo', 'VARCHAR(255)'),
        ]

        for col_name, col_type in user_columns_to_add:
            cursor.execute('''
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = %s
            ''', (col_name,))
            if not cursor.fetchone():
                try:
                    cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')
                    logger.info(f"  ✓ Added users.{col_name}")
                except Exception as e:
                    logger.warning(f"  ⚠ Could not add users.{col_name}: {e}")

        logger.info("  Starting migration 13: products table cod_available column")
        # Migration: Add cod_available column to products table if missing
        cursor.execute('''
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'products' AND column_name = 'cod_available'
        ''')
        if not cursor.fetchone():
            cursor.execute('ALTER TABLE products ADD COLUMN cod_available BOOLEAN DEFAULT FALSE')
            logger.info("  ✓ Added products.cod_available column")
        else:
            logger.info("  ✓ products.cod_available column exists")
        if conn:
            conn.commit()  # Force commit so column is visible to other connections

        logger.info("  Starting migration 14: cart_log table")
        # Migration: Ensure cart_log table exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cart_log (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) NOT NULL,
                product_key VARCHAR(255) NOT NULL,
                quantity INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        if conn:
            conn.commit()  # Force commit so table is visible to other connections
        logger.info("  ✓ cart_log table checked")

        logger.info("  Starting migration 15: user_sessions table user_email column")
        # Migration: Add user_email column to user_sessions table if table exists
        cursor.execute('''
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'user_sessions'
            )
        ''')
        if cursor.fetchone()[0]:
            cursor.execute('''
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'user_sessions' AND column_name = 'user_email'
            ''')
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE user_sessions ADD COLUMN user_email VARCHAR(255)')
                logger.info("  ✓ Added user_sessions.user_email column")
            else:
                logger.info("  ✓ user_sessions.user_email column exists")
            if conn:
                conn.commit()  # Force commit so column is visible to other connections
        else:
            logger.info("  ⚠ user_sessions table does not exist, skipping user_email column")

        # Migration 12: Create all indexes
        indexes = [
            ('idx_users_email', 'users', 'email'),
            ('idx_products_seller', 'products', 'seller_email'),
            ('idx_products_category', 'products', 'category'),
            ('idx_orders_user', 'orders', 'user_email'),
            ('idx_orders_status', 'orders', 'status'),
            ('idx_messages_conversation', 'messages', 'conversation_id'),
            ('idx_messages_receiver', 'messages', 'receiver_email'),
            ('idx_user_flags_email', 'user_flags', 'user_email'),
            ('idx_user_flags_active', 'user_flags', 'is_active'),
            ('idx_user_product_views_user', 'user_product_views', 'user_email'),
        ]

        for idx_name, table, column in indexes:
            try:
                cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})')
            except Exception as e:
                pass  # Index might already exist or table missing

        logger.info("  ✓ Indexes checked")

        # Final commit to ensure all changes are persisted
        if conn:
            conn.commit()
        logger.info("✅ All migrations completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration error: {e}")
        if conn:
            conn.rollback()
        return False


def init_db():
    """Initialize PostgreSQL database with all required tables"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            logger.info("Creating PostgreSQL tables for Zo-Zi Marketplace...")

            # Users table - matching your SQLite structure
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    is_seller BOOLEAN DEFAULT FALSE,
                    is_support BOOLEAN DEFAULT FALSE,
                    phone_number VARCHAR(20),
                    address TEXT,
                    parish VARCHAR(50),
                    post_office VARCHAR(100),
                    profile_picture VARCHAR(255),
                    discount_used BOOLEAN DEFAULT FALSE,
                    notification_preference VARCHAR(10),
                    business_name VARCHAR(255),
                    business_address TEXT,
                    security_question TEXT,
                    security_answer TEXT,
                    discount_applied BOOLEAN DEFAULT FALSE,
                    gender VARCHAR(20),
                    delivery_address TEXT,
                    billing_address TEXT,
                    whatsapp_number VARCHAR(20),
                    business_description TEXT,
                    verification_status VARCHAR(50) DEFAULT 'pending_documents',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    purchase_count INTEGER DEFAULT 0
                )
            ''')

            # Products table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    product_key VARCHAR(255) UNIQUE NOT NULL,
                    seller_email VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    price DECIMAL(10,2) NOT NULL,
                    category VARCHAR(100),
                    sizes JSONB DEFAULT '{}',
                    image_urls JSONB DEFAULT '[]',
                    image_url VARCHAR(255),
                    posted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    clicks INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    sold INTEGER DEFAULT 0,
                    stock_quantity INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')

            # Orders table - matching your SQLite structure
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    order_id VARCHAR(255) UNIQUE NOT NULL,
                    user_email VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    phone_number VARCHAR(20),
                    address TEXT,
                    parish VARCHAR(50),
                    post_office VARCHAR(100),
                    total DECIMAL(10,2) NOT NULL,
                    discount DECIMAL(10,2) DEFAULT 0,
                    payment_method VARCHAR(50),
                    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'pending',
                    shipping_option VARCHAR(100),
                    shipping_fee DECIMAL(10,2) DEFAULT 0,
                    tax DECIMAL(10,2) DEFAULT 0,
                    lynk_reference VARCHAR(255),
                    payment_verified BOOLEAN DEFAULT FALSE
                )
            ''')

            # Order items table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS order_items (
                    id SERIAL PRIMARY KEY,
                    order_id VARCHAR(255) NOT NULL,
                    product_key VARCHAR(255) NOT NULL,
                    quantity INTEGER NOT NULL,
                    price DECIMAL(10,2) NOT NULL,
                    size VARCHAR(50)
                )
            ''')

            # Admin users table - matching your SQLite structure
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    admin_level VARCHAR(50) DEFAULT 'admin',
                    created_by VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    permissions TEXT DEFAULT '{"users":true,"products":true,"orders":true,"analytics":true,"financials":true}'
                )
            ''')

            logger.info("✅ PostgreSQL core tables created!")

            # Now run migrations to add any missing tables/columns
            # Pass cursor so migrations run in same transaction
            run_migrations(cursor=cursor, conn=conn)

            return True

    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")
        return False


def test_connection():
    """Test PostgreSQL database connection"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            result = cursor.fetchone()
            logger.info(f"✅ PostgreSQL connection successful! Found {result[0]} users")
            return True
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection failed: {e}")
        return False


# User-related database functions (PostgreSQL compatible)
def create_user(email, first_name, last_name, password, phone_number=None, parish='Kingston', is_seller=False):
    """Create a new user account"""
    try:
        # Hash password if not already hashed
        if password and not ('pbkdf2:' in password or 'scrypt:' in password or 'bcrypt' in password):
            password = generate_password_hash(password)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (email, first_name, last_name, password, phone_number, parish, is_seller,
                                 discount_applied, discount_used)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (email, first_name, last_name, password, phone_number, parish, is_seller, False, False))
            return True
    except psycopg2.IntegrityError:
        return False  # User already exists
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return False


def get_user_by_email(email):
    """Get user details by email"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return None


def get_user_by_phone(phone_number):
    """Get user details by phone number"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM users WHERE phone_number = %s', (phone_number,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting user by phone: {e}")
        return None


def verify_user_login(identifier, password):
    """Verify user login credentials (email or phone)"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT * FROM users
                WHERE email = %s OR phone_number = %s
            ''', (identifier, identifier))
            user = cursor.fetchone()

            if user and user['password']:
                # Check if password is hashed
                if 'pbkdf2:' in user['password'] or 'scrypt:' in user['password'] or 'bcrypt' in user['password']:
                    if check_password_hash(user['password'], password):
                        return user
                else:
                    # Plain text password - check and update
                    if user['password'] == password:
                        # Update to hashed password
                        hashed_password = generate_password_hash(password)
                        cursor.execute('UPDATE users SET password = %s WHERE email = %s',
                                       (hashed_password, user['email']))
                        conn.commit()
                        return user
            return None
    except Exception as e:
        logger.error(f"Error verifying login: {e}")
        return None


def update_user_profile(email, **kwargs):
    """Update user profile information"""
    try:
        # Build dynamic update query
        fields = []
        values = []
        for key, value in kwargs.items():
            if value is not None:
                fields.append(f"{key} = %s")
                values.append(value)

        if not fields:
            return False

        values.append(email)
        query = f"UPDATE users SET {', '.join(fields)} WHERE email = %s"

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, values)
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        return False


# Product-related database functions (PostgreSQL compatible)
def get_all_products(active_only=True):
    """Get all products from the database"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM products ORDER BY posted_date DESC')
            products = []
            for row in cursor.fetchall():
                product = dict(row)
                # Handle JSON fields - PostgreSQL JSONB returns Python objects directly
                image_urls = product.get('image_urls', [])
                if isinstance(image_urls, str):
                    try:
                        product['image_urls'] = json.loads(image_urls)
                    except:
                        product['image_urls'] = []
                elif isinstance(image_urls, list):
                    product['image_urls'] = image_urls
                else:
                    product['image_urls'] = []

                sizes = product.get('sizes', {})
                if isinstance(sizes, str):
                    try:
                        product['sizes'] = json.loads(sizes)
                    except:
                        product['sizes'] = {}
                elif isinstance(sizes, dict):
                    product['sizes'] = sizes
                else:
                    product['sizes'] = {}
                products.append(product)
            return products
    except Exception as e:
        logger.error(f"Error getting products: {e}")
        return []


def get_product_by_key(product_key):
    """Get a specific product by its key"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM products WHERE product_key = %s', (product_key,))
            row = cursor.fetchone()
            if row:
                product = dict(row)
                # Handle JSON fields
                image_urls = product.get('image_urls', [])
                if isinstance(image_urls, str):
                    try:
                        product['image_urls'] = json.loads(image_urls)
                    except:
                        product['image_urls'] = []
                elif isinstance(image_urls, list):
                    product['image_urls'] = image_urls
                else:
                    product['image_urls'] = []

                sizes = product.get('sizes', {})
                if isinstance(sizes, str):
                    try:
                        product['sizes'] = json.loads(sizes)
                    except:
                        product['sizes'] = {}
                elif isinstance(sizes, dict):
                    product['sizes'] = sizes
                else:
                    product['sizes'] = {}
                return product
            return None
    except Exception as e:
        logger.error(f"Error getting product: {e}")
        return None


def get_products_by_seller(seller_email):
    """Get all products for a specific seller"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM products WHERE seller_email = %s ORDER BY posted_date DESC', (seller_email,))
            products = []
            for row in cursor.fetchall():
                product = dict(row)
                # Handle JSON fields
                image_urls = product.get('image_urls', [])
                if isinstance(image_urls, str):
                    try:
                        product['image_urls'] = json.loads(image_urls)
                    except:
                        product['image_urls'] = []
                elif isinstance(image_urls, list):
                    product['image_urls'] = image_urls
                else:
                    product['image_urls'] = []

                sizes = product.get('sizes', {})
                if isinstance(sizes, str):
                    try:
                        product['sizes'] = json.loads(sizes)
                    except:
                        product['sizes'] = {}
                elif isinstance(sizes, dict):
                    product['sizes'] = sizes
                else:
                    product['sizes'] = {}
                products.append(product)
            return products
    except Exception as e:
        logger.error(f"Error getting seller products: {e}")
        return []


def search_products(query, category=None):
    """Search products by name, description, or category"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            if category:
                cursor.execute('''
                    SELECT * FROM products
                    WHERE (name ILIKE %s OR description ILIKE %s)
                    AND category = %s
                    ORDER BY clicks DESC, likes DESC
                ''', (f'%{query}%', f'%{query}%', category))
            else:
                cursor.execute('''
                    SELECT * FROM products
                    WHERE (name ILIKE %s OR description ILIKE %s)
                    ORDER BY clicks DESC, likes DESC
                ''', (f'%{query}%', f'%{query}%'))

            products = []
            for row in cursor.fetchall():
                product = dict(row)
                # Handle JSON fields
                image_urls = product.get('image_urls', [])
                if isinstance(image_urls, str):
                    try:
                        product['image_urls'] = json.loads(image_urls)
                    except:
                        product['image_urls'] = []
                elif isinstance(image_urls, list):
                    product['image_urls'] = image_urls
                else:
                    product['image_urls'] = []

                sizes = product.get('sizes', {})
                if isinstance(sizes, str):
                    try:
                        product['sizes'] = json.loads(sizes)
                    except:
                        product['sizes'] = {}
                elif isinstance(sizes, dict):
                    product['sizes'] = sizes
                else:
                    product['sizes'] = {}
                products.append(product)
            return products
    except Exception as e:
        logger.error(f"Error searching products: {e}")
        return []


def update_product_stats(product_key, field, increment=1):
    """Update product statistics (clicks, likes, etc.)"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE products SET {field} = {field} + %s WHERE product_key = %s',
                           (increment, product_key))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating product stats: {e}")
        return False


# Order-related functions (PostgreSQL compatible)
def get_user_orders(user_email):
    """Get all orders for a user"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT * FROM orders
                WHERE user_email = %s
                ORDER BY order_date DESC
            ''', (user_email,))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting user orders: {e}")
        return []


def get_order_items(order_id):
    """Get all items for a specific order"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT oi.*, p.name, p.image_url
                FROM order_items oi
                LEFT JOIN products p ON oi.product_key = p.product_key
                WHERE oi.order_id = %s
            ''', (order_id,))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting order items: {e}")
        return []


# Admin-related functions (PostgreSQL compatible)
def get_admin_user(email):
    """Get admin user details"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM admin_users WHERE email = %s AND is_active = TRUE', (email,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting admin user: {e}")
        return None


def get_user_flags(user_email):
    """Get active flags for a user"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT * FROM user_flags
                WHERE user_email = %s AND is_active = TRUE
                AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY flag_date DESC
            ''', (user_email,))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting user flags: {e}")
        return []


def get_all_flagged_users():
    """Get all users with active flags - for admin dashboard"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT DISTINCT user_email FROM user_flags
                WHERE is_active = TRUE
                AND (expires_at IS NULL OR expires_at > NOW())
            ''')
            return [row['user_email'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting flagged users: {e}")
        return []


def log_admin_activity(admin_email, action_type, target_type=None, target_id=None, description=None, ip_address=None):
    """Log admin activity"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO admin_activity_log
                (admin_email, action_type, target_type, target_id, description, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (admin_email, action_type, target_type, target_id, description, ip_address))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error logging admin activity: {e}")
        return False


# Seller financial functions (PostgreSQL compatible)
def get_seller_finances(seller_email):
    """Get seller's financial information"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT * FROM seller_finances WHERE seller_email = %s', (seller_email,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting seller finances: {e}")
        return None


def get_seller_transactions(seller_email, limit=10):
    """Get seller's recent transactions"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT * FROM seller_transactions
                WHERE seller_email = %s
                ORDER BY transaction_date DESC
                LIMIT %s
            ''', (seller_email, limit))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting seller transactions: {e}")
        return []


def get_withdrawal_requests(seller_email, limit=5):
    """Get seller's withdrawal request history"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT * FROM withdrawal_requests
                WHERE seller_email = %s
                ORDER BY request_date DESC
                LIMIT %s
            ''', (seller_email, limit))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting withdrawal requests: {e}")
        return []


# Analytics functions for admin dashboard
def get_daily_stats(days=30):
    """Get daily statistics for the last N days"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT
                    DATE(order_date) as date,
                    COUNT(*) as orders_count,
                    SUM(total) as revenue,
                    AVG(total) as avg_order_value
                FROM orders
                WHERE order_date >= NOW() - INTERVAL '%s days'
                AND status != 'cancelled'
                GROUP BY DATE(order_date)
                ORDER BY date DESC
            ''', (days,))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting daily stats: {e}")
        return []


def get_category_stats():
    """Get sales statistics by category"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT
                    p.category,
                    COUNT(DISTINCT p.product_key) as products_count,
                    SUM(p.sold) as total_sold,
                    SUM(p.sold * p.price) as revenue
                FROM products p
                WHERE p.sold > 0
                GROUP BY p.category
                ORDER BY revenue DESC
            ''')
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting category stats: {e}")
        return []


# Utility functions
def get_database_stats():
    """Get general database statistics - PostgreSQL compatible"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Count users
            cursor.execute('SELECT COUNT(*) as total_users FROM users')
            total_users = cursor.fetchone()['total_users']

            # Count sellers
            cursor.execute('SELECT COUNT(*) as total_sellers FROM users WHERE is_seller = TRUE')
            total_sellers = cursor.fetchone()['total_sellers']

            # Count products
            cursor.execute('SELECT COUNT(*) as total_products FROM products')
            total_products = cursor.fetchone()['total_products']

            # Total orders
            cursor.execute('SELECT COUNT(*) as total_orders FROM orders')
            total_orders = cursor.fetchone()['total_orders']

            # Total revenue
            cursor.execute('SELECT SUM(total) as total_revenue FROM orders WHERE status != %s', ('cancelled',))
            total_revenue = cursor.fetchone()['total_revenue'] or 0

            # Platform fees (5%)
            platform_fees = float(total_revenue) * 0.05

            return {
                'total_users': total_users,
                'total_sellers': total_sellers,
                'total_products': total_products,
                'total_orders': total_orders,
                'total_revenue': float(total_revenue),
                'platform_fees': platform_fees
            }
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {}


# User Browsing History & Personalization Functions

def track_product_view(user_email, product_key, category):
    """Track when a user views a product for personalization"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_product_views (user_email, product_key, category)
                VALUES (%s, %s, %s)
            ''', (user_email, product_key, category))
            return True
    except Exception as e:
        logger.error(f"Error tracking product view: {e}")
        return False


def get_last_viewed_product(user_email):
    """Get the most recently viewed product by a user"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT product_key, category, viewed_at
                FROM user_product_views
                WHERE user_email = %s
                ORDER BY viewed_at DESC
                LIMIT 1
            ''', (user_email,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting last viewed product: {e}")
        return None


def get_user_viewing_history(user_email, limit=10):
    """Get user's viewing history"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('''
                SELECT DISTINCT category
                FROM user_product_views
                WHERE user_email = %s
                ORDER BY viewed_at DESC
                LIMIT %s
            ''', (user_email, limit))
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting user viewing history: {e}")
        return []


def get_personalized_products(user_email, excluded_seller_emails=None):
    """
    Get products personalized based on user's browsing history
    Returns products ordered by:
    1. Same category as last viewed
    2. Similar categories based on viewing history
    3. Popular products (high clicks/likes)
    4. Random remaining products
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get last viewed product category
            last_viewed = get_last_viewed_product(user_email)

            if last_viewed and last_viewed['category']:
                last_category = last_viewed['category']

                # Build exclusion clause for flagged sellers
                exclusion_clause = ""
                params = [last_category]

                if excluded_seller_emails:
                    placeholders = ','.join(['%s'] * len(excluded_seller_emails))
                    exclusion_clause = f"AND seller_email NOT IN ({placeholders})"
                    params.extend(excluded_seller_emails)

                # Get products with personalized ordering
                query = f'''
                    SELECT *,
                        CASE
                            WHEN category = %s THEN 1
                            WHEN category IN (
                                SELECT DISTINCT category
                                FROM user_product_views
                                WHERE user_email = %s
                                LIMIT 5
                            ) THEN 2
                            ELSE 3
                        END as priority,
                        (clicks + likes * 2) as popularity_score
                    FROM products
                    WHERE 1=1 {exclusion_clause}
                    ORDER BY priority ASC, popularity_score DESC, RANDOM()
                '''

                params.insert(1, user_email)
                cursor.execute(query, params)
            else:
                # No viewing history - show popular products first
                exclusion_clause = ""
                params = []

                if excluded_seller_emails:
                    placeholders = ','.join(['%s'] * len(excluded_seller_emails))
                    exclusion_clause = f"WHERE seller_email NOT IN ({placeholders})"
                    params.extend(excluded_seller_emails)

                query = f'''
                    SELECT *,
                        (clicks + likes * 2) as popularity_score
                    FROM products
                    {exclusion_clause}
                    ORDER BY popularity_score DESC, RANDOM()
                '''

                cursor.execute(query, params)

            products = {}
            for row in cursor.fetchall():
                product = dict(row)
                # Handle JSON fields
                image_urls = product.get('image_urls', [])
                if isinstance(image_urls, str):
                    try:
                        product['image_urls'] = json.loads(image_urls)
                    except:
                        product['image_urls'] = []
                elif isinstance(image_urls, list):
                    product['image_urls'] = image_urls
                else:
                    product['image_urls'] = []

                sizes = product.get('sizes', {})
                if isinstance(sizes, str):
                    try:
                        product['sizes'] = json.loads(sizes)
                    except:
                        product['sizes'] = {}
                elif isinstance(sizes, dict):
                    product['sizes'] = sizes
                else:
                    product['sizes'] = {}
                products[product['product_key']] = product

            return products

    except Exception as e:
        logger.error(f"Error getting personalized products: {e}")
        # Fallback to all products
        return get_all_products()


if __name__ == "__main__":
    # Test the database when running this file directly
    print("🔧 Testing Zo-Zi PostgreSQL database connection...")
    print(f"📁 Database URL: {get_database_url()}")

    if test_connection():
        print("✅ Ready to migrate from SQLite to PostgreSQL!")
    else:
        print("❌ Please check your PostgreSQL configuration and ensure the database is running.")
        print("💡 Create a database named 'zozi_marketplace' in PostgreSQL first.")