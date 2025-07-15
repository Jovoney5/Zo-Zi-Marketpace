# complete_database_setup.py
# Run this script to create your entire ZoZi database from scratch!

import sqlite3
import json
import hashlib
from datetime import datetime
import os


def create_zozi_database():
    """Create the complete ZoZi marketplace database"""

    # Create database file
    db_name = 'zozi_marketplace.db'

    if os.path.exists(db_name):
        backup_name = f'{db_name}.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        os.rename(db_name, backup_name)
        print(f"📦 Backed up existing database to {backup_name}")

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    print("🚀 Creating ZoZi marketplace database...")

    # Enable foreign keys
    cursor.execute('PRAGMA foreign_keys = ON')

    # 1. USERS TABLE
    cursor.execute('''
        CREATE TABLE users (
            email TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            phone_number TEXT,
            business_name TEXT,
            business_address TEXT,
            profile_picture TEXT,
            is_seller BOOLEAN DEFAULT 0,
            is_verified BOOLEAN DEFAULT 0,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME,
            parish TEXT DEFAULT 'Kingston'
        )
    ''')
    print("✅ Created users table")

    # 2. PRODUCTS TABLE
    cursor.execute('''
        CREATE TABLE products (
            product_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price DECIMAL(10,2) NOT NULL,
            category TEXT,
            seller_email TEXT NOT NULL,
            image_url TEXT,
            image_urls TEXT, -- JSON array of image URLs
            sizes TEXT, -- JSON object for sizes/colors
            condition_item TEXT DEFAULT 'new',
            posted_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            sold INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            add_to_cart INTEGER DEFAULT 0,
            bought_last_month INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (seller_email) REFERENCES users (email)
        )
    ''')
    print("✅ Created products table")

    # 3. CART TABLE
    cursor.execute('''
        CREATE TABLE cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            product_key TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            price DECIMAL(10,2) NOT NULL,
            image_url TEXT,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_email) REFERENCES users (email),
            FOREIGN KEY (product_key) REFERENCES products (product_key),
            UNIQUE(user_email, product_key)
        )
    ''')
    print("✅ Created cart table")

    # 4. ORDERS TABLE
    cursor.execute('''
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY,
            buyer_email TEXT NOT NULL,
            seller_email TEXT NOT NULL,
            product_key TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price DECIMAL(10,2) NOT NULL,
            total_amount DECIMAL(10,2) NOT NULL,
            status TEXT DEFAULT 'pending',
            order_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            shipping_address TEXT,
            tracking_number TEXT,
            notes TEXT,
            FOREIGN KEY (buyer_email) REFERENCES users (email),
            FOREIGN KEY (seller_email) REFERENCES users (email),
            FOREIGN KEY (product_key) REFERENCES products (product_key)
        )
    ''')
    print("✅ Created orders table")

    # 5. SELLER FINANCES TABLE
    cursor.execute('''
        CREATE TABLE seller_finances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT UNIQUE NOT NULL,
            balance DECIMAL(10,2) DEFAULT 0.00,
            total_earnings DECIMAL(10,2) DEFAULT 0.00,
            pending_withdrawals DECIMAL(10,2) DEFAULT 0.00,
            last_withdrawal_date DATETIME,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_email) REFERENCES users (email)
        )
    ''')
    print("✅ Created seller_finances table")

    # 6. SELLER TRANSACTIONS TABLE
    cursor.execute('''
        CREATE TABLE seller_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            transaction_type TEXT NOT NULL, -- 'sale', 'withdrawal_request', 'withdrawal_completed', 'fee', 'refund'
            amount DECIMAL(10,2) NOT NULL,
            product_key TEXT,
            buyer_email TEXT,
            order_id TEXT,
            description TEXT,
            transaction_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            reference_number TEXT,
            FOREIGN KEY (seller_email) REFERENCES users (email)
        )
    ''')
    print("✅ Created seller_transactions table")

    # 7. WITHDRAWAL REQUESTS TABLE
    cursor.execute('''
        CREATE TABLE withdrawal_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            fee DECIMAL(10,2) NOT NULL,
            net_amount DECIMAL(10,2) NOT NULL,
            method TEXT NOT NULL, -- 'instant', 'standard', 'paypal', 'bank'
            status TEXT DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed', 'cancelled'
            request_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_date DATETIME,
            processing_time TEXT,
            reference_number TEXT,
            payment_details TEXT, -- JSON string for payment method details
            admin_notes TEXT,
            FOREIGN KEY (seller_email) REFERENCES users (email)
        )
    ''')
    print("✅ Created withdrawal_requests table")

    # 8. SELLER PAYMENT METHODS TABLE
    cursor.execute('''
        CREATE TABLE seller_payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            method_type TEXT NOT NULL, -- 'bank', 'paypal', 'mobile_money'
            method_name TEXT NOT NULL, -- User-friendly name
            account_details TEXT NOT NULL, -- JSON string with account info
            is_verified BOOLEAN DEFAULT 0,
            is_default BOOLEAN DEFAULT 0,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_email) REFERENCES users (email)
        )
    ''')
    print("✅ Created seller_payment_methods table")

    # 9. PRODUCT REVIEWS TABLE
    cursor.execute('''
        CREATE TABLE product_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_key TEXT NOT NULL,
            reviewer_email TEXT NOT NULL,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            review_text TEXT,
            review_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_verified_purchase BOOLEAN DEFAULT 0,
            FOREIGN KEY (product_key) REFERENCES products (product_key),
            FOREIGN KEY (reviewer_email) REFERENCES users (email),
            UNIQUE(product_key, reviewer_email)
        )
    ''')
    print("✅ Created product_reviews table")

    # 10. SELLER RATINGS TABLE
    cursor.execute('''
        CREATE TABLE seller_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            rater_email TEXT NOT NULL,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            comment TEXT,
            order_id TEXT,
            rating_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_email) REFERENCES users (email),
            FOREIGN KEY (rater_email) REFERENCES users (email),
            UNIQUE(seller_email, rater_email, order_id)
        )
    ''')
    print("✅ Created seller_ratings table")

    # 11. USER SESSIONS TABLE (for login tracking)
    cursor.execute('''
        CREATE TABLE user_sessions (
            session_id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_email) REFERENCES users (email)
        )
    ''')
    print("✅ Created user_sessions table")

    # 12. PRODUCT CATEGORIES TABLE
    cursor.execute('''
        CREATE TABLE product_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT UNIQUE NOT NULL,
            description TEXT,
            parent_category_id INTEGER,
            is_active BOOLEAN DEFAULT 1,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_category_id) REFERENCES product_categories (id)
        )
    ''')
    print("✅ Created product_categories table")

    # CREATE INDEXES FOR BETTER PERFORMANCE
    indexes = [
        'CREATE INDEX idx_products_seller ON products(seller_email)',
        'CREATE INDEX idx_products_category ON products(category)',
        'CREATE INDEX idx_products_active ON products(is_active)',
        'CREATE INDEX idx_cart_user ON cart(user_email)',
        'CREATE INDEX idx_orders_buyer ON orders(buyer_email)',
        'CREATE INDEX idx_orders_seller ON orders(seller_email)',
        'CREATE INDEX idx_orders_status ON orders(status)',
        'CREATE INDEX idx_seller_finances_email ON seller_finances(seller_email)',
        'CREATE INDEX idx_seller_transactions_email ON seller_transactions(seller_email)',
        'CREATE INDEX idx_seller_transactions_date ON seller_transactions(transaction_date)',
        'CREATE INDEX idx_withdrawal_requests_email ON withdrawal_requests(seller_email)',
        'CREATE INDEX idx_withdrawal_status ON withdrawal_requests(status)',
        'CREATE INDEX idx_reviews_product ON product_reviews(product_key)',
        'CREATE INDEX idx_ratings_seller ON seller_ratings(seller_email)',
        'CREATE INDEX idx_sessions_user ON user_sessions(user_email)',
        'CREATE INDEX idx_sessions_active ON user_sessions(is_active)'
    ]

    for index in indexes:
        cursor.execute(index)
    print("✅ Created database indexes")

    # INSERT DEFAULT CATEGORIES
    categories = [
        ('Electronics', 'Phones, computers, gadgets'),
        ('Clothing', 'Fashion, shoes, accessories'),
        ('Home & Garden', 'Furniture, decor, tools'),
        ('Sports & Fitness', 'Equipment, apparel, supplements'),
        ('Books & Education', 'Textbooks, novels, courses'),
        ('Beauty & Health', 'Cosmetics, skincare, wellness'),
        ('Automotive', 'Car parts, accessories, tools'),
        ('Food & Beverages', 'Local foods, spices, drinks'),
        ('Arts & Crafts', 'Handmade items, supplies'),
        ('Toys & Games', 'Children toys, board games'),
        ('Music & Instruments', 'Instruments, equipment, music'),
        ('Services', 'Professional services, tutoring')
    ]

    cursor.executemany('''
        INSERT INTO product_categories (category_name, description) 
        VALUES (?, ?)
    ''', categories)
    print("✅ Added default product categories")

    # CREATE TRIGGER TO AUTO-UPDATE SELLER FINANCES
    cursor.execute('''
        CREATE TRIGGER update_seller_finances_on_sale
        AFTER UPDATE OF sold ON products
        WHEN NEW.sold > OLD.sold
        BEGIN
            -- Update seller balance and earnings
            INSERT OR REPLACE INTO seller_finances (
                seller_email, 
                balance, 
                total_earnings,
                updated_date
            )
            VALUES (
                NEW.seller_email,
                COALESCE(
                    (SELECT balance FROM seller_finances WHERE seller_email = NEW.seller_email), 0
                ) + (NEW.price * (NEW.sold - OLD.sold)),
                COALESCE(
                    (SELECT total_earnings FROM seller_finances WHERE seller_email = NEW.seller_email), 0
                ) + (NEW.price * (NEW.sold - OLD.sold)),
                datetime('now')
            );

            -- Create transaction record
            INSERT INTO seller_transactions (
                seller_email, 
                transaction_type, 
                amount, 
                product_key, 
                description
            )
            VALUES (
                NEW.seller_email,
                'sale',
                NEW.price * (NEW.sold - OLD.sold),
                NEW.product_key,
                'Sale of ' || NEW.name || ' (' || (NEW.sold - OLD.sold) || ' units)'
            );
        END;
    ''')
    print("✅ Created automatic financial update trigger")

    # CREATE SAMPLE DATA FOR TESTING
    def hash_password(password):
        return hashlib.sha256(password.encode()).hexdigest()

    # Sample users
    sample_users = [
        ('john@zozi.com', 'John', 'Brown', hash_password('password123'), '876-555-0101', 'John\'s Electronics',
         'Kingston', 'profile1.jpg', 1, 1, 'Kingston'),
        ('sarah@zozi.com', 'Sarah', 'Johnson', hash_password('password123'), '876-555-0102', 'Sarah\'s Fashion',
         'Spanish Town', 'profile2.jpg', 1, 1, 'St. Catherine'),
        ('mike@zozi.com', 'Mike', 'Williams', hash_password('password123'), '876-555-0103', '', 'Montego Bay', None, 0,
         0, 'St. James'),
        ('admin@zozi.com', 'ZoZi', 'Admin', hash_password('admin123'), '876-555-0000', 'ZoZi Marketplace', 'Kingston',
         None, 1, 1, 'Kingston')
    ]

    cursor.executemany('''
        INSERT INTO users (email, first_name, last_name, password_hash, phone_number, business_name, business_address, profile_picture, is_seller, is_verified, parish)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', sample_users)
    print("✅ Added sample users")

    # Sample products
    sample_products = [
        ('iPhone 13 Pro Max', 'iPhone 13 Pro Max - Excellent condition, unlocked', 85000.00, 'Electronics',
         'john@zozi.com', 'iphone13.jpg',
         json.dumps(['iphone13_1.jpg', 'iphone13_2.jpg']), json.dumps({'Blue': 'No Size', 'Gold': 'No Size'}),
         'excellent'),
        ('Nike Air Force 1', 'Classic white Nike Air Force 1 sneakers', 12000.00, 'Clothing', 'sarah@zozi.com',
         'airforce1.jpg',
         json.dumps(['af1_1.jpg', 'af1_2.jpg']), json.dumps({'White': ['8', '9', '10', '11'], 'Black': ['9', '10']}),
         'new'),
        ('Samsung Galaxy S24', 'Brand new Samsung Galaxy S24, factory sealed', 95000.00, 'Electronics', 'john@zozi.com',
         'galaxy_s24.jpg',
         json.dumps(['galaxy_1.jpg', 'galaxy_2.jpg']), json.dumps({'Black': 'No Size', 'White': 'No Size'}), 'new'),
        ('Vintage Denim Jacket', 'Authentic vintage denim jacket from the 90s', 8500.00, 'Clothing', 'sarah@zozi.com',
         'denim_jacket.jpg',
         json.dumps(['denim_1.jpg', 'denim_2.jpg']), json.dumps({'Blue': ['S', 'M', 'L']}), 'good')
    ]

    for i, product in enumerate(sample_products):
        product_key = f"PROD_{i + 1:04d}"
        cursor.execute('''
            INSERT INTO products (product_key, name, description, price, category, seller_email, image_url, image_urls, sizes, condition_item, sold, clicks, likes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (product_key,) + product + (0, 15 + i * 5, 3 + i * 2))

    print("✅ Added sample products")

    # Initialize seller finances for sample sellers
    cursor.execute('''
        INSERT INTO seller_finances (seller_email, balance, total_earnings)
        VALUES ('john@zozi.com', 0.00, 0.00)
    ''')

    cursor.execute('''
        INSERT INTO seller_finances (seller_email, balance, total_earnings)
        VALUES ('sarah@zozi.com', 0.00, 0.00)
    ''')
    print("✅ Initialized seller finances")

    conn.commit()
    conn.close()

    print(f"\n🎉 ZoZi database '{db_name}' created successfully!")
    print("\n📊 Database includes:")
    print("   • User management (buyers & sellers)")
    print("   • Product catalog with images & variants")
    print("   • Shopping cart & orders")
    print("   • Financial tracking & withdrawals")
    print("   • Reviews & ratings")
    print("   • Categories & search indexes")
    print("   • Sample data for testing")

    print("\n👥 Sample accounts created:")
    print("   • john@zozi.com / password123 (Seller)")
    print("   • sarah@zozi.com / password123 (Seller)")
    print("   • mike@zozi.com / password123 (Buyer)")
    print("   • admin@zozi.com / admin123 (Admin)")

    print(f"\n📁 Database file: {os.path.abspath(db_name)}")
    print("\n🚀 Ready to launch ZoZi!")


if __name__ == "__main__":
    create_zozi_database()