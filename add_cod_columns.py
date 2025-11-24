"""
Add COD (Cash on Delivery) columns to database for trust-based COD system
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://jovoneybrown@localhost:5432/zozi_marketplace')
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("🔧 Adding COD System Columns")
print("=" * 70)

try:
    # Add cod_enabled to users table
    print("\n1. Adding 'cod_enabled' column to users table...")
    cursor.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS cod_enabled BOOLEAN DEFAULT FALSE;
    """)
    conn.commit()
    print("   ✓ Added cod_enabled to users table")

    # Add cod_available to products table
    print("\n2. Adding 'cod_available' column to products table...")
    cursor.execute("""
        ALTER TABLE products
        ADD COLUMN IF NOT EXISTS cod_available BOOLEAN DEFAULT FALSE;
    """)
    conn.commit()
    print("   ✓ Added cod_available to products table")

    # Verify columns were added
    print("\n3. Verifying columns...")
    cursor.execute("""
        SELECT column_name, data_type, column_default
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'cod_enabled';
    """)
    result = cursor.fetchone()
    print(f"   users.cod_enabled: {result}")

    cursor.execute("""
        SELECT column_name, data_type, column_default
        FROM information_schema.columns
        WHERE table_name = 'products' AND column_name = 'cod_available';
    """)
    result = cursor.fetchone()
    print(f"   products.cod_available: {result}")

    print("\n" + "=" * 70)
    print("✅ COD columns added successfully!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Update admin dashboard with COD toggle per seller")
    print("2. Update seller product form to show COD checkbox")
    print("3. Add COD badges to product display")
    print("4. Update checkout logic to filter COD availability")
    print("=" * 70)

except Exception as e:
    print(f"\n❌ Error: {e}")
    conn.rollback()
finally:
    cursor.close()
    conn.close()
