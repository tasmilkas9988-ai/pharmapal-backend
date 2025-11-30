#!/usr/bin/env python3
"""
Script to make a user admin
Usage: python make_admin.py <email>
"""
import asyncio
import sys
import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

async def make_admin(email):
    """Make a user admin by email"""
    
    # Connect to MongoDB
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', 'pharmapal_db')]
    
    print(f"🔌 Connected to MongoDB")
    print(f"📧 Looking for user: {email}")
    
    # Check if user exists
    user = await db.users.find_one({"email": email})
    if not user:
        print(f"❌ User not found with email: {email}")
        client.close()
        return False
    
    print(f"✅ User found: {user['full_name']}")
    
    # Check if already admin
    if user.get('is_admin', False):
        print(f"⚠️  User is already an admin!")
        client.close()
        return True
    
    # Update to admin
    result = await db.users.update_one(
        {"email": email},
        {"$set": {"is_admin": True}}
    )
    
    if result.modified_count > 0:
        print(f"🎉 SUCCESS! {user['full_name']} is now an admin!")
        print(f"\n📱 Next steps:")
        print(f"  1. Logout from the app")
        print(f"  2. Login again")
        print(f"  3. You'll see a '🎛️ Admin' button in the dashboard")
        print(f"  4. Click it to access Admin Dashboard!")
    else:
        print(f"❌ Failed to update user")
    
    client.close()
    return result.modified_count > 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <email>")
        print("Example: python make_admin.py admin@pharmapal.com")
        sys.exit(1)
    
    email = sys.argv[1]
    success = asyncio.run(make_admin(email))
    sys.exit(0 if success else 1)
