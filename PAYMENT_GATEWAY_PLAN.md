# 💳 Payment Gateway & Money Split Implementation Plan
## For Zo-Zi Marketplace (Jamaica)

---

## 🎯 OVERVIEW

You need to solve TWO main challenges:
1. **Accept payments** from customers (locally in Jamaica and internationally)
2. **Split money** between your platform (commission) and sellers (their earnings)

---

## 💰 PAYMENT GATEWAY OPTIONS FOR JAMAICA

### Option 1: **NCB Payment Gateway** (Your Bank) ⭐ RECOMMENDED FOR LOCAL
**Pros:**
- ✅ You already bank with NCB - easier setup
- ✅ Supports JMD (Jamaican Dollars) natively
- ✅ Local support in Jamaica
- ✅ Lower fees for local transactions
- ✅ Trusted by Jamaican customers
- ✅ Can handle debit/credit cards

**Cons:**
- ❌ Limited international reach
- ❌ May not support all international cards
- ❌ Less documentation/developer resources

**Setup Process:**
1. Visit NCB Business Banking branch
2. Request "NCB Payment Gateway for E-Commerce"
3. Requirements:
   - Business registration documents
   - TRN (Tax Registration Number)
   - Website details
   - Bank account for settlements
4. Developer API documentation
5. Integration (they may provide PHP/Python SDK)

**Fees (Estimated):**
- Setup fee: ~$10,000-30,000 JMD (one-time)
- Transaction fee: ~3-5% per transaction
- Monthly fee: ~$5,000-10,000 JMD

**NCB Contact:**
- Business Banking: 1-888-NCB-FIRST (622-3477)
- Website: ncbjamaica.com

---

### Option 2: **Stripe** ⭐ RECOMMENDED FOR INTERNATIONAL + LOCAL
**Pros:**
- ✅ Works in 135+ countries
- ✅ Excellent documentation and APIs
- ✅ **Stripe Connect** - PERFECT for marketplace money splits!
- ✅ Automatic payouts to sellers
- ✅ Handles multi-currency (JMD, USD, etc.)
- ✅ No monthly fees
- ✅ Quick integration (1-2 weeks)
- ✅ Fraud protection built-in

**Cons:**
- ❌ Requires business registration
- ❌ Slightly higher fees than local options
- ❌ Payout might take 7-14 days initially

**Setup Process:**
1. Register at stripe.com
2. Provide:
   - Business details
   - TRN
   - Bank account (NCB works!)
   - ID verification
3. Enable **Stripe Connect** (for marketplace)
4. Integrate using Python SDK (stripe library)

**Fees:**
- No setup fee
- No monthly fee
- Transaction: 2.9% + $0.30 USD per charge
- Stripe Connect: Additional 2% for platform fee

**Stripe Contact:**
- Website: stripe.com/connect
- Support: Online chat + email

---

### Option 3: **PayPal Business**
**Pros:**
- ✅ Widely recognized globally
- ✅ Customers trust PayPal
- ✅ Quick setup
- ✅ Works in Jamaica

**Cons:**
- ❌ High fees (4-5% + currency conversion)
- ❌ Money can be held/frozen
- ❌ Difficult money split system
- ❌ Not ideal for marketplace model

**Not Recommended** for your marketplace.

---

### Option 4: **2Checkout (Verifone)**
**Pros:**
- ✅ Works in Jamaica
- ✅ Supports 87 currencies
- ✅ Good for international sales

**Cons:**
- ❌ Higher fees (~3.5% + $0.35)
- ❌ Complex marketplace setup
- ❌ Less popular than Stripe

---

## 🏆 MY RECOMMENDATION

### **HYBRID APPROACH** (Best of Both Worlds)

**For Jamaican Customers:**
- Use **NCB Payment Gateway**
- Lower fees for local transactions
- Customers trust local bank

**For International Customers:**
- Use **Stripe**
- Better international card support
- Handles USD, EUR, CAD, etc.

**OR - Simpler Option:**

**Just Use Stripe** (Easier to manage)
- Handles both local (JMD) and international
- One integration, one system
- Automatic money splits with Stripe Connect
- Lower development effort

---

## 💸 MONEY SPLIT SYSTEM DESIGN

### Current Database Setup
I see you already have:
- `seller_finances` table
- `seller_transactions` table
- Platform fee tracking (5%)

### How Money Split Works

