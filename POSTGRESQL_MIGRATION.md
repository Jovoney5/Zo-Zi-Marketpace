# 🚀 PostgreSQL Migration Guide for Zo-Zi Marketplace

This guide will help you migrate your Jamaican marketplace from SQLite to PostgreSQL for better performance and scalability.

## Why PostgreSQL?

✅ **Better concurrency** - Multiple buyers/sellers can use the platform simultaneously
✅ **Improved performance** - Handles complex queries and large datasets better
✅ **Production ready** - Used by major platforms like Instagram, Uber, Netflix
✅ **ACID compliance** - Better data integrity for financial transactions

## 🔧 Migration Steps

### Step 1: Setup PostgreSQL

Run the automated setup script:

```bash
python setup_postgres.py
```

This will:
- Install PostgreSQL (on macOS via Homebrew)
- Create the `zozi_marketplace` database
- Setup environment variables
- Test the connection

**Manual Setup (if needed):**

```bash
# Install PostgreSQL (macOS)
brew install postgresql@15
brew services start postgresql@15

# Create database
createdb zozi_marketplace

# Set environment variable
export DATABASE_URL='postgresql://$(whoami)@localhost:5432/zozi_marketplace'
```

### Step 2: Migrate Your Data

```bash
python migrate_to_postgres.py
```

This will:
- Initialize PostgreSQL tables
- Transfer all your existing data from SQLite
- Handle JSON field conversions
- Preserve all user accounts, products, orders, etc.

### Step 3: Update Your App

Your app will automatically detect PostgreSQL and use it instead of SQLite.

**Start your app:**
```bash
python app.py
```

## 🔄 How It Works

### Database Selection Logic

The system automatically chooses the database:

```python
# Uses PostgreSQL if DATABASE_URL is set
USE_POSTGRESQL = os.getenv('DATABASE_URL') or os.getenv('USE_POSTGRESQL', 'true')

if USE_POSTGRESQL:
    # Use PostgreSQL
else:
    # Fallback to SQLite
```

### Environment Variables

Create a `.env` file:
```env
DATABASE_URL=postgresql://username:password@localhost:5432/zozi_marketplace
USE_POSTGRESQL=true
FLASK_ENV=development
DEBUG=True
```

## 🗂️ File Structure

- `database_postgres.py` - PostgreSQL connection and functions
- `database.py` - Smart database selector (PostgreSQL/SQLite)
- `migrate_to_postgres.py` - Migration script
- `setup_postgres.py` - Automated setup
- `.env.example` - Environment template

## 📊 Tables Migrated

✅ Users (buyers, sellers, admins)
✅ Products (with images and sizes)
✅ Orders and order items
✅ Seller finances and transactions
✅ Admin users and activity logs
✅ User flags and verification data
✅ Messages between buyers/sellers
✅ Payment transactions
✅ Withdrawal requests

## 🔧 Troubleshooting

### Connection Issues

```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Test connection manually
psql -d zozi_marketplace -c "SELECT 1;"
```

### Migration Issues

```bash
# Check tables exist in PostgreSQL
psql -d zozi_marketplace -c "\dt"

# Check data was migrated
psql -d zozi_marketplace -c "SELECT COUNT(*) FROM users;"
```

### Environment Issues

```bash
# Check environment variables
echo $DATABASE_URL

# Test database selection
python -c "from database import USE_POSTGRESQL; print('PostgreSQL:', USE_POSTGRESQL)"
```

## 🚀 Production Deployment

### Heroku
```bash
# Heroku automatically sets DATABASE_URL
heroku addons:create heroku-postgresql:hobby-dev
```

### Railway
```bash
# Railway provides PostgreSQL with DATABASE_URL
railway add postgresql
```

### Other Platforms
Set `DATABASE_URL` environment variable with your PostgreSQL connection string.

## 🔒 Security Notes

- Never commit `.env` files to version control
- Use strong passwords for production databases
- Consider connection pooling for high traffic
- Enable SSL in production: `?sslmode=require`

## 📈 Performance Benefits

After migration, you should see:
- Faster concurrent user handling
- Better performance with large product catalogs
- More reliable financial transactions
- Improved admin dashboard responsiveness

## 🆘 Need Help?

1. **Database connection fails**: Check PostgreSQL is running and DATABASE_URL is correct
2. **Migration incomplete**: Check SQLite file exists and has data
3. **App won't start**: Check .env file and dependencies installed

## 🎉 Success!

Once migrated:
- Your marketplace will handle multiple concurrent users
- Financial transactions will be more reliable
- You'll be ready for production deployment
- Your Jamaican marketplace will scale with your business!

---

**Ready to migrate?** Run `python setup_postgres.py` to get started! 🚀