#!/usr/bin/env python3
"""
Import SFDA medication data from sfda_prices.json into MongoDB
"""
import asyncio
import json
import os
from motor.motor_asyncio import AsyncIOMotorClient

async def import_sfda_data():
    """Import SFDA medication data from JSON file"""
    
    # Connect to MongoDB
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client['pharmacydb']
    
    print("🔌 متصل بقاعدة البيانات MongoDB")
    
    # Load data from file
    with open('/app/backend/sfda_prices.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    medications = data.get('medications', [])
    print(f"📦 عدد الأدوية في الملف: {len(medications)}")
    
    if not medications:
        print("❌ لا توجد أدوية للاستيراد!")
        return
    
    # Drop existing collection to start fresh
    print("🗑️  حذف البيانات القديمة...")
    await db.sfda_medications.drop()
    
    # Transform data to match expected format
    transformed_medications = []
    for med in medications:
        transformed = {
            "trade_name": med.get('name_en', ''),
            "trade_name_ar": med.get('name_ar', ''),
            "trade_name_lower": med.get('name_en', '').lower(),
            "active_ingredients": med.get('active_ingredient', ''),
            "active_ingredients_lower": med.get('active_ingredient', '').lower(),
            "strength": med.get('strength', ''),
            "price_sar": med.get('price_sar', 0),
            "pack": med.get('package_size', ''),
            "pack_ar": med.get('package_size', ''),
            "package_size": med.get('package_size', ''),
            "manufacturer": "Various",
            "manufacturer_ar": "متنوع",
            "dosage_form": "Tablet",
            "dosage_form_ar": "أقراص"
        }
        transformed_medications.append(transformed)
    
    # Insert medications
    print(f"\n📥 استيراد {len(transformed_medications)} دواء...")
    result = await db.sfda_medications.insert_many(transformed_medications)
    print(f"   ✅ تم استيراد {len(result.inserted_ids)} دواء")
    
    # Create indexes for fast search - both English and Arabic
    print("\n🔍 إنشاء indexes للبحث السريع...")
    
    await db.sfda_medications.create_index("trade_name_lower")
    print("   ✅ Index: trade_name_lower")
    
    await db.sfda_medications.create_index("active_ingredients_lower")
    print("   ✅ Index: active_ingredients_lower")
    
    # Create indexes for Arabic fields
    await db.sfda_medications.create_index("trade_name_ar")
    print("   ✅ Index: trade_name_ar")
    
    # Verify import
    count = await db.sfda_medications.count_documents({})
    print(f"\n✅ إجمالي الأدوية في القاعدة: {count}")
    
    # Show sample
    print("\n📝 عينة من البيانات:")
    sample = await db.sfda_medications.find_one({})
    if sample:
        sample.pop('_id', None)
        print(f"  الاسم بالإنجليزية: {sample.get('trade_name')}")
        print(f"  الاسم بالعربية: {sample.get('trade_name_ar')}")
        print(f"  المادة الفعالة: {sample.get('active_ingredients')}")
        print(f"  السعر: {sample.get('price_sar')} ريال")
    
    # Test Arabic search
    print("\n🧪 اختبار البحث بالعربية...")
    ar_result = await db.sfda_medications.find_one({"trade_name_ar": {"$regex": "بانادول", "$options": "i"}})
    if ar_result:
        print(f"  ✅ وجد: {ar_result.get('trade_name_ar')}")
    else:
        print("  ❌ لم يجد نتائج بالعربية")
    
    # Test English search
    print("\n🧪 اختبار البحث بالإنجليزية...")
    en_result = await db.sfda_medications.find_one({"trade_name": {"$regex": "panadol", "$options": "i"}})
    if en_result:
        print(f"  ✅ وجد: {en_result.get('trade_name')}")
    else:
        print("  ❌ لم يجد نتائج بالإنجليزية")
    
    client.close()
    print("\n🎉 اكتمل الاستيراد بنجاح!")

if __name__ == "__main__":
    asyncio.run(import_sfda_data())
