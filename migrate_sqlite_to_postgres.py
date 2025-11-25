#!/usr/bin/env python3
"""
Migrate data from SQLite (zo-zi.db) to PostgreSQL on Render
"""
import sqlite3
import psycopg2
import psycopg2.extras
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Get PostgreSQL connection URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL not found in environment")
    print("Make sure you have the DATABASE_URL from Render in your .env file")
    exit(1)

# Connect to SQLite
print("📂 Connecting to SQLite database...")
sqlite_conn = sqlite3.connect('zo-zi.db')
sqlite_conn.row_factory = sqlite3.Row
sqlite_cursor = sqlite_conn.cursor()

# Connect to PostgreSQL
print("🐘 Connecting to PostgreSQL database...")
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
pg_conn = psycopg2.connect(DATABASE_URL)
pg_cursor = pg_conn.cursor()

print("\n" + "="*60)
print("MIGRATION STARTING")
print("="*60)

# Migrate users
print("\n👥 Migrating users...")
sqlite_cursor.execute("SELECT * FROM users")
users = sqlite_cursor.fetchall()
users_migrated = 0
users_skipped = 0

for user_row in users:
    try:
        user = dict(user_row)  # Convert Row to dict
        pg_cursor.execute('''
            INSERT INTO users (
                email, password, first_name, last_name, is_seller, is_support,
                phone_number, address, parish, post_office, profile_picture,
                discount_used, notification_preference, business_name, business_address,
                security_question, security_answer, discount_applied, gender,
                delivery_address, billing_address, whatsapp_number, business_description,
                verification_status, purchase_count
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (email) DO NOTHING
        ''', (
            user['email'], user['password'], user['first_name'], user['last_name'],
            bool(user['is_seller']), bool(user.get('is_support', 0)),
            user.get('phone_number'), user.get('address'), user.get('parish'),
            user.get('post_office'), user.get('profile_picture'),
            bool(user.get('discount_used', 0)), user.get('notification_preference'),
            user.get('business_name'), user.get('business_address'),
            user.get('security_question'), user.get('security_answer'),
            bool(user.get('discount_applied', 0)), user.get('gender'),
            user.get('delivery_address'), user.get('billing_address'),
            user.get('whatsapp_number'), user.get('business_description'),
            user.get('verification_status', 'pending_documents'),
            user.get('purchase_count', 0)
        ))
        if pg_cursor.rowcount > 0:
            users_migrated += 1
            print(f"  ✓ Migrated user: {user['email']}")
        else:
            users_skipped += 1
            print(f"  ⊙ Skipped (already exists): {user['email']}")
    except Exception as e:
        print(f"  ✗ Error migrating user {user['email']}: {e}")

pg_conn.commit()
print(f"\n✅ Users: {users_migrated} migrated, {users_skipped} skipped")

# Migrate products
print("\n🛍️  Migrating products...")
sqlite_cursor.execute("SELECT * FROM products")
products = sqlite_cursor.fetchall()
products_migrated = 0
products_skipped = 0

for product_row in products:
    try:
        product = dict(product_row)  # Convert Row to dict
        # Handle JSON fields
        sizes = product.get('sizes', '{}')
        if isinstance(sizes, str):
            try:
                sizes = json.loads(sizes)
            except:
                sizes = {}

        image_urls = product.get('image_urls', '[]')
        if isinstance(image_urls, str):
            try:
                image_urls = json.loads(image_urls)
            except:
                image_urls = []

        pg_cursor.execute('''
            INSERT INTO products (
                product_key, seller_email, name, description, price, category,
                sizes, image_urls, image_url, clicks, likes, sold,
                stock_quantity, is_active
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (product_key) DO NOTHING
        ''', (
            product['product_key'], product['seller_email'], product['name'],
            product['description'], product['price'], product['category'],
            json.dumps(sizes), json.dumps(image_urls), product.get('image_url'),
            product.get('clicks', 0), product.get('likes', 0), product.get('sold', 0),
            product.get('stock_quantity', 0), bool(product.get('is_active', 1))
        ))
        if pg_cursor.rowcount > 0:
            products_migrated += 1
            print(f"  ✓ Migrated: {product['name']} ({product['product_key']})")
        else:
            products_skipped += 1
            print(f"  ⊙ Skipped (already exists): {product['name']}")
    except Exception as e:
        print(f"  ✗ Error migrating product {product['name']}: {e}")

pg_conn.commit()
print(f"\n✅ Products: {products_migrated} migrated, {products_skipped} skipped")

# Migrate orders if they exist
try:
    sqlite_cursor.execute("SELECT COUNT(*) FROM orders")
    order_count = sqlite_cursor.fetchone()[0]
    if order_count > 0:
        print(f"\n📦 Migrating {order_count} orders...")
        sqlite_cursor.execute("SELECT * FROM orders")
        orders = sqlite_cursor.fetchall()
        orders_migrated = 0

        for order_row in orders:
            try:
                order = dict(order_row)  # Convert Row to dict
                pg_cursor.execute('''
                    INSERT INTO orders (
                        order_id, user_email, full_name, phone_number, address,
                        parish, post_office, total, discount, payment_method,
                        status, shipping_option, shipping_fee, tax, lynk_reference,
                        payment_verified
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) ON CONFLICT (order_id) DO NOTHING
                ''', (
                    order['order_id'], order['user_email'], order.get('full_name'),
                    order.get('phone_number'), order.get('address'), order.get('parish'),
                    order.get('post_office'), order['total'], order.get('discount', 0),
                    order.get('payment_method'), order.get('status', 'pending'),
                    order.get('shipping_option'), order.get('shipping_fee', 0),
                    order.get('tax', 0), order.get('lynk_reference'),
                    bool(order.get('payment_verified', 0))
                ))
                if pg_cursor.rowcount > 0:
                    orders_migrated += 1
            except Exception as e:
                print(f"  ✗ Error migrating order {order['order_id']}: {e}")

        pg_conn.commit()
        print(f"✅ Orders: {orders_migrated} migrated")
except Exception as e:
    print(f"⚠️  No orders to migrate or error: {e}")

# Close connections
sqlite_conn.close()
pg_conn.close()

print("\n" + "="*60)
print("MIGRATION COMPLETE!")
print("="*60)
print(f"✅ {users_migrated} users migrated")
print(f"✅ {products_migrated} products migrated")
print("\nYour data is now on Render PostgreSQL!")
