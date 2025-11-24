#!/usr/bin/env python3
"""
Migration script to add missing columns to PostgreSQL database
Run this once to fix column errors
"""

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def add_missing_columns():
    """Add missing columns to PostgreSQL tables"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    try:
        # Connect to PostgreSQL
        print("🔗 Connecting to PostgreSQL database...")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("✅ Connected successfully!")
        print("\n" + "="*60)
        print("Adding missing columns...")
        print("="*60 + "\n")

        # 1. Add business_description to users table
        print("1️⃣  Adding 'business_description' to users table...")
        try:
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS business_description TEXT;
            """)
            conn.commit()
            print("   ✅ business_description column added/verified")
        except Exception as e:
            print(f"   ⚠️  Note: {e}")
            conn.rollback()

        # 2. Add lynk_reference to orders table
        print("\n2️⃣  Adding 'lynk_reference' to orders table...")
        try:
            cursor.execute("""
                ALTER TABLE orders
                ADD COLUMN IF NOT EXISTS lynk_reference VARCHAR(255);
            """)
            conn.commit()
            print("   ✅ lynk_reference column added/verified")
        except Exception as e:
            print(f"   ⚠️  Note: {e}")
            conn.rollback()

        # 3. Add payment_verified to orders table
        print("\n3️⃣  Adding 'payment_verified' to orders table...")
        try:
            cursor.execute("""
                ALTER TABLE orders
                ADD COLUMN IF NOT EXISTS payment_verified BOOLEAN DEFAULT FALSE;
            """)
            conn.commit()
            print("   ✅ payment_verified column added/verified")
        except Exception as e:
            print(f"   ⚠️  Note: {e}")
            conn.rollback()

        # 4. Verify the columns exist
        print("\n" + "="*60)
        print("Verifying columns...")
        print("="*60 + "\n")

        # Check users table
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name = 'business_description';
        """)
        result = cursor.fetchone()
        if result:
            print(f"✅ users.business_description: {result[1]}")
        else:
            print("❌ users.business_description: NOT FOUND")

        # Check orders table
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'orders'
            AND column_name IN ('lynk_reference', 'payment_verified')
            ORDER BY column_name;
        """)
        results = cursor.fetchall()
        for col in results:
            print(f"✅ orders.{col[0]}: {col[1]}")

        print("\n" + "="*60)
        print("✅ Migration completed successfully!")
        print("="*60)

        # Close connection
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
    print("PostgreSQL Migration Script - Add Missing Columns")
    print("="*60 + "\n")

    success = add_missing_columns()

    if success:
        print("\n🎉 You can now run your Flask app without column errors!")
        print("\n💡 Next step: Restart your Flask app")
    else:
        print("\n⚠️  Migration failed. Please check the errors above.")

    print()