**Example Transaction:**
```
Customer buys product for 5,000 JMD

├─ Gross Amount: 5,000 JMD
├─ Payment Gateway Fee (3%): -150 JMD
├─ Net Amount: 4,850 JMD
│
├─ Platform Fee (5%): -242.50 JMD (5% of 4,850)
└─ Seller Gets: 4,607.50 JMD
```

### Two Approaches:

#### **Approach 1: MANUAL PAYOUTS** (Simpler, start here)
**How it works:**
1. Customer pays → money goes to YOUR NCB account
2. You track what each seller earned (database)
3. Weekly/Monthly: You manually transfer to sellers via NCB

**Pros:**
- ✅ Simple to implement
- ✅ You control cash flow
- ✅ Can verify orders before paying
- ✅ No complex API integration

**Cons:**
- ❌ Manual work every week/month
- ❌ Sellers wait for payouts
- ❌ More accounting work

**Implementation:**
```python
# When order completes:
1. Add to seller_finances table
2. Update seller's pending_balance
3. At payout time:
   - Generate payout report
   - Transfer via NCB mobile/online banking
   - Mark as paid in database
```

---

#### **Approach 2: AUTOMATIC PAYOUTS** (Stripe Connect) ⭐ BEST LONG-TERM
**How it works:**
1. Each seller connects their bank account to Stripe
2. Customer pays → Stripe automatically splits:
   - Your platform fee → Your Stripe account
   - Seller earnings → Seller's bank account
3. Happens automatically within 2-7 days

**Pros:**
- ✅ Fully automated (no manual work!)
- ✅ Sellers get paid faster
- ✅ Professional system
- ✅ Scalable to 1000s of sellers

**Cons:**
- ❌ More complex initial setup
- ❌ Requires seller onboarding
- ❌ Stripe Connect fees (2%)

**Stripe Connect Models:**

**Standard Accounts** (Recommended):
- Seller creates their own Stripe account
- You send payments directly to them
- They manage their own payouts
- Full control for sellers

**Express Accounts**:
- You create account on seller's behalf
- Simpler for sellers
- You control more of the experience

---

## 📋 STEP-BY-STEP IMPLEMENTATION PLAN

### Phase 1: FOUNDATION (Week 1-2)
**Goals:**
- Choose payment gateway
- Set up business account
- Get legal requirements ready

**Tasks:**
1. ✅ Register your business (if not done)
   - Company name: "Zo-Zi Marketplace Ltd" or similar
   - Business registration at Companies Office of Jamaica

2. ✅ Get TRN (Tax Registration Number)
   - Visit TAJ (Tax Administration Jamaica)
   - Required for payment gateways

3. ✅ Open business bank account at NCB (if needed)
   - Bring: Business registration, TRN, ID

4. ✅ Decide: NCB vs Stripe vs Both
   - **My suggestion: Start with Stripe** (easier, faster)

---

### Phase 2: PAYMENT GATEWAY SETUP (Week 3-4)

#### **If Using NCB:**
**Week 3:**
1. Visit NCB Business Banking
2. Request "E-Commerce Payment Gateway"
3. Submit documents
4. Wait for approval (1-2 weeks)

**Week 4:**
5. Receive API credentials
6. Read NCB API documentation
7. Test in sandbox environment

#### **If Using Stripe:**
**Week 3:**
1. Sign up: stripe.com/en-jm
2. Complete business verification:
   - Upload business documents
   - Add bank account (NCB)
   - Verify identity
3. Enable Stripe Connect
4. Read documentation: stripe.com/docs/connect

**Week 4:**
5. Set up test mode
6. Create test transactions
7. Verify money flow

---

### Phase 3: CODE INTEGRATION (Week 5-6)

**Week 5: Basic Payment Acceptance**

**Install Stripe:**
```bash
pip install stripe
```

**Add to your app.py:**
```python
import stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

@app.route('/create-payment-intent', methods=['POST'])
def create_payment():
    data = request.json
    amount = data['amount']  # In cents (5000 JMD = 500000 cents)

    intent = stripe.PaymentIntent.create(
        amount=amount,
        currency='jmd',
        metadata={'order_id': data['order_id']}
    )

    return jsonify({'client_secret': intent.client_secret})
```

**Update checkout.html:**
```html
<script src="https://js.stripe.com/v3/"></script>
<script>
    const stripe = Stripe('pk_live_YOUR_PUBLIC_KEY');
    // Payment form integration
</script>
```

