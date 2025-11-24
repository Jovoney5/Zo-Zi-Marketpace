#!/usr/bin/env python3
# migrate_to_postgres.py - Migration script from SQLite to PostgreSQL for Zo-Zi Marketplace

import os
import sys
import json
import sqlite3
import psycopg2
import psycopg2.extras
from datetime import datetime
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import our database modules
from database_postgres import get_db as get_postgres_db, init_db as init_postgres_db

def get_sqlite_connection():
    """Get SQLite database connection"""
    sqlite_path = 'zo-zi.db'
    if not os.path.exists(sqlite_path):
        logger.error(f"SQLite database not found at {sqlite_path}")
        return None

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_table_data(table_name, sqlite_conn, postgres_conn, field_mapping=None, transform_fn=None):
    """
    Migrate data from SQLite table to PostgreSQL table

    Args:
        table_name: Name of the table to migrate
        sqlite_conn: SQLite connection
        postgres_conn: PostgreSQL connection
        field_mapping: Dict mapping SQLite field names to PostgreSQL field names
        transform_fn: Function to transform row data before insertion
    """
    try:
        sqlite_cursor = sqlite_conn.cursor()
        postgres_cursor = postgres_conn.cursor()

        # Get all data from SQLite table
        sqlite_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cursor.fetchall()

        if not rows:
            logger.info(f"✅ Table {table_name}: No data to migrate")
            return True

        logger.info(f"🔄 Migrating {len(rows)} rows from {table_name}...")

        migrated_count = 0
        for row in rows:
            try:
                # Convert SQLite row to dict
                row_dict = dict(row)

                # Apply field mapping if provided
                if field_mapping:
                    mapped_row = {}
                    for sqlite_field, postgres_field in field_mapping.items():
                        if sqlite_field in row_dict:
                            mapped_row[postgres_field] = row_dict[sqlite_field]
                    row_dict = mapped_row

                # Apply transformation function if provided
                if transform_fn:
                    row_dict = transform_fn(row_dict)

                # Skip id field as it's auto-generated in PostgreSQL
                if 'id' in row_dict:
                    del row_dict['id']

                # Build INSERT query
                fields = list(row_dict.keys())
                placeholders = ['%s'] * len(fields)
                values = [row_dict[field] for field in fields]

                insert_query = f"""
                    INSERT INTO {table_name} ({', '.join(fields)})
                    VALUES ({', '.join(placeholders)})
                    ON CONFLICT DO NOTHING
                """

                postgres_cursor.execute(insert_query, values)
                migrated_count += 1

            except Exception as e:
                logger.warning(f"Failed to migrate row from {table_name}: {e}")
                continue

        postgres_conn.commit()
        logger.info(f"✅ Table {table_name}: Successfully migrated {migrated_count}/{len(rows)} rows")
        return True

    except Exception as e:
        logger.error(f"❌ Error migrating table {table_name}: {e}")
        return False

def products_transform(row_dict):
    """Transform products data for PostgreSQL compatibility"""
    # Ensure JSON fields are properly formatted
    if 'image_urls' in row_dict and row_dict['image_urls']:
        if isinstance(row_dict['image_urls'], str):
            try:
                # Validate JSON
                json.loads(row_dict['image_urls'])
            except:
                row_dict['image_urls'] = '[]'
    else:
        row_dict['image_urls'] = '[]'

    if 'sizes' in row_dict and row_dict['sizes']:
        if isinstance(row_dict['sizes'], str):
            try:
                # Validate JSON
                json.loads(row_dict['sizes'])
            except:
                row_dict['sizes'] = '{}'
    else:
        row_dict['sizes'] = '{}'

    return row_dict

def payments_transform(row_dict):
    """Transform payment transactions for PostgreSQL compatibility"""
    # Ensure JSON fields are properly formatted
    if 'gateway_response' in row_dict and row_dict['gateway_response']:
        if isinstance(row_dict['gateway_response'], str):
            try:
                # Validate JSON
                json.loads(row_dict['gateway_response'])
            except:
                row_dict['gateway_response'] = '{}'
    else:
        row_dict['gateway_response'] = '{}'

    return row_dict

def withdrawals_transform(row_dict):
    """Transform withdrawal requests for PostgreSQL compatibility"""
    # Ensure JSON fields are properly formatted
    if 'bank_details' in row_dict and row_dict['bank_details']:
        if isinstance(row_dict['bank_details'], str):
            try:
                # Validate JSON
                json.loads(row_dict['bank_details'])
            except:
                row_dict['bank_details'] = '{}'
    else:
        row_dict['bank_details'] = '{}'

    return row_dict

