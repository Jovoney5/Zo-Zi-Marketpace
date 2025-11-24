#!/usr/bin/env python3
"""
Script to check what's in the admin_users table
"""

import sqlite3
from werkzeug.security import check_password_hash

# Database path
DB_PATH = 'zo-zi.db'

def check_admin():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get all admin users
        cursor.execute("SELECT email, password, admin_level, is_active FROM admin_users")
        admins = cursor.fetchall()

        if admins:
            print("📋 Admin users in database:")
            print("-" * 60)
            for admin in admins:
                print(f"Email: {admin['email']}")
                print(f"Admin Level: {admin['admin_level']}")
                print(f"Is Active: {admin['is_active']}")
                print(f"Password Hash: {admin['password'][:50]}...")

                # Test password
                test_passwords = ['adminpassword', '!', 'admin', 'password']
                for pwd in test_passwords:
                    try:
                        if check_password_hash(admin['password'], pwd):
                            print(f"✅ PASSWORD FOUND: '{pwd}'")
                            break
                    except:
                        pass

                print("-" * 60)
        else:
            print("❌ No admin users found in database")

        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_admin()
