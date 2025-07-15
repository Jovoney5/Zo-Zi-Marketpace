# database.py - Database helper functions for ZoZi (Compatible with existing app.py)

import sqlite3
import os
import json
from contextlib import contextmanager
from datetime import datetime
import logging

# Database configuration - MATCH YOUR EXISTING APP.PY
DATABASE_NAME = 'zo-zi.db'  # Changed to match your app.py


def get_db_path():
    """Get the full path to the database file"""
    return os.path.join(os.getcwd(), DATABASE_NAME)


def init_db():
    """Initialize the database (run once when setting up the app)"""
    if not os.path.exists(get_db_path()):
        print("❌ Database not found! Please run your existing init_db() from app.py first")
        return False

    print(f"✅ Database found at: {get_db_path()}")
    return True


@contextmanager
def get_db():
    """
    Context manager for database connections - COMPATIBLE WITH YOUR APP.PY
    Usage:
        with get_db() as conn:
            cursor = conn.cursor()
            # do database operations
    """
    conn = None
    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row  # This allows accessing columns by name
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def get_db_connection():
    """
    Alternative method - simple connection getter
    Remember to close the connection when done!
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# User-related database functions (COMPATIBLE WITH YOUR SCHEMA)
def create_user(email, first_name, last_name, password, phone_number=None, parish='Kingston', is_seller=False):
    """Create a new user account - matches your existing schema"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (email, first_name, last_name, password, phone_number, parish, is_seller, 
                                 discount_applied, discount_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (email, first_name, last_name, password, phone_number, parish, is_seller, False, False))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False  # User already exists
    except Exception as e:
        logging.error(f"Error creating user: {e}")
        return False


def get_user_by_email(email):
    """Get user details by email"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            return cursor.fetchone()
    except Exception as e:
        logging.error(f"Error getting user: {e}")
        return None


def get_user_by_phone(phone_number):
    """Get user details by phone number"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE phone_number = ?', (phone_number,))
            return cursor.fetchone()
    except Exception as e:
        logging.error(f"Error getting user by phone: {e}")
        return None


def verify_user_login(identifier, password):
    """Verify user login credentials (email or phone)"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM users 
                WHERE (email = ? OR phone_number = ?) AND password = ?
            ''', (identifier, identifier, password))
            return cursor.fetchone()
    except Exception as e:
        logging.error(f"Error verifying login: {e}")
        return None


def update_user_profile(email, **kwargs):
    """Update user profile information"""
    try:
        # Build dynamic update query
        fields = []
        values = []
        for key, value in kwargs.items():
            if value is not None:
                fields.append(f"{key} = ?")
                values.append(value)

        if not fields:
            return False

        values.append(email)
        query = f"UPDATE users SET {', '.join(fields)} WHERE email = ?"

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, values)
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"Error updating user profile: {e}")
        return False


# Product-related database functions (COMPATIBLE WITH YOUR SCHEMA)
def get_all_products(active_only=True):
    """Get all products from the database"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            # Your schema doesn't have is_active, so we get all products
            cursor.execute('SELECT * FROM products ORDER BY posted_date DESC')
            products = []
            for row in cursor.fetchall():
                product = dict(row)
                # Parse JSON fields
                product['image_urls'] = json.loads(product['image_urls']) if product['image_urls'] else []
                product['sizes'] = json.loads(product['sizes']) if product['sizes'] else {}
                products.append(product)
            return products
    except Exception as e:
        logging.error(f"Error getting products: {e}")
        return []


def get_product_by_key(product_key):
    """Get a specific product by its key"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM products WHERE product_key = ?', (product_key,))
            row = cursor.fetchone()
            if row:
                product = dict(row)
                product['image_urls'] = json.loads(product['image_urls']) if product['image_urls'] else []
                product['sizes'] = json.loads(product['sizes']) if product['sizes'] else {}
                return product
            return None
    except Exception as e:
        logging.error(f"Error getting product: {e}")
        return None


def get_products_by_seller(seller_email):
    """Get all products for a specific seller"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM products WHERE seller_email = ? ORDER BY posted_date DESC', (seller_email,))
            products = []
            for row in cursor.fetchall():
                product = dict(row)
                product['image_urls'] = json.loads(product['image_urls']) if product['image_urls'] else []
                product['sizes'] = json.loads(product['sizes']) if product['sizes'] else {}
                products.append(product)
            return products
    except Exception as e:
        logging.error(f"Error getting seller products: {e}")
        return []


