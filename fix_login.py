#!/usr/bin/env python3
"""
fix_login.py - Reset admin and support login credentials for PostgreSQL
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

from werkzeug.security import generate_password_hash
from database_postgres import get_db

def fix_logins():
    """Reset admin and support account passwords"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            print("🔧 Fixing login credentials...")
            print("=" * 60)

            # 1. Fix Admin Account
            print("\n1️⃣  Fixing Admin Account...")

            # Check if admin exists
            cursor.execute("SELECT email FROM admin_users WHERE email = %s", ('admin@test.com',))
            admin_exists = cursor.fetchone()

            admin_password_hash = generate_password_hash('admin123')

            if admin_exists:
                # Update existing admin password
                cursor.execute('''
                    UPDATE admin_users
                    SET password = %s
                    WHERE email = %s
                ''', (admin_password_hash, 'admin@test.com'))
                print("   ✓ Updated existing admin password")
            else:
                # Create new admin
                cursor.execute('''
                    INSERT INTO admin_users (email, password)
                    VALUES (%s, %s)
                ''', ('admin@test.com', admin_password_hash))
                print("   ✓ Created new admin account")

            print("   📧 Email: admin@test.com")
            print("   🔑 Password: admin123")

            # 2. Fix Support Agent Account
            print("\n2️⃣  Fixing Support Agent Account...")

            # Check if support exists
            cursor.execute("SELECT email FROM users WHERE email = %s", ('support@yaad.com',))
            support_exists = cursor.fetchone()

            support_password_hash = generate_password_hash('support123')

            if support_exists:
                # Update existing support password
                cursor.execute('''
                    UPDATE users
                    SET password = %s, is_support = %s
                    WHERE email = %s
                ''', (support_password_hash, True, 'support@yaad.com'))
                print("   ✓ Updated existing support password")
            else:
                # Create new support agent
                cursor.execute('''
                    INSERT INTO users (email, password, is_support, first_name, last_name, is_seller, phone_number)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', ('support@yaad.com', support_password_hash, True, 'Support', 'Agent', False, '876-555-0000'))
                print("   ✓ Created new support account")

            print("   📧 Email: support@yaad.com")
            print("   🔑 Password: support123")

            # Commit changes
            conn.commit()

            print("\n" + "=" * 60)
            print("✅ Login credentials fixed successfully!")
            print("\n📝 LOGIN INFORMATION:")
            print("   Admin Dashboard: http://localhost:8080/admin_login")
            print("   └─ admin@test.com / admin123")
            print("\n   Support/Regular Login: http://localhost:8080/login")
            print("   └─ support@yaad.com / support123")
            print("=" * 60)

            return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = fix_logins()
    sys.exit(0 if success else 1)
