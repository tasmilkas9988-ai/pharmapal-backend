import firebase_admin
from firebase_admin import credentials, messaging
import os
import json

# Initialize Firebase Admin SDK
def initialize_firebase():
    """Initialize Firebase Admin SDK with service account"""
    try:
        # Check if already initialized
        if firebase_admin._apps:
            return firebase_admin.get_app()
        
        # Load project JSON (without private_key)
        project_json_raw = os.environ.get("FIREBASE_PROJECT_JSON")
        private_key_raw = os.environ.get("FIREBASE_PRIVATE_KEY")

        if project_json_raw and private_key_raw:
            project = json.loads(project_json_raw)
            project["private_key"] = private_key_raw

            cred = credentials.Certificate(project)
        else:
            # Load from file for local development
            service_account_path = os.environ.get(
                "FIREBASE_SERVICE_ACCOUNT_PATH",
                "/app/backend/firebase-service-account.json"
            )

            if os.path.exists(service_account_path):
                cred = credentials.Certificate(service_account_path)
            else:
                print("⚠️ Firebase service account not found. Push notifications disabled.")
                return None

        app = firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin SDK initialized successfully")
        return app
        
    except Exception as e:
        print(f"❌ Error initializing Firebase: {e}")
        return None


async def send_push_notification(fcm_token: str, title: str, body: str, data: dict = None):
    """Send push notification to a specific device"""
    try:
        if not firebase_admin._apps:
            initialize_firebase()
            
        if not firebase_admin._apps:
            print("Firebase not initialized. Skipping notification.")
            return None
        
        # Convert data to string-only
        string_data = {k: str(v) for k, v in (data or {}).items()}

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=string_data,
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="default",
                    channel_id="medication_reminders"
                )
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=1)
                )
            ),
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon="/logo192.png",
                    badge="/logo192.png",
                    vibrate=[200, 100, 200],
                    require_interaction=True
                )
            ),
        )

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, messaging.send, message)

        print(f"✅ Notification sent successfully: {response}")
        return response

    except Exception as e:
        print(f"❌ Error sending notification: {e}")
        return None


async def send_batch_notifications(tokens: list, title: str, body: str, data: dict = None):
    """Send push notification to multiple devices"""
    try:
        if not firebase_admin._apps:
            initialize_firebase()
            
        if not firebase_admin._apps or not tokens:
            return None

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            tokens=tokens,
        )

        response = messaging.send_multicast(message)
        print(f"✅ Batch notification sent: {response.success_count} success, {response.failure_count} failed")
        return response
        
    except Exception as e:
        print(f"❌ Error sending batch notifications: {e}")
        return None


# Initialize on module import
initialize_firebase()
