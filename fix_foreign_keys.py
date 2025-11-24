#!/usr/bin/env python3
"""
Migration script to fix foreign key constraints
Run this once to allow:
1. Guest emails that don't exist in users table
2. Product keys with variations that don't exactly match products table
"""

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def fix_foreign_keys():
    """Remove foreign key constraints that block guest checkout and product variations"""

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
        print("Fixing Foreign Key Constraints")
        print("="*60 + "\n")

        # 1. Check existing foreign key constraints on orders table
        print("1️⃣  Checking foreign key constraints on orders table...")
        cursor.execute("""
            SELECT constraint_name, column_name
            FROM information_schema.key_column_usage
            WHERE table_name = 'orders'
            AND constraint_name IN (
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'orders'
                AND constraint_type = 'FOREIGN KEY'
            );
        """)
        orders_constraints = cursor.fetchall()

        if orders_constraints:
            print(f"   Found {len(orders_constraints)} constraint(s):")
            for constraint in orders_constraints:
                print(f"   - {constraint[0]} on column {constraint[1]}")
        else:
            print("   ℹ️  No foreign key constraints found on orders table")

        # 2. Remove foreign key constraint on orders.user_email
        print("\n2️⃣  Removing foreign key constraint on orders.user_email...")
        try:
            cursor.execute("""
                ALTER TABLE orders
                DROP CONSTRAINT IF EXISTS orders_user_email_fkey;
            """)
            conn.commit()
            print("   ✅ orders_user_email_fkey constraint removed")
        except Exception as e:
            print(f"   ℹ️  Note: {e}")
            conn.rollback()

        # 3. Check existing foreign key constraints on order_items table
        print("\n3️⃣  Checking foreign key constraints on order_items table...")
        cursor.execute("""
            SELECT constraint_name, column_name
            FROM information_schema.key_column_usage
            WHERE table_name = 'order_items'
            AND constraint_name IN (
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'order_items'
                AND constraint_type = 'FOREIGN KEY'
            );
        """)
        order_items_constraints = cursor.fetchall()

        if order_items_constraints:
            print(f"   Found {len(order_items_constraints)} constraint(s):")
            for constraint in order_items_constraints:
                print(f"   - {constraint[0]} on column {constraint[1]}")
        else:
            print("   ℹ️  No foreign key constraints found on order_items table")

        # 4. Remove foreign key constraint on order_items.product_key
        print("\n4️⃣  Removing foreign key constraint on order_items.product_key...")
        try:
            cursor.execute("""
                ALTER TABLE order_items
                DROP CONSTRAINT IF EXISTS order_items_product_key_fkey;
            """)
            conn.commit()
            print("   ✅ order_items_product_key_fkey constraint removed")
        except Exception as e:
            print(f"   ℹ️  Note: {e}")
            conn.rollback()

        # 5. Verify the constraints were removed
        print("\n" + "="*60)
        print("Verifying changes...")
        print("="*60 + "\n")

        # Check orders table
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'orders'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%user_email%';
        """)
        remaining_orders = cursor.fetchall()

        if remaining_orders:
            print("⚠️  Warning: Some user_email constraints still exist on orders:")
            for constraint in remaining_orders:
                print(f"   - {constraint[0]}")
        else:
            print("✅ orders.user_email: No foreign key constraints")

        # Check order_items table
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'order_items'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%product_key%';
        """)
        remaining_items = cursor.fetchall()

        if remaining_items:
            print("⚠️  Warning: Some product_key constraints still exist on order_items:")
            for constraint in remaining_items:
                print(f"   - {constraint[0]}")
        else:
            print("✅ order_items.product_key: No foreign key constraints")

        # 6. Test inserts (dry run)
        print("\n" + "="*60)
        print("Testing inserts (will rollback)...")
        print("="*60 + "\n")

        try:
            # Start a savepoint for testing
            cursor.execute("SAVEPOINT test_inserts")

            # Test 1: Guest email
            test_email = "guest-test@example.com"
            cursor.execute("""
                INSERT INTO orders (order_id, user_email, full_name, total, order_date, status)
                VALUES (%s, %s, %s, %s, NOW(), %s)
            """, ('TEST-ORDER-1', test_email, 'Test Guest', 100.00, 'pending'))
            print(f"✅ Test 1: Guest email insert successful ({test_email})")

            # Test 2: Product key with variation
            test_product_key = "test product - 100 JMD"
            cursor.execute("""
                INSERT INTO order_items (order_id, product_key, quantity, price)
                VALUES (%s, %s, %s, %s)
            """, ('TEST-ORDER-1', test_product_key, 1, 100.00))
            print(f"✅ Test 2: Product key insert successful ({test_product_key})")

            # Rollback the test inserts
            cursor.execute("ROLLBACK TO SAVEPOINT test_inserts")
            print("\n   (Test inserts rolled back - no data was saved)")

        except psycopg2.errors.ForeignKeyViolation as e:
            print(f"❌ Test failed: Foreign key constraint still exists!")
            print(f"   Error: {e}")
            cursor.execute("ROLLBACK TO SAVEPOINT test_inserts")
        except Exception as e:
            print(f"⚠️  Test error (may be normal): {e}")
            cursor.execute("ROLLBACK TO SAVEPOINT test_inserts")

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
    print("PostgreSQL Migration Script - Fix Foreign Keys")
    print("="*60 + "\n")

    success = fix_foreign_keys()

    if success:
        print("\n🎉 Foreign key constraints removed!")
        print("\n💡 What this enables:")
        print("   ✅ Guest checkout with any email")
        print("   ✅ Product variations in cart (color, size, etc.)")
        print("\n💡 Next steps:")
        print("   1. Restart your Flask app")
        print("   2. Test guest checkout")
        print("   3. Test checkout with product variations")
    else:
        print("\n⚠️  Migration failed. Please check the errors above.")

    print()
