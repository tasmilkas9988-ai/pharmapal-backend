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
        
        # Try to get service account from environment variable
        service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
        
        if service_account_json:
            # Parse JSON from environment variable
            service_account = json.loads(service_account_json)
            cred = credentials.Certificate(service_account)
        else:
            # Try to load from file (for development)
            service_account_path = os.environ.get(
                'FIREBASE_SERVICE_ACCOUNT_PATH',
                '/app/backend/firebase-service-account.json'
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
        
        # Create message
        # Convert all data values to strings (Firebase requires string values)
        string_data = {}
        if data:
            for key, value in data.items():
                string_data[key] = str(value) if value is not None else ""
        
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=string_data,
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    sound='default',
                    channel_id='medication_reminders'
                )
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1
                    )
                )
            ),
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon='/logo192.png',
                    badge='/logo192.png',
                    vibrate=[200, 100, 200],
                    require_interaction=True
                )
            )
        )
        
        # Send message (run in executor since messaging.send is synchronous)
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, messaging.send, message)
        print(f"✅ Notification sent successfully: {response}")
        return response
        
    except Exception as e:
        print(f"❌ Error sending notification: {e}")
        import traceback
        traceback.print_exc()
        return None


async def send_batch_notifications(tokens: list, title: str, body: str, data: dict = None):
    """Send push notification to multiple devices"""
    try:
        if not firebase_admin._apps:
            initialize_firebase()
            
        if not firebase_admin._apps or not tokens:
            return None
        
        # Create multicast message
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            tokens=tokens,
        )
        
        # Send batch
        response = messaging.send_multicast(message)
        print(f"✅ Batch notification sent: {response.success_count} successful, {response.failure_count} failed")
        return response
        
    except Exception as e:
        print(f"❌ Error sending batch notifications: {e}")
        return None


# Initialize on module import
initialize_firebase()
