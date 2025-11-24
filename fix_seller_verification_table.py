#!/usr/bin/env python3
"""
Migration script to add missing columns to seller_verification table
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def fix_seller_verification_table():
    """Add missing columns to seller_verification table"""

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
        print("Adding Missing Columns to seller_verification Table")
        print("="*60 + "\n")

        # 1. Add id_document_type column
        print("1️⃣  Adding 'id_document_type' column...")
        try:
            cursor.execute("""
                ALTER TABLE seller_verification
                ADD COLUMN IF NOT EXISTS id_document_type VARCHAR(50);
            """)
            conn.commit()
            print("   ✅ id_document_type column added")
        except Exception as e:
            print(f"   ℹ️  Note: {e}")
            conn.rollback()

        # 2. Add trn_number column
        print("\n2️⃣  Adding 'trn_number' column...")
        try:
            cursor.execute("""
                ALTER TABLE seller_verification
                ADD COLUMN IF NOT EXISTS trn_number VARCHAR(9);
            """)
            conn.commit()
            print("   ✅ trn_number column added")
        except Exception as e:
            print(f"   ℹ️  Note: {e}")
            conn.rollback()

        # 3. Add trn_document_path column
        print("\n3️⃣  Adding 'trn_document_path' column...")
        try:
            cursor.execute("""
                ALTER TABLE seller_verification
                ADD COLUMN IF NOT EXISTS trn_document_path VARCHAR(255);
            """)
            conn.commit()
            print("   ✅ trn_document_path column added")
        except Exception as e:
            print(f"   ℹ️  Note: {e}")
            conn.rollback()

        # 4. Add notes column
        print("\n4️⃣  Adding 'notes' column...")
        try:
            cursor.execute("""
                ALTER TABLE seller_verification
                ADD COLUMN IF NOT EXISTS notes TEXT;
            """)
            conn.commit()
            print("   ✅ notes column added")
        except Exception as e:
            print(f"   ℹ️  Note: {e}")
            conn.rollback()

        # 5. Verify all columns exist
        print("\n" + "="*60)
        print("Verifying columns...")
        print("="*60 + "\n")

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'seller_verification'
            AND column_name IN ('id_document_type', 'trn_number', 'trn_document_path', 'notes')
            ORDER BY column_name;
        """)
        columns = cursor.fetchall()

        if len(columns) == 4:
            print("✅ All required columns verified:")
            for col in columns:
                print(f"   - {col[0]}: {col[1]}")
        else:
            print(f"⚠️  Warning: Expected 4 columns, found {len(columns)}")
            for col in columns:
                print(f"   - {col[0]}: {col[1]}")

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
    print("PostgreSQL Migration - Fix seller_verification Table")
    print("="*60 + "\n")

    success = fix_seller_verification_table()

    if success:
        print("\n🎉 seller_verification table fixed!")
        print("\n💡 Next steps:")
        print("   1. Restart your Flask app")
        print("   2. Test seller verification flow")
        print("   3. Upload documents should now work")
    else:
        print("\n⚠️  Migration failed. Please check the errors above.")

    print()
