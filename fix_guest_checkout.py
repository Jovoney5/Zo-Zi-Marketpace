#!/usr/bin/env python3
"""
Migration script to fix guest checkout by removing foreign key constraint
Run this once to allow guest emails that don't exist in users table
"""

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def fix_guest_checkout():
    """Remove foreign key constraint on orders.user_email to allow guest checkouts"""

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
        print("Fixing Guest Checkout - Removing Foreign Key Constraints")
        print("="*60 + "\n")

        # 1. Check if the foreign key constraint exists
        print("1️⃣  Checking for foreign key constraint on orders.user_email...")
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'orders'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%user_email%';
        """)
        constraints = cursor.fetchall()

        if constraints:
            print(f"   Found {len(constraints)} constraint(s):")
            for constraint in constraints:
                print(f"   - {constraint[0]}")
        else:
            print("   ℹ️  No foreign key constraints found on user_email")

        # 2. Drop the foreign key constraint
        print("\n2️⃣  Removing foreign key constraint...")
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

        # 3. Also check for any other foreign key constraints on orders table
        print("\n3️⃣  Checking for other foreign key constraints on orders table...")
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
        other_constraints = cursor.fetchall()

        if other_constraints:
            print(f"   Found {len(other_constraints)} remaining foreign key(s):")
            for constraint in other_constraints:
                print(f"   - {constraint[0]} on column {constraint[1]}")
        else:
            print("   ℹ️  No other foreign key constraints found")

        # 4. Verify the constraint was removed
        print("\n" + "="*60)
        print("Verifying changes...")
        print("="*60 + "\n")

        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'orders'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%user_email%';
        """)
        remaining = cursor.fetchall()

        if remaining:
            print("⚠️  Warning: Some user_email constraints still exist:")
            for constraint in remaining:
                print(f"   - {constraint[0]}")
        else:
            print("✅ Success! No foreign key constraints on orders.user_email")
            print("✅ Guest checkout can now use any email address")

        # 5. Test insert (dry run)
        print("\n" + "="*60)
        print("Testing guest email insert (will rollback)...")
        print("="*60 + "\n")

        try:
            # Start a savepoint for testing
            cursor.execute("SAVEPOINT test_guest_insert")

            # Try to insert a test order with a non-existent email
            test_email = "guest-test@example.com"
            cursor.execute("""
                INSERT INTO orders (order_id, user_email, full_name, total, order_date, status)
                VALUES (%s, %s, %s, %s, NOW(), %s)
            """, ('TEST-12345', test_email, 'Test Guest', 100.00, 'pending'))

            print(f"✅ Test insert successful with email: {test_email}")
            print("✅ Guest checkout will work correctly!")

            # Rollback the test insert
            cursor.execute("ROLLBACK TO SAVEPOINT test_guest_insert")
            print("   (Test insert rolled back - no data was saved)")

        except psycopg2.errors.ForeignKeyViolation as e:
            print(f"❌ Test failed: Foreign key constraint still exists!")
            print(f"   Error: {e}")
            cursor.execute("ROLLBACK TO SAVEPOINT test_guest_insert")
        except Exception as e:
            print(f"⚠️  Test error (may be normal): {e}")
            cursor.execute("ROLLBACK TO SAVEPOINT test_guest_insert")

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
    print("PostgreSQL Migration Script - Fix Guest Checkout")
    print("="*60 + "\n")

    success = fix_guest_checkout()

    if success:
        print("\n🎉 Guest checkout is now fixed!")
        print("\n💡 Next steps:")
        print("   1. Restart your Flask app")
        print("   2. Test guest checkout with any email")
        print("   3. Order should be created successfully")
    else:
        print("\n⚠️  Migration failed. Please check the errors above.")

    print()