def clear_postgresql_data():
    """Clear all data from PostgreSQL tables"""
    try:
        with get_postgres_db() as postgres_conn:
            cursor = postgres_conn.cursor()

            # Get all table names
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)
            tables = [row[0] for row in cursor.fetchall()]

            # Clear each table
            for table in tables:
                cursor.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")

            postgres_conn.commit()
            logger.info("✅ Cleared all PostgreSQL data")
            return True
    except Exception as e:
        logger.error(f"❌ Error clearing PostgreSQL data: {e}")
        return False

def boolean_transform(row_dict):
    """Transform boolean values for PostgreSQL compatibility"""
    for key, value in row_dict.items():
        if key in ['is_seller', 'is_support', 'discount_used', 'discount_applied', 'is_active', 'payment_verified', 'read_status']:
            if value in [1, '1', 'TRUE', 'True', 'true']:
                row_dict[key] = True
            elif value in [0, '0', 'FALSE', 'False', 'false']:
                row_dict[key] = False
    return row_dict

def main():
    """Main migration function"""
    print("🚀 Starting Zo-Zi Marketplace migration from SQLite to PostgreSQL")
    print("=" * 60)

    # Check if DATABASE_URL is set
    if not os.getenv('DATABASE_URL'):
        print("❌ DATABASE_URL environment variable not set!")
        print("💡 Set it like: export DATABASE_URL='postgresql://user:pass@localhost:5432/zozi_marketplace'")
        return False

    # Get connections
    sqlite_conn = get_sqlite_connection()
    if not sqlite_conn:
        return False

    try:
        with get_postgres_db() as postgres_conn:
            # Initialize PostgreSQL database first
            print("🔧 Initializing PostgreSQL database...")
            if not init_postgres_db():
                logger.error("Failed to initialize PostgreSQL database")
                return False

            # Clear existing data
            print("🧹 Clearing existing PostgreSQL data...")
            if not clear_postgresql_data():
                logger.error("Failed to clear PostgreSQL data")
                return False

            # Define tables to migrate and their configurations
            migration_config = [
                {
                    'table': 'users',
                    'transform_fn': boolean_transform,
                    'field_mapping': None
                },
                {
                    'table': 'admin_users',
                    'transform_fn': boolean_transform,
                    'field_mapping': None
                },
                {
                    'table': 'products',
                    'transform_fn': products_transform,
                    'field_mapping': None
                },
                {
                    'table': 'orders',
                    'transform_fn': boolean_transform,
                    'field_mapping': None
                },
                {
                    'table': 'order_items',
                    'transform_fn': None,
                    'field_mapping': None
                },
                {
                    'table': 'seller_finances',
                    'transform_fn': None,
                    'field_mapping': None
                },
                {
                    'table': 'seller_transactions',
                    'transform_fn': None,
                    'field_mapping': None
                },
                {
                    'table': 'withdrawal_requests',
                    'transform_fn': withdrawals_transform,
                    'field_mapping': None
                },
                {
                    'table': 'user_flags',
                    'transform_fn': None,
                    'field_mapping': None
                },
                {
                    'table': 'admin_activity_log',
                    'transform_fn': None,
                    'field_mapping': None
                },
                {
                    'table': 'seller_verification',
                    'transform_fn': None,
                    'field_mapping': None
                },
                {
                    'table': 'messages',
                    'transform_fn': boolean_transform,
                    'field_mapping': None
                },
                {
                    'table': 'payment_transactions',
                    'transform_fn': payments_transform,
                    'field_mapping': None
                },
                {
                    'table': 'contact_sessions',
                    'transform_fn': None,
                    'field_mapping': None
                }
            ]

            # Check which tables exist in SQLite
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in sqlite_cursor.fetchall()]

            print(f"📋 Found {len(existing_tables)} tables in SQLite database")

            # Migrate each table
            success_count = 0
            total_tables = 0

            for config in migration_config:
                table_name = config['table']

                if table_name not in existing_tables:
                    logger.info(f"⏭️  Table {table_name}: Not found in SQLite, skipping")
                    continue

                total_tables += 1
                success = migrate_table_data(
                    table_name,
                    sqlite_conn,
                    postgres_conn,
                    config.get('field_mapping'),
                    config.get('transform_fn')
                )

                if success:
                    success_count += 1

            print("\n" + "=" * 60)
            print(f"🎉 Migration completed!")
            print(f"✅ Successfully migrated: {success_count}/{total_tables} tables")

            if success_count == total_tables:
                print("\n🔥 All data migrated successfully!")
                print("💡 You can now set DATABASE_URL in your environment to use PostgreSQL")
                print("💡 Example: export DATABASE_URL='postgresql://user:pass@localhost:5432/zozi_marketplace'")
                return True
            else:
                print(f"\n⚠️  {total_tables - success_count} tables had migration issues")
                return False

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)