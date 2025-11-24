# 💰 Complete Money Flow System - Zo-Zi Marketplace

## 🎯 YOUR REQUIREMENTS

1. ✅ Payment methods: **WiPay + Lynk + Cash on Delivery**
2. ✅ **Remove shipping fee** from checkout (already in product price)
3. ✅ Show **5% platform handling fee** clearly
4. ✅ Show **payment gateway fee** (WiPay/Lynk)
5. ✅ Money goes to correct people:
   - Seller gets their portion
   - You (Zo-Zi) get platform fee
   - Gateway gets their fee

---

## 💸 MONEY FLOW BREAKDOWN

### **Example: Customer buys 5,000 JMD product**

#### **BEFORE (What You Have Now):**
```
Product base price:     2,500 JMD (set by seller)
Shipping cost:         +  400 JMD (added by seller when listing)
──────────────────────────────────
Product display price:  2,900 JMD (what customer sees)
```

#### **AT CHECKOUT (What Customer Sees):**
```
Cart Summary:
├─ Product A                     2,900 JMD
├─ Product B                     3,100 JMD
│
├─ Subtotal:                     6,000 JMD
├─ Platform Handling Fee (5%):  +  300 JMD
│
├─ TOTAL:                        6,300 JMD
│
└─ Payment Method:
   □ WiPay (Card) - 4% fee = +252 JMD → Final: 6,552 JMD
   □ Lynk - 1% fee = +63 JMD → Final: 6,363 JMD
   □ Cash on Delivery - No fee → Final: 6,300 JMD
```

#### **AFTER PAYMENT (Where Money Goes):**

**Scenario 1: Customer pays with WiPay (6,552 JMD total)**
```
Customer pays:          6,552 JMD
│
├─ WiPay Fee (4%):     -  252 JMD → Goes to WiPay
├─ Net received:        6,300 JMD → Goes to YOUR business account
│
│   From this 6,300 JMD:
│   ├─ Platform Fee (5% of subtotal):  -300 JMD → YOU keep
│   ├─ Seller A portion:               2,900 JMD → Pay to Seller A
│   └─ Seller B portion:               3,100 JMD → Pay to Seller B
│
└─ FINAL SPLIT:
    • WiPay:     252 JMD (4%)
    • Zo-Zi:     300 JMD (5% of subtotal)
    • Seller A: 2,900 JMD (includes shipping they set)
    • Seller B: 3,100 JMD (includes shipping they set)
```

**Scenario 2: Customer pays with Lynk (6,363 JMD total)**
```
Customer pays:          6,363 JMD
│
├─ Lynk Fee (1%):      -   63 JMD → Goes to Lynk
├─ Net received:        6,300 JMD → Goes to YOUR business account
│
│   From this 6,300 JMD:
│   ├─ Platform Fee (5%):     -300 JMD → YOU keep
│   ├─ Seller A:             2,900 JMD → Pay to Seller A
│   └─ Seller B:             3,100 JMD → Pay to Seller B
│
└─ FINAL SPLIT:
    • Lynk:      63 JMD (1%)
    • Zo-Zi:    300 JMD (5% of subtotal)
    • Seller A: 2,900 JMD
    • Seller B: 3,100 JMD
```

**Scenario 3: Customer pays Cash on Delivery (6,300 JMD)**
```
Customer pays driver:   6,300 JMD cash
│
├─ Driver brings to you: 6,300 JMD → Your business account
│
│   From this 6,300 JMD:
│   ├─ Platform Fee (5%):     -300 JMD → YOU keep
│   ├─ Seller A:             2,900 JMD → Pay to Seller A
│   └─ Seller B:             3,100 JMD → Pay to Seller B
│
└─ FINAL SPLIT:
    • Zo-Zi:    300 JMD (5%)
    • Seller A: 2,900 JMD
    • Seller B: 3,100 JMD
```

---

## 📊 DATABASE TRACKING

### **When Order is Created:**

