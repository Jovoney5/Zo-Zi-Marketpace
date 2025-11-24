#!/usr/bin/env python3
"""
Migration script to create user_product_views table for tracking browsing history
Run this once to add the table to your PostgreSQL database
"""

import os
import psycopg2
from psycopg2 import sql

def create_user_views_table():
    """Create the user_product_views table in PostgreSQL"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        print("💡 Make sure you have set DATABASE_URL in your .env file")
        return False

    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("✅ Connected to PostgreSQL database")

        # Create the user_product_views table
        create_table_query = """
        CREATE TABLE IF NOT EXISTS user_product_views (
            id SERIAL PRIMARY KEY,
            user_email VARCHAR(255) NOT NULL,
            product_key TEXT NOT NULL,
            category VARCHAR(100),
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_email) REFERENCES users(email) ON DELETE CASCADE
        );
        """

        cursor.execute(create_table_query)
        print("✅ Created user_product_views table")

        # Create index for faster queries
        create_index_query = """
        CREATE INDEX IF NOT EXISTS idx_user_views_email_date
        ON user_product_views(user_email, viewed_at DESC);
        """

        cursor.execute(create_index_query)
        print("✅ Created index on user_email and viewed_at")

        # Create index for category queries
        create_category_index = """
        CREATE INDEX IF NOT EXISTS idx_user_views_category
        ON user_product_views(category);
        """

        cursor.execute(create_category_index)
        print("✅ Created index on category")

        # Commit changes
        conn.commit()
        print("✅ All changes committed successfully")

        # Verify table was created
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'user_product_views'
            ORDER BY ordinal_position;
        """)

        columns = cursor.fetchall()
        print("\n📋 Table structure:")
        for col in columns:
            print(f"   • {col[0]}: {col[1]}")

        cursor.close()
        conn.close()

        print("\n🎉 Migration completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Error creating table: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Creating user_product_views table for browsing history...")
    print("=" * 60)
    create_user_views_table()
