"""
Import SFDA medications from Excel file to MongoDB
"""
import pandas as pd
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import uuid
from datetime import datetime, timezone
import warnings
warnings.filterwarnings('ignore')

load_dotenv()

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'pharmapal_db')

async def import_medications():
    """Import medications from Excel to MongoDB"""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    print("📂 Reading Excel file...")
    df = pd.read_excel('sfda_medications.xlsx')
    print(f"✅ Found {len(df)} medications in Excel file")
    
    # Clear existing medications
    print("🗑️  Clearing existing medications...")
    result = await db.medications.delete_many({})
    print(f"✅ Deleted {result.deleted_count} existing medications")
    
    # Prepare medications for insertion
    medications = []
    
    for idx, row in df.iterrows():
        # Handle NaN values
        def safe_str(val):
            return str(val) if pd.notna(val) and str(val) != 'nan' and str(val) != '#VALUE!' else ''
        
        def safe_float(val):
            try:
                if pd.notna(val) and str(val) != '#VALUE!':
                    return float(val)
                return None
            except:
                return None
        
        medication = {
            "id": str(uuid.uuid4()),
            "commercial_name_en": safe_str(row.get('trade Name', '')),
            "commercial_name_ar": safe_str(row.get('الاسم التجاري', '')),
            "scientific_name": safe_str(row.get('scientific Name', '')),
            "scientific_name_ar": safe_str(row.get('الاسم العلمي', '')),
            "package_size": safe_float(row.get('package Size')),
            "size": safe_float(row.get('size')),
            "strength": safe_str(row.get('strength', '')),
            "strength_ar": safe_str(row.get('قوة', '')),
            "price_sar": safe_float(row.get('price SAR')),
            "drug_type": safe_str(row.get('drug Type', '')),
            "drug_type_ar": safe_str(row.get('نوع الدواء', '')),
            "package_type": safe_str(row.get('package Type', '')),
            "package_type_ar": safe_str(row.get('نوع الحزمة', '')),
            "size_unit": safe_str(row.get('size Unit', '')),
            "size_unit_ar": safe_str(row.get('وحدة الحجم', '')),
            "strength_unit": safe_str(row.get('strength Unit', '')),
            "strength_unit_ar": safe_str(row.get('وحدة القوة', '')),
            "administration_route": safe_str(row.get('administration Route', '')),
            "administration_route_ar": safe_str(row.get('طريق الإدارة', '')),
            "dosage_form": safe_str(row.get('doesage Form', '')),
            "dosage_form_ar": safe_str(row.get('شكل الجرعة', '')),
            "legal_status": safe_str(row.get('legal Status', '')),
            "legal_status_ar": safe_str(row.get('الوضع القانوني', '')),
            "manufacturer": safe_str(row.get('manufacturer Name', '')),
            "manufacturer_ar": safe_str(row.get('اسم الشركة المصنعة', '')),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        medications.append(medication)
        
        # Insert in batches of 1000
        if len(medications) >= 1000:
            await db.medications.insert_many(medications)
            print(f"✅ Inserted {len(medications)} medications (total: {idx + 1})")
            medications = []
    
    # Insert remaining medications
    if medications:
        await db.medications.insert_many(medications)
        print(f"✅ Inserted {len(medications)} medications")
    
    # Create indexes for search
    print("📇 Creating indexes for search optimization...")
    await db.medications.create_index([("commercial_name_en", "text"), ("commercial_name_ar", "text"), ("scientific_name", "text")])
    print("✅ Indexes created")
    
    # Verify count
    total_count = await db.medications.count_documents({})
    print(f"\n🎉 Import complete! Total medications in database: {total_count}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(import_medications())
