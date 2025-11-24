#!/usr/bin/env python3
"""
Script to randomize the 'sold' count for existing products (dummy data)
This makes the marketplace look more realistic with varied sales numbers
"""

import os
import random
import psycopg2
from psycopg2 import sql

def randomize_sold_counts():
    """Update existing products with random sold counts"""

    database_url = os.getenv('DATABASE_URL', 'postgresql://jovoneybrown@localhost:5432/zozi_marketplace')

    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("=" * 70)
        print("🎲 Randomizing Sold Counts for Existing Products")
        print("=" * 70)

        # Get all existing products
        cursor.execute("SELECT product_key, name, sold FROM products ORDER BY product_key")
        products = cursor.fetchall()

        print(f"\n📦 Found {len(products)} products to update\n")

        # Realistic sold count ranges
        sold_ranges = [
            (0, 10, 0.15),    # 15% have 0-10 sold (new/unpopular)
            (11, 30, 0.25),   # 25% have 11-30 sold (moderate)
            (31, 60, 0.30),   # 30% have 31-60 sold (popular)
            (61, 100, 0.20),  # 20% have 61-100 sold (very popular)
            (101, 200, 0.10)  # 10% have 101-200 sold (bestsellers)
        ]

        updated_count = 0

        for product_key, name, current_sold in products:
            # Choose a random range based on weighted probabilities
            rand = random.random()
            cumulative = 0

            for min_sold, max_sold, probability in sold_ranges:
                cumulative += probability
                if rand <= cumulative:
                    new_sold = random.randint(min_sold, max_sold)
                    break
            else:
                new_sold = random.randint(0, 50)  # Fallback

            # Update the product
            cursor.execute(
                "UPDATE products SET sold = %s WHERE product_key = %s",
                (new_sold, product_key)
            )

            updated_count += 1
            print(f"✅ {name[:40]:<40} | Old: {current_sold:>3} → New: {new_sold:>3} sold")

        # Commit all changes
        conn.commit()

        print("\n" + "=" * 70)
        print(f"🎉 Successfully updated {updated_count} products!")
        print("=" * 70)

        # Show distribution
        print("\n📊 Distribution of sold counts:")
        cursor.execute("""
            SELECT
                CASE
                    WHEN sold BETWEEN 0 AND 10 THEN '0-10'
                    WHEN sold BETWEEN 11 AND 30 THEN '11-30'
                    WHEN sold BETWEEN 31 AND 60 THEN '31-60'
                    WHEN sold BETWEEN 61 AND 100 THEN '61-100'
                    WHEN sold > 100 THEN '100+'
                END as range,
                COUNT(*) as count
            FROM products
            GROUP BY range
            ORDER BY range
        """)

        for range_label, count in cursor.fetchall():
            if range_label:
                print(f"   {range_label:>10} sold: {count:>3} products")

        cursor.close()
        conn.close()

        print("\n💡 All new products added from now on will start at 0 sold.")
        print("   The sold count will only increment when actual sales happen!\n")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    randomize_sold_counts()
