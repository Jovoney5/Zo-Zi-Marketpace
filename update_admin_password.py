#!/usr/bin/env python3
"""
Script to update admin password in the database
This will NOT delete any data - only updates the admin password
"""

import sqlite3
from werkzeug.security import generate_password_hash

# Database path
DB_PATH = 'zo-zi.db'

# New admin password
NEW_PASSWORD = 'Admin2024!'

def update_admin_password():
    try:
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if admin exists
        cursor.execute("SELECT email FROM admin_users WHERE email = ?", ('admin@test.com',))
        admin = cursor.fetchone()

        if admin:
            # Update password
            hashed_password = generate_password_hash(NEW_PASSWORD)
            cursor.execute("UPDATE admin_users SET password = ? WHERE email = ?",
                          (hashed_password, 'admin@test.com'))
            conn.commit()
            print("✅ Admin password updated successfully!")
            print(f"📧 Email: admin@test.com")
            print(f"🔑 New Password: {NEW_PASSWORD}")
        else:
            print("❌ Admin user not found in database")

        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("🔄 Updating admin password...")
    update_admin_password()