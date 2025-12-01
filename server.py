from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Depends, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import base64
import hashlib
import random
import re

# OpenAI for AI features
from openai import AsyncOpenAI
import bcrypt
import jwt
from PIL import Image
import io
import asyncio

# Import Firebase for push notifications
try:
    from firebase_config import send_push_notification
    FIREBASE_ENABLED = True
except Exception as e:
    print(f"⚠️ Firebase not available: {e}")
    FIREBASE_ENABLED = False

# Import Medication Scheduler
try:
    from medication_scheduler import start_scheduler, stop_scheduler
    SCHEDULER_ENABLED = True
except Exception as e:
    print(f"⚠️ Medication scheduler not available: {e}")
    SCHEDULER_ENABLED = False

# Import AI Drug Info
try:
    from ai_drug_info import AIDrugInfo
    from multi_source_dosage import dosage_service
    AI_DRUG_INFO_ENABLED = True
    ai_drug_info = AIDrugInfo()
except Exception as e:
    print(f"⚠️ AI Drug Info not available: {e}")
    AI_DRUG_INFO_ENABLED = False


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=False)  # Kubernetes env vars take precedence

# Import Email Service (AFTER load_dotenv)
try:
    from email_service import email_service
    EMAIL_ENABLED = True
    print(f"✅ Email service loaded. Configured: {email_service.is_configured()}")
except Exception as e:
    print(f"⚠️ Email service not available: {e}")
    EMAIL_ENABLED = False
    email_service = None

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'pharmapal_db')]

# JWT Secret - must be set in production
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    # Development fallback only
    JWT_SECRET = 'pharmapal-secret-key-change-in-production'
    print("⚠️ WARNING: Using default JWT_SECRET! Set JWT_SECRET environment variable for production.")
JWT_ALGORITHM = "HS256"

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer()

# Initialize mock SFDA database on startup
async def init_sfda_database():
    count = await db.medications.count_documents({})
    if count == 0:
        medications = [
            {
                "id": str(uuid.uuid4()),
                "commercial_name_en": "Panadol Extra",
                "commercial_name_ar": "بانادول إكسترا",
                "scientific_name": "Paracetamol + Caffeine",
                "dosage_strength": "500mg/65mg",
                "dosage_form": "Tablet",
                "dosage_form_ar": "قرص",
                "sfda_code": "SFDA-001-2024",
                "manufacturer": "GSK",
                "indications": "Pain relief, headache, fever",
                "indications_ar": "تخفيف الألم، صداع، حمى",
                "contraindications": "Liver disease, alcohol abuse",
                "side_effects": "Nausea, allergic reactions",
                "interactions": ["Warfarin", "Isoniazid"],
                "max_daily_dose": "8 tablets"
            },
            {
                "id": str(uuid.uuid4()),
                "commercial_name_en": "Ventolin Inhaler",
                "commercial_name_ar": "فنتولين بخاخ",
                "scientific_name": "Salbutamol",
                "dosage_strength": "100mcg",
                "dosage_form": "Inhaler",
                "dosage_form_ar": "بخاخ",
                "sfda_code": "SFDA-002-2024",
                "manufacturer": "GSK",
                "indications": "Asthma, bronchospasm",
                "indications_ar": "الربو، تشنج القصبات",
                "contraindications": "Hypersensitivity to salbutamol",
                "side_effects": "Tremor, headache, palpitations",
                "interactions": ["Beta-blockers", "Digoxin"],
                "max_daily_dose": "8 puffs"
            },
            {
                "id": str(uuid.uuid4()),
                "commercial_name_en": "Augmentin",
                "commercial_name_ar": "أوجمنتين",
                "scientific_name": "Amoxicillin + Clavulanic Acid",
                "dosage_strength": "625mg",
                "dosage_form": "Tablet",
                "dosage_form_ar": "قرص",
                "sfda_code": "SFDA-003-2024",
                "manufacturer": "GSK",
                "indications": "Bacterial infections",
                "indications_ar": "عدوى بكتيرية",
                "contraindications": "Penicillin allergy, liver dysfunction",
                "side_effects": "Diarrhea, nausea, rash",
                "interactions": ["Methotrexate", "Warfarin", "Oral contraceptives"],
                "max_daily_dose": "3 tablets"
            },
            {
                "id": str(uuid.uuid4()),
                "commercial_name_en": "Polydexa with Phenylephrine",
                "commercial_name_ar": "بوليديكسا مع فينيليفرين",
                "scientific_name": "Dexamethasone + Neomycin + Polymyxin B + Phenylephrine",
                "dosage_strength": "1mg/5mg/10000IU/2.5mg per mL",
                "dosage_form": "Nasal Spray",
                "dosage_form_ar": "بخاخ أنفي",
                "sfda_code": "SFDA-004-2024",
                "manufacturer": "Laboratoires Bouchara-Recordati",
                "indications": "Rhinitis, sinusitis, rhinopharyngitis",
                "indications_ar": "التهاب الأنف، التهاب الجيوب الأنفية",
                "contraindications": "Glaucoma, viral infections",
                "side_effects": "Nasal dryness, nosebleeds",
                "interactions": ["MAO inhibitors", "Other corticosteroids"],
                "max_daily_dose": "5 sprays per nostril"
            },
            {
                "id": str(uuid.uuid4()),
                "commercial_name_en": "Sinusephrin Nasal Spray",
                "commercial_name_ar": "سينوسيفرين بخاخ أنفي",
                "scientific_name": "Xylometazoline",
                "dosage_strength": "0.1%",
                "dosage_form": "Nasal Spray",
                "dosage_form_ar": "بخاخ أنفي",
                "sfda_code": "SFDA-005-2024",
                "manufacturer": "Various",
                "indications": "Nasal congestion, common cold",
                "indications_ar": "احتقان الأنف، نزلات البرد",
                "contraindications": "Angle-closure glaucoma, cardiovascular disease",
                "side_effects": "Rebound congestion, burning sensation",
                "interactions": ["MAO inhibitors", "Tricyclic antidepressants"],
                "max_daily_dose": "3 applications per nostril"
            }
        ]
        await db.medications.insert_many(medications)
        logging.info("SFDA mock database initialized")


# Define Models
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    full_name: str
    phone: str  # Mobile phone number (required, Saudi format: 05xxxxxxxx)
    phone_verified: bool = False  # Phone verification status
    is_professional: bool = False
    is_premium: bool = False
    is_admin: bool = False  # Admin flag
    language: str = "en"
    medical_conditions: List[str] = []
    allergies: List[str] = []
    daily_routine: Optional[dict] = None
    sfda_searches_used: int = 0  # Track SFDA searches for free users (max 3)
    medications_added_count: int = 0  # Track total medications added (never decreases)
    subscription_tier: str = "trial"  # trial, weekly, monthly, yearly
    subscription_start_date: Optional[str] = None
    subscription_end_date: Optional[str] = None
    trial_used: bool = False  # Track if user has used their 48h trial
    account_deleted: bool = False  # Track if account was deleted (for phone reuse prevention)
    last_login: Optional[str] = None  # Track last login time
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class UserRegister(BaseModel):
    password: str
    full_name: str
    phone: str  # Mobile phone number (required, Saudi format: 05xxxxxxxx)
    is_professional: bool = False
    language: str = "en"

class UserLogin(BaseModel):
    phone: str  # Login with phone number instead of email
    password: str

