#!/usr/bin/env python3
"""
Test script to demonstrate the personalized product recommendation system
"""

import os
from database_postgres import (
    track_product_view,
    get_last_viewed_product,
    get_personalized_products,
    get_user_viewing_history
)

def test_personalization():
    """Test the personalization features"""

    print("=" * 70)
    print("🧪 Testing Personalized Product Recommendation System")
    print("=" * 70)

    # Use a test user email (replace with actual user from your database)
    test_user = input("\n📧 Enter a user email to test (or press Enter for 'test@example.com'): ").strip()
    if not test_user:
        test_user = "test@example.com"

    print(f"\n✅ Testing with user: {test_user}")

    # Test 1: Track some product views
    print("\n" + "=" * 70)
    print("Test 1: Tracking Product Views")
    print("=" * 70)

    test_products = [
        ("Women's Dress", "Women Clothing"),
        ("Beach Bikini", "Beachwear"),
        ("Summer Sandals", "Shoes"),
    ]

    for product_key, category in test_products:
        result = track_product_view(test_user, product_key, category)
        if result:
            print(f"✅ Tracked view: {product_key} ({category})")
        else:
            print(f"❌ Failed to track: {product_key}")

    # Test 2: Get last viewed product
    print("\n" + "=" * 70)
    print("Test 2: Get Last Viewed Product")
    print("=" * 70)

    last_viewed = get_last_viewed_product(test_user)
    if last_viewed:
        print(f"✅ Last viewed product:")
        print(f"   📦 Product: {last_viewed['product_key']}")
        print(f"   📁 Category: {last_viewed['category']}")
        print(f"   🕐 Viewed at: {last_viewed['viewed_at']}")
    else:
        print("ℹ️  No viewing history found for this user")

    # Test 3: Get viewing history
    print("\n" + "=" * 70)
    print("Test 3: Get User's Viewing History")
    print("=" * 70)

    history = get_user_viewing_history(test_user, limit=10)
    if history:
        print(f"✅ Found {len(history)} categories in viewing history:")
        for idx, record in enumerate(history, 1):
            print(f"   {idx}. {record['category']}")
    else:
        print("ℹ️  No viewing history found")

    # Test 4: Get personalized products
    print("\n" + "=" * 70)
    print("Test 4: Get Personalized Products")
    print("=" * 70)

    personalized = get_personalized_products(test_user)
    if personalized:
        print(f"✅ Retrieved {len(personalized)} personalized products")
        print("\nFirst 5 products (showing personalization priority):")
        for idx, (key, product) in enumerate(list(personalized.items())[:5], 1):
            print(f"   {idx}. {product['name']} ({product.get('category', 'N/A')})")
            if idx == 1:
                print(f"      ⭐ This is likely from category: {last_viewed['category'] if last_viewed else 'N/A'}")
    else:
        print("❌ No personalized products retrieved")

    print("\n" + "=" * 70)
    print("🎉 Personalization Test Complete!")
    print("=" * 70)
    print("\n💡 Tips:")
    print("   • View different products on your site")
    print("   • Check homepage - you'll see more products from viewed categories")
    print("   • Each login will show different products based on your interests!")
    print("\n")

if __name__ == "__main__":
    try:
        test_personalization()
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        print("\n💡 Make sure:")
        print("   1. PostgreSQL is running")
        print("   2. DATABASE_URL is set in your .env file")
        print("   3. You ran create_user_views_table.py migration")
        print("   4. You have some products in your database")
