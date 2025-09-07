import sqlite3


def fix_database():
    conn = sqlite3.connect('zo-zi.db')
    cursor = conn.cursor()

    # Check if column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    print("Current columns:", columns)

    if 'verification_status' not in columns:
        print("Adding verification_status column...")
        cursor.execute('ALTER TABLE users ADD COLUMN verification_status TEXT DEFAULT "pending_documents"')
        print("✅ Column added successfully!")

        # Update existing sellers to have verification status
        cursor.execute('UPDATE users SET verification_status = "pending_documents" WHERE is_seller = 1')
        print("✅ Updated existing sellers with verification status")
    else:
        print("⚠️ Column already exists")

    # Check seller_verifications table structure
    cursor.execute("PRAGMA table_info(seller_verifications)")
    verification_columns = [column[1] for column in cursor.fetchall()]
    print("seller_verifications columns:", verification_columns)

    # If table exists but with wrong structure, drop and recreate
    if verification_columns and 'seller_email' not in verification_columns:
        print("🔄 Recreating seller_verifications table with correct structure...")
        cursor.execute('DROP TABLE IF EXISTS seller_verifications')

    # Create seller_verifications table with correct structure
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seller_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email TEXT NOT NULL,
            verification_status TEXT DEFAULT 'pending_documents',
            id_document_path TEXT,
            id_document_type TEXT,
            trn_number TEXT,
            trn_document_path TEXT,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            reviewed_at DATETIME,
            reviewed_by TEXT,
            rejection_reason TEXT,
            notes TEXT,
            phone_verified BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (seller_email) REFERENCES users(email)
        )
    ''')
    print("✅ seller_verifications table created/verified with correct structure")

    # Verify the column was added
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    print("Updated columns:", columns)

    # Verify seller_verifications structure
    cursor.execute("PRAGMA table_info(seller_verifications)")
    verification_columns = [column[1] for column in cursor.fetchall()]
    print("seller_verifications final structure:", verification_columns)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    fix_database()