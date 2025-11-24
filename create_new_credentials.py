#!/usr/bin/env python3
"""
Script to create new admin and support user credentials
"""

import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# New credentials
NEW_ADMIN_EMAIL = 'admin@zozi.com'
NEW_ADMIN_PASSWORD = 'ZoziAdmin2025!'

NEW_SUPPORT_EMAIL = 'support@zozi.com'
NEW_SUPPORT_PASSWORD = 'ZoziSupport2025!'

def create_new_credentials():
    """Create or update admin and support user credentials"""

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in .env file")
        return False

    try:
        print("🔗 Connecting to PostgreSQL database...")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        print("✅ Connected successfully!")
        print("\n" + "="*60)
        print("Creating New Admin and Support Accounts")
        print("="*60 + "\n")

        # 1. Update existing admin users or create new
        print("1️⃣  Setting up admin account...")
        cursor.execute("SELECT email FROM admin_users WHERE email = %s", (NEW_ADMIN_EMAIL,))
        existing_admin = cursor.fetchone()

        if existing_admin:
            # Update existing admin
            admin_hash = generate_password_hash(NEW_ADMIN_PASSWORD)
            cursor.execute("""
                UPDATE admin_users
                SET password = %s, admin_level = %s, permissions = %s, is_active = %s, last_login = NOW()
                WHERE email = %s
            """, (
                admin_hash,
                'super_admin',
                '{"users":true,"products":true,"orders":true,"analytics":true,"financials":true,"admin_management":true}',
                True,
                NEW_ADMIN_EMAIL
            ))
            print(f"   ✅ Updated existing admin: {NEW_ADMIN_EMAIL}")
        else:
            # Create new admin (will be done in step 2)
            print(f"   ℹ️  Will create new admin account")

        # 2. Create new admin user (if doesn't exist)
        print("\n2️⃣  Creating new super admin account...")

        if not existing_admin:
            admin_hash = generate_password_hash(NEW_ADMIN_PASSWORD)
            cursor.execute("""
                INSERT INTO admin_users (
                    email, password, admin_level, permissions, is_active,
                    created_at, last_login
                )
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            """, (
                NEW_ADMIN_EMAIL,
                admin_hash,
                'super_admin',
                '{"users":true,"products":true,"orders":true,"analytics":true,"financials":true,"admin_management":true}',
                True
            ))
            print(f"   ✅ Super admin created: {NEW_ADMIN_EMAIL}")
        else:
            print(f"   ✅ Admin password updated for: {NEW_ADMIN_EMAIL}")

        conn.commit()

        # 3. Update existing support users or create new
        print("\n3️⃣  Setting up support account...")
        cursor.execute("SELECT email FROM users WHERE email = %s", (NEW_SUPPORT_EMAIL,))
        existing_support = cursor.fetchone()

        if existing_support:
            # Update existing support
            support_hash = generate_password_hash(NEW_SUPPORT_PASSWORD)
            cursor.execute("""
                UPDATE users
                SET password = %s, first_name = %s, last_name = %s, is_support = %s, is_seller = %s
                WHERE email = %s
            """, (support_hash, 'Support', 'Team', True, False, NEW_SUPPORT_EMAIL))
            print(f"   ✅ Updated existing support: {NEW_SUPPORT_EMAIL}")
        else:
            print(f"   ℹ️  Will create new support account")

        # 4. Create new support user (if doesn't exist)
        print("\n4️⃣  Creating new support account...")

        if not existing_support:
            support_hash = generate_password_hash(NEW_SUPPORT_PASSWORD)
            cursor.execute("""
                INSERT INTO users (
                    email, password, first_name, last_name, is_support,
                    is_seller, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (
                NEW_SUPPORT_EMAIL,
                support_hash,
                'Support',
                'Team',
                True,
                False
            ))
            print(f"   ✅ Support account created: {NEW_SUPPORT_EMAIL}")
        else:
            print(f"   ✅ Support password updated for: {NEW_SUPPORT_EMAIL}")

        conn.commit()

        # 5. Verify accounts were created
        print("\n" + "="*60)
        print("Verifying new accounts...")
        print("="*60 + "\n")

        # Check admin
        cursor.execute("SELECT email, admin_level, is_active FROM admin_users WHERE email = %s",
                      (NEW_ADMIN_EMAIL,))
        admin = cursor.fetchone()

        if admin:
            print("✅ ADMIN ACCOUNT VERIFIED:")
            print(f"   Email: {admin['email']}")
            print(f"   Level: {admin['admin_level']}")
            print(f"   Active: {admin['is_active']}")
        else:
            print("❌ Admin account not found!")

        # Check support
        cursor.execute("SELECT email, first_name, last_name, is_support FROM users WHERE email = %s",
                      (NEW_SUPPORT_EMAIL,))
        support = cursor.fetchone()

        if support:
            print("\n✅ SUPPORT ACCOUNT VERIFIED:")
            print(f"   Email: {support['email']}")
            print(f"   Name: {support['first_name']} {support['last_name']}")
            print(f"   Support: {support['is_support']}")
        else:
            print("❌ Support account not found!")

        cursor.close()
        conn.close()

        print("\n" + "="*60)
        print("✅ New credentials created successfully!")
        print("="*60)

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
    print("PostgreSQL - Create New Admin & Support Credentials")
    print("="*60 + "\n")

    success = create_new_credentials()

    if success:
        print("\n🎉 New credentials are ready to use!")
        print("\n" + "="*60)
        print("📝 NEW LOGIN CREDENTIALS")
        print("="*60)
        print("\n🔐 ADMIN LOGIN:")
        print(f"   URL: http://localhost:8080/admin_login")
        print(f"   Email: {NEW_ADMIN_EMAIL}")
        print(f"   Password: {NEW_ADMIN_PASSWORD}")
        print("\n🔐 SUPPORT LOGIN:")
        print(f"   URL: http://localhost:8080/login")
        print(f"   Email: {NEW_SUPPORT_EMAIL}")
        print(f"   Password: {NEW_SUPPORT_PASSWORD}")
        print("\n" + "="*60)
        print("\n⚠️  SAVE THESE CREDENTIALS SECURELY!")
        print("💡 Change passwords after first login")
    else:
        print("\n⚠️  Failed to create credentials. Check errors above.")

    print()
