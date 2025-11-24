#!/usr/bin/env python3
"""
Script to add product ratings to the database
- Adds a rating column (0.0 to 5.0)
- Randomizes ratings for existing products (mostly high 4-5 stars)
"""

import os
import random
import psycopg2

def add_and_randomize_ratings():
    """Add rating column and set varied ratings for existing products"""

    database_url = os.getenv('DATABASE_URL', 'postgresql://jovoneybrown@localhost:5432/zozi_marketplace')

    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("=" * 70)
        print("⭐ Adding Product Rating System")
        print("=" * 70)

        # Step 1: Add rating column
        print("\n📊 Step 1: Adding rating column to products table...")
        try:
            cursor.execute("""
                ALTER TABLE products
                ADD COLUMN IF NOT EXISTS rating DECIMAL(2,1) DEFAULT 5.0
            """)
            conn.commit()
            print("✅ Rating column added successfully")
        except Exception as e:
            print(f"⚠️  Column might already exist: {e}")
            conn.rollback()

        # Step 2: Randomize ratings for existing products
        print("\n📊 Step 2: Randomizing ratings for existing products...")

        cursor.execute("SELECT product_key, name FROM products ORDER BY product_key")
        products = cursor.fetchall()

        print(f"📦 Found {len(products)} products to update\n")

        # Rating distribution (weighted towards high ratings)
        # 60% will get 4.5-5.0 stars (excellent)
        # 25% will get 4.0-4.4 stars (very good)
        # 12% will get 3.5-3.9 stars (good)
        # 3% will get 3.0-3.4 stars (decent)

        rating_ranges = [
            (4.5, 5.0, 0.60),   # 60% excellent (4.5-5.0 stars)
            (4.0, 4.4, 0.25),   # 25% very good (4.0-4.4 stars)
            (3.5, 3.9, 0.12),   # 12% good (3.5-3.9 stars)
            (3.0, 3.4, 0.03)    # 3% decent (3.0-3.4 stars)
        ]

        updated_count = 0
        rating_distribution = {
            '5.0': 0,
            '4.5-4.9': 0,
            '4.0-4.4': 0,
            '3.5-3.9': 0,
            '3.0-3.4': 0
        }

        for product_key, name in products:
            # Choose rating range based on weighted probability
            rand = random.random()
            cumulative = 0

            for min_rating, max_rating, probability in rating_ranges:
                cumulative += probability
                if rand <= cumulative:
                    # Generate rating with 0.1 precision (e.g., 4.7, 4.3, 3.8)
                    rating = round(random.uniform(min_rating, max_rating), 1)
                    # Ensure it doesn't exceed 5.0
                    rating = min(rating, 5.0)
                    break
            else:
                rating = 4.5  # Fallback to high rating

            # Update the product
            cursor.execute(
                "UPDATE products SET rating = %s WHERE product_key = %s",
                (rating, product_key)
            )

            # Track distribution
            if rating == 5.0:
                rating_distribution['5.0'] += 1
            elif rating >= 4.5:
                rating_distribution['4.5-4.9'] += 1
            elif rating >= 4.0:
                rating_distribution['4.0-4.4'] += 1
            elif rating >= 3.5:
                rating_distribution['3.5-3.9'] += 1
            else:
                rating_distribution['3.0-3.4'] += 1

            updated_count += 1

            # Generate star display
            full_stars = int(rating)
            half_star = 1 if (rating - full_stars) >= 0.5 else 0
            empty_stars = 5 - full_stars - half_star

            star_display = '★' * full_stars + ('⯨' if half_star else '') + '☆' * empty_stars

            print(f"✅ {name[:35]:<35} | Rating: {rating} {star_display}")

        # Commit all changes
        conn.commit()

        print("\n" + "=" * 70)
        print(f"🎉 Successfully updated {updated_count} products!")
        print("=" * 70)

        # Show distribution
        print("\n📊 Rating Distribution:")
        print(f"   ★★★★★ (5.0 stars)     : {rating_distribution['5.0']:>3} products ({rating_distribution['5.0']/len(products)*100:.1f}%)")
        print(f"   ★★★★⯨ (4.5-4.9 stars) : {rating_distribution['4.5-4.9']:>3} products ({rating_distribution['4.5-4.9']/len(products)*100:.1f}%)")
        print(f"   ★★★★☆ (4.0-4.4 stars) : {rating_distribution['4.0-4.4']:>3} products ({rating_distribution['4.0-4.4']/len(products)*100:.1f}%)")
        print(f"   ★★★⯨☆ (3.5-3.9 stars) : {rating_distribution['3.5-3.9']:>3} products ({rating_distribution['3.5-3.9']/len(products)*100:.1f}%)")
        print(f"   ★★★☆☆ (3.0-3.4 stars) : {rating_distribution['3.0-3.4']:>3} products ({rating_distribution['3.0-3.4']/len(products)*100:.1f}%)")

        cursor.close()
        conn.close()

        print("\n💡 All new products will default to 5.0 stars and adjust with reviews.")
        print("   The rating system is now live!\n")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    add_and_randomize_ratings()
