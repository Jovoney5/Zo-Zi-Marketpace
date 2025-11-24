"""
Create missing payment system tables:
- seller_payment_methods
- payment_transactions (or verify withdrawal_requests is sufficient)
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

print("=" * 70)
print("Creating Missing Payment System Tables")
print("=" * 70)

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    print("\n1. Creating seller_payment_methods table...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_payment_methods (
            id SERIAL PRIMARY KEY,
            seller_email VARCHAR(255) NOT NULL,
            payment_type VARCHAR(20) NOT NULL,  -- 'card', 'mobile', 'bank', 'lynk'
            account_number VARCHAR(100),
            account_name VARCHAR(100),
            bank_name VARCHAR(100),
            phone_number VARCHAR(20),  -- For Lynk/mobile payments
            is_default BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_email) REFERENCES users(email) ON DELETE CASCADE
        );
    ''')
    print("   ✅ seller_payment_methods table created!")

    print("\n2. Adding indexes for performance...")
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_seller_payment_methods_seller
        ON seller_payment_methods(seller_email);
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_seller_payment_methods_default
        ON seller_payment_methods(seller_email, is_default)
        WHERE is_default = true;
    ''')
    print("   ✅ Indexes created!")

    print("\n3. Checking if payment_transactions table exists...")
    cursor.execute('''
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'payment_transactions'
        );
    ''')
    exists = cursor.fetchone()[0]

    if exists:
        print("   ✅ payment_transactions table already exists!")
    else:
        print("   Creating payment_transactions table...")
        cursor.execute('''
            CREATE TABLE payment_transactions (
                id SERIAL PRIMARY KEY,
                transaction_id VARCHAR(50) UNIQUE NOT NULL,
                seller_email VARCHAR(255),
                amount DECIMAL(10,2) NOT NULL,
                fee DECIMAL(10,2) DEFAULT 0,
                net_amount DECIMAL(10,2) NOT NULL,
                transaction_type VARCHAR(20) NOT NULL,  -- 'withdrawal', 'payout', 'refund'
                payment_method_id INTEGER,
                payment_method VARCHAR(20),  -- 'bank', 'lynk', 'card', 'mobile'
                status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'completed', 'failed', 'cancelled'
                reference_number VARCHAR(100),  -- External reference (bank confirmation, etc.)
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (seller_email) REFERENCES users(email) ON DELETE SET NULL,
                FOREIGN KEY (payment_method_id) REFERENCES seller_payment_methods(id) ON DELETE SET NULL
            );
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_payment_transactions_seller
            ON payment_transactions(seller_email);
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_payment_transactions_status
            ON payment_transactions(status);
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_payment_transactions_type
            ON payment_transactions(transaction_type);
        ''')
        print("   ✅ payment_transactions table created!")

    conn.commit()
    print("\n" + "=" * 70)
    print("✅ ALL TABLES CREATED SUCCESSFULLY!")
    print("=" * 70)

    # Show table info
    print("\n📊 Table Summary:")
    cursor.execute('''
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name IN ('seller_payment_methods', 'payment_transactions', 'withdrawal_requests')
        ORDER BY table_name;
    ''')

    tables = cursor.fetchall()
    for table in tables:
        print(f"   ✅ {table[0]}")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

finally:
    if 'conn' in locals():
        conn.close()
        print("\n✅ Database connection closed.")
