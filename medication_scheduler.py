"""
Medication Reminder Scheduler
Automatically sends push notifications to users when it's time to take their medications
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from motor.motor_asyncio import AsyncIOMotorClient
import os

# Import Firebase functions
try:
    from firebase_config import send_push_notification, send_batch_notifications
    FIREBASE_ENABLED = True
except Exception as e:
    print(f"⚠️ Firebase not available: {e}")
    FIREBASE_ENABLED = False

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'pharmapal_db')]

# Scheduler instance
scheduler = AsyncIOScheduler()


async def check_and_send_medication_reminders():
    """
    Check all medications and send reminders for those due now
    Runs every minute
    """
    try:
        if not FIREBASE_ENABLED:
            logger.warning("Firebase not enabled, skipping medication reminders")
            return
        
        # Get current time in Saudi Arabia timezone (UTC+3)
        # You can adjust timezone based on your needs
        current_time = datetime.now(timezone.utc) + timedelta(hours=3)
        current_hour = current_time.strftime("%H")
        current_minute = current_time.strftime("%M")
        current_time_str = f"{current_hour}:{current_minute}"
        
        logger.info(f"🕐 Checking medication reminders for time: {current_time_str}")
        
        # Find all active medications that have a time matching current time
        medications_cursor = db.user_medications.find({
            "active": True,  # Fixed: changed from "is_active" to "active"
            "times": current_time_str  # Check if current time is in the times array
        })
        
        medications = await medications_cursor.to_list(length=1000)
        
        if not medications:
            logger.info(f"No medications due at {current_time_str}")
            return
        
        logger.info(f"📋 Found {len(medications)} medication(s) due at {current_time_str}")
        
        # Group medications by user_id
        user_medications = {}
        for med in medications:
            user_id = med.get('user_id')
            if user_id not in user_medications:
                user_medications[user_id] = []
            user_medications[user_id].append(med)
        
        # Send notifications to each user
        notifications_sent = 0
        
        for user_id, meds in user_medications.items():
            try:
                logger.info(f"Processing user: {user_id}")
                
                # Get user's FCM tokens
                tokens_cursor = db.fcm_tokens.find({"user_id": user_id})
                tokens_data = await tokens_cursor.to_list(length=100)
                
                logger.info(f"Found {len(tokens_data)} FCM token(s) for user {user_id}")
                
                if not tokens_data:
                    logger.warning(f"⚠️ No FCM tokens found for user {user_id}")
                    continue
                
                # Get user info
                user = await db.users.find_one({"id": user_id}, {"full_name": 1, "_id": 0})
                user_name = user.get('full_name', 'المستخدم') if user else 'المستخدم'
                
                # Prepare notification message
                if len(meds) == 1:
                    # Single medication
                    med = meds[0]
                    title = "⏰ تذكير بتناول الدواء"
                    body = f"حان وقت تناول دواء {med.get('brand_name', 'الدواء')} - {current_time_str}"
                    
                    # Add dosage info if available
                    if med.get('prescribed_dosage'):
                        body += f"\nالجرعة: {med['prescribed_dosage']}"
                    
                    data = {
                        "type": "medication_reminder",
                        "medication_id": med.get('id', ''),
                        "medication_name": med.get('brand_name', ''),
                        "time": current_time_str
                    }
                else:
                    # Multiple medications
                    title = f"⏰ تذكير بتناول {len(meds)} أدوية"
                    med_names = ", ".join([m.get('brand_name', 'دواء') for m in meds[:3]])
                    if len(meds) > 3:
                        med_names += f" و{len(meds) - 3} أدوية أخرى"
                    body = f"حان وقت تناول: {med_names} - {current_time_str}"
                    
                    data = {
                        "type": "medication_reminder",
                        "count": len(meds),
                        "time": current_time_str
                    }
                
                # Send to all user's devices
                logger.info(f"Attempting to send to {len(tokens_data)} device(s)")
                for token_data in tokens_data:
                    fcm_token = token_data.get('token')
                    logger.info(f"Sending to token: {fcm_token[:20]}...")
                    try:
                        response = await send_push_notification(
                            fcm_token=fcm_token,
                            title=title,
                            body=body,
                            data=data
                        )
                        
                        logger.info(f"Response from Firebase: {response}")
                        
                        if response:
                            notifications_sent += 1
                            logger.info(f"✅ Notification sent to user {user_id}")
                        else:
                            logger.warning(f"⚠️ Firebase returned None/False for token")
                        
                    except Exception as e:
                        logger.error(f"❌ Error sending to token {fcm_token[:20]}...: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        # Remove invalid token
                        await db.fcm_tokens.delete_one({"token": fcm_token})
                
            except Exception as e:
                logger.error(f"❌ Error processing user {user_id}: {e}")
        
        logger.info(f"✅ Sent {notifications_sent} notification(s) for {current_time_str}")
        
    except Exception as e:
        logger.error(f"❌ Error in medication reminder scheduler: {e}")


async def cleanup_expired_tokens():
    """
    Remove FCM tokens that haven't been used in 30 days
    Runs once per day
    """
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        
        result = await db.fcm_tokens.delete_many({
            "last_used": {"$lt": cutoff_date}
        })
        
        if result.deleted_count > 0:
            logger.info(f"🗑️ Cleaned up {result.deleted_count} expired FCM tokens")
        
    except Exception as e:
        logger.error(f"❌ Error cleaning up tokens: {e}")


def start_scheduler():
    """Start the medication reminder scheduler"""
    try:
        # Add job to check medications every minute
        scheduler.add_job(
            check_and_send_medication_reminders,
            'cron',
            minute='*',  # Every minute
            id='medication_reminders',
            replace_existing=True
        )
        
        # Add job to cleanup expired tokens once per day at 3 AM
        scheduler.add_job(
            cleanup_expired_tokens,
            'cron',
            hour=3,
            minute=0,
            id='cleanup_tokens',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("✅ Medication reminder scheduler started")
        logger.info("📅 Checking for reminders every minute")
        logger.info("🧹 Cleaning up expired tokens daily at 3 AM")
        
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {e}")


def stop_scheduler():
    """Stop the scheduler"""
    try:
        scheduler.shutdown()
        logger.info("⏹️ Medication reminder scheduler stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping scheduler: {e}")


# For testing purposes
async def test_scheduler():
    """Test the scheduler by running it manually"""
    logger.info("🧪 Testing medication reminder scheduler...")
    await check_and_send_medication_reminders()


if __name__ == "__main__":
    # Run test
    asyncio.run(test_scheduler())