```python
# Order Table
order_id: "ORD-2025-001"
user_email: "buyer@example.com"
subtotal: 6000  # Sum of all products (including their shipping)
platform_fee: 300  # 5% of subtotal
payment_gateway_fee: 252  # 4% for WiPay (or 63 for Lynk, or 0 for COD)
total: 6552  # subtotal + platform_fee + gateway_fee
payment_method: "wipay"  # or "lynk" or "cash_on_delivery"
status: "pending"

# Order Items Table
Item 1:
  - order_id: "ORD-2025-001"
  - product_key: "Product A - 2900 JMD"
  - seller_email: "seller1@example.com"
  - price: 2900
  - quantity: 1
  - seller_payout: 2900  # Full product price goes to seller

Item 2:
  - order_id: "ORD-2025-001"
  - product_key: "Product B - 3100 JMD"
  - seller_email: "seller2@example.com"
  - price: 3100
  - quantity: 1
  - seller_payout: 3100

# Seller Finances Table
Seller A:
  - seller_email: "seller1@example.com"
  - pending_balance: +2900  # Add to their pending payout
  - total_sales: +2900

Seller B:
  - seller_email: "seller2@example.com"
  - pending_balance: +3100
  - total_sales: +3100

# Platform Finances (Your account)
Zo-Zi Platform:
  - total_platform_fees: +300  # Your revenue
  - total_gateway_fees_paid: +252  # Cost you paid to WiPay
```

---

## 🔄 COMPLETE WORKFLOW

### **1. CUSTOMER CHECKOUT PROCESS**

```
Customer adds products to cart
    ↓
Views cart summary:
  - Product A: 2,900 JMD (shipping included)
  - Product B: 3,100 JMD (shipping included)
  - Subtotal: 6,000 JMD
  - Platform Fee (5%): 300 JMD
  - Total before payment: 6,300 JMD
    ↓
Chooses payment method:
  □ WiPay → Add 4% fee → 6,552 JMD
  □ Lynk → Add 1% fee → 6,363 JMD
  □ Cash on Delivery → 6,300 JMD
    ↓
Completes payment
    ↓
Order confirmed ✅
```

### **2. PAYMENT PROCESSING**

**If WiPay/Lynk:**
```
Payment gateway receives: 6,552 JMD (or 6,363)
    ↓
Gateway takes their fee (4% or 1%)
    ↓
Net amount deposited to YOUR NCB account: 6,300 JMD
    ↓
Database updated:
  - Order status: "paid"
  - Seller A pending_balance: +2,900
  - Seller B pending_balance: +3,100
  - Platform revenue: +300
```

**If Cash on Delivery:**
```
Order status: "pending_delivery"
    ↓
Driver delivers to customer
    ↓
Customer pays cash: 6,300 JMD
    ↓
Driver returns to you with: 6,300 JMD
    ↓
You deposit to YOUR NCB account
    ↓
Update order status: "delivered"
    ↓
Database updated (same as above)
```

### **3. SELLER PAYOUT PROCESS**

**Weekly/Bi-weekly:**
```
Generate payout report:
  - Seller A has: 15,000 JMD pending (5 sales)
  - Seller B has: 23,000 JMD pending (7 sales)
    ↓
You transfer from YOUR NCB account:
  - To Seller A's account: 15,000 JMD
  - To Seller B's account: 23,000 JMD
    ↓
Update database:
  - Move from pending_balance to paid_balance
  - Create transaction records
  - Mark as "paid" in seller_transactions
```

---

## 💻 CHECKOUT PAGE CHANGES NEEDED

### **CURRENT CHECKOUT (What to Remove):**
```html
<!-- REMOVE THIS -->
<div class="checkout-line">
    <span>Shipping:</span>
    <span>400 JMD</span>
</div>
```