def search_products(query, category=None):
    """Search products by name, description, or category"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            if category:
                cursor.execute('''
                    SELECT * FROM products 
                    WHERE (name LIKE ? OR description LIKE ?) 
                    AND category = ?
                    ORDER BY clicks DESC, likes DESC
                ''', (f'%{query}%', f'%{query}%', category))
            else:
                cursor.execute('''
                    SELECT * FROM products 
                    WHERE (name LIKE ? OR description LIKE ?)
                    ORDER BY clicks DESC, likes DESC
                ''', (f'%{query}%', f'%{query}%'))

            products = []
            for row in cursor.fetchall():
                product = dict(row)
                product['image_urls'] = json.loads(product['image_urls']) if product['image_urls'] else []
                product['sizes'] = json.loads(product['sizes']) if product['sizes'] else {}
                products.append(product)
            return products
    except Exception as e:
        logging.error(f"Error searching products: {e}")
        return []


def update_product_stats(product_key, field, increment=1):
    """Update product statistics (clicks, likes, etc.)"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE products SET {field} = {field} + ? WHERE product_key = ?',
                           (increment, product_key))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logging.error(f"Error updating product stats: {e}")
        return False


# Order-related functions (COMPATIBLE WITH YOUR SCHEMA)
def get_user_orders(user_email):
    """Get all orders for a user"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM orders 
                WHERE user_email = ? 
                ORDER BY order_date DESC
            ''', (user_email,))
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Error getting user orders: {e}")
        return []


def get_order_items(order_id):
    """Get all items for a specific order"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT oi.*, p.name, p.image_url
                FROM order_items oi
                LEFT JOIN products p ON oi.product_key = p.product_key
                WHERE oi.order_id = ?
            ''', (order_id,))
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Error getting order items: {e}")
        return []


# Admin-related functions (COMPATIBLE WITH YOUR SCHEMA)
def get_admin_user(email):
    """Get admin user details"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM admin_users WHERE email = ? AND is_active = 1', (email,))
            return cursor.fetchone()
    except Exception as e:
        logging.error(f"Error getting admin user: {e}")
        return None


def get_user_flags(user_email):
    """Get active flags for a user"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM user_flags 
                WHERE user_email = ? AND is_active = 1
                AND (expires_at IS NULL OR expires_at > datetime('now'))
                ORDER BY flag_date DESC
            ''', (user_email,))
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Error getting user flags: {e}")
        return []


def log_admin_activity(admin_email, action_type, target_type=None, target_id=None, description=None, ip_address=None):
    """Log admin activity"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO admin_activity_log 
                (admin_email, action_type, target_type, target_id, description, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (admin_email, action_type, target_type, target_id, description, ip_address))
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error logging admin activity: {e}")
        return False


# Seller financial functions (COMPATIBLE WITH YOUR SCHEMA)
def get_seller_finances(seller_email):
    """Get seller's financial information"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM seller_finances WHERE seller_email = ?', (seller_email,))
            return cursor.fetchone()
    except Exception as e:
        logging.error(f"Error getting seller finances: {e}")
        return None


