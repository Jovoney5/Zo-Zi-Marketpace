#!/usr/bin/env python3
"""
Migration script to add payment system tables and columns
For: WiPay + Lynk + COD payment system
"""

import os
import psycopg2

def add_payment_system_tables():
    """Add platform_finances table and update orders table"""

    database_url = os.getenv('DATABASE_URL', 'postgresql://jovoneybrown@localhost:5432/zozi_marketplace')

    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("=" * 70)
        print("💰 Adding Payment System Tables")
        print("=" * 70)

        # Step 1: Create platform_finances table
        print("\n📊 Step 1: Creating platform_finances table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS platform_finances (
                id SERIAL PRIMARY KEY,
                date DATE DEFAULT CURRENT_DATE,
                order_id VARCHAR(100),
                revenue_from_fees DECIMAL(10,2) DEFAULT 0,  -- 5% platform fee
                gateway_fees_paid DECIMAL(10,2) DEFAULT 0,  -- WiPay/Lynk fees
                net_revenue DECIMAL(10,2) DEFAULT 0,         -- revenue - gateway fees
                payment_method VARCHAR(20),                  -- 'wipay', 'lynk', 'cod'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE SET NULL
            );
        """)
        print("✅ platform_finances table created")

        # Step 2: Update orders table with new columns
        print("\n📊 Step 2: Adding new columns to orders table...")

        columns_to_add = [
            ("subtotal", "DECIMAL(10,2) DEFAULT 0"),
            ("platform_fee", "DECIMAL(10,2) DEFAULT 0"),
            ("payment_gateway_fee", "DECIMAL(10,2) DEFAULT 0"),
            ("payment_method", "VARCHAR(20) DEFAULT 'cod'"),
            ("total_before_gateway_fee", "DECIMAL(10,2) DEFAULT 0"),
        ]

        for column_name, column_type in columns_to_add:
            try:
                cursor.execute(f"""
                    ALTER TABLE orders
                    ADD COLUMN IF NOT EXISTS {column_name} {column_type}
                """)
                print(f"✅ Added column: {column_name}")
            except Exception as e:
                print(f"⚠️  Column {column_name} might already exist: {e}")

        # Step 3: Create index for faster queries
        print("\n📊 Step 3: Creating indexes...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_platform_finances_date
            ON platform_finances(date DESC);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_platform_finances_order
            ON platform_finances(order_id);
        """)
        print("✅ Indexes created")

        # Step 4: Update seller_transactions table if needed
        print("\n📊 Step 4: Ensuring seller_transactions table is ready...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seller_transactions (
                id SERIAL PRIMARY KEY,
                seller_email VARCHAR(255) NOT NULL,
                transaction_type VARCHAR(50),  -- 'sale', 'payout', 'refund'
                amount DECIMAL(10,2),
                order_id VARCHAR(100),
                description TEXT,
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'completed',  -- 'pending', 'completed', 'failed'
                FOREIGN KEY (seller_email) REFERENCES users(email) ON DELETE CASCADE
            );
        """)
        print("✅ seller_transactions table ready")

        # Commit all changes
        conn.commit()

        print("\n" + "=" * 70)
        print("🎉 Payment System Tables Added Successfully!")
        print("=" * 70)

        # Verify tables
        print("\n📋 Verifying tables...")
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('platform_finances', 'seller_transactions', 'orders')
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()
        print("\n✅ Tables verified:")
        for table in tables:
            print(f"   • {table[0]}")

        # Show new columns in orders table
        print("\n📋 New columns in orders table:")
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'orders'
            AND column_name IN ('subtotal', 'platform_fee', 'payment_gateway_fee',
                               'payment_method', 'total_before_gateway_fee')
            ORDER BY ordinal_position;
        """)

        columns = cursor.fetchall()
        for col in columns:
            print(f"   • {col[0]}: {col[1]}")

        cursor.close()
        conn.close()

        print("\n💡 Database is ready for payment system!")
        print("   Next steps:")
        print("   1. Update checkout.html")
        print("   2. Update checkout route in app.py")
        print("   3. Add payment integrations\n")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    add_payment_system_tables()