**Week 6: Money Split Logic**

**Option A - Manual Payouts:**
```python
# When order is confirmed:
@app.route('/confirm_order', methods=['POST'])
def confirm_order():
    # Calculate splits
    total = order['total']
    gateway_fee = total * 0.03  # 3%
    net_amount = total - gateway_fee
    platform_fee = net_amount * 0.05  # 5%
    seller_earnings = net_amount - platform_fee

    # Save to database
    cursor.execute('''
        UPDATE seller_finances
        SET pending_balance = pending_balance + %s
        WHERE seller_email = %s
    ''', (seller_earnings, seller_email))
```

**Option B - Stripe Connect:**
```python
# Create connected account for seller
@app.route('/seller/connect-stripe', methods=['POST'])
def connect_stripe():
    account = stripe.Account.create(
        type='express',
        country='JM',
        email=seller_email,
        capabilities={
            'card_payments': {'requested': True},
            'transfers': {'requested': True},
        },
    )

    # Save account.id to database
    # Generate onboarding link for seller

# When processing payment
def create_payment_with_split(amount, seller_account_id):
    platform_fee = amount * 0.05

    payment = stripe.PaymentIntent.create(
        amount=amount,
        currency='jmd',
        application_fee_amount=int(platform_fee),
        transfer_data={'destination': seller_account_id}
    )
```

---

### Phase 4: SELLER ONBOARDING (Week 7)

**For Manual Payouts:**
1. Add bank account fields to seller registration
   - Bank name
   - Account number
   - Account name
   - Branch

**For Stripe Connect:**
1. Create "Connect Stripe" button on seller dashboard
2. Generate Stripe onboarding link
3. Seller completes Stripe verification
4. Save Stripe account ID to database

---

### Phase 5: PAYOUT SYSTEM (Week 8)

**Manual Payout Process:**

**Create admin payout page:**
```python
@app.route('/admin/payouts', methods=['GET'])
def admin_payouts():
    # Get all sellers with pending balance > 0
    cursor.execute('''
        SELECT seller_email, pending_balance,
               bank_name, account_number
        FROM seller_finances
        WHERE pending_balance > 0
        ORDER BY pending_balance DESC
    ''')
    sellers = cursor.fetchall()

    return render_template('admin_payouts.html', sellers=sellers)

@app.route('/admin/mark-paid', methods=['POST'])
def mark_paid():
    seller_email = request.form['seller_email']
    amount = request.form['amount']

    # Move from pending to paid
    cursor.execute('''
        UPDATE seller_finances
        SET pending_balance = pending_balance - %s,
            paid_balance = paid_balance + %s
        WHERE seller_email = %s
    ''', (amount, amount, seller_email))

    # Log transaction
    cursor.execute('''
        INSERT INTO seller_transactions
        (seller_email, type, amount, description)
        VALUES (%s, 'payout', %s, 'Manual payout')
    ''', (seller_email, amount))
```

**Automatic Payout (Stripe Connect):**
- Stripe handles this automatically!
- Sellers receive money within 2-7 days
- No code needed for payouts

---

## 🏦 VISITING NCB - WHAT TO BRING