### **NEW CHECKOUT (What to Show):**
```html
<!-- Cart Items -->
<div class="cart-items">
    {% for item in cart_items %}
    <div class="cart-item">
        <span>{{ item.name }}</span>
        <span>{{ item.price }} JMD × {{ item.quantity }}</span>
        <span class="item-total">{{ item.price * item.quantity }} JMD</span>
        <small class="shipping-note">✓ Shipping included in price</small>
    </div>
    {% endfor %}
</div>

<!-- Summary -->
<div class="order-summary">
    <div class="summary-line">
        <span>Subtotal:</span>
        <span>{{ subtotal }} JMD</span>
    </div>

    <div class="summary-line platform-fee">
        <span>Platform Handling Fee (5%):</span>
        <span>+{{ platform_fee }} JMD</span>
    </div>

    <div class="summary-line total-before-payment">
        <strong>Total:</strong>
        <strong>{{ total_before_payment }} JMD</strong>
    </div>

    <hr>

    <!-- Payment Method Selection -->
    <div class="payment-methods">
        <h3>Choose Payment Method:</h3>

        <label class="payment-option">
            <input type="radio" name="payment_method" value="wipay" data-fee-percent="4">
            <div class="payment-info">
                <strong>💳 Credit/Debit Card (WiPay)</strong>
                <small>Gateway fee: 4% (+{{ wipay_fee }} JMD)</small>
                <strong class="final-total">Final Total: {{ total_with_wipay }} JMD</strong>
            </div>
        </label>

        <label class="payment-option">
            <input type="radio" name="payment_method" value="lynk" data-fee-percent="1">
            <div class="payment-info">
                <strong>📱 Lynk Digital Wallet</strong>
                <small>Gateway fee: 1% (+{{ lynk_fee }} JMD)</small>
                <strong class="final-total">Final Total: {{ total_with_lynk }} JMD</strong>
            </div>
        </label>

        <label class="payment-option">
            <input type="radio" name="payment_method" value="cod" data-fee-percent="0">
            <div class="payment-info">
                <strong>💵 Cash on Delivery</strong>
                <small>No additional fees</small>
                <strong class="final-total">Final Total: {{ total_before_payment }} JMD</strong>
            </div>
        </label>
    </div>
</div>
```

---

## 🧮 CALCULATION FORMULAS

### **In Your Code (app.py):**

```python
# Calculate order totals
def calculate_order_totals(cart_items):
    """
    Calculate all order amounts
    Note: Shipping is already included in product price!
    """

    # Step 1: Calculate subtotal (sum of all products)
    subtotal = 0
    for item in cart_items:
        subtotal += item['price'] * item['quantity']

    # Step 2: Calculate platform fee (5% of subtotal)
    platform_fee = subtotal * 0.05

    # Step 3: Total before payment gateway fee
    total_before_payment = subtotal + platform_fee

    # Step 4: Calculate gateway fees (different for each method)
    wipay_fee = total_before_payment * 0.04  # 4%
    lynk_fee = total_before_payment * 0.01   # 1%
    cod_fee = 0

    # Step 5: Final totals
    total_with_wipay = total_before_payment + wipay_fee
    total_with_lynk = total_before_payment + lynk_fee
    total_with_cod = total_before_payment  # No extra fee

    return {
        'subtotal': subtotal,
        'platform_fee': platform_fee,
        'total_before_payment': total_before_payment,
        'wipay_fee': wipay_fee,
        'lynk_fee': lynk_fee,
        'cod_fee': cod_fee,
        'total_with_wipay': total_with_wipay,
        'total_with_lynk': total_with_lynk,
        'total_with_cod': total_with_cod
    }

# When processing payment
def process_payment(order_id, payment_method):
    """
    Process payment and update balances
    """

    # Get order details
    order = get_order(order_id)
    cart_items = get_order_items(order_id)

    # Calculate what each seller gets
    for item in cart_items:
        seller_email = item['seller_email']
        seller_payout = item['price'] * item['quantity']  # Full product price

        # Add to seller's pending balance
        cursor.execute('''
            UPDATE seller_finances
            SET pending_balance = pending_balance + %s,
                total_sales = total_sales + %s
            WHERE seller_email = %s
        ''', (seller_payout, seller_payout, seller_email))

    # Record platform fee (your revenue)
    platform_fee = order['platform_fee']
    cursor.execute('''
        INSERT INTO platform_finances (date, order_id, revenue_from_fees, gateway_fees_paid)
        VALUES (CURRENT_DATE, %s, %s, %s)
    ''', (order_id, platform_fee, order['payment_gateway_fee']))

    conn.commit()
```

