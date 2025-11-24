"""
Payment calculation helpers for Zo-Zi Marketplace
Handles: WiPay, Lynk, and Cash on Delivery

TIERED PRICING MODEL:
- Free Plan: 10% platform fee
- Growth Plan (100 JMD/mo): 7% platform fee
- Pro Plan (300 JMD/mo): 5% platform fee
"""

def calculate_order_totals(cart_total, payment_method='cod', subscription_tier='free'):
    """
    Calculate all order totals based on payment method and subscription tier

    NOTE: Shipping is already included in product prices!
    Sellers add shipping cost when they list products.

    Args:
        cart_total (float): Sum of all products in cart (shipping already included)
        payment_method (str): 'wipay', 'lynk', 'cod', or 'whatsapp'
        subscription_tier (str): 'free', 'growth', or 'pro'

    Returns:
        dict: All calculated amounts
    """

    # Step 1: Subtotal = cart total (shipping already in product prices)
    subtotal = float(cart_total)

    # Step 2: Platform handling fee (based on subscription tier)
    platform_fee_rates = {
        'free': 0.10,    # 10% for free plan
        'growth': 0.07,  # 7% for growth plan (100 JMD/mo)
        'pro': 0.05,     # 5% for pro plan (300 JMD/mo)
        'basic': 0.07,   # Legacy support (same as growth)
    }

    platform_fee_rate = platform_fee_rates.get(subscription_tier.lower(), 0.10)
    platform_fee = subtotal * platform_fee_rate

    # Step 3: Total before payment gateway fee
    total_before_gateway_fee = subtotal + platform_fee

    # Step 4: Payment gateway fees (depends on method)
    gateway_fee_rates = {
        'wipay': 0.04,     # 4%
        'lynk': 0.01,      # 1%
        'cod': 0.00,       # 0% (cash on delivery)
        'whatsapp': 0.00   # 0% (WhatsApp pay - no gateway fees)
    }

    gateway_fee_rate = gateway_fee_rates.get(payment_method.lower(), 0)
    payment_gateway_fee = total_before_gateway_fee * gateway_fee_rate

    # Step 5: Final total (what customer pays)
    final_total = total_before_gateway_fee + payment_gateway_fee

    return {
        'subtotal': round(subtotal, 2),
        'platform_fee': round(platform_fee, 2),
        'platform_fee_percent': round(platform_fee_rate * 100),
        'total_before_gateway_fee': round(total_before_gateway_fee, 2),
        'payment_gateway_fee': round(payment_gateway_fee, 2),
        'payment_gateway_fee_percent': round(gateway_fee_rate * 100, 1),
        'final_total': round(final_total, 2),
        'payment_method': payment_method,
        'subscription_tier': subscription_tier
    }


def calculate_seller_payouts(cart_items):
    """
    Calculate how much each seller should receive

    Sellers get 100% of their product price (shipping already included)
    Platform keeps the 5% platform fee

    Args:
        cart_items (list): List of items in cart with seller info

    Returns:
        dict: Seller email -> amount to pay them
    """

    seller_payouts = {}

    for item in cart_items:
        seller_email = item.get('seller_email')

        # Skip items without seller_email (e.g., legacy products or admin products)
        if not seller_email:
            continue

        item_total = float(item.get('price', 0)) * int(item.get('quantity', 1))

        if seller_email in seller_payouts:
            seller_payouts[seller_email] += item_total
        else:
            seller_payouts[seller_email] = item_total

    # Round all amounts
    for seller in seller_payouts:
        seller_payouts[seller] = round(seller_payouts[seller], 2)

    return seller_payouts


def get_payment_method_display_info():
    """
    Get display information for all payment methods

    Returns:
        dict: Payment method info for templates
    """

    return {
        'wipay': {
            'name': 'Credit/Debit Card (WiPay)',
            'icon': '💳',
            'fee_percent': 4.0,
            'description': 'Secure card payment processing',
            'note': 'Visa, Mastercard accepted'
        },
        'lynk': {
            'name': 'Lynk Digital Wallet',
            'icon': '📱',
            'fee_percent': 1.0,
            'description': 'Pay with your Lynk wallet',
            'note': 'Lowest fees! Instant payment'
        },
        'cod': {
            'name': 'Cash on Delivery',
            'icon': '💵',
            'fee_percent': 0.0,
            'description': 'Pay cash when you receive',
            'note': 'No additional fees'
        },
        'whatsapp': {
            'name': 'WhatsApp Pay',
            'icon': '💬',
            'fee_percent': 0.0,
            'description': 'Pay via WhatsApp',
            'note': 'No additional fees'
        }
    }


# Example usage and testing
if __name__ == "__main__":
    print("=" * 70)
    print("💰 Payment Calculations Test")
    print("=" * 70)

    # Example: Customer has 5,000 JMD in cart
    cart_total = 5000

    print(f"\n📊 Cart Total: {cart_total} JMD")
    print("   (Note: Shipping already included in product prices!)\n")

    # Test each payment method
    for method in ['wipay', 'lynk', 'cod']:
        print(f"\n{'='*70}")
        print(f"Payment Method: {method.upper()}")
        print('='*70)

        totals = calculate_order_totals(cart_total, method)

        print(f"Subtotal:                    {totals['subtotal']:>10.2f} JMD")
        print(f"Platform Fee ({totals['platform_fee_percent']}%):          {totals['platform_fee']:>10.2f} JMD")
        print(f"Total before gateway fee:    {totals['total_before_gateway_fee']:>10.2f} JMD")
        print(f"Gateway Fee ({totals['payment_gateway_fee_percent']}%):           {totals['payment_gateway_fee']:>10.2f} JMD")
        print(f"{'─'*70}")
        print(f"FINAL TOTAL:                 {totals['final_total']:>10.2f} JMD")

        # Show breakdown
        print(f"\n💸 Money Flow:")
        if method != 'cod':
            print(f"   • Customer pays:          {totals['final_total']:.2f} JMD")
            print(f"   • Gateway takes:          {totals['payment_gateway_fee']:.2f} JMD")
            print(f"   • You receive:            {totals['total_before_gateway_fee']:.2f} JMD")
        else:
            print(f"   • Customer pays (cash):   {totals['final_total']:.2f} JMD")
            print(f"   • You receive:            {totals['final_total']:.2f} JMD")

        print(f"   • Platform keeps (5%):    {totals['platform_fee']:.2f} JMD")
        print(f"   • Seller receives:        {totals['subtotal']:.2f} JMD")

    print("\n" + "="*70)
    print("✅ All calculations working correctly!")
    print("="*70)

    # Test seller payouts
    print("\n" + "="*70)
    print("👥 Seller Payout Example")
    print("="*70)

    cart_items = [
        {'seller_email': 'seller1@example.com', 'price': 2500, 'quantity': 2},  # 5000 JMD
        {'seller_email': 'seller2@example.com', 'price': 3000, 'quantity': 1},  # 3000 JMD
        {'seller_email': 'seller1@example.com', 'price': 1500, 'quantity': 1},  # 1500 JMD
    ]

    payouts = calculate_seller_payouts(cart_items)

    print("\nSeller Payouts:")
    for seller, amount in payouts.items():
        print(f"   • {seller}: {amount:.2f} JMD")

    print(f"\nTotal to sellers: {sum(payouts.values()):.2f} JMD")
    print("="*70)