### Documents Needed:
1. ✅ **Business Registration Certificate**
2. ✅ **TRN (Tax Registration Number)**
3. ✅ **Government-issued ID** (Driver's license or Passport)
4. ✅ **Proof of Address** (Utility bill, bank statement)
5. ✅ **Website URL** (your deployed site)
6. ✅ **Business Plan** (simple 1-2 page document explaining Zo-Zi)
7. ✅ **Bank Statements** (last 3 months if available)

### Questions to Ask NCB:
1. "What is your e-commerce payment gateway called?"
2. "What are the setup fees and transaction fees?"
3. "How long does approval take?"
4. "Do you provide API documentation?"
5. "Do you support marketplace/multi-vendor payments?"
6. "Can I test in a sandbox environment first?"
7. "What currencies do you support?" (JMD, USD?)
8. "How do chargebacks work?"
9. "What is the settlement time?" (When do I receive money?)
10. "Do you provide fraud protection?"

---

## 💡 MY PERSONAL RECOMMENDATION

### **START SIMPLE, SCALE LATER**

**Phase 1 (Launch - Month 1-3):**
- ✅ Use **Stripe** for payments (easier setup)
- ✅ Use **Manual Payouts** to sellers
- ✅ Pay sellers weekly via NCB transfer
- ✅ Platform fee: 5%

**Why:**
- Get to market faster
- Learn seller/customer behavior
- Less complexity initially
- Stripe works with NCB accounts

**Phase 2 (After 3 months):**
- ✅ Switch to **Stripe Connect** (automatic splits)
- ✅ Add NCB gateway for local customers (optional)
- ✅ Automated seller payouts

**Why:**
- You now have proven sellers
- Automated system saves time
- Can scale to 100+ sellers

---

## 📊 COST BREAKDOWN

### Option 1: Stripe (Manual Payouts)
**Initial Costs:**
- Setup: $0
- Monthly: $0

**Per Transaction (5,000 JMD sale):**
- Stripe fee (2.9% + $0.30): ~$2 USD = ~300 JMD
- Your platform fee (5%): 250 JMD
- Seller receives: 4,450 JMD
- You keep: 250 JMD

**Manual payout costs:**
- NCB transfer fee: ~$200-500 JMD per transfer
- Your time: 2-3 hours/week

---

### Option 2: Stripe Connect (Automatic)
**Initial Costs:**
- Setup: $0
- Monthly: $0

**Per Transaction (5,000 JMD sale):**
- Stripe fee (2.9% + $0.30): ~300 JMD
- Stripe Connect fee (2%): 100 JMD
- Your platform fee (5%): 250 JMD
- Seller receives: 4,350 JMD
- You keep: 250 JMD

**Benefits:**
- No manual work
- Instant splits
- Scalable

---

### Option 3: NCB Gateway (Manual Payouts)
**Initial Costs:**
- Setup: ~15,000-30,000 JMD
- Monthly: ~5,000-10,000 JMD

**Per Transaction (5,000 JMD sale):**
- NCB fee (3-5%): ~150-250 JMD
- Your platform fee (5%): 250 JMD
- Seller receives: 4,500-4,600 JMD
- You keep: 250 JMD

**Benefits:**
- Lower per-transaction cost
- Local support

---

## 🎯 FINAL RECOMMENDATION

### **For You (Zo-Zi Marketplace):**

1. **Start with Stripe + Manual Payouts**
   - Fastest to launch (2-3 weeks)
   - Low initial cost ($0)
   - Works with your NCB account
   - Easy to implement

2. **After 3-6 months:**
   - Upgrade to Stripe Connect
   - Fully automated
   - Scale to unlimited sellers

3. **Optional - Add NCB later:**
   - If most customers are Jamaican
   - To reduce fees
   - As a backup option

---

## 📝 NEXT STEPS (ACTION ITEMS)

### This Week:
1. ✅ Decide: Stripe vs NCB vs Both
2. ✅ Gather business documents (registration, TRN)
3. ✅ Sign up for Stripe account (if chosen)
4. ✅ Visit NCB to inquire about gateway (if chosen)

### Next Week:
5. ✅ Complete payment gateway setup
6. ✅ Review Stripe/NCB documentation
7. ✅ Plan seller payout process

### Week 3-4:
8. ✅ Implement payment integration
9. ✅ Test with dummy transactions
10. ✅ Create payout tracking system

---

## 🤝 I CAN HELP YOU WITH:

1. **Stripe Integration Code** (Python/Flask)
2. **Database schema updates** for payments
3. **Admin payout dashboard**
4. **Seller payout tracking**
5. **Webhook handling** (payment confirmations)
6. **Testing payment flows**

---

## 📞 CONTACTS & RESOURCES

**NCB Jamaica:**
- Phone: 1-888-NCB-FIRST (622-3477)
- Email: contact@jncb.com
- Website: ncbjamaica.com

**Stripe:**
- Website: stripe.com
- Documentation: stripe.com/docs
- Support: support.stripe.com
- Jamaica Guide: stripe.com/en-jm

**TAJ (Tax Registration):**
- Phone: 1-888-TAJ-TTAX (1-888-825-8829)
- Website: jamaicatax.gov.jm

**Companies Office of Jamaica:**
- Phone: (876) 906-4558-61
- Website: orcjamaica.com

---

## 🚀 READY TO START?

Let me know which option you want to pursue and I can:
1. Write the Stripe integration code for you
2. Create the payout tracking system
3. Build the admin payout dashboard
4. Help prepare for your NCB meeting

**What would you like to tackle first?**
