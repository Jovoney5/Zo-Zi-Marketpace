#!/usr/bin/env python3
# setup_postgres.py - Setup script for PostgreSQL migration

import os
import sys
import subprocess
import platform

def check_postgresql_installed():
    """Check if PostgreSQL is installed"""
    try:
        result = subprocess.run(['psql', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ PostgreSQL found: {result.stdout.strip()}")
            return True
        else:
            return False
    except FileNotFoundError:
        return False

def install_postgresql_macos():
    """Install PostgreSQL on macOS using Homebrew"""
    print("🍺 Installing PostgreSQL using Homebrew...")
    try:
        # Check if Homebrew is installed
        subprocess.run(['brew', '--version'], capture_output=True, check=True)

        # Install PostgreSQL
        subprocess.run(['brew', 'install', 'postgresql@15'], check=True)
        subprocess.run(['brew', 'services', 'start', 'postgresql@15'], check=True)

        print("✅ PostgreSQL installed and started!")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install PostgreSQL via Homebrew")
        return False
    except FileNotFoundError:
        print("❌ Homebrew not found. Please install Homebrew first:")
        print("   /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
        return False

def create_database():
    """Create the zozi_marketplace database"""
    try:
        print("🗄️  Creating database 'zozi_marketplace'...")

        # Try to create database
        result = subprocess.run([
            'createdb', 'zozi_marketplace'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ Database 'zozi_marketplace' created successfully!")
            return True
        elif "already exists" in result.stderr:
            print("ℹ️  Database 'zozi_marketplace' already exists")
            return True
        else:
            print(f"❌ Failed to create database: {result.stderr}")
            print("💡 Try running manually: createdb zozi_marketplace")
            return False

    except FileNotFoundError:
        print("❌ createdb command not found. Make sure PostgreSQL is in your PATH")
        return False

def setup_environment():
    """Setup environment variables"""
    db_url = "postgresql://$(whoami)@localhost:5432/zozi_marketplace"

    print("\n🔧 Environment Setup:")
    print("Add this to your shell profile (.bashrc, .zshrc, etc.):")
    print(f"   export DATABASE_URL='{db_url}'")
    print("\nOr for development, create a .env file:")
    print(f"   echo 'DATABASE_URL={db_url}' > .env")

    # Try to create .env file
    try:
        with open('.env', 'w') as f:
            f.write(f"DATABASE_URL={db_url}\n")
            f.write("USE_POSTGRESQL=true\n")
            f.write("FLASK_ENV=development\n")
            f.write("DEBUG=True\n")
        print("✅ Created .env file with DATABASE_URL")
    except Exception as e:
        print(f"⚠️  Could not create .env file: {e}")

def test_connection():
    """Test PostgreSQL connection"""
    print("\n🧪 Testing PostgreSQL connection...")
    try:
        # Set environment for testing
        os.environ['DATABASE_URL'] = 'postgresql://localhost:5432/zozi_marketplace'

        from database_postgres import test_connection
        if test_connection():
            print("✅ PostgreSQL connection successful!")
            return True
        else:
            print("❌ PostgreSQL connection failed")
            return False
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 Zo-Zi Marketplace PostgreSQL Setup")
    print("=" * 50)

    # Detect OS
    os_name = platform.system()
    print(f"🖥️  Operating System: {os_name}")

    # Check if PostgreSQL is installed
    if not check_postgresql_installed():
        print("❌ PostgreSQL not found")

        if os_name == "Darwin":  # macOS
            install_choice = input("🤔 Install PostgreSQL using Homebrew? (y/n): ").lower()
            if install_choice == 'y':
                if not install_postgresql_macos():
                    return False
            else:
                print("💡 Please install PostgreSQL manually and run this script again")
                return False
        else:
            print("💡 Please install PostgreSQL for your operating system:")
            print("   - Ubuntu/Debian: sudo apt-get install postgresql postgresql-contrib")
            print("   - CentOS/RHEL: sudo yum install postgresql postgresql-server")
            print("   - Windows: Download from https://www.postgresql.org/download/windows/")
            return False

    # Create database
    if not create_database():
        return False

    # Setup environment
    setup_environment()

    # Test connection
    if test_connection():
        print("\n🎉 Setup completed successfully!")
        print("\n📋 Next steps:")
        print("1. Run the migration script: python migrate_to_postgres.py")
        print("2. Start your app: python app.py")
        print("3. Your app will now use PostgreSQL!")
        return True
    else:
        print("\n❌ Setup completed but connection test failed")
        print("💡 Check your PostgreSQL installation and try again")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)