---

## 📋 DATABASE SCHEMA UPDATES NEEDED

### **Add Platform Finances Table:**
```sql
CREATE TABLE IF NOT EXISTS platform_finances (
    id SERIAL PRIMARY KEY,
    date DATE DEFAULT CURRENT_DATE,
    order_id VARCHAR(50),
    revenue_from_fees DECIMAL(10,2),  -- Your 5% platform fee
    gateway_fees_paid DECIMAL(10,2),  -- What you paid to WiPay/Lynk
    net_revenue DECIMAL(10,2),        -- revenue_from_fees - gateway_fees_paid
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### **Update Orders Table:**
```sql
ALTER TABLE orders
ADD COLUMN IF NOT EXISTS subtotal DECIMAL(10,2),
ADD COLUMN IF NOT EXISTS platform_fee DECIMAL(10,2),
ADD COLUMN IF NOT EXISTS payment_gateway_fee DECIMAL(10,2),
ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20);  -- 'wipay', 'lynk', 'cod'
```

---

## 🎯 MONEY FLOW SUMMARY

### **WHO GETS WHAT:**

**1. Payment Gateway (WiPay/Lynk):**
- Takes their fee immediately when customer pays
- 4% for WiPay
- 1% for Lynk
- 0% for Cash on Delivery

**2. Zo-Zi Platform (YOU):**
- Gets 5% of subtotal as platform fee
- Money goes to YOUR business NCB account
- This is YOUR revenue

**3. Sellers:**
- Get 100% of product price (includes shipping they set)
- You pay them weekly/bi-weekly from your account
- They don't lose anything to platform fee

### **EXAMPLE WITH REAL NUMBERS:**

**Product costs 5,000 JMD (seller set this price, shipping included)**

**Customer pays with WiPay:**
```
Customer pays:     5,250 JMD (5000 + 250 platform fee)
                 + 210 JMD (4% WiPay fee)
                 ─────────
Total paid:        5,460 JMD

Money flow:
├─ WiPay takes:      210 JMD (their fee)
├─ You receive:    5,250 JMD
│
│  From this:
│  ├─ YOU keep:      250 JMD (platform fee = your revenue!)
│  └─ Seller gets: 5,000 JMD (their full product price)
│
└─ You pay seller 5,000 JMD weekly
```

**Customer pays with Lynk:**
```
Customer pays:     5,250 JMD
                 +   53 JMD (1% Lynk fee)
                 ─────────
Total paid:        5,303 JMD

Money flow:
├─ Lynk takes:        53 JMD
├─ You receive:    5,250 JMD
│
│  From this:
│  ├─ YOU keep:      250 JMD (your revenue)
│  └─ Seller gets: 5,000 JMD
```

**Customer pays Cash:**
```
Customer pays:     5,250 JMD (cash to driver)

Money flow:
├─ You receive:    5,250 JMD
│
│  From this:
│  ├─ YOU keep:      250 JMD
│  └─ Seller gets: 5,000 JMD
```

---

## ✅ KEY POINTS

1. **Shipping is already in product price** ✓
   - Seller adds shipping when listing product
   - No separate shipping charge at checkout

2. **Platform fee is clear** ✓
   - 5% shown separately
   - Customer knows what they're paying for

3. **Gateway fees are transparent** ✓
   - Different for each payment method
   - Customer chooses based on fee

4. **Money goes to right people** ✓
   - Gateway gets their cut automatically
   - You keep platform fee (5%)
   - Sellers get full product price
   - You pay sellers weekly

5. **All tracked in database** ✓
   - Every penny accounted for
   - Easy to generate reports
   - Audit trail

---

## 🚀 WHAT I'LL BUILD FOR YOU

1. **Updated checkout page** (no shipping, clear fees)
2. **Payment method selector** (WiPay/Lynk/COD)
3. **Order processing logic** (correct money splits)
4. **Seller payout tracking** (pending balances)
5. **Admin payout dashboard** (weekly payouts)
6. **Platform revenue tracking** (your earnings)

**Ready to start coding this?** Let me know and I'll begin! 🎯