class Medication(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    commercial_name_en: str
    commercial_name_ar: str
    scientific_name: str
    dosage_strength: str
    dosage_form: str
    dosage_form_ar: str
    sfda_code: str
    manufacturer: str
    indications: str
    indications_ar: str
    contraindications: str
    side_effects: str
    interactions: List[str]
    max_daily_dose: str

class MedicationRecognitionResponse(BaseModel):
    medication_info: Optional[dict]
    ai_analysis: str
    confidence: str
    warnings: List[str] = []
    auto_add_data: Optional[dict] = None

class UserMedication(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    medication_id: str
    brand_name: Optional[str] = None  # Trade/commercial name of the medication (optional for backward compatibility)
    active_ingredient: Optional[str] = None  # Generic/scientific name (CRITICAL for interaction checks)
    condition: str
    prescribed_dosage: str
    frequency: str
    times: List[str]
    start_date: str
    end_date: Optional[str] = None
    active: bool = True
    archived: bool = False
    notes: Optional[str] = None
    classification: Optional[str] = None  # Medical classification (e.g., Antibiotic, NSAID, Diuretic)
    timing_note: Optional[str] = None  # Medical timing guidance (e.g., "Take with food", "Best taken in morning")
    manufacturer: Optional[str] = None  # Manufacturer from SFDA
    pack: Optional[str] = None  # Pack/dosage form from SFDA
    dosage_form: Optional[str] = None  # Dosage form (Tablet, Capsule, Syrup, Inhaler, etc.)
    price_sar: Optional[float] = None  # Official SFDA price
    scientific_name: Optional[str] = None  # Scientific name from SFDA
    strength: Optional[str] = None  # Strength from SFDA
    strength_unit: Optional[str] = None  # Strength unit from SFDA
    package_size: Optional[int] = None  # Package size from SFDA
    trade_name_ar: Optional[str] = None  # Arabic trade/brand name from SFDA
    scientific_name_ar: Optional[str] = None  # Arabic scientific name from SFDA
    manufacturer_ar: Optional[str] = None  # Arabic manufacturer name from SFDA
    dosage_form_ar: Optional[str] = None  # Arabic dosage form from SFDA
    pack_ar: Optional[str] = None  # Arabic pack description from SFDA
    strength_ar: Optional[str] = None  # Arabic strength from SFDA
    strength_unit_ar: Optional[str] = None  # Arabic strength unit from SFDA
    administration_route: Optional[str] = None  # Administration route from SFDA
    administration_route_ar: Optional[str] = None  # Arabic administration route from SFDA
    storage_conditions: Optional[str] = None  # Storage conditions from SFDA
    storage_conditions_ar: Optional[str] = None  # Arabic storage conditions from SFDA
    legal_status: Optional[str] = None  # Legal status from SFDA
    legal_status_ar: Optional[str] = None  # Arabic legal status from SFDA
    courseAnalysis: Optional[dict] = None  # Course duration analysis from FDA API
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_dosage_confirmed: Optional[bool] = None  # User has confirmed manual dosage input
    user_dosage_info: Optional[dict] = None  # User's manual dosage info (duration_days, amount_per_time, times_per_day)

class UserMedicationCreate(BaseModel):
    medication_id: str
    brand_name: Optional[str] = None  # Trade/commercial name of the medication (optional for backward compatibility)
    active_ingredient: Optional[str] = None  # Generic/scientific name (CRITICAL for interaction checks)
    condition: str
    prescribed_dosage: str
    frequency: str
    times: List[str]
    start_date: str
    end_date: Optional[str] = None
    notes: Optional[str] = None
    classification: Optional[str] = None  # Medical classification (e.g., Antibiotic, NSAID, Diuretic)
    timing_note: Optional[str] = None  # Medical timing guidance (e.g., "Take with food", "Best taken in morning")
    manufacturer: Optional[str] = None  # Manufacturer from SFDA
    pack: Optional[str] = None  # Pack/dosage form from SFDA
    dosage_form: Optional[str] = None  # Dosage form (Tablet, Capsule, Syrup, Inhaler, etc.)
    price_sar: Optional[float] = None  # Official SFDA price
    scientific_name: Optional[str] = None  # Scientific name from SFDA
    strength: Optional[str] = None  # Strength from SFDA
    strength_unit: Optional[str] = None  # Strength unit from SFDA
    package_size: Optional[int] = None  # Package size from SFDA
    trade_name_ar: Optional[str] = None  # Arabic trade/brand name from SFDA
    scientific_name_ar: Optional[str] = None  # Arabic scientific name from SFDA
    manufacturer_ar: Optional[str] = None  # Arabic manufacturer name from SFDA
    dosage_form_ar: Optional[str] = None  # Arabic dosage form from SFDA
    pack_ar: Optional[str] = None  # Arabic pack description from SFDA
    strength_ar: Optional[str] = None  # Arabic strength from SFDA
    strength_unit_ar: Optional[str] = None  # Arabic strength unit from SFDA
    administration_route: Optional[str] = None  # Administration route from SFDA
    administration_route_ar: Optional[str] = None  # Arabic administration route from SFDA
    storage_conditions: Optional[str] = None  # Storage conditions from SFDA
    storage_conditions_ar: Optional[str] = None  # Arabic storage conditions from SFDA
    legal_status: Optional[str] = None  # Legal status from SFDA
    legal_status_ar: Optional[str] = None  # Arabic legal status from SFDA
    courseAnalysis: Optional[dict] = None  # Course duration analysis from FDA API

class HealthData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    date: str
    heart_rate: Optional[int] = None
    sleep_hours: Optional[float] = None
    steps: Optional[int] = None
    activity_level: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ProfileHealthData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    date: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ProfileHealthDataCreate(BaseModel):
    age: Optional[int] = None
    weight: Optional[float] = None
    height: Optional[float] = None

# Medication Reminder Models
class MedicationReminder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    medication_id: str
    medication_name: str
    reminder_times: List[str]  # List of times like ["08:00", "14:00", "20:00"]
    enabled: bool = True
    last_taken: Optional[str] = None  # ISO timestamp of last taken dose
    adherence_log: List[dict] = Field(default_factory=list)  # [{date, time, taken: bool}]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MedicationReminderCreate(BaseModel):
    medication_id: str
    medication_name: str
    reminder_times: List[str]

class MedicationReminderUpdate(BaseModel):
    reminder_times: Optional[List[str]] = None
    enabled: Optional[bool] = None

class DoseTaken(BaseModel):
    reminder_id: str
    taken_time: str  # ISO timestamp

# FCM Token Models
class FCMTokenCreate(BaseModel):
    token: str
    device_type: Optional[str] = None  # "web", "android", "ios"

class FCMToken(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    token: str
    device_type: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TestNotificationRequest(BaseModel):
    title: str
    body: str

class Notification(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    body: str
    type: str = "info"  # info, reminder, warning, success
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: Optional[dict] = None  # Additional data (e.g., medication_id, reminder_id)

class NotificationMarkRead(BaseModel):
    notification_ids: List[str]

# Medication Timing Rules by Classification
MEDICATION_TIMING_RULES = {
    "Diuretic": {
        "timing_type": "fixed",  # وقت ثابت
        "default_times": ["08:00"],
        "note": "Best taken in morning to avoid nighttime urination",
        "note_ar": "يفضل تناوله صباحاً لتجنب التبول الليلي"
    },
    "Antihypertensive": {
        "timing_type": "flexible",  # أي وقت ثابت يومياً
        "default_times": [],
        "note": "Take at the same time each day",
        "note_ar": "تناول في نفس الوقت يومياً"
    },
    "Statin": {
        "timing_type": "fixed",  # وقت ثابت
        "default_times": ["20:00"],
        "note": "Evening dosing recommended for short-acting statins",
        "note_ar": "يفضل تناوله مساءً"
    },
    "Corticosteroid": {
        "timing_type": "fixed",  # وقت ثابت
        "default_times": ["08:00"],
        "note": "Morning dosing mimics natural cortisol rhythm",
        "note_ar": "يفضل تناوله صباحاً لمحاكاة إيقاع الكورتيزول الطبيعي"
    },
    "Thyroid": {
        "timing_type": "flexible",  # مرتبط بالوجبة
        "default_times": [],
        "note": "Take on empty stomach, 30-60 minutes before breakfast",
        "note_ar": "تناول على معدة فارغة، قبل الإفطار بـ 30-60 دقيقة"
    },
    "Antibiotic": {
        "timing_type": "frequency_based",  # يعتمد على التكرار
        "Once daily": ["08:00"],
        "Twice daily": ["08:00", "20:00"],
        "Three times daily": ["08:00", "14:00", "20:00"],
        "Four times daily": ["08:00", "12:00", "16:00", "20:00"]
    },
    "NSAID": {
        "timing_type": "flexible",  # مع الطعام
        "default_times": [],
        "note": "Take with food to protect stomach",
        "note_ar": "تناول مع الطعام لحماية المعدة"
    },
    "Antidepressant": {
        "timing_type": "fixed",
        "SSRI": ["08:00"],
        "Sedating": ["20:00"]
    },
    "PPI": {
        "timing_type": "flexible",  # مرتبط بالوجبة
        "default_times": [],
        "note": "Take 30-60 minutes before first meal of the day",
        "note_ar": "تناول قبل الوجبة الأولى بـ 30-60 دقيقة"
    },
    "Bisphosphonate": {
        "timing_type": "flexible",  # مرتبط بالوجبة
        "default_times": [],
        "note": "Take on empty stomach first thing in morning, 30-60 minutes before food. Remain upright.",
        "note_ar": "تناول على معدة فارغة صباحاً، قبل الطعام بـ 30-60 دقيقة. ابقَ في وضع مستقيم"
    },
    "Insulin": {
        "timing_type": "flexible",
        "default_times": [],
        "note": "Timing must match meals - consult with healthcare provider",
        "note_ar": "يجب أن يتوافق التوقيت مع الوجبات - استشر طبيبك"
    },
    "Anticoagulant": {
        "timing_type": "fixed",
        "default_times": ["20:00"],
        "note": "Evening dosing allows for next-day monitoring",
        "note_ar": "يفضل تناوله مساءً لتسهيل المتابعة في اليوم التالي"
    }
}

def get_suggested_times(classification: str, frequency: str = None, language: str = "en") -> tuple:
    """
    Get suggested medication times based on classification and frequency.
    Priority: Classification FIRST, then frequency.
    Returns: (suggested_times, note)
    
    timing_type options:
    - "fixed": وقت محدد ثابت (مثل: 08:00)
    - "flexible": مرن - بدون وقت محدد (مثل: قبل الطعام)
    - "frequency_based": يعتمد على التكرار (مثل: المضادات الحيوية)
    """
    # Default fallback - single dose
    default_times = ["08:00"]
    default_note = "Take once daily at consistent time"
    default_note_ar = "تناول مرة واحدة يومياً في وقت ثابت"
    
    # PRIORITY 1: Classification-based timing (most important!)
    if classification:
        # Normalize classification
        classification_normalized = classification.strip().title()
        
        # Check if classification exists in rules
        if classification_normalized in MEDICATION_TIMING_RULES:
            rules = MEDICATION_TIMING_RULES[classification_normalized]
            timing_type = rules.get("timing_type", "fixed")
            
            # Special case: Antibiotics - frequency matters for this class
            if timing_type == "frequency_based" and classification_normalized == "Antibiotic" and frequency:
                freq_lower = frequency.lower()
                # Try to parse frequency
                if "once" in freq_lower or ("1" in frequency and "time" in freq_lower):
                    return (rules.get("Once daily", ["08:00"]), "Take once daily at consistent time")
                elif "twice" in freq_lower or ("2" in frequency and "time" in freq_lower) or "مرتين" in freq_lower:
                    return (rules.get("Twice daily", ["08:00", "20:00"]), "Space doses evenly throughout the day")
                elif "three" in freq_lower or ("3" in frequency and "time" in freq_lower) or "ثلاث" in freq_lower:
                    return (rules.get("Three times daily", ["08:00", "14:00", "20:00"]), "Space doses evenly throughout the day")
                elif "four" in freq_lower or ("4" in frequency and "time" in freq_lower) or "أربع" in freq_lower:
                    return (rules.get("Four times daily", ["08:00", "12:00", "16:00", "20:00"]), "Space doses evenly throughout the day")
                # Default for antibiotics if frequency unclear
                return (rules.get("Once daily", ["08:00"]), "Space doses evenly throughout the day")
            
            # Flexible timing: no specific times, only instructions
            if timing_type == "flexible":
                note = rules.get("note_ar", rules.get("note", "")) if language == "ar" else rules.get("note", "")
                return ([], note)  # Empty times array = no specific times
            
            # Fixed timing: specific times provided
            if timing_type == "fixed" and "default_times" in rules:
                note = rules.get("note_ar", rules.get("note", default_note)) if language == "ar" else rules.get("note", default_note)
                return (rules["default_times"], note)
    
    # PRIORITY 2: If no classification match, use frequency only
    if frequency:
        freq_lower = frequency.lower()
        # Only match explicit frequency indicators
        if "twice" in freq_lower or ("2" in frequency and "time" in freq_lower) or "مرتين" in freq_lower:
            return (["08:00", "20:00"], "Take twice daily, approximately 12 hours apart")
        elif "three" in freq_lower or ("3" in frequency and "time" in freq_lower) or "ثلاث" in freq_lower:
            return (["08:00", "14:00", "20:00"], "Take three times daily, space evenly")
        elif "four" in freq_lower or ("4" in frequency and "time" in freq_lower) or "أربع" in freq_lower:
            return (["08:00", "12:00", "16:00", "20:00"], "Take four times daily, space evenly")
    
    # PRIORITY 3: Default fallback (once daily)
    note = default_note_ar if language == "ar" else default_note
    return (default_times, note)


# Helper functions
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=30)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get current user from JWT token"""
    token = credentials.credentials
    payload = verify_jwt_token(token)
    user_id = payload.get("user_id")
    
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Fetch user from database
    user = await db.users.find_one({"id": user_id}, {"password_hash": 0, "_id": 0})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

async def create_notification(user_id: str, title: str, body: str, notification_type: str = "info", data: dict = None):
    """Helper function to create a notification"""
    try:
        notification = Notification(
            user_id=user_id,
            title=title,
            body=body,
            type=notification_type,
            data=data
        )
        
        await db.notifications.insert_one(notification.model_dump())
        logger.info(f"Created notification for user {user_id}: {title}")
        return notification
    except Exception as e:
        logger.error(f"Error creating notification: {e}")
        return None

# Admin-only dependency
async def get_admin_user(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def validate_saudi_phone(phone: str) -> str:
    """Validate and normalize Saudi phone number (05xxxxxxxx format only)"""
    # Remove spaces and special characters except digits
    phone = re.sub(r'[^\d]', '', phone)
    
    # Check if it starts with 05
    if phone.startswith('05'):
        # Valid format
        pass
    elif phone.startswith('5') and len(phone) == 9:
        # Add leading 0
        phone = '0' + phone
    else:
        raise HTTPException(
            status_code=400, 
            detail="رقم الجوال يجب أن يبدأ بـ 05 متبوعاً بـ 8 أرقام / Phone number must start with 05 followed by 8 digits"
        )
    
    # Validate length (should be 10 digits: 05xxxxxxxx)
    if len(phone) != 10:
        raise HTTPException(
            status_code=400, 
            detail="رقم الجوال يجب أن يكون 10 أرقام (05xxxxxxxx) / Phone number must be 10 digits (05xxxxxxxx)"
        )
    
    return phone

# Auth Routes
@api_router.post("/auth/register")
async def register(user_data: UserRegister):
    # Validate and normalize phone
    phone = validate_saudi_phone(user_data.phone)
    
    # Check if phone already registered (including deleted accounts)
    existing_phone = await db.users.find_one({"phone": phone})
    if existing_phone:
        # Check if this phone was used in a deleted account that had trial
        if existing_phone.get("account_deleted") and existing_phone.get("trial_used"):
            raise HTTPException(status_code=400, detail="رقم الجوال مستخدم سابقاً. يرجى استخدام رقم آخر / Phone number was used before. Please use a different number")
        raise HTTPException(status_code=400, detail="رقم الجوال مسجل مسبقاً / Phone number already registered")
    
    # Create user with 48h trial
    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(hours=48)
    
    user_dict = user_data.model_dump()
    user_dict["phone"] = phone  # Use normalized phone
    user_dict["phone_verified"] = True  # Mark phone as verified by default
    user_dict["subscription_tier"] = "trial"
    user_dict["subscription_start_date"] = now.isoformat()
    user_dict["subscription_end_date"] = trial_end.isoformat()
    user_dict["trial_used"] = False  # Will be set to True when trial ends
    user_dict["account_deleted"] = False
    
    hashed_pw = hash_password(user_dict.pop("password"))
    user_dict["password_hash"] = hashed_pw
    user_obj = User(**{k: v for k, v in user_dict.items() if k != "password_hash"})
    
    doc = user_obj.model_dump()
    doc["password_hash"] = hashed_pw
    
    await db.users.insert_one(doc)
    
    token = create_jwt_token(user_obj.id, user_obj.phone)
    return {"token": token, "user": user_obj}

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    # Validate and normalize phone
    phone = validate_saudi_phone(credentials.phone)
    
    user = await db.users.find_one({"phone": phone})
    # Support both 'password' and 'password_hash' field names
    password_field = user.get("password_hash") or user.get("password") if user else None
    if not user or not password_field or not verify_password(credentials.password, password_field):
        raise HTTPException(status_code=401, detail="رقم الجوال أو كلمة المرور غير صحيحة / Invalid phone or password")
    
    # Update last login time
    await db.users.update_one(
        {"phone": phone},
        {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}}
    )
    
    token = create_jwt_token(user["id"], user["phone"])
    user["last_login"] = datetime.now(timezone.utc).isoformat()
    user.pop("password_hash", None)
    user.pop("password", None)  # Remove password field if exists
    user.pop("_id", None)
    return {"token": token, "user": user}


# Medication Routes
@api_router.get("/medications", response_model=List[Medication])
async def get_medications(search: Optional[str] = None):
    query = {}
    if search:
        query = {
            "$or": [
                {"commercial_name_en": {"$regex": search, "$options": "i"}},
                {"commercial_name_ar": {"$regex": search, "$options": "i"}},
                {"scientific_name": {"$regex": search, "$options": "i"}}
            ]
        }
    medications = await db.medications.find(query, {"_id": 0}).to_list(100)
    return medications

# Search SFDA Medications Route
@api_router.get("/medications/{medication_id}", response_model=Medication)
async def get_medication(medication_id: str):
    medication = await db.medications.find_one({"id": medication_id}, {"_id": 0})
    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found")
    return medication


# Medication Recognition Route
@api_router.post("/medications/recognize")
async def recognize_medication(
    image: UploadFile = File(...),
    language: str = Form("en"),
    current_user: dict = Depends(get_current_user)
):
    """Recognize medication from image using OpenAI GPT-4o Vision"""
    try:
        # Check medication limit BEFORE processing
        user_id = current_user["id"]
        is_premium = current_user.get("is_premium", False)
        
        can_add = await check_medication_limit(user_id, is_premium)
        if not can_add:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "medication_limit_reached",
                    "message": "You have exhausted your 3 attempts to add medications. Upgrade to Premium for unlimited medications.",
                    "limit": FREE_USER_LIMITS["max_medications"]
                }
            )
        
        # Read and process image
        image_data = await image.read()
        if not image_data:
            raise HTTPException(status_code=400, detail="No image provided")
        
        # Optimize image
        img = Image.open(io.BytesIO(image_data))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        max_size = (2048, 2048)
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=95)
        image_bytes = buffer.getvalue()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Get OpenAI API key
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        # Initialize OpenAI client
        client = AsyncOpenAI(api_key=api_key)
        
        # Prompt
        prompt = """Extract medication information from this image.

Find:
- Medication name (brand/trade name)
- Active ingredient (generic name)
- Dosage/Strength (e.g. 500mg)
- Dosage form (tablet/capsule/syrup/injection)
- Package size/count (e.g. 20, 30, 100 - the NUMBER of tablets/capsules in the box)
- Drug classification (e.g. Antibiotic, NSAID, Diuretic, Statin, Thyroid, Corticosteroid, Antihypertensive, PPI, etc.)

Return JSON only:
{
  "medication_name": "name",
  "active_ingredient": "ingredient",
  "dosage_strength": "500mg",
  "dosage_form": "tablet",
  "package_size": 20,
  "recommended_frequency": "as directed",
  "classification": "drug class"
}

If you can read the medication name, return it. Package size should be a number. Classification is optional but helpful. Be flexible."""
        
        # Call OpenAI Vision API
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a pharmaceutical expert. Extract medication information from images accurately."
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=500,
                    temperature=0.3
                ),
                timeout=30.0
            )
            
            ai_response = response.choices[0].message.content
            
        except asyncio.TimeoutError:
            logging.error("AI recognition timeout")
            raise HTTPException(status_code=408, detail="AI analysis timed out. Please try again.")
        except Exception as e:
            logging.error(f"OpenAI API error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")
        
        # Parse JSON from response
        result = {}
        try:
            json_start = ai_response.find('{')
            json_end = ai_response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = ai_response[json_start:json_end]
                result = json.loads(json_str)
                logging.info(f"Successfully parsed: {result}")
            else:
                logging.error(f"No JSON found in response: {ai_response[:200]}")
                result = {"medication_name": None}
        except Exception as parse_error:
            logging.error(f"JSON parse error: {str(parse_error)}, Response: {ai_response[:200]}")
            result = {"medication_name": None}
        
        # Prepare auto-add data
        auto_add_data = None
        success = False
        timing_note = None
        
        if result.get("medication_name"):
            classification = result.get("classification")
            frequency = result.get("recommended_frequency", "As directed")
            
            # Get suggested times
            suggested_times, timing_note = get_suggested_times(classification, frequency, language)
            
            auto_add_data = {
                "medication_name": result["medication_name"],
                "active_ingredient": result.get("active_ingredient", ""),
                "dosage_strength": result.get("dosage_strength", "As directed"),
                "dosage_form": result.get("dosage_form", ""),
                "package_size": result.get("package_size"),
                "recommended_frequency": frequency,
                "best_times": suggested_times,
                "classification": classification
            }
            success = True
        else:
            logging.warning("No medication name found in recognition")
        
        return {
            "success": success,
            "auto_add_data": auto_add_data,
            "timing_note": timing_note
        }
        
    except Exception as e:
        logging.error(f"Error recognizing medication: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Recognition failed: {str(e)}")


# User Medications Routes
@api_router.post("/user-medications")
async def add_user_medication(
    medication_data: UserMedicationCreate,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    is_premium = current_user.get("is_premium", False)
    
    # Check medication limit for free users
    can_add = await check_medication_limit(user_id, is_premium)
    if not can_add:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "medication_limit_reached",
                "message": "Free users can only add up to 3 medications. Upgrade to Premium for unlimited medications.",
                "limit": FREE_USER_LIMITS["max_medications"]
            }
        )
    
    med_dict = medication_data.model_dump()
    med_dict["user_id"] = user_id
    
    # Backward compatibility: If brand_name is not provided, use condition as brand_name
    if not med_dict.get("brand_name"):
        med_dict["brand_name"] = med_dict.get("condition", "Unknown")
    
    user_med = UserMedication(**med_dict)
    
    doc = user_med.model_dump()
    await db.user_medications.insert_one(doc)
    
    # Auto-create reminders if user_dosage_confirmed is True
    if med_dict.get('user_dosage_confirmed') is True and med_dict.get('times'):
        reminder_times = med_dict['times']
        medication_id = doc['id']
        medication_name = doc.get('brand_name') or doc.get('trade_name') or doc.get('condition') or 'Medication'
        
        # Create reminder
        new_reminder = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "medication_id": medication_id,
            "medication_name": medication_name,
            "reminder_times": reminder_times,
            "enabled": True,
            "adherence_log": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.medication_reminders.insert_one(new_reminder)
        logger.info(f"✅ Created reminders for new medication {medication_id}: {reminder_times}")
    
    # Increment medications_added_count for free users (permanent counter)
    if not is_premium:
        await db.users.update_one(
            {"id": user_id},
            {"$inc": {"medications_added_count": 1}}
        )
    
    return user_med

# Add Medication from Search Route
@api_router.get("/user-medications", response_model=List[UserMedication])
async def get_user_medications(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    
    medications = await db.user_medications.find(
        {"user_id": user_id, "active": True},
        {"_id": 0}
    ).to_list(None)  # No limit - support infinite medications
    
    # Enrich medications with price from SFDA database
    for med in medications:
        brand_name = med.get('brand_name', '').strip()
        if brand_name:
            # Try to find price in SFDA database by brand name (using regex for partial match)
            regex_pattern = f"^{re.escape(brand_name)}"
            sfda_med = await db.sfda_medications.find_one(
                {"trade_name_lower": {"$regex": regex_pattern, "$options": "i"}},
                {"_id": 0, "price_sar": 1}
            )
            if sfda_med and sfda_med.get('price_sar'):
                med['price_sar'] = sfda_med['price_sar']
    
    return medications

@api_router.delete("/user-medications/{medication_id}")
async def delete_user_medication(medication_id: str, current_user: dict = Depends(get_current_user)):
    """Delete medication and all its associated reminders"""
    user_id = current_user["id"]
    
    # Delete the medication - search by both id and medication_id
    med_result = await db.user_medications.delete_one({
        "$or": [
            {"id": medication_id, "user_id": user_id},
            {"medication_id": medication_id, "user_id": user_id}
        ]
    })
    
    # Delete all reminders associated with this medication
    reminders_result = await db.medication_reminders.delete_many({
        "user_id": user_id,
        "medication_id": medication_id
    })
    
    return {
        "message": "Medication and associated reminders deleted",
        "medication_deleted": med_result.deleted_count > 0,
        "reminders_deleted": reminders_result.deleted_count
    }

@api_router.patch("/user-medications/{medication_id}/archive")
async def archive_user_medication(medication_id: str, current_user: dict = Depends(get_current_user)):
    await db.user_medications.update_one(
        {"id": medication_id},
        {"$set": {"active": False, "archived": True}}
    )
    return {"message": "Medication archived"}

@api_router.patch("/user-medications/{medication_id}/unarchive")
async def unarchive_user_medication(medication_id: str, current_user: dict = Depends(get_current_user)):
    await db.user_medications.update_one(
        {"id": medication_id},
        {"$set": {"active": True, "archived": False}}
    )
    return {"message": "Medication restored"}

@api_router.get("/user-medications/archived", response_model=List[UserMedication])


@api_router.put("/user-medications/{medication_id}")
async def update_medication(
    medication_id: str,
    updates: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Update medication fields (e.g., courseAnalysis, user_dosage_confirmed)
    Auto-creates reminders when user confirms dosage
    """
    try:
        # Get the medication first to check brand_name
        medication = await db.user_medications.find_one(
            {"medication_id": medication_id, "user_id": current_user["id"]},
            {"_id": 0}
        )
        
        if not medication:
            raise HTTPException(status_code=404, detail="Medication not found")
        
        # Update the medication
        result = await db.user_medications.update_one(
            {"medication_id": medication_id, "user_id": current_user["id"]},
            {"$set": updates}
        )
        
        # If user_dosage_confirmed is being set to True, auto-create/update reminders
        if updates.get('user_dosage_confirmed') is True:
            # Use the actual times from the medication, or from user_dosage_info
            reminder_times = []
            
            # First priority: use 'times' field from updates
            if updates.get('times') and len(updates.get('times')) > 0:
                reminder_times = updates['times']
            # Second priority: use existing medication times
            elif medication.get('times') and len(medication.get('times')) > 0:
                reminder_times = medication['times']
            # Fallback: calculate from times_per_day if provided
            elif updates.get('user_dosage_info'):
                user_dosage_info = updates.get('user_dosage_info')
                times_per_day = int(user_dosage_info.get('times_per_day', 1))
                
                # Calculate reminder times based on times_per_day
                if times_per_day == 1:
                    reminder_times = ['09:00']
                elif times_per_day == 2:
                    reminder_times = ['09:00', '21:00']
                elif times_per_day == 3:
                    reminder_times = ['08:00', '14:00', '20:00']
                elif times_per_day == 4:
                    reminder_times = ['08:00', '12:00', '17:00', '21:00']
                else:
                    # For more than 4 times, distribute evenly
                    interval = 24 // times_per_day
                    for i in range(times_per_day):
                        hour = (8 + (i * interval)) % 24
                        reminder_times.append(f"{hour:02d}:00")
            
            # Only create/update reminder if we have valid times
            if reminder_times and len(reminder_times) > 0:
                # Check if reminder already exists
                existing_reminder = await db.medication_reminders.find_one(
                    {"medication_id": medication_id, "user_id": current_user["id"]},
                    {"_id": 0}
                )
                
                medication_name = medication.get('brand_name') or medication.get('trade_name') or medication.get('condition') or 'Medication'
                
                if existing_reminder:
                    # Update existing reminder
                    await db.medication_reminders.update_one(
                        {"medication_id": medication_id, "user_id": current_user["id"]},
                        {"$set": {
                            "reminder_times": reminder_times,
                            "enabled": True,
                            "medication_name": medication_name
                        }}
                    )
                    logger.info(f"Updated reminders for medication {medication_id}: {reminder_times}")
                else:
                    # Create new reminder
                    new_reminder = {
                        "id": str(uuid.uuid4()),
                        "user_id": current_user["id"],
                        "medication_id": medication_id,
                        "medication_name": medication_name,
                        "reminder_times": reminder_times,
                        "enabled": True,
                        "adherence_log": [],
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db.medication_reminders.insert_one(new_reminder)
                    logger.info(f"Created reminders for medication {medication_id}: {reminder_times}")
        
        return {"success": True, "message": "Medication updated successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating medication: {str(e)}")

async def get_archived_medications(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    
    medications = await db.user_medications.find(
        {"user_id": user_id, "archived": True},
        {"_id": 0}
    ).to_list(None)  # No limit - support infinite archived medications
    
    return medications



# Accept Terms and Conditions
@api_router.post("/accept-terms")
async def accept_terms(current_user: dict = Depends(get_current_user)):
    """Update user to mark that they have accepted terms"""
    try:
        user_id = current_user["id"]
        
        # Update user document
        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "has_accepted_terms": True,
                "terms_accepted_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"User {user_id} accepted terms and conditions")
        
        return {"success": True, "message": "Terms accepted successfully"}
    except Exception as e:
        logger.error(f"Error accepting terms: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Drug Interaction Checker
@api_router.post("/check-interactions")
async def check_interactions(medication_ids: List[str]):
    medications = await db.medications.find(
        {"id": {"$in": medication_ids}},
        {"_id": 0}
    ).to_list(100)
    
    interactions = []
    for i, med1 in enumerate(medications):
        for med2 in medications[i+1:]:
            # Check if any interactions exist
            med1_interactions = set(med1.get("interactions", []))
            if med2["scientific_name"] in med1_interactions or med2["commercial_name_en"] in med1_interactions:
                interactions.append({
                    "medication1": med1["commercial_name_en"],
                    "medication2": med2["commercial_name_en"],
                    "severity": "moderate",
                    "description": f"Potential interaction between {med1['scientific_name']} and {med2['scientific_name']}"
                })
    
    return {"interactions": interactions}


# Health Data Routes (Mock Wearable)
@api_router.post("/health-data")
async def add_health_data(
    heart_rate: Optional[int] = None,
    sleep_hours: Optional[float] = None,
    steps: Optional[int] = None,
    activity_level: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    
    data = HealthData(
        user_id=user_id,
        date=datetime.now(timezone.utc).isoformat(),
        heart_rate=heart_rate,
        sleep_hours=sleep_hours,
        steps=steps,
        activity_level=activity_level
    )
    
    doc = data.model_dump()
    await db.health_data.insert_one(doc)
    
    return data

@api_router.get("/health-data/latest")
async def get_latest_health_data(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    
    # Return mock data if no real data exists
    data = await db.health_data.find_one(
        {"user_id": user_id},
        {"_id": 0},
        sort=[("created_at", -1)]
    )
    
    if not data:
        # Return mock wearable data
        data = {
            "heart_rate": 72,
            "sleep_hours": 7.5,
            "steps": 8500,
            "activity_level": "moderate",
            "date": datetime.now(timezone.utc).isoformat()
        }
    
    return data


# Profile Health Data Routes (BMI-related)
@api_router.post("/profile-health")
async def add_profile_health_data(
    health_data: ProfileHealthDataCreate,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    
    data = ProfileHealthData(
        user_id=user_id,
        date=datetime.now(timezone.utc).isoformat(),
        age=health_data.age,
        weight=health_data.weight,
        height=health_data.height
    )
    
    doc = data.model_dump()
    await db.profile_health.insert_one(doc)
    
    return data

@api_router.get("/profile-health/latest")
async def get_latest_profile_health(current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    
    data = await db.profile_health.find_one(
        {"user_id": user_id},
        {"_id": 0},
        sort=[("created_at", -1)]
    )
    
    if not data:
        return None
    
    return data


# Drug Interactions Checker
@api_router.post("/check-drug-interactions")
async def check_drug_interactions(request: dict, current_user: dict = Depends(get_current_user)):
    """Check for drug interactions with optimized caching and faster AI processing"""
    try:
        medications = request.get("medications", [])
        language = request.get("language", "en")
        
        if not medications or len(medications) < 2:
            no_meds_msg = "يرجى إضافة دوائين على الأقل للفحص" if language == "ar" else "Please add at least 2 medications to check"
            return {"has_interactions": False, "details": no_meds_msg}
        
        # Sort medications for consistent caching
        medications_sorted = sorted(
            medications, 
            key=lambda m: (
                (m.get('active_ingredient') or '').lower(),
                (m.get('brand_name') or m.get('name') or '').lower()
            )
        )
        
        # Create cache key (language-independent for consistency)
        cache_key_data = []
        for med in medications_sorted:
            active_ing = (med.get('active_ingredient') or '').strip().lower()
            brand = (med.get('brand_name') or med.get('name') or '').strip().lower()
            cache_key_data.append(f"{active_ing}|{brand}")
        
        cache_key = hashlib.md5(f"{'-'.join(cache_key_data)}".encode()).hexdigest()
        
        # Check cache first (24-hour validity)
        cached_result = await db.interaction_cache.find_one({"cache_key": cache_key})
        if cached_result:
            logging.info("✅ Cache hit for drug interactions check")
            cached_result.pop("_id", None)
            cached_result.pop("cache_key", None)
            cached_result.pop("cached_at", None)
            return cached_result
        
        logging.info("⚠️ Cache miss - calling AI for drug interactions")
        
        # Prepare medication list with brand names (to avoid checking ingredients within same drug)
        med_list = []
        for idx, med in enumerate(medications_sorted, 1):
            brand = med.get('brand_name', med.get('name', 'Unknown'))
            active_ing = med.get('active_ingredient', '')
            if active_ing:
                med_list.append(f"{idx}. {brand} (Active: {active_ing})")
            else:
                med_list.append(f"{idx}. {brand}")
        
        meds_text = "\n".join(med_list)
        
        # Get API key
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        # Initialize OpenAI client
        client = AsyncOpenAI(api_key=api_key)
        
        prompt = f"""Analyze drug interactions between these DIFFERENT medications:
{meds_text}

IMPORTANT: 
- Check interactions ONLY between different medications (different brand names)
- Do NOT check interactions between ingredients within the same medication
- If ingredients are from same brand, they are in ONE medication

Return ONLY valid JSON (no markdown):
{{
  "has_interactions": true/false,
  "total_interactions": number,
  "interactions": [
    {{
      "severity": "severe/moderate/minor",
      "drug1": "first brand name",
      "drug2": "second brand name",
      "effect": "brief clinical effect in {'Arabic' if language == 'ar' else 'English'}",
      "action": "recommendation in {'Arabic' if language == 'ar' else 'English'}"
    }}
  ]
}}

Check interactions between DIFFERENT medications only. If no interactions found, return empty interactions array."""
        
        # Call OpenAI
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a clinical pharmacist. Check interactions ONLY between different medications, NOT between ingredients within the same medication. Return JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        response_text = response.choices[0].message.content
        
        # Parse JSON response
        import json
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                interaction_data = json.loads(json_str)
            else:
                interaction_data = {
                    "has_interactions": False,
                    "total_interactions": 0,
                    "interactions": []
                }
        except (json.JSONDecodeError, ValueError):
            interaction_data = {
                "has_interactions": False,
                "total_interactions": 0,
                "interactions": []
            }
        
        # Add metadata
        result = {
            **interaction_data,
            "checked_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "medications_checked": len(medications_sorted)
        }
        
        # Cache result for 24 hours
        cache_doc = {
            "cache_key": cache_key,
            **result,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        }
        
        try:
            await db.interaction_cache.insert_one(cache_doc)
            await db.interaction_cache.create_index("expires_at", expireAfterSeconds=0)
        except Exception as cache_error:
            logging.warning(f"Cache insertion failed: {str(cache_error)}")
        
        return result
        
    except Exception as e:
        logging.error(f"Drug interaction check error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Get Medication Details Route
@api_router.post("/medications/get-details")
async def get_medication_details(request: dict, current_user: dict = Depends(get_current_user)):
    """Get comprehensive medication information from Drug Guide and SFDA databases"""
    try:
        medication_name = request.get("medication_name", "")
        active_ingredient = request.get("active_ingredient", "")
        language = request.get("language", "en")
        
        logging.info(f"Getting details for: {medication_name} ({active_ingredient})")
        
        # Step 1: Try Drug Guide first (comprehensive info)
        # Search by trade name first (more specific), then by generic
        drug_guide = None
        
        # Try exact match with trade name first
        if medication_name:
            # Try to find exact match in variants
            drug_guide = await db.drug_guide.find_one({
                "variants": {
                    "$elemMatch": {
                        "trade_name": {"$regex": f"^{medication_name}$", "$options": "i"}
                    }
                }
            })
            
            # If not found, try broader search (contains)
            if not drug_guide:
                drug_guide = await db.drug_guide.find_one({
                    "variants.trade_name": {"$regex": medication_name, "$options": "i"}
                })
        
        # If not found by trade name, try by generic (active ingredient) - but only exact match
        if not drug_guide and active_ingredient:
            # Only match if generic is EXACTLY the same (not just contains)
            drug_guide = await db.drug_guide.find_one({
                "generic_lower": active_ingredient.lower().strip()
            })
        
        if drug_guide:
            logging.info(f"✅ Found in Drug Guide: {drug_guide.get('generic')}")
            
            # Find matching variant if exists
            variants = drug_guide.get('variants', [])
            matching_variant = None
            for v in variants:
                if medication_name.lower() in v.get('trade_name', '').lower():
                    matching_variant = v
                    break
            
            # Use first variant if no match
            if not matching_variant and variants:
                matching_variant = variants[0]
            
            trade_name_display = matching_variant.get('trade_name', medication_name) if matching_variant else medication_name
            company_display = matching_variant.get('company', 'غير متوفر') if matching_variant else 'غير متوفر'
            
            # Get SFDA price if available
            sfda_price = None
            sfda_med = await db.sfda_medications.find_one({
                "$or": [
                    {"trade_name_lower": medication_name.lower()},
                    {"active_ingredients_lower": {"$regex": active_ingredient.lower()}}
                ]
            })
            if sfda_med:
                sfda_price = sfda_med.get('price_sar')
            
            # Show available variants
            variants_list = ""
            if len(variants) > 1:
                if language == "ar":
                    variants_list = "\n\n**📦 العبوات المتوفرة:**\n"
                    for v in variants[:5]:  # Show max 5
                        variants_list += f"• {v.get('trade_name', '')}\n"
                else:
                    variants_list = "\n\n**📦 Available Variants:**\n"
                    for v in variants[:5]:
                        variants_list += f"• {v.get('trade_name', '')}\n"
            
            # Format details based on language
            if language == "ar":
                details = f"""
📋 **الاسم التجاري:** {trade_name_display}
💊 **المادة الفعالة:** {drug_guide.get('generic', 'غير متوفر')}
🏭 **الشركة المصنعة:** {company_display}
💰 **السعر:** {sfda_price if sfda_price else 'غير متوفر'} ريال
{variants_list}
**📖 الاستخدامات:**
{drug_guide.get('usage', 'غير متوفر')}

**💊 كيفية الاستخدام:**
{drug_guide.get('how_to_use', 'غير متوفر')}

**⚠️ تحذيرات مهمة:**
{drug_guide.get('warnings', 'غير متوفر')}

**😷 الآثار الجانبية المحتملة:**
{drug_guide.get('side_effects', 'غير متوفر')}

**🔄 التداخلات الدوائية:**
{drug_guide.get('interactions', 'غير متوفر')}

**💡 نصيحة مهمة:**
{drug_guide.get('key_advice', 'غير متوفر')}
"""
            else:
                details = f"""
📋 **Trade Name:** {trade_name_display}
💊 **Active Ingredient:** {drug_guide.get('generic', 'Not available')}
🏭 **Manufacturer:** {company_display}
💰 **Price:** {sfda_price if sfda_price else 'Not available'} SAR
{variants_list}
**📖 What is it used for:**
{drug_guide.get('usage', 'Not available')}

**💊 How to use:**
{drug_guide.get('how_to_use', 'Not available')}

**⚠️ Important Warnings:**
{drug_guide.get('warnings', 'Not available')}

**😷 Possible Side Effects:**
{drug_guide.get('side_effects', 'Not available')}

**🔄 Drug Interactions:**
{drug_guide.get('interactions', 'Not available')}

**💡 Key Advice:**
{drug_guide.get('key_advice', 'Not available')}
"""
            
            return {
                "medication_name": medication_name,
                "active_ingredient": active_ingredient,
                "details": details,
                "source": "Drug Guide",
                "reliability": 0.95,
                "available": True
            }
        
        # Step 2: Fallback to SFDA if not in Drug Guide
        sfda_medication = await db.sfda_medications.find_one({
            "$or": [
                {"trade_name_lower": medication_name.lower()},
                {"active_ingredients_lower": {"$regex": active_ingredient.lower()}}
            ]
        })
        
        if sfda_medication:
            logging.info(f"✅ Found in SFDA: {sfda_medication.get('trade_name')}")
            
            details_ar = f"""
📋 الاسم التجاري: {sfda_medication.get('trade_name', 'غير متوفر')}
💊 المادة الفعالة: {sfda_medication.get('active_ingredients', 'غير متوفر')}
🏭 الشركة المصنعة: {sfda_medication.get('manufacturer', 'غير متوفر')}
💰 السعر: {sfda_medication.get('price_sar', 'غير متوفر')} ريال
📦 العبوة: {sfda_medication.get('pack', 'غير متوفر')}
⚕️ القوة: {sfda_medication.get('strength', 'غير متوفر')}
"""
            
            details_en = f"""
📋 Trade Name: {sfda_medication.get('trade_name', 'Not available')}
💊 Active Ingredient: {sfda_medication.get('active_ingredients', 'Not available')}
🏭 Manufacturer: {sfda_medication.get('manufacturer', 'Not available')}
💰 Price: {sfda_medication.get('price_sar', 'Not available')} SAR
📦 Pack: {sfda_medication.get('pack', 'Not available')}
⚕️ Strength: {sfda_medication.get('strength', 'Not available')}
"""
            
            return {
                "medication_name": medication_name,
                "active_ingredient": active_ingredient,
                "details": details_ar if language == "ar" else details_en,
                "source": "SFDA",
                "reliability": 1.0,
                "available": True
            }
        
        else:
            # Not found anywhere
            no_data_msg = "عذراً، لا توجد معلومات متاحة عن هذا الدواء في قاعدة البيانات." if language == "ar" else "Sorry, no information available for this medication in the database."
            
            return {
                "medication_name": medication_name,
                "active_ingredient": active_ingredient,
                "details": no_data_msg,
                "source": "None",
                "reliability": 0.0,
                "available": False
            }
        
    except Exception as e:
        logging.error(f"❌ Medication details error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# User Profile Routes
@api_router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    return current_user

@api_router.put("/profile")
async def update_profile(
    updates: dict,
    current_user: dict = Depends(get_current_user)
):
    # Remove protected fields
    updates.pop("id", None)
    updates.pop("email", None)
    updates.pop("password_hash", None)
    
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": updates}
    )
    
    return {"message": "Profile updated"}

@api_router.post("/change-password")
async def change_password(
    password_data: dict,
    current_user: dict = Depends(get_current_user)
):
    current_password = password_data.get("current_password")
    new_password = password_data.get("new_password")
    
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Missing password fields")
    
    # Verify current password (current_user already has password_hash excluded)
    # We need to get the user with password_hash to verify
    user_with_password = await db.users.find_one({"id": current_user["id"]})
    if not user_with_password:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not verify_password(current_password, user_with_password["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    
    # Hash new password and update
    new_hash = hash_password(new_password)
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"password_hash": new_hash}}
    )
    
    return {"message": "Password changed successfully"}


# ===========================
# Medication Reminders Routes
# ===========================

@api_router.post("/reminders")
async def create_reminder(
    reminder_data: MedicationReminderCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new medication reminder"""
    user_id = current_user["id"]
    is_premium = current_user.get("is_premium", False)
    
    # Check reminder limit for free users
    can_add = await check_reminder_limit(user_id, is_premium)
    if not can_add:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "reminder_limit_reached",
                "message": f"Free users can only create up to {FREE_USER_LIMITS['max_reminders']} reminders. Upgrade to Premium for unlimited reminders.",
                "limit": FREE_USER_LIMITS["max_reminders"]
            }
        )
    
    # Check if reminder already exists for this medication
    existing = await db.medication_reminders.find_one({
        "user_id": user_id,
        "medication_id": reminder_data.medication_id
    })
    
    if existing:
        raise HTTPException(status_code=400, detail="Reminder already exists for this medication")
    
    reminder_dict = reminder_data.model_dump()
    reminder_dict["user_id"] = user_id
    reminder_dict["id"] = str(uuid.uuid4())
    reminder_dict["enabled"] = True
    reminder_dict["adherence_log"] = []
    reminder_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.medication_reminders.insert_one(reminder_dict)
    
    return MedicationReminder(**reminder_dict)


@api_router.get("/reminders")
async def get_reminders(current_user: dict = Depends(get_current_user)):
    """Get all reminders for current user (only for existing medications)"""
    user_id = current_user["id"]
    
    # Clean up orphan reminders (reminders without medications)
    all_reminders = await db.medication_reminders.find({"user_id": user_id}).to_list(None)
    orphan_ids = []
    
    for reminder in all_reminders:
        med_id = reminder.get("medication_id")
        # Check if medication still exists
        med_exists = await db.user_medications.find_one({
            "medication_id": med_id,
            "user_id": user_id,
            "active": True
        })
        
        if not med_exists:
            orphan_ids.append(reminder.get("id"))
    
    # Delete orphan reminders
    if orphan_ids:
        await db.medication_reminders.delete_many({"id": {"$in": orphan_ids}})
        logger.info(f"🧹 Cleaned up {len(orphan_ids)} orphan reminders for user {user_id}")
    
    reminders = await db.medication_reminders.find({"user_id": user_id}, {"_id": 0}).to_list(length=None)
    
    # If no reminders, return empty list
    if not reminders:
        return []
    
    # Get all medication IDs to verify they still exist
    medication_ids = [r.get("medication_id") for r in reminders if r.get("medication_id")]
    
    # Only check if we have medication_ids to check
    existing_med_ids = set()
    if medication_ids:
        existing_medications = await db.user_medications.find({
            "user_id": user_id,
            "id": {"$in": medication_ids}
        }, {"_id": 0, "id": 1}).to_list(length=None)
        
        existing_med_ids = {med["id"] for med in existing_medications}
    
    # Track orphaned reminders to clean up (only if we found some existing medications)
    orphaned_reminder_ids = []
    valid_reminders = []
    
    for reminder in reminders:
        medication_id = reminder.get("medication_id")
        
        # If no medication_id, keep the reminder (legacy data)
        if not medication_id:
            if "created_at" in reminder and isinstance(reminder["created_at"], datetime):
                reminder["created_at"] = reminder["created_at"].isoformat()
            valid_reminders.append(reminder)
            continue
        
        # Only filter if we have existing medications to compare against
        if medication_ids and existing_med_ids:
            # Skip if medication doesn't exist anymore
            if medication_id not in existing_med_ids:
                orphaned_reminder_ids.append(reminder["id"])
                continue
        
        # Convert datetime objects to ISO strings for Pydantic
        if "created_at" in reminder and isinstance(reminder["created_at"], datetime):
            reminder["created_at"] = reminder["created_at"].isoformat()
        
        valid_reminders.append(reminder)
    
    # Clean up orphaned reminders in background (only if we're sure they're orphaned)
    if orphaned_reminder_ids and existing_med_ids:
        await db.medication_reminders.delete_many({
            "id": {"$in": orphaned_reminder_ids},
            "user_id": user_id
        })
    
    return [MedicationReminder(**reminder) for reminder in valid_reminders]


@api_router.get("/reminders/upcoming")
async def get_upcoming_reminders(current_user: dict = Depends(get_current_user)):
    """Get upcoming reminders for today (only for existing medications)"""
    user_id = current_user["id"]
    
    # Get all enabled reminders
    reminders = await db.medication_reminders.find({
        "user_id": user_id,
        "enabled": True
    }).to_list(length=None)
    
    # If no reminders, return empty list
    if not reminders:
        return {"upcoming_reminders": [], "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    
    # Get all medication IDs to verify they still exist
    medication_ids = [r.get("medication_id") for r in reminders if r.get("medication_id")]
    
    # Only check if we have medication_ids to check
    existing_med_ids = set()
    if medication_ids:
        existing_medications = await db.user_medications.find({
            "user_id": user_id,
            "id": {"$in": medication_ids}
        }, {"_id": 0, "id": 1}).to_list(length=None)
        
        existing_med_ids = {med["id"] for med in existing_medications}
    
    # Get current time
    now = datetime.now(timezone.utc)
    current_time = now.strftime("%H:%M")
    today_date = now.strftime("%Y-%m-%d")
    
    # Track orphaned reminders to clean up
    orphaned_reminder_ids = []
    
    upcoming = []
    for reminder in reminders:
        medication_id = reminder.get("medication_id")
        
        # If no medication_id, skip for upcoming (shouldn't happen for new reminders)
        if not medication_id:
            continue
        
        # Only filter if we have existing medications to compare against
        should_skip = False
        if medication_ids and existing_med_ids:
            # Skip if medication doesn't exist anymore
            if medication_id not in existing_med_ids:
                orphaned_reminder_ids.append(reminder["id"])
                should_skip = True
        
        if should_skip:
            continue
            
        for reminder_time in reminder.get("reminder_times", []):
            # Check if this time hasn't passed yet today
            if reminder_time >= current_time:
                # Check adherence log to see if already taken today
                adherence_log = reminder.get("adherence_log", [])
                taken_today = any(
                    log.get("date") == today_date and 
                    log.get("time") == reminder_time and 
                    log.get("taken")
                    for log in adherence_log
                )
                
                upcoming.append({
                    "reminder_id": reminder["id"],
                    "medication_id": medication_id,
                    "medication_name": reminder["medication_name"],
                    "time": reminder_time,
                    "taken": taken_today
                })
    
    # Clean up orphaned reminders in background (only if we're sure they're orphaned)
    if orphaned_reminder_ids and existing_med_ids:
        await db.medication_reminders.delete_many({
            "id": {"$in": orphaned_reminder_ids},
            "user_id": user_id
        })
    
    # Sort by time
    upcoming.sort(key=lambda x: x["time"])
    
    return {"upcoming_reminders": upcoming, "date": today_date}


@api_router.patch("/reminders/{reminder_id}")
async def update_reminder(
    reminder_id: str,
    update_data: MedicationReminderUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update reminder times or enable/disable"""
    user_id = current_user["id"]
    
    # Find reminder
    reminder = await db.medication_reminders.find_one({
        "id": reminder_id,
        "user_id": user_id
    })
    
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    # Update fields
    update_fields = {}
    if update_data.reminder_times is not None:
        update_fields["reminder_times"] = update_data.reminder_times
    if update_data.enabled is not None:
        update_fields["enabled"] = update_data.enabled
    
    if update_fields:
        await db.medication_reminders.update_one(
            {"id": reminder_id},
            {"$set": update_fields}
        )
    
    # Get updated reminder
    updated_reminder = await db.medication_reminders.find_one({"id": reminder_id})
    
    return MedicationReminder(**updated_reminder)


@api_router.patch("/reminders/{reminder_id}/toggle")
async def toggle_reminder(
    reminder_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Toggle reminder enabled/disabled"""
    user_id = current_user["id"]
    
    reminder = await db.medication_reminders.find_one({
        "id": reminder_id,
        "user_id": user_id
    })
    
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    new_enabled = not reminder.get("enabled", True)
    
    await db.medication_reminders.update_one(
        {"id": reminder_id},
        {"$set": {"enabled": new_enabled}}
    )
    
    return {"enabled": new_enabled}


@api_router.delete("/reminders/{reminder_id}")
async def delete_reminder(
    reminder_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a reminder"""
    user_id = current_user["id"]
    
    result = await db.medication_reminders.delete_one({
        "id": reminder_id,
        "user_id": user_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    return {"message": "Reminder deleted successfully"}


@api_router.post("/reminders/mark-taken")
async def mark_dose_taken(
    dose_data: DoseTaken,
    current_user: dict = Depends(get_current_user)
):
    """Mark a dose as taken"""
    user_id = current_user["id"]
    
    # Find reminder
    reminder = await db.medication_reminders.find_one({
        "id": dose_data.reminder_id,
        "user_id": user_id
    })
    
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    # Parse taken time
    taken_dt = datetime.fromisoformat(dose_data.taken_time.replace('Z', '+00:00'))
    taken_date = taken_dt.strftime("%Y-%m-%d")
    taken_time = taken_dt.strftime("%H:%M")
    
    # Add to adherence log
    adherence_log = reminder.get("adherence_log", [])
    
    # Check if already logged for this date/time
    existing_log = next((log for log in adherence_log 
                        if log.get("date") == taken_date and log.get("time") == taken_time), None)
    
    if existing_log:
        # Update existing log
        existing_log["taken"] = True
        existing_log["actual_time"] = dose_data.taken_time
    else:
        # Add new log entry
        adherence_log.append({
            "date": taken_date,
            "time": taken_time,
            "taken": True,
            "actual_time": dose_data.taken_time
        })
    
    # Update reminder
    await db.medication_reminders.update_one(
        {"id": dose_data.reminder_id},
        {
            "$set": {
                "adherence_log": adherence_log,
                "last_taken": dose_data.taken_time
            }
        }
    )
    
    return {"message": "Dose marked as taken", "adherence_log": adherence_log}


@api_router.get("/reminders/{reminder_id}/adherence")
async def get_adherence_stats(
    reminder_id: str,
    days: int = 7,
    current_user: dict = Depends(get_current_user)
):
    """Get adherence statistics for a reminder"""
    user_id = current_user["id"]
    
    reminder = await db.medication_reminders.find_one({
        "id": reminder_id,
        "user_id": user_id
    })
    
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    
    # Calculate adherence for last N days
    adherence_log = reminder.get("adherence_log", [])
    reminder_times = reminder.get("reminder_times", [])
    
    # Calculate expected doses
    expected_doses = days * len(reminder_times)
    
    # Count taken doses in last N days
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    taken_doses = sum(1 for log in adherence_log 
                     if log.get("taken") and log.get("date") >= cutoff_date)
    
    adherence_rate = (taken_doses / expected_doses * 100) if expected_doses > 0 else 0
    
    return {
        "reminder_id": reminder_id,
        "medication_name": reminder["medication_name"],
        "days_analyzed": days,
        "expected_doses": expected_doses,
        "taken_doses": taken_doses,
        "missed_doses": expected_doses - taken_doses,
        "adherence_rate": round(adherence_rate, 1)
    }




# Medication Course Analysis Models
class MedicationCourseRequest(BaseModel):
    medication_name: str
    active_ingredient: Optional[str] = None
    dosage_form: Optional[str] = None
    condition: Optional[str] = None

class MedicationCourseAnalysis(BaseModel):
    is_as_needed: bool
    recommended_duration: Optional[int] = None  # days
    category: str  # 'antibiotic', 'painkiller', 'chronic', 'as_needed'
    warning: Optional[str] = None
    warning_ar: Optional[str] = None
    usage_note: Optional[str] = None
    usage_note_ar: Optional[str] = None

@api_router.post("/analyze-medication-course", response_model=MedicationCourseAnalysis)
async def analyze_medication_course(
    request: MedicationCourseRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze medication using FDA API to determine treatment course duration
    Falls back to keyword matching if FDA API fails
    """
    try:
        # Try FDA API first
        fda_result = await query_fda_for_course_info(
            medication_name=request.medication_name,
            active_ingredient=request.active_ingredient,
            dosage_form=request.dosage_form
        )
        
        if fda_result:
            return MedicationCourseAnalysis(**fda_result)
        
        # Fallback to keyword matching
        print(f"FDA API returned no results, using fallback for {request.medication_name}")
        return MedicationCourseAnalysis(**fallback_medication_analysis(request.medication_name, request.active_ingredient))
        
    except Exception as e:
        print(f"Error in medication course analysis: {e}")
        return MedicationCourseAnalysis(**fallback_medication_analysis(request.medication_name, request.active_ingredient))


async def query_fda_for_course_info(
    medication_name: str,
    active_ingredient: Optional[str],
    dosage_form: Optional[str]
) -> Optional[dict]:
    """
    Query FDA OpenFDA API for medication course information
    """
    try:
        import httpx
        
        # Prepare search query
        search_parts = []
        
        if active_ingredient:
            # Clean and prepare active ingredient
            clean_ingredient = active_ingredient.strip().lower()
            
            # Handle common name variations (UK vs US)
            ingredient_mapping = {
                'paracetamol': 'acetaminophen',
                'salbutamol': 'albuterol',
                'adrenaline': 'epinephrine'
            }
            
            clean_ingredient = ingredient_mapping.get(clean_ingredient, clean_ingredient)
            
            # Handle multiple ingredients (e.g., "amoxicillin,clavulanic acid")
            if ',' in clean_ingredient:
                # Take only the first ingredient for search
                clean_ingredient = clean_ingredient.split(',')[0].strip()
            
            search_parts.append(f'openfda.generic_name:"{clean_ingredient}"')
        else:
            # Use medication name as fallback
            clean_name = medication_name.strip().lower()
            search_parts.append(f'openfda.brand_name:"{clean_name}"')
        
        # Don't filter by dosage form as it causes too many false negatives
        # FDA API dosage_form field is not standardized enough
        
        # Build FDA API query
        search_query = '+AND+'.join(search_parts)
        fda_url = f"https://api.fda.gov/drug/label.json?search={search_query}&limit=1"
        
        print(f"🔍 Querying FDA API: {fda_url}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(fda_url)
            
            if response.status_code != 200:
                print(f"FDA API returned status {response.status_code}")
                return None
            
            data = response.json()
            
            if not data.get('results'):
                print(f"No FDA results found for {medication_name}")
                return None
            
            result = data['results'][0]
            
            # Extract dosage and administration info
            dosage_info = result.get('dosage_and_administration', [''])[0] if result.get('dosage_and_administration') else ''
            indications = result.get('indications_and_usage', [''])[0] if result.get('indications_and_usage') else ''
            
            # Analyze the text to determine course duration
            analysis = analyze_fda_label_text(dosage_info, indications, medication_name, active_ingredient)
            
            print(f"✅ FDA analysis complete: {analysis.get('category')} - {analysis.get('recommended_duration')} days")
            
            return analysis
            
    except Exception as e:
        print(f"Error querying FDA API: {e}")
        return None


def analyze_fda_label_text(dosage_text: str, indications_text: str, med_name: str, active_ingredient: Optional[str]) -> dict:
    """
    Analyze FDA label text to extract course duration
    """
    combined_text = (dosage_text + " " + indications_text).lower()
    med_lower = (med_name + " " + (active_ingredient or "")).lower()
    
    # Check for painkillers/analgesics
    painkillers = ['pain', 'analgesic', 'paracetamol', 'acetaminophen', 'ibuprofen', 'aspirin', 'naproxen']
    if any(p in med_lower for p in painkillers) or any(p in combined_text for p in painkillers):
        return {
            "is_as_needed": True,
            "recommended_duration": None,
            "category": "painkiller",
            "warning": "Do not exceed the maximum daily dose. Consult a doctor if pain persists for more than 3 days.",
            "warning_ar": "لا تتجاوز الجرعة اليومية القصوى. استشر الطبيب إذا استمر الألم لأكثر من 3 أيام.",
            "usage_note": "Take only when needed for pain or fever. Do not use regularly without medical advice.",
            "usage_note_ar": "تناول فقط عند الحاجة للألم أو الحمى. لا تستخدم بشكل منتظم دون استشارة طبية."
        }
    
    # Extract duration from FDA text
    duration_patterns = [
        (r'(\d+)\s*day', 'days'),
        (r'(\d+)\s*week', 'weeks'),
        (r'(\d+)\s*to\s*(\d+)\s*day', 'days_range'),
        (r'for\s*(\d+)', 'days')
    ]
    
    import re
    recommended_duration = None
    
    for pattern, unit in duration_patterns:
        match = re.search(pattern, combined_text)
        if match:
            if unit == 'days_range':
                # Take the maximum of the range
                recommended_duration = int(match.group(2))
            elif unit == 'weeks':
                recommended_duration = int(match.group(1)) * 7
            else:
                recommended_duration = int(match.group(1))
            break
    
    # Check for antibiotics
    antibiotics = ['antibiotic', 'amoxicillin', 'penicillin', 'cephalosporin', 'azithromycin', 'infection', 'bacterial']
    is_antibiotic = any(a in med_lower for a in antibiotics) or any(a in combined_text for a in antibiotics)
    
    if is_antibiotic:
        if not recommended_duration:
            recommended_duration = 7  # Default for antibiotics
        return {
            "is_as_needed": False,
            "recommended_duration": recommended_duration,
            "category": "antibiotic",
            "warning": "⚠️ مهم: أكمل مدة العلاج الكاملة حتى لو شعرت بتحسن. التوقف المبكر قد يؤدي لعودة الأعراض أو مضاعفات.",
            "warning_ar": "⚠️ مهم: أكمل الكورس كاملاً حتى لو شعرت بتحسن. التوقف المبكر قد يسبب مقاومة للمضاد الحيوي.",
            "usage_note": "Take at the same time each day for best results. Do not skip doses.",
            "usage_note_ar": "تناول في نفس الوقت يومياً للحصول على أفضل النتائج. لا تفوت أي جرعة."
        }
    
    # Check for chronic medications
    chronic_keywords = ['chronic', 'maintenance', 'long-term', 'daily', 'blood pressure', 'diabetes', 'cholesterol']
    is_chronic = any(c in combined_text for c in chronic_keywords)
    
    if is_chronic:
        return {
            "is_as_needed": False,
            "recommended_duration": 30,
            "category": "chronic",
            "warning": "This is a chronic medication. Continue taking as prescribed. Do not stop without consulting your doctor.",
            "warning_ar": "هذا دواء مزمن. استمر في تناوله كما وصف لك. لا تتوقف دون استشارة الطبيب.",
            "usage_note": "Take daily at the same time for best control of your condition.",
            "usage_note_ar": "تناول يومياً في نفس الوقت للتحكم الأمثل في حالتك."
        }
    
    # Default: short course
    if not recommended_duration:
        recommended_duration = 5
    
    return {
        "is_as_needed": False,
        "recommended_duration": recommended_duration,
        "category": "short_course",
        "warning": "Follow your doctor's instructions regarding duration.",
        "warning_ar": "اتبع تعليمات الطبيب بخصوص مدة الاستخدام.",
        "usage_note": "Take as prescribed by your healthcare provider.",
        "usage_note_ar": "تناول حسب وصف مقدم الرعاية الصحية."
    }


# Keep the old function that was here
@api_router.post("/analyze-medication-course-old", response_model=MedicationCourseAnalysis)
async def analyze_medication_course_old(
    request: MedicationCourseRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Analyze medication using AI to determine if it needs a full course or as-needed usage (OLD VERSION)
    """
    try:
        # Prepare medication info for AI analysis
        med_info = f"""
Medication Name: {request.medication_name}
Active Ingredient: {request.active_ingredient or 'Unknown'}
Dosage Form: {request.dosage_form or 'Unknown'}
Condition: {request.condition or 'Unknown'}
"""
        
        # AI prompt for medication course analysis
        prompt = f"""You are a medication expert. Analyze this medication and determine:

{med_info}

Determine:
1. Is this medication taken "as needed" (PRN) or does it require a full treatment course?
2. If it's a full course, what is the typical duration in days?
3. What category does it belong to? (antibiotic, painkiller, chronic, as_needed)
4. Any important warnings or usage notes?

Respond in JSON format:
{{
  "is_as_needed": boolean,
  "recommended_duration": integer or null,
  "category": "antibiotic" | "painkiller" | "chronic" | "as_needed",
  "warning": "English warning text",
  "warning_ar": "Arabic warning text",
  "usage_note": "English usage note",
  "usage_note_ar": "Arabic usage note"
}}

Guidelines:
- Antibiotics: Full course (7-14 days typically)
- Painkillers (Paracetamol, Ibuprofen, etc.): As needed
- Blood pressure/diabetes medications: Chronic (no specific duration)
- Cough/cold medications: As needed or short course (3-5 days)
- Anti-inflammatories: Depends on condition (5-10 days if prescribed)
"""

        # Call OpenAI
        api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('EMERGENT_LLM_KEY')
        client = AsyncOpenAI(api_key=api_key)
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a clinical pharmacist expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        response_text = response.choices[0].message.content
        
        # Parse JSON from response
        try:
            # Find JSON in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                analysis_data = json.loads(json_str)
            else:
                # Fallback analysis based on keywords
                analysis_data = fallback_medication_analysis(request.medication_name, request.active_ingredient)
        except Exception as e:
            print(f"Error parsing AI response: {e}")
            # Fallback analysis
            analysis_data = fallback_medication_analysis(request.medication_name, request.active_ingredient)
        
        return MedicationCourseAnalysis(**analysis_data)
        
    except Exception as e:
        print(f"Error in medication course analysis: {e}")
        # Return fallback analysis
        return MedicationCourseAnalysis(**fallback_medication_analysis(request.medication_name, request.active_ingredient))


def fallback_medication_analysis(medication_name: str, active_ingredient: Optional[str]) -> dict:
    """
    Fallback analysis when AI is not available
    """
    med_lower = (medication_name + " " + (active_ingredient or "")).lower()
    
    # Check for painkillers
    painkillers = ['paracetamol', 'ibuprofen', 'aspirin', 'panadol', 'brufen', 'voltaren', 'diclofenac', 'مسكن', 'باراسيتامول', 'ايبوبروفين']
    if any(p in med_lower for p in painkillers):
        return {
            "is_as_needed": True,
            "recommended_duration": None,
            "category": "painkiller",
            "warning": "Do not exceed the maximum daily dose. Consult a doctor if pain persists for more than 3 days.",
            "warning_ar": "لا تتجاوز الجرعة اليومية القصوى. استشر الطبيب إذا استمر الألم لأكثر من 3 أيام.",
            "usage_note": "Take only when needed for pain or fever. Do not use regularly without medical advice.",
            "usage_note_ar": "تناول فقط عند الحاجة للألم أو الحمى. لا تستخدم بشكل منتظم دون استشارة طبية."
        }
    
    # Check for antibiotics
    antibiotics = ['antibiotic', 'amoxicillin', 'augmentin', 'azithromycin', 'cephalexin', 'ciprofloxacin', 'مضاد حيوي', 'اوجمنتين', 'اموكسيسيلين']
    if any(a in med_lower for a in antibiotics):
        return {
            "is_as_needed": False,
            "recommended_duration": 7,
            "category": "antibiotic",
            "warning": "⚠️ مهم: أكمل مدة العلاج الكاملة حتى لو شعرت بتحسن. التوقف المبكر قد يؤدي لعودة الأعراض أو مضاعفات.",
            "warning_ar": "⚠️ مهم: أكمل الكورس كاملاً حتى لو شعرت بتحسن. التوقف المبكر قد يسبب مقاومة للمضاد الحيوي.",
            "usage_note": "Take at the same time each day for best results. Do not skip doses.",
            "usage_note_ar": "تناول في نفس الوقت يومياً للحصول على أفضل النتائج. لا تفوت أي جرعة."
        }
    
    # Check for chronic medications
    chronic_keywords = ['blood pressure', 'diabetes', 'cholesterol', 'thyroid', 'ضغط', 'سكر', 'كوليسترول', 'الغدة']
    if any(c in med_lower for c in chronic_keywords):
        return {
            "is_as_needed": False,
            "recommended_duration": 30,
            "category": "chronic",
            "warning": "This is a chronic medication. Continue taking as prescribed. Do not stop without consulting your doctor.",
            "warning_ar": "هذا دواء مزمن. استمر في تناوله كما وصف لك. لا تتوقف دون استشارة الطبيب.",
            "usage_note": "Take daily at the same time for best control of your condition.",
            "usage_note_ar": "تناول يومياً في نفس الوقت للتحكم الأمثل في حالتك."
        }
    
    # Default: short course
    return {
        "is_as_needed": False,
        "recommended_duration": 5,
        "category": "as_needed",
        "warning": "Follow your doctor's instructions regarding duration.",
        "warning_ar": "اتبع تعليمات الطبيب بخصوص مدة الاستخدام.",
        "usage_note": "Take as prescribed by your healthcare provider.",
        "usage_note_ar": "تناول حسب وصف مقدم الرعاية الصحية."
    }

@api_router.get("/sfda-medications/search")
async def search_sfda_medications(
    query: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """Search SFDA medications database by trade name, active ingredient, or manufacturer"""
    try:
        user_id = current_user["id"]
        is_premium = current_user.get("is_premium", False)
        
        if not query or len(query) < 2:
            return {
                "success": True,
                "results": [],
                "total": 0,
                "message": "Query too short"
            }
        
        # Check search limit for free users
        current_searches = current_user.get("sfda_searches_used", 0)
        can_search = await check_sfda_search_limit(user_id, is_premium, current_searches)
        
        if not can_search:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "search_limit_reached",
                    "message": f"Free users can only perform {FREE_USER_LIMITS['max_sfda_searches']} SFDA searches. Upgrade to Premium for unlimited searches.",
                    "limit": FREE_USER_LIMITS["max_sfda_searches"],
                    "used": current_searches
                }
            )
        
        query_lower = query.lower()
        
        # Search in trade name (English & Arabic), scientific name, active ingredients, and manufacturer
        search_filter = {
            "$or": [
                {"trade_name": {"$regex": query, "$options": "i"}},
                {"trade_name_ar": {"$regex": query, "$options": "i"}},
                {"commercial_name_en": {"$regex": query, "$options": "i"}},
                {"commercial_name_ar": {"$regex": query, "$options": "i"}},
                {"scientific_name": {"$regex": query, "$options": "i"}},
                {"scientific_name_ar": {"$regex": query, "$options": "i"}},
                {"active_ingredients": {"$regex": query, "$options": "i"}},
                {"manufacturer": {"$regex": query, "$options": "i"}},
                {"manufacturer_ar": {"$regex": query, "$options": "i"}}
            ]
        }
        
        # Get total count
        total = await db.medications.count_documents(search_filter)
        
        # Get results
        cursor = db.medications.find(
            search_filter,
            {"_id": 0}
        ).limit(limit)
        
        results = await cursor.to_list(length=limit)
        
        # Increment search counter for free users (only if results found)
        if not is_premium and len(results) > 0:
            await db.users.update_one(
                {"id": user_id},
                {"$inc": {"sfda_searches_used": 1}}
            )
        
        return {
            "success": True,
            "results": results,
            "total": total,
            "showing": len(results),
            "searches_remaining": FREE_USER_LIMITS["max_sfda_searches"] - current_searches - 1 if not is_premium else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error searching SFDA medications: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/sfda-medications/details")
async def get_sfda_medication_details(
    trade_name: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed information about a specific medication from SFDA database"""
    try:
        medication = await db.sfda_medications.find_one(
            {"trade_name": trade_name},
            {"_id": 0}
        )
        
        if not medication:
            # Try case-insensitive search
            medication = await db.sfda_medications.find_one(
                {"trade_name": {"$regex": f"^{trade_name}$", "$options": "i"}},
                {"_id": 0}
            )
        
        if medication:
            return {
                "success": True,
                "medication": medication
            }
        else:
            raise HTTPException(status_code=404, detail="Medication not found in SFDA database")
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting SFDA medication details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/ai/drug-info")
async def get_ai_medication_info(
    drug_name: Optional[str] = None,
    scientific_name: Optional[str] = None,
    language: str = "ar",
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive medication information using AI (OpenAI GPT-4)
    
    Searches by EITHER trade name OR scientific name (or both for best accuracy):
    - Trade name: "Claritine", "Panadol", etc.
    - Scientific name: "Loratidine", "Paracetamol", etc.
    
    Provides accurate, evidence-based medical information including:
    - Drug classification
    - Medical uses
    - Recommended dosage
    - Warnings and precautions
    - Pregnancy and lactation information
    
    Source: AI (OpenAI GPT-4) with Emergent LLM Key (Free)
    """
    try:
        if not AI_DRUG_INFO_ENABLED:
            raise HTTPException(
                status_code=503,
                detail="AI Drug Info service is not available"
            )
        
        if not drug_name and not scientific_name:
            raise HTTPException(
                status_code=400,
                detail="Either drug_name or scientific_name is required"
            )
        
        # Use drug_name or scientific_name (or both)
        search_name = drug_name or scientific_name
        
        # Fetch information from AI (using async method)
        result = await ai_drug_info.get_drug_info_async(
            drug_name=search_name,
            scientific_name=scientific_name if scientific_name != drug_name else None,
            language=language
        )
        
        if not result.get("success"):
            return {
                "success": False,
                "message": "Could not get information from AI",
                "error": result.get("error", "Unknown error")
            }
        
        # Try to match with SFDA database for package size and accurate info
        sfda_match = None
        treatment_duration_days = None
        
        try:
            # Search in SFDA database
            query = {
                "$or": [
                    {"trade_name_lower": {"$regex": search_name.lower(), "$options": "i"}},
                    {"scientific_name": {"$regex": search_name, "$options": "i"}}
                ]
            }
            sfda_match = await db.sfda_medications.find_one(query, {"_id": 0})
            
            # Extract package size from drug name if not in SFDA or SFDA has wrong size
            package_size_from_name = None
            size_match = re.search(r'(\d+\.?\d*)\s*(g|gm|gram|ml|mg|ملغ|مجم|جم)', drug_name, re.IGNORECASE)
            if size_match:
                size_value = float(size_match.group(1))
                size_unit = size_match.group(2).lower()
                # Normalize units to grams or ml
                if size_unit in ['g', 'gm', 'gram', 'جم']:
                    package_size_from_name = size_value
                elif size_unit in ['ml']:
                    package_size_from_name = size_value
                elif size_unit in ['mg', 'ملغ', 'مجم']:
                    package_size_from_name = size_value / 1000  # Convert mg to g
            
            if sfda_match or package_size_from_name:
                # Calculate treatment duration based on dosage and package size
                dosage_text = result.get("dosage", "")
                
                # Use package size from name if available and SFDA is unreliable (< 2)
                package_size = package_size_from_name if package_size_from_name and (not sfda_match or sfda_match.get("package_size", 0) < 2) else sfda_match.get("package_size", 0) if sfda_match else 0
                
                if package_size and dosage_text:
                    # Parse dosage to extract times per day
                    import re
                    times_per_day = 1  # Default
                    
                    # Arabic patterns
                    if "مرتين" in dosage_text or "twice" in dosage_text.lower():
                        times_per_day = 2
                    elif "ثلاث مرات" in dosage_text or "three times" in dosage_text.lower():
                        times_per_day = 3
                    elif "أربع مرات" in dosage_text or "four times" in dosage_text.lower():
                        times_per_day = 4
                    elif "مرة واحدة" in dosage_text or "once" in dosage_text.lower():
                        times_per_day = 1
                    
                    # Check for "every X hours" pattern
                    hours_match = re.search(r'كل\s*(\d+)(?:-\d+)?\s*ساعات?', dosage_text)
                    if hours_match:
                        hours = int(hours_match.group(1))
                        times_per_day = 24 // hours
                    
                    # Check for text numbers (five times, four days, etc.)
                    text_numbers = {
                        'five': 5, 'four': 4, 'three': 3, 'two': 2, 'one': 1,
                        'six': 6, 'seven': 7, 'eight': 8
                    }
                    times_text_match = re.search(r'(five|four|three|two|one|six|seven|eight)\s+times', dosage_text, re.IGNORECASE)
                    if times_text_match:
                        times_per_day = text_numbers.get(times_text_match.group(1).lower(), times_per_day)
                    
                    # Extract treatment duration in days
                    duration_days = None
                    duration_text_match = re.search(r'(?:for|لمدة)\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+(day|days|يوم|أيام)', dosage_text, re.IGNORECASE)
                    if duration_text_match:
                        duration_num = duration_text_match.group(1).lower()
                        if duration_num.isdigit():
                            duration_days = int(duration_num)
                        else:
                            duration_days = text_numbers.get(duration_num, 1)
                    
                    # Calculate pills per time (default 1 unless specified)
                    pills_per_time = 1
                    pills_match = re.search(r'حبتين|حبتان|two tablets?', dosage_text, re.IGNORECASE)
                    if pills_match:
                        pills_per_time = 2
                    
                    # For topical medications (creams, ointments), assume 1g per application
                    dosage_form = (sfda_match.get('dosage_form', '') if sfda_match else '') or drug_name
                    is_topical = 'cream' in dosage_form.lower() or 'ointment' in dosage_form.lower() or 'gel' in dosage_form.lower() or 'كريم' in dosage_form.lower() or 'مرهم' in dosage_form.lower()
                    
                    logging.info(f"Checking topical: is_topical={is_topical}, package_size_from_name={package_size_from_name}, duration_days={duration_days}, dosage_form={dosage_form}")
                    
                    if is_topical and package_size_from_name and duration_days:
                        # For topical: calculate based on grams/ml
                        # Assume 1g or 1ml per application
                        grams_per_application = 1.0
                        total_applications = times_per_day * duration_days
                        total_grams_needed = total_applications * grams_per_application
                        
                        # Calculate number of packages needed
                        packages_needed = int(total_grams_needed / package_size_from_name) + (1 if total_grams_needed % package_size_from_name > 0 else 0)
                        
                        # Treatment duration = total days
                        treatment_duration_days = duration_days
                        
                        logging.info(f"Topical medication {search_name}: {packages_needed} package(s) needed for {duration_days} days (package: {package_size_from_name}g, {times_per_day}x daily)")
                    else:
                        # For tablets/capsules: regular calculation
                        daily_usage = times_per_day * pills_per_time
                        
                        # Calculate treatment duration
                        if daily_usage > 0:
                            treatment_duration_days = int(package_size / daily_usage)
                            
                            logging.info(f"Calculated treatment duration for {search_name}: {treatment_duration_days} days (package: {package_size}, daily: {daily_usage})")
        
        except Exception as e:
            logging.error(f"Error matching with SFDA database: {str(e)}")
        
        response_data = {
            "classification": result.get("classification", ""),
            "uses": result.get("uses", ""),
            "dosage": result.get("dosage", ""),
            "warnings": result.get("warnings", ""),
            "pregnancy_lactation": result.get("pregnancy_lactation", ""),
            "source": "AI (OpenAI GPT-4)",
            "search_term": result.get("search_term", "")
        }
        
        # Add SFDA info if matched
        if sfda_match:
            legal_status = sfda_match.get("legal_status", "").lower()
            is_prescription = "prescription" in legal_status
            
            response_data["sfda_match"] = {
                "trade_name": sfda_match.get("trade_name", ""),
                "trade_name_ar": sfda_match.get("trade_name_ar", ""),
                "package_size": sfda_match.get("package_size", 0),
                "strength": sfda_match.get("strength", ""),
                "strength_unit": sfda_match.get("strength_unit", ""),
                "dosage_form": sfda_match.get("dosage_form", ""),
                "dosage_form_ar": sfda_match.get("dosage_form_ar", ""),
                "price_sar": sfda_match.get("price_sar", 0),
                "legal_status": sfda_match.get("legal_status", ""),
                "legal_status_ar": sfda_match.get("legal_status_ar", ""),
                "is_prescription": is_prescription
            }
            
            if treatment_duration_days:
                response_data["sfda_match"]["calculated_treatment_duration_days"] = treatment_duration_days
            
            # Add prescription warning if applicable
            if is_prescription:
                response_data["prescription_warning"] = {
                    "ar": "⚠️ هذا الدواء يحتاج وصفة طبية. الجرعات تختلف باختلاف الحالة الطبية ودائماً يجب الرجوع للطبيب المعالج.",
                    "en": "⚠️ This medication requires a prescription. Dosages vary depending on the medical condition and you should always consult your treating physician."
                }
        
        return {
            "success": True,
            "data": response_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching AI drug info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# ADMIN ROUTES
# ============================================

@api_router.put("/admin/users/{user_id}/subscription")
async def update_user_subscription(
    user_id: str,
    subscription_data: dict,
    admin_user: dict = Depends(get_admin_user)
):
    """Update user subscription tier"""
    try:
        tier = subscription_data.get("tier")
        duration_days = {
            "weekly": 7,
            "monthly": 30,
            "yearly": 365
        }.get(tier, 30)
        
        end_date = datetime.now(timezone.utc) + timedelta(days=duration_days)
        
        await db.users.update_one(
            {"id": user_id},
            {
                "$set": {
                    "subscription_tier": tier,
                    "subscription_status": "active",
                    "subscription_end_date": end_date.isoformat(),
                    "is_premium": True
                }
            }
        )
        
        return {"success": True, "message": "Subscription updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.put("/admin/users/{user_id}/disable")
async def disable_user_account(
    user_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """Disable user account"""
    try:
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"account_disabled": True, "disabled_at": datetime.now(timezone.utc).isoformat()}}
        )
        return {"success": True, "message": "User disabled"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/analytics")
async def get_admin_analytics(admin_user: dict = Depends(get_admin_user)):
    """Get advanced analytics"""
    try:
        # Total registered
        total_users = await db.users.count_documents({})
        
        # Active users (logged in last 7 days)
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        active_users = await db.users.count_documents({
            "last_login": {"$gte": seven_days_ago.isoformat()}
        })
        
        # Deleted accounts
        deleted_users = await db.users.count_documents({"account_deleted": True})
        
        # Gender distribution (if available)
        gender_stats = {
            "male": await db.users.count_documents({"gender": "male"}),
            "female": await db.users.count_documents({"gender": "female"}),
            "other": await db.users.count_documents({"gender": "other"}),
            "not_specified": await db.users.count_documents({"gender": {"$exists": False}})
        }
        
        # Age distribution (if available)
        # This would need birth_date field
        
        # User growth over time (last 30 days)
        user_growth = []
        for i in range(30, -1, -1):
            date = datetime.now(timezone.utc) - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            count = await db.users.count_documents({
                "created_at": {"$lte": date.isoformat()}
            })
            user_growth.append({"date": date_str, "count": count})
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "deleted_users": deleted_users,
            "gender_stats": gender_stats,
            "user_growth": user_growth
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/top-medications")
async def get_top_medications(admin_user: dict = Depends(get_admin_user)):
    """Get top 100 most added medications"""
    try:
        # Aggregate medications by name
        pipeline = [
            {"$group": {
                "_id": "$medication_name",
                "count": {"$sum": 1},
                "users": {"$addToSet": "$user_id"}
            }},
            {"$project": {
                "_id": 0,
                "name": "$_id",
                "count": 1,
                "unique_users": {"$size": "$users"}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 100}
        ]
        
        top_meds = await db.user_medications.aggregate(pipeline).to_list(length=100)
        
        return {"medications": top_meds}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/contact-messages")
async def get_contact_messages(admin_user: dict = Depends(get_admin_user)):
    """Get all contact messages from users"""
    try:
        messages = await db.contact_messages.find(
            {},
            {"_id": 0}
        ).sort("created_at", -1).to_list(length=100)
        
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/reply-message")
async def reply_to_message(
    reply_data: dict,
    admin_user: dict = Depends(get_admin_user)
):
    """Reply to a contact message"""
    try:
        message_id = reply_data.get("message_id")
        reply = reply_data.get("reply")
        
        if not message_id or not reply:
            raise HTTPException(status_code=400, detail="Message ID and reply required")
        
        # Update the message with admin reply
        result = await db.contact_messages.update_one(
            {"id": message_id},
            {
                "$set": {
                    "admin_reply": reply,
                    "is_read": True,
                    "replied_at": datetime.now(timezone.utc).isoformat(),
                    "replied_by": admin_user["id"]
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Message not found")
        
        return {"success": True, "message": "Reply sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@api_router.post("/admin/send-notification-bulk")
async def send_notification_bulk(
    notification_data: dict,
    admin_user: dict = Depends(get_admin_user)
):
    """Send notification to multiple users by category"""
    try:
        title = notification_data.get("title")
        body = notification_data.get("body")
        category = notification_data.get("category", "all")  # all, new, premium, trial
        
        if not title or not body:
            raise HTTPException(status_code=400, detail="Title and body required")
        
        # Build query based on category
        query = {}
        if category == "new":
            # Users registered in last 7 days
            seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
            query["created_at"] = {"$gte": seven_days_ago.isoformat()}
        elif category == "premium":
            query["is_premium"] = True
        elif category == "trial":
            query["subscription_tier"] = "trial"
        
        # Get matching users
        users = await db.users.find(query, {"id": 1, "_id": 0}).to_list(length=None)
        
        # Create notifications
        notifications = []
        for user in users:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "title": title,
                "body": body,
                "type": "admin",
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            notifications.append(notification)
        
        if notifications:
            await db.notifications.insert_many(notifications)
        
        return {
            "success": True,
            "message": f"Sent to {len(notifications)} users",
            "count": len(notifications)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/stats")
async def get_admin_stats(admin_user: dict = Depends(get_admin_user)):
    """Get dashboard statistics for admin"""
    try:
        # Total users
        total_users = await db.users.count_documents({})
        active_users = await db.users.count_documents({"is_premium": False})
        premium_users = await db.users.count_documents({"is_premium": True})
        
        # Total medications added
        total_medications = await db.user_medications.count_documents({})
        active_medications = await db.user_medications.count_documents({"active": True})
        
        # SFDA Database stats
        total_sfda_meds = await db.sfda_medications.count_documents({})
        
        # Recent users (last 7 days)
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        recent_users = await db.users.count_documents({
            "created_at": {"$gte": seven_days_ago}
        })
        
        # Recent medications (last 7 days)
        recent_medications = await db.user_medications.count_documents({
            "created_at": {"$gte": seven_days_ago}
        })
        
        return {
            "success": True,
            "stats": {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "premium": premium_users,
                    "recent": recent_users
                },
                "medications": {
                    "total": total_medications,
                    "active": active_medications,
                    "recent": recent_medications
                },
                "sfda": {
                    "total": total_sfda_meds
                }
            }
        }
    except Exception as e:
        logging.error(f"Error getting admin stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/users")
async def get_all_users(
    skip: int = 0,
    limit: int = 50,
    search: str = None,
    filter_type: str = None,  # "all", "premium", "free", "admin"
    admin_user: dict = Depends(get_admin_user)
):
    """Get all users with pagination and filters"""
    try:
        query = {}
        
        # Search filter
        if search:
            query["$or"] = [
                {"email": {"$regex": search, "$options": "i"}},
                {"full_name": {"$regex": search, "$options": "i"}}
            ]
        
        # Type filter
        if filter_type == "premium":
            query["is_premium"] = True
        elif filter_type == "free":
            query["is_premium"] = False
        elif filter_type == "admin":
            query["is_admin"] = True
        
        # Get users
        users = await db.users.find(
            query,
            {"password_hash": 0, "_id": 0}
        ).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
        
        # Get total count
        total = await db.users.count_documents(query)
        
        # Get medication count for each user
        for user in users:
            med_count = await db.user_medications.count_documents({
                "user_id": user["id"],
                "active": True
            })
            user["medication_count"] = med_count
        
        return {
            "success": True,
            "users": users,
            "total": total,
            "page": skip // limit + 1 if limit > 0 else 1,
            "pages": (total + limit - 1) // limit if limit > 0 else 1
        }
    except Exception as e:
        logging.error(f"Error getting users: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/user/{user_id}")
async def get_user_details(
    user_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """Get detailed information about a specific user"""
    try:
        # Get user
        user = await db.users.find_one({"id": user_id}, {"password_hash": 0, "_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get user medications
        medications = await db.user_medications.find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(length=None)
        
        # Get health data
        health_data = await db.profile_health.find_one(
            {"user_id": user_id},
            {"_id": 0}
        )
        
        # Get reminders
        reminders = await db.medication_reminders.find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(length=None)
        
        return {
            "success": True,
            "user": user,
            "medications": medications,
            "health_data": health_data,
            "reminders": reminders,
            "stats": {
                "total_medications": len(medications),
                "active_medications": len([m for m in medications if m.get("active")]),
                "total_reminders": len(reminders),
                "active_reminders": len([r for r in reminders if r.get("enabled")])
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting user details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/user/{user_id}")
async def update_user_admin(
    user_id: str,
    request: dict,
    admin_user: dict = Depends(get_admin_user)
):
    """Update user settings (premium status, admin status) - accepts JSON body"""
    try:
        # Extract updates from request body
        updates = {}
        if "is_premium" in request and request["is_premium"] is not None:
            updates["is_premium"] = request["is_premium"]
        if "is_admin" in request and request["is_admin"] is not None:
            updates["is_admin"] = request["is_admin"]
        
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        # Log with email or phone (for admins without email)
        admin_identifier = admin_user.get('email') or admin_user.get('phone') or 'unknown'
        logging.info(f"Admin {admin_identifier} updating user {user_id} with: {updates}")
        
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": updates}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "success": True,
            "message": "User updated successfully",
            "updates": updates
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/user/{user_id}")
@api_router.delete("/admin/users/{user_id}")
async def delete_user_admin(
    user_id: str,
    admin_user: dict = Depends(get_admin_user)
):
    """Delete a user account and all associated data - Admin only"""
    try:
        # Get the user to be deleted
        user_to_delete = await db.users.find_one({"id": user_id}, {"_id": 0})
        
        if not user_to_delete:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prevent deleting yourself
        if user_id == admin_user.get('id'):
            raise HTTPException(
                status_code=403, 
                detail="Cannot delete your own account"
            )
        
        # Allow deleting other admins (removed restriction)
        
        # Delete all user data
        # 1. Delete user medications
        meds_result = await db.user_medications.delete_many({"user_id": user_id})
        
        # 2. Delete medication reminders
        reminders_result = await db.medication_reminders.delete_many({"user_id": user_id})
        
        # 3. Delete FCM tokens
        fcm_result = await db.fcm_tokens.delete_many({"user_id": user_id})
        
        # 4. Delete notifications
        notif_result = await db.notifications.delete_many({"user_id": user_id})
        
        # 5. Delete user account
        user_result = await db.users.delete_one({"id": user_id})
        
        admin_identifier = admin_user.get('email') or admin_user.get('phone') or 'unknown'
        logging.info(f"Admin {admin_identifier} deleted user {user_id} - Deleted: {meds_result.deleted_count} medications, {reminders_result.deleted_count} reminders, {fcm_result.deleted_count} FCM tokens, {notif_result.deleted_count} notifications")
        
        return {
            "success": True,
            "message": "User account deleted successfully",
            "deleted": {
                "user": user_result.deleted_count,
                "medications": meds_result.deleted_count,
                "reminders": reminders_result.deleted_count,
                "fcm_tokens": fcm_result.deleted_count,
                "notifications": notif_result.deleted_count
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/analytics")
async def get_analytics(
    days: int = 30,
    admin_user: dict = Depends(get_admin_user)
):
    """Get analytics and reports"""
    try:
        # Date range
        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # User growth
        users_by_day = []
        for i in range(days):
            day_start = (datetime.now(timezone.utc) - timedelta(days=days-i)).isoformat()
            day_end = (datetime.now(timezone.utc) - timedelta(days=days-i-1)).isoformat()
            count = await db.users.count_documents({
                "created_at": {"$gte": day_start, "$lt": day_end}
            })
            users_by_day.append({
                "date": day_start.split("T")[0],
                "count": count
            })
        
        # Most added medications
        pipeline = [
            {"$match": {"active": True}},
            {"$group": {
                "_id": "$brand_name",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        top_meds = await db.user_medications.aggregate(pipeline).to_list(length=10)
        
        # Most searched SFDA medications (from recent user medications)
        recent_meds = await db.user_medications.find(
            {"created_at": {"$gte": start_date}},
            {"brand_name": 1, "_id": 0}
        ).limit(100).to_list(length=100)
        
        # Activity stats
        total_meds_added = await db.user_medications.count_documents({
            "created_at": {"$gte": start_date}
        })
        
        total_reminders_created = await db.medication_reminders.count_documents({
            "created_at": {"$gte": start_date}
        })
        
        return {
            "success": True,
            "analytics": {
                "user_growth": users_by_day,
                "top_medications": top_meds,
                "activity": {
                    "medications_added": total_meds_added,
                    "reminders_created": total_reminders_created
                }
            }
        }
    except Exception as e:
        logging.error(f"Error getting analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/sfda/upload")
async def upload_sfda_file(
    file: UploadFile = File(...),
    admin_user: dict = Depends(get_admin_user)
):
    """Upload new SFDA Excel file and update database"""
    try:
        # Save uploaded file
        file_path = f"/tmp/sfda_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Process Excel file
        import pandas as pd
        df = pd.read_excel(file_path)
        
        medications = []
        for idx, row in df.iterrows():
            med = {
                "manufacturer": str(row['Manufacturer']).strip() if pd.notna(row['Manufacturer']) else "",
                "trade_name": str(row['Trade Name']).strip() if pd.notna(row['Trade Name']) else "",
                "trade_name_lower": str(row['Trade Name']).strip().lower() if pd.notna(row['Trade Name']) else "",
                "strength": str(row['Strength']).strip() if pd.notna(row['Strength']) else "",
                "pack": str(row['Pack']).strip() if pd.notna(row['Pack']) else "",
                "active_ingredients": str(row['Active Ingrediants']).strip() if pd.notna(row['Active Ingrediants']) else "",
                "active_ingredients_lower": str(row['Active Ingrediants']).strip().lower() if pd.notna(row['Active Ingrediants']) else "",
                "price_sar": float(row['MOH Price']) if pd.notna(row['MOH Price']) else None,
                "source": "SFDA",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            medications.append(med)
        
        # Drop old collection and insert new
        await db.sfda_medications.drop()
        if medications:
            await db.sfda_medications.insert_many(medications)
        
        # Recreate indexes
        await db.sfda_medications.create_index("trade_name_lower")
        await db.sfda_medications.create_index("active_ingredients_lower")
        await db.sfda_medications.create_index("manufacturer")
        
        # Clean up
        import os
        os.remove(file_path)
        
        return {
            "success": True,
            "message": "SFDA database updated successfully",
            "total_medications": len(medications)
        }
    except Exception as e:
        logging.error(f"Error uploading SFDA file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/sfda/stats")
async def get_sfda_stats(admin_user: dict = Depends(get_admin_user)):
    """Get SFDA database statistics"""
    try:
        total = await db.sfda_medications.count_documents({})
        
        # Count by manufacturer
        pipeline = [
            {"$group": {
                "_id": "$manufacturer",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        top_manufacturers = await db.sfda_medications.aggregate(pipeline).to_list(length=10)
        
        # Price statistics
        pipeline_price = [
            {"$match": {"price_sar": {"$ne": None}}},
            {"$group": {
                "_id": None,
                "avg_price": {"$avg": "$price_sar"},
                "min_price": {"$min": "$price_sar"},
                "max_price": {"$max": "$price_sar"}
            }}
        ]
        price_stats = await db.sfda_medications.aggregate(pipeline_price).to_list(length=1)
        
        return {
            "success": True,
            "stats": {
                "total": total,
                "top_manufacturers": top_manufacturers,
                "price_stats": price_stats[0] if price_stats else {}
            }
        }
    except Exception as e:
        logging.error(f"Error getting SFDA stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Support Ticket Models
class SupportTicketCreate(BaseModel):
    """Model for creating a support ticket"""
    subject: str
    message: str
    category: str  # "bug", "feature", "payment", "general"

class SupportTicket(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_email: str
    user_name: str
    subject: str
    message: str
    category: str  # "bug", "feature", "payment", "general"
    status: str = "open"  # "open", "in_progress", "closed"
    priority: str = "medium"  # "low", "medium", "high"
    admin_response: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@api_router.post("/support/ticket")
async def create_support_ticket(
    ticket_data: SupportTicketCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a support ticket"""
    try:
        ticket = SupportTicket(
            user_id=current_user["id"],
            user_email=current_user["email"],
            user_name=current_user["full_name"],
            subject=ticket_data.subject,
            message=ticket_data.message,
            category=ticket_data.category
        )
        
        await db.support_tickets.insert_one(ticket.dict())
        
        return {
            "success": True,
            "message": "Support ticket created successfully",
            "ticket_id": ticket.id
        }
    except Exception as e:
        logging.error(f"Error creating support ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/support/tickets")
async def get_support_tickets(
    status: str = None,
    category: str = None,
    skip: int = 0,
    limit: int = 50,
    admin_user: dict = Depends(get_admin_user)
):
    """Get all support tickets with filters"""
    try:
        query = {}
        if status:
            query["status"] = status
        if category:
            query["category"] = category
        
        tickets = await db.support_tickets.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
        
        total = await db.support_tickets.count_documents(query)
        
        return {
            "success": True,
            "tickets": tickets,
            "total": total
        }
    except Exception as e:
        logging.error(f"Error getting support tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.patch("/admin/support/ticket/{ticket_id}")
async def update_support_ticket(
    ticket_id: str,
    status: str = None,
    priority: str = None,
    admin_response: str = None,
    admin_user: dict = Depends(get_admin_user)
):
    """Update support ticket"""
    try:
        updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if status:
            updates["status"] = status
        if priority:
            updates["priority"] = priority
        if admin_response:
            updates["admin_response"] = admin_response
        
        result = await db.support_tickets.update_one(
            {"id": ticket_id},
            {"$set": updates}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        return {
            "success": True,
            "message": "Ticket updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating support ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# FREEMIUM LIMITS & HELPER FUNCTIONS
# =============================================================================

FREE_USER_LIMITS = {
    "max_medications": 100,  # Increased for testing
    "max_sfda_searches": 100,  # Increased for testing
    "max_reminders": 100,  # Increased for testing
    "reminder_expiry_days": 30  # Increased for testing
}

async def check_medication_limit(user_id: str, is_premium: bool) -> bool:
    """Check if user can add more medications based on total attempts (not active count)"""
    if is_premium:
        return True
    
    # Check total medications added (never decreases even after deletion)
    user = await db.users.find_one({"id": user_id}, {"medications_added_count": 1})
    if not user:
        return False
    
    medications_added = user.get("medications_added_count", 0)
    return medications_added < FREE_USER_LIMITS["max_medications"]

async def check_sfda_search_limit(user_id: str, is_premium: bool, current_searches: int) -> bool:
    """Check if user can perform more SFDA searches"""
    if is_premium:
        return True
    
    return current_searches < FREE_USER_LIMITS["max_sfda_searches"]

async def check_reminder_limit(user_id: str, is_premium: bool) -> bool:
    """Check if user can add more reminders"""
    if is_premium:
        return True
    
    count = await db.medication_reminders.count_documents({"user_id": user_id, "enabled": True})
    return count < FREE_USER_LIMITS["max_reminders"]

async def cleanup_expired_reminders():
    """Delete reminders for free users that are older than 3 days"""
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=FREE_USER_LIMITS["reminder_expiry_days"])).isoformat()
        
        # Get all non-premium users
        free_users = await db.users.find({"is_premium": False}, {"id": 1}).to_list(length=None)
        free_user_ids = [user["id"] for user in free_users]
        
        # Delete old reminders for free users
        result = await db.medication_reminders.delete_many({
            "user_id": {"$in": free_user_ids},
            "created_at": {"$lt": cutoff_date}
        })
        
        if result.deleted_count > 0:
            logger.info(f"Deleted {result.deleted_count} expired reminders for free users")
    except Exception as e:
        logger.error(f"Error cleaning up expired reminders: {e}")


# =============================================================================
# TAP PAYMENTS & SUBSCRIPTIONS
# ===========================

# Import Tap Payments client
try:
    from tap_payments import TapPaymentsClient
    TAP_ENABLED = True
    tap_client = TapPaymentsClient()
except Exception as e:
    print(f"⚠️ Tap Payments not available: {e}")
    TAP_ENABLED = False
    tap_client = None

# Subscription Plans
SUBSCRIPTION_PLANS = {
    "monthly": {
        "id": "premium_monthly",
        "name": "Premium شهري",
        "name_en": "Premium Monthly",
        "amount": 29.99,
        "currency": "SAR",
        "billing_interval": "month",
        "features": [
            "تذكيرات غير محدودة",
            "تقارير صحية متقدمة", 
            "تحليل الالتزام بالدواء",
            "نسخ احتياطي للبيانات",
            "دعم فني أولوية",
            "بدون إعلانات"
        ],
        "features_en": [
            "Unlimited reminders",
            "Advanced health reports",
            "Medication adherence analysis", 
            "Data backup",
            "Priority support",
            "No ads"
        ]
    },
    "yearly": {
        "id": "premium_yearly",
        "name": "Premium سنوي",
        "name_en": "Premium Yearly",
        "amount": 249.99,
        "currency": "SAR",
        "billing_interval": "year",
        "discount": "30%",
        "save_amount": 109.89,
        "features": [
            "كل مميزات الشهري",
            "خصم 30% - وفر 110 ريال!",
            "3 أشهر مجاناً! 🎁",
            "تذكيرات غير محدودة",
            "تقارير صحية متقدمة",
            "تحليل الالتزام بالدواء",
            "نسخ احتياطي للبيانات",
            "دعم فني أولوية VIP",
            "بدون إعلانات"
        ],
        "features_en": [
            "All monthly features",
            "30% discount - Save 110 SAR!",
            "3 months free! 🎁",
            "Unlimited reminders",
            "Advanced health reports",
            "Medication adherence analysis",
            "Data backup",
            "VIP priority support",
            "No ads"
        ]
    }
}

class ChargeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_id: str
    source_id: str
    customer_name: str
    customer_email: str

@api_router.get("/subscription-plans")
async def get_subscription_plans():
    """Get available subscription plans"""
    return {
        "success": True,
        "plans": SUBSCRIPTION_PLANS
    }

@api_router.post("/create-checkout")
async def create_checkout(
    plan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Create Tap checkout session for subscription"""
    
    if not TAP_ENABLED:
        raise HTTPException(status_code=503, detail="Payment service unavailable")
    
    import httpx
    
    try:
        # Get plan details
        plan = SUBSCRIPTION_PLANS.get(plan_id.replace("premium_", ""))
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Get frontend URL for redirect
        frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
        
        # Create checkout session via Tap API
        payload = {
            "amount": plan["amount"],
            "currency": plan["currency"],
            "customer_initiated": True,
            "threeDSecure": True,
            "save_card": False,
            "description": f"PharmaPal {plan['name']} Subscription",
            "metadata": {
                "user_id": current_user["id"],
                "plan_id": plan_id,
                "udf1": current_user.get("email", current_user.get("phone", ""))
            },
            "reference": {
                "transaction": f"txn_{current_user['id']}_{int(datetime.now(timezone.utc).timestamp())}",
                "order": f"order_{current_user['id']}_{plan_id}"
            },
            "receipt": {
                "email": True,
                "sms": True
            },
            "customer": {
                "first_name": current_user.get("full_name", "User").split()[0] if current_user.get("full_name") else "User",
                "last_name": " ".join(current_user.get("full_name", "").split()[1:]) if current_user.get("full_name") and len(current_user.get("full_name", "").split()) > 1 else "",
                "email": current_user.get("email") or f"{current_user.get('phone', 'user')}@medtrack.local",
                "phone": {
                    "country_code": "966",
                    "number": current_user.get("phone", "5000000000").replace("+966", "").replace("966", "").lstrip("0")
                }
            },
            "merchant": {
                "id": ""
            },
            "source": {
                "id": "src_all"
            },
            "post": {
                "url": f"{frontend_url}/payment-callback"
            },
            "redirect": {
                "url": f"{frontend_url}/payment-success"
            }
        }
        
        # Call Tap API to create charge
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{tap_client.base_url}/v2/charges",
                json=payload,
                headers=tap_client.headers,
                timeout=30.0
            )
            response.raise_for_status()
            charge_result = response.json()
        
        # Store payment record
        payment_record = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "charge_id": charge_result.get("id"),
            "plan_id": plan_id,
            "amount": plan["amount"],
            "currency": plan["currency"],
            "status": charge_result.get("status", "INITIATED"),
            "tap_response": charge_result,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.payments.insert_one(payment_record)
        
        logger.info(f"Created checkout session {charge_result.get('id')} for user {current_user['id']}")
        
        # Return the transaction URL where user should be redirected
        transaction_url = charge_result.get("transaction", {}).get("url")
        
        if not transaction_url:
            raise HTTPException(status_code=500, detail="Failed to get payment URL from Tap")
        
        return {
            "success": True,
            "charge_id": charge_result.get("id"),
            "payment_url": transaction_url,
            "status": charge_result.get("status")
        }
        
    except httpx.HTTPError as e:
        logger.error(f"Tap API error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response: {e.response.text}")
        raise HTTPException(status_code=400, detail=f"Payment initialization failed: {str(e)}")
    except Exception as e:
        logger.error(f"Checkout creation error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Payment failed: {str(e)}")

@api_router.get("/payment-status/{charge_id}")
async def get_payment_status(
    charge_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Check payment status and update user premium if successful"""
    
    if not TAP_ENABLED:
        raise HTTPException(status_code=503, detail="Payment service unavailable")
    
    try:
        # Get charge from Tap
        charge_data = await tap_client.retrieve_charge(charge_id)
        
        # Update payment record
        payment = await db.payments.find_one({"charge_id": charge_id}, {"_id": 0})
        
        if payment:
            await db.payments.update_one(
                {"charge_id": charge_id},
                {"$set": {
                    "status": charge_data.get("status"),
                    "tap_response": charge_data,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # If payment captured, activate premium
            if charge_data.get("status") == "CAPTURED":
                plan_id = payment.get("plan_id", "")
                
                # Calculate expiry based on plan
                now = datetime.now(timezone.utc)
                if "monthly" in plan_id:
                    expiry = now + timedelta(days=30)
                else:  # yearly
                    expiry = now + timedelta(days=365)
                
                # Update user premium status
                await db.users.update_one(
                    {"id": current_user["id"]},
                    {"$set": {
                        "is_premium": True,
                        "premium_expires_at": expiry.isoformat(),
                        "premium_plan": plan_id
                    }}
                )
                
                logger.info(f"Activated premium for user {current_user['id']}")
        
        return {
            "success": True,
            "status": charge_data.get("status"),
            "amount": charge_data.get("amount"),
            "currency": charge_data.get("currency")
        }
        
    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Status check failed: {str(e)}")


# Router will be included at the end of file after all routes are defined

# Subscription Management Endpoints

@api_router.post("/admin/activate-premium-self")
async def activate_premium_self(admin_user: dict = Depends(get_admin_user)):
    """Admin can activate premium features for themselves forever"""
    try:
        admin_id = admin_user.get("id")
        
        # Update admin to have premium forever
        await db.users.update_one(
            {"id": admin_id},
            {
                "$set": {
                    "is_premium": True,
                    "subscription_status": "active",
                    "subscription_tier": "lifetime",
                    "subscription_end_date": None,  # No expiry
                    "premium_activated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        return {
            "success": True,
            "message": "Premium features activated forever"
        }
        
    except Exception as e:
        logger.error(f"Error activating premium: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/subscription/status")
async def check_subscription_status(authorization: str = Header(None)):
    """Check if user's subscription is still valid"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    user_data = verify_jwt_token(token)
    user_id = user_data.get("user_id")
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    now = datetime.now(timezone.utc)
    
    # Check if subscription is still valid
    is_active = False
    days_remaining = 0
    hours_remaining = 0
    
    if user.get("subscription_end_date"):
        end_date = datetime.fromisoformat(user["subscription_end_date"].replace('Z', '+00:00'))
        time_remaining = end_date - now
        
        is_active = time_remaining.total_seconds() > 0
        days_remaining = time_remaining.days
        hours_remaining = int(time_remaining.total_seconds() / 3600)
        
        # Update trial_used if trial has expired
        if user.get("subscription_tier") == "trial" and not is_active and not user.get("trial_used"):
            await db.users.update_one(
                {"id": user_id},
                {"$set": {"trial_used": True}}
            )
    
    return {
        "is_active": is_active,
        "subscription_tier": user.get("subscription_tier", "trial"),
        "subscription_end_date": user.get("subscription_end_date"),
        "days_remaining": days_remaining,
        "hours_remaining": hours_remaining,
        "trial_used": user.get("trial_used", False)
    }

@api_router.post("/subscription/upgrade")
async def upgrade_subscription(
    tier: str,
    authorization: str = Header(None)
):
    """Upgrade user subscription"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    user_data = verify_jwt_token(token)
    user_id = user_data.get("user_id")
    
    # Define subscription durations
    durations = {
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
        "yearly": timedelta(days=365)
    }
    
    if tier not in durations:
        raise HTTPException(status_code=400, detail="Invalid subscription tier")
    
    now = datetime.now(timezone.utc)
    end_date = now + durations[tier]
    
    await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "subscription_tier": tier,
                "subscription_start_date": now.isoformat(),
                "subscription_end_date": end_date.isoformat(),
                "is_premium": True
            }
        }
    )
    
    return {
        "success": True,
        "subscription_tier": tier,
        "subscription_end_date": end_date.isoformat()
    }

@api_router.delete("/account")
async def delete_account(authorization: str = Header(None)):
    """Delete user account - marks phone as used to prevent re-registration"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    user_data = verify_jwt_token(token)
    user_id = user_data.get("user_id")
    
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Mark account as deleted and keep trial_used status
    await db.users.update_one(
        {"id": user_id},
        {
            "$set": {
                "account_deleted": True,
                "trial_used": user.get("trial_used", False),
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Delete user's medications and reminders
    await db.user_medications.delete_many({"user_id": user_id})
    await db.reminders.delete_many({"user_id": user_id})
    await db.notifications.delete_many({"user_id": user_id})
    
    return {"success": True, "message": "Account deleted successfully"}

# ============================================
# CONTACT US & EMAIL ENDPOINTS
# ============================================

class ContactEmailRequest(BaseModel):
    """Model for contact form submission"""
    subject: str
    message: str
    user_name: Optional[str] = None
    user_phone: Optional[str] = None

@api_router.post("/send-contact-email")
async def send_contact_email(
    contact_data: ContactEmailRequest,
    current_user: dict = Depends(get_current_user)
):
    """Send contact form email to info@pharmapal.online"""
    try:
        if not EMAIL_ENABLED or not email_service.is_configured():
            # Save to database as fallback
            contact_message = {
                "id": str(uuid.uuid4()),
                "user_id": current_user["id"],
                "user_name": current_user.get("full_name", ""),
                "user_phone": current_user.get("phone", ""),
                "subject": contact_data.subject,
                "message": contact_data.message,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.contact_messages.insert_one(contact_message)
            
            return {
                "success": True,
                "message": "Message saved. Email service is not configured.",
                "saved_to_db": True
            }
        
        # Prepare email content
        user_name = current_user.get("full_name", "مستخدم")
        user_phone = current_user.get("phone", "غير متوفر")
        
        email_subject = f"رسالة من PharmaPal: {contact_data.subject}"
        
        email_body = f"""
رسالة جديدة من تطبيق PharmaPal

نوع الرسالة: {contact_data.subject}

من: {user_name}
رقم الهاتف: {user_phone}

الرسالة:
{contact_data.message}

---
تم الإرسال في: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        
        html_body = f"""
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #10b981 0%, #14b8a6 100%); color: white; padding: 20px; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f9fafb; padding: 20px; border: 1px solid #e5e7eb; }}
        .footer {{ background: #f3f4f6; padding: 15px; text-center; font-size: 12px; color: #6b7280; border-radius: 0 0 10px 10px; }}
        .info-row {{ margin: 10px 0; padding: 10px; background: white; border-radius: 5px; }}
        .label {{ font-weight: bold; color: #059669; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin: 0;">💊 PharmaPal</h2>
            <p style="margin: 5px 0 0 0;">رسالة جديدة من تطبيق PharmaPal</p>
        </div>
        <div class="content">
            <div class="info-row">
                <span class="label">نوع الرسالة:</span> {contact_data.subject}
            </div>
            <div class="info-row">
                <span class="label">من:</span> {user_name}
            </div>
            <div class="info-row">
                <span class="label">رقم الهاتف:</span> {user_phone}
            </div>
            <div class="info-row">
                <span class="label">الرسالة:</span>
                <p style="margin-top: 10px; white-space: pre-wrap;">{contact_data.message}</p>
            </div>
        </div>
        <div class="footer">
            تم الإرسال في: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
        </div>
    </div>
</body>
</html>
"""
        
        # Send email
        success = email_service.send_email(
            to_email="info@pharmapal.online",
            subject=email_subject,
            body=email_body,
            html_body=html_body
        )
        
        # Save to database regardless of email success
        contact_message = {
            "id": str(uuid.uuid4()),
            "user_id": current_user["id"],
            "user_name": user_name,
            "user_phone": user_phone,
            "subject": contact_data.subject,
            "message": contact_data.message,
            "status": "sent" if success else "failed",
            "email_sent": success,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.contact_messages.insert_one(contact_message)
        
        if success:
            return {
                "success": True,
                "message": "Email sent successfully",
                "email_sent": True
            }
        else:
            return {
                "success": False,
                "message": "Failed to send email, but message was saved",
                "email_sent": False,
                "saved_to_db": True
            }
            
    except Exception as e:
        logger.error(f"Error in send_contact_email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# ADMIN NOTIFICATION ENDPOINTS
# ============================================

@api_router.post("/admin/notifications/broadcast")
async def broadcast_notification(
    notification_data: dict,
    admin_user: dict = Depends(get_admin_user)
):
    """Send notification to all users"""
    try:
        title = notification_data.get("title")
        body = notification_data.get("body")
        notification_type = notification_data.get("type", "info")
        
        if not title or not body:
            raise HTTPException(status_code=400, detail="Title and body are required")
        
        # Get all users
        users = await db.users.find({}, {"id": 1, "_id": 0}).to_list(length=None)
        
        # Create notifications for all users
        notifications = []
        for user in users:
            notification = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "title": title,
                "body": body,
                "type": notification_type,
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            notifications.append(notification)
        
        if notifications:
            await db.notifications.insert_many(notifications)
        
        # If Firebase is enabled, send push notifications
        if FIREBASE_ENABLED:
            try:
                # Get all FCM tokens
                tokens_cursor = db.fcm_tokens.find({}, {"token": 1, "_id": 0})
                tokens = await tokens_cursor.to_list(length=None)
                fcm_tokens = [t["token"] for t in tokens if t.get("token")]
                
                if fcm_tokens:
                    pass
            except Exception as e:
                logger.warning(f"Failed to send push notifications: {e}")
        
        return {
            "success": True,
            "message": f"Notification sent to {len(notifications)} users",
            "count": len(notifications)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/notifications/send")
async def send_notification_to_user(
    notification_data: dict,
    admin_user: dict = Depends(get_admin_user)
):
    """Send notification to a specific user"""
    try:
        user_id = notification_data.get("user_id")
        title = notification_data.get("title")
        body = notification_data.get("body")
        notification_type = notification_data.get("type", "info")
        
        if not user_id or not title or not body:
            raise HTTPException(status_code=400, detail="user_id, title, and body are required")
        
        # Verify user exists
        user = await db.users.find_one({"id": user_id}, {"id": 1})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Create notification
        notification = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title,
            "body": body,
            "type": notification_type,
            "read": False,
            "created_at": datetime.now(timezone.utc)
        }
        
        # Insert notification
        await db.notifications.insert_one(notification)
        
        return {"success": True, "message": "Notification sent successfully"}
    
    except Exception as e:
        logging.error(f"Error sending notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/medications/dosage-info")
async def get_multi_source_dosage(
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Get dosage information from multiple reliable sources
    Supports multiple active ingredients with strict matching
    """
    try:
        drug_name = request.get('drug_name')
        use_ai = request.get('use_ai_verification', True)
        
        if not drug_name:
            raise HTTPException(status_code=400, detail="drug_name is required")
        
        # Get dosage info from multiple sources
        result = await dosage_service.get_dosage_info(drug_name, use_ai)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/admin/notifications/stats")
async def get_notification_stats(admin_user: dict = Depends(get_admin_user)):
    """Get notification statistics"""
    try:
        total_sent = await db.notifications.count_documents({})
        total_read = await db.notifications.count_documents({"read": True})
        total_unread = await db.notifications.count_documents({"read": False})
        
        # Get recent notifications
        recent_notifications = await db.notifications.find(
            {},
            {"_id": 0}
        ).sort("created_at", -1).limit(20).to_list(length=20)
        
        return {
            "success": True,
            "total_sent": total_sent,
            "total_read": total_read,
            "total_unread": total_unread,
            "recent_notifications": recent_notifications
        }
        
    except Exception as e:
        logger.error(f"Error getting notification stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)



logger = logging.getLogger(__name__)

# Include the API router in the main app
app.include_router(api_router)

@app.on_event("startup")
async def startup_event():
    await init_sfda_database()
    
    # Create admin account if it doesn't exist
    # Read from environment variables with fallbacks for development
    admin_email = os.environ.get('ADMIN_EMAIL', "admin@pharmapal.com")
    admin_phone = os.environ.get('ADMIN_PHONE', "0500000000")
    admin_password = os.environ.get('ADMIN_PASSWORD', "PharmaAdmin2025!")
    
    # Warn if using default credentials in production
    if admin_password == "PharmaAdmin2025!" and os.environ.get('ENVIRONMENT') == 'production':
        logger.warning("⚠️ Using default admin password in production! Please set ADMIN_PASSWORD environment variable.")
    
    existing_admin = await db.users.find_one({"email": admin_email})
    if not existing_admin:
        admin_user = {
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "phone": admin_phone,
            "password_hash": hash_password(admin_password),
            "full_name": "PharmaPal Admin",
            "phone_verified": True,
            "is_professional": True,
            "is_premium": True,
            "is_admin": True,
            "language": "en",
            "medical_conditions": [],
            "allergies": [],
            "daily_routine": None,
            "sfda_searches_used": 0,
            "medications_added_count": 0,
            "subscription_tier": "premium",
            "subscription_start_date": datetime.now(timezone.utc),
            "subscription_end_date": None,
            "trial_used": False,
            "account_deleted": False,
            "last_login": None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(admin_user)
        logger.info(f"Admin account created: {admin_email} / {admin_phone}")
    else:
        logger.info("Admin account already exists")
    
    # Start medication reminder scheduler
    if SCHEDULER_ENABLED and FIREBASE_ENABLED:
        start_scheduler()
        logger.info("✅ Medication reminder scheduler started")
    else:
        logger.warning("⚠️ Medication scheduler not started (Firebase or Scheduler disabled)")
    
    logger.info("PharmaPal API started")

@app.on_event("shutdown")
async def shutdown_db_client():
    # Stop scheduler
    if SCHEDULER_ENABLED:
        stop_scheduler()
        logger.info("⏹️ Medication reminder scheduler stopped")
    
    client.close()
