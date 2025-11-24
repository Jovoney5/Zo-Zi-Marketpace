#!/usr/bin/env python3
"""
Migration script to create seller_notifications table
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def create_seller_notifications_table():
    """Create seller_notifications table in PostgreSQL"""

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    try:
        print("🔗 Connecting to PostgreSQL database...")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("✅ Connected successfully!")
        print("\n" + "="*60)
        print("Creating seller_notifications Table")
        print("="*60 + "\n")

        # Create seller_notifications table
        print("1️⃣  Creating seller_notifications table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seller_notifications (
                id SERIAL PRIMARY KEY,
                seller_email VARCHAR(255) NOT NULL,
                notification_type VARCHAR(50) NOT NULL,
                product_key VARCHAR(255),
                product_name TEXT,
                buyer_email VARCHAR(255),
                quantity INTEGER,
                price DECIMAL(10, 2),
                sale_date TIMESTAMP,
                order_id VARCHAR(50),
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (seller_email) REFERENCES users(email) ON DELETE CASCADE
            );
        """)
        conn.commit()
        print("   ✅ seller_notifications table created")

        # Create index for faster queries
        print("\n2️⃣  Creating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_seller_notifications_email
            ON seller_notifications(seller_email);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_seller_notifications_read
            ON seller_notifications(seller_email, is_read);
        """)
        conn.commit()
        print("   ✅ Indexes created")

        # Verify table exists
        print("\n" + "="*60)
        print("Verifying table...")
        print("="*60 + "\n")

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'seller_notifications'
            ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()

        if columns:
            print(f"✅ seller_notifications table verified with {len(columns)} columns:")
            for col in columns[:5]:  # Show first 5 columns
                print(f"   - {col[0]}: {col[1]}")
            if len(columns) > 5:
                print(f"   ... and {len(columns) - 5} more columns")
        else:
            print("❌ Table not found!")

        print("\n" + "="*60)
        print("✅ Migration completed successfully!")
        print("="*60)

        cursor.close()
        conn.close()

        return True

    except psycopg2.Error as e:
        print(f"\n❌ PostgreSQL Error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("\n" + "="*60)
    print("PostgreSQL Migration - Create seller_notifications Table")
    print("="*60 + "\n")

    success = create_seller_notifications_table()

    if success:
        print("\n🎉 seller_notifications table created!")
        print("\n💡 Next steps:")
        print("   1. Restart your Flask app")
        print("   2. Seller notifications will now work")
    else:
        print("\n⚠️  Migration failed. Please check the errors above.")

    print()
