#!/usr/bin/env python3
"""
Import SFDA medication data into MongoDB
"""
import asyncio
import json
import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

async def import_sfda_data():
    """Import SFDA medication data from JSON chunks"""
    
    # Connect to MongoDB
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', 'pharmapal_db')]
    
    print("🔌 متصل بقاعدة البيانات MongoDB")
    
    # Drop existing collection to start fresh
    print("🗑️  حذف البيانات القديمة...")
    await db.sfda_medications.drop()
    
    # Import data from chunks
    total_imported = 0
    chunk_files = sorted(Path('/tmp').glob('sfda_new_chunk_*.json'))
    
    print(f"📦 عدد ال-chunks: {len(chunk_files)}")
    
    for chunk_file in chunk_files:
        print(f"\n📥 استيراد: {chunk_file.name}")
        
        with open(chunk_file, 'r', encoding='utf-8') as f:
            medications = json.load(f)
        
        if medications:
            result = await db.sfda_medications.insert_many(medications)
            total_imported += len(result.inserted_ids)
            print(f"   ✅ تم استيراد {len(result.inserted_ids):,} دواء")
    
    # Create indexes for fast search
    print("\n🔍 إنشاء indexes للبحث السريع...")
    
    await db.sfda_medications.create_index("trade_name_lower")
    print("   ✅ Index: trade_name_lower")
    
    await db.sfda_medications.create_index("active_ingredients_lower")
    print("   ✅ Index: active_ingredients_lower")
    
    await db.sfda_medications.create_index("manufacturer")
    print("   ✅ Index: manufacturer")
    
    await db.sfda_medications.create_index([
        ("trade_name_lower", "text"),
        ("active_ingredients_lower", "text")
    ])
    print("   ✅ Text index: للبحث النصي")
    
    # Verify import
    count = await db.sfda_medications.count_documents({})
    print(f"\n✅ إجمالي الأدوية المستوردة: {count:,}")
    
    # Show sample
    print("\n📝 عينة من البيانات:")
    sample = await db.sfda_medications.find_one({})
    if sample:
        sample.pop('_id', None)
        print(json.dumps(sample, ensure_ascii=False, indent=2))
    
    client.close()
    print("\n🎉 اكتمل الاستيراد بنجاح!")

if __name__ == "__main__":
    asyncio.run(import_sfda_data())