def get_seller_transactions(seller_email, limit=10):
    """Get seller's recent transactions"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM seller_transactions 
                WHERE seller_email = ? 
                ORDER BY transaction_date DESC 
                LIMIT ?
            ''', (seller_email, limit))
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Error getting seller transactions: {e}")
        return []


def get_withdrawal_requests(seller_email, limit=5):
    """Get seller's withdrawal request history"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM withdrawal_requests 
                WHERE seller_email = ? 
                ORDER BY request_date DESC 
                LIMIT ?
            ''', (seller_email, limit))
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Error getting withdrawal requests: {e}")
        return []


# Analytics functions for admin dashboard
def get_daily_stats(days=30):
    """Get daily statistics for the last N days"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    DATE(order_date) as date,
                    COUNT(*) as orders_count,
                    SUM(total) as revenue,
                    AVG(total) as avg_order_value
                FROM orders 
                WHERE order_date >= date('now', '-{} days')
                AND status != 'cancelled'
                GROUP BY DATE(order_date)
                ORDER BY date DESC
            '''.format(days))
            return cursor.fetchall()
    except Exception as e:
        logging.error(f"Error getting daily stats: {e}")
        return []


def get_category_stats():
    """Get sales statistics by category"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
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
        logging.error(f"Error getting category stats: {e}")
        return []


# Utility functions
def get_database_stats():
    """Get general database statistics - COMPATIBLE WITH YOUR SCHEMA"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Count users
            cursor.execute('SELECT COUNT(*) as total_users FROM users')
            total_users = cursor.fetchone()['total_users']

            # Count sellers
            cursor.execute('SELECT COUNT(*) as total_sellers FROM users WHERE is_seller = 1')
            total_sellers = cursor.fetchone()['total_sellers']

            # Count products
            cursor.execute('SELECT COUNT(*) as total_products FROM products')
            total_products = cursor.fetchone()['total_products']

            # Total orders
            cursor.execute('SELECT COUNT(*) as total_orders FROM orders')
            total_orders = cursor.fetchone()['total_orders']

            # Total revenue
            cursor.execute('SELECT SUM(total) as total_revenue FROM orders WHERE status != "cancelled"')
            total_revenue = cursor.fetchone()['total_revenue'] or 0

            # Platform fees (5%)
            platform_fees = total_revenue * 0.05

            return {
                'total_users': total_users,
                'total_sellers': total_sellers,
                'total_products': total_products,
                'total_orders': total_orders,
                'total_revenue': total_revenue,
                'platform_fees': platform_fees
            }
    except Exception as e:
        logging.error(f"Error getting database stats: {e}")
        return {}


# Test database connection
def test_connection():
    """Test if database connection works"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM users')
            result = cursor.fetchone()
            print(f"✅ Database connection successful! Found {result['count']} users")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def verify_schema():
    """Verify that all expected tables exist"""
    expected_tables = [
        'users', 'products', 'orders', 'order_items', 'admin_users',
        'user_flags', 'admin_activity_log', 'seller_finances',
        'seller_transactions', 'withdrawal_requests'
    ]

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row['name'] for row in cursor.fetchall()]

            missing_tables = []
            for table in expected_tables:
                if table not in existing_tables:
                    missing_tables.append(table)

            if missing_tables:
                print(f"⚠️  Missing tables: {', '.join(missing_tables)}")
                print("🔧 Run your app.py init_db() function to create missing tables")
                return False
            else:
                print("✅ All expected tables found!")
                return True

    except Exception as e:
        print(f"❌ Error verifying schema: {e}")
        return False


if __name__ == "__main__":
    # Test the database when running this file directly
    print("🔧 Testing ZoZi database connection...")
    print(f"📁 Database path: {get_db_path()}")

    if test_connection():
        print("\n📋 Verifying database schema...")
        if verify_schema():
            print("\n📊 Database Stats:")
            stats = get_database_stats()
            print(f"   • Users: {stats.get('total_users', 0)}")
            print(f"   • Sellers: {stats.get('total_sellers', 0)}")
            print(f"   • Products: {stats.get('total_products', 0)}")
            print(f"   • Orders: {stats.get('total_orders', 0)}")
            print(f"   • Total Revenue: ${stats.get('total_revenue', 0):,.2f} JMD")
            print(f"   • Platform Fees: ${stats.get('platform_fees', 0):,.2f} JMD")
    else:
        print("💡 Make sure your zo-zi.db database exists and run your app.py first!")