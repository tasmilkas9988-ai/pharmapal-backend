import os
import json
import firebase_admin
from firebase_admin import credentials

def initialize_firebase():
    try:
        firebase_json = os.getenv("FIREBASE_PROJECT_JSON")

        if not firebase_json:
            print("⚠️ Firebase service account not found. Push notifications disabled.")
            return None

        firebase_dict = json.loads(firebase_json)

        cred = credentials.Certificate(firebase_dict)
        firebase_admin.initialize_app(cred)

        print("🚀 Firebase Admin SDK initialized successfully")
        return True

    except Exception as e:
        print(f"❌ Error initializing Firebase: {e}")
        return None
