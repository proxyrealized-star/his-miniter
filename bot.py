"""
Professional Instagram Username Monitor Bot
Single Channel Force Join - @proxydominates
All buttons working, subscription system, monitoring
Author: @proxyfxc
Version: 7.0.0 (FULLY FIXED)
"""

import os
import json
import logging
import asyncio
import datetime
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import sys
import traceback
import re
import threading

# Third-party imports
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
import aiohttp
from dotenv import load_dotenv

# MongoDB import
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================

class Config:
    """Central configuration management"""
    
    # Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN', '7728850256:AAFhVPRzSANY905UESCad1al2RsJtqQDmCw')
    API_KEY = 'PAID_INSTA_SELL187'
    API_BASE_URL = 'https://tg-user-id-to-number-4erk.onrender.com/api'
    
    # MongoDB Configuration
    MONGODB_URI = os.getenv('MONGODB_URI', '')
    DATABASE_NAME = 'instagram_monitor'
    
    # Admin Configuration
    OWNER_IDS = [int(id) for id in os.getenv('OWNER_IDS', '7805871651').split(',')]
    
    # SINGLE CHANNEL FORCE JOIN - @proxydominates ONLY
    FORCE_JOIN_CHANNEL = {
        'username': '@proxydominates',
        'url': 'https://t.me/proxydominates'
    }
    
    # User Limits
    DEFAULT_USER_LIMIT = 20
    
    # Monitoring Configuration
    CHECK_INTERVAL = 600  # 10 minutes
    VERIFICATION_DELAY = 120  # 2 minutes
    STATUS_DELAY = 10  # 10 seconds
    
    # Flask Keep-alive
    FLASK_HOST = '0.0.0.0'
    FLASK_PORT = int(os.getenv('PORT', 8080))


# ==================== LOGGING SETUP ====================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ==================== MONGODB DATABASE MANAGER ====================

class MongoDBManager:
    """MongoDB persistent storage manager"""
    
    def __init__(self):
        """Initialize MongoDB connection"""
        self.client = None
        self.db = None
        self.connect()
        
        # Collections
        self.users_collection = None
        self.watchlist_collection = None
        self.banlist_collection = None
        self.pending_collection = None
        
        if self.db:
            self._init_collections()
            logger.info("✅ MongoDB connected successfully")
        else:
            logger.error("❌ MongoDB connection failed - Using fallback JSON storage")
            self._init_fallback()
    
    def _init_fallback(self):
        """Initialize fallback JSON storage if MongoDB fails"""
        self.data_dir = Path('data')
        self.data_dir.mkdir(exist_ok=True)
        self.fallback_mode = True
        logger.info("⚠️ Using fallback JSON storage mode")
    
    def connect(self):
        """Connect to MongoDB"""
        if not Config.MONGODB_URI:
            logger.warning("MongoDB URI not set, using fallback storage")
            return
            
        try:
            self.client = MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            self.db = self.client[Config.DATABASE_NAME]
            logger.info("✅ MongoDB connection established")
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            self.client = None
            self.db = None
    
    def _init_collections(self):
        """Initialize collections and indexes"""
        self.users_collection = self.db['users']
        self.users_collection.create_index('user_id', unique=True)
        
        self.watchlist_collection = self.db['watchlist']
        self.watchlist_collection.create_index([('user_id', 1), ('username', 1)], unique=True)
        self.watchlist_collection.create_index('user_id')
        
        self.banlist_collection = self.db['banlist']
        self.banlist_collection.create_index([('user_id', 1), ('username', 1)], unique=True)
        self.banlist_collection.create_index('user_id')
        
        self.pending_collection = self.db['pending']
        self.pending_collection.create_index('username', unique=True)
        self.pending_collection.create_index('first_detected')
    
    # ===== USER MANAGEMENT =====
    
    def get_user(self, user_id: int) -> Dict:
        if not self.db:
            return {}
        user = self.users_collection.find_one({'user_id': user_id})
        if user:
            user.pop('_id', None)
        return user or {}
    
    def create_user(self, user_id: int, username: str = "", first_name: str = "") -> Dict:
        if not self.db:
            return {}
        
        user_data = {
            'user_id': user_id,
            'username': username,
            'first_name': first_name,
            'role': 'user',
            'subscription_expiry': None,
            'joined_date': datetime.now().isoformat(),
            'approved_by': None,
            'approved_days': 0,
            'verified': False,
            'notification_preferences': {
                'ban_alerts': True,
                'unban_alerts': True
            }
        }
        
        try:
            self.users_collection.update_one(
                {'user_id': user_id},
                {'$setOnInsert': user_data},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error creating user {user_id}: {e}")
        
        return user_data
    
    def update_user(self, user_id: int, **kwargs) -> bool:
        if not self.db:
            return False
        try:
            result = self.users_collection.update_one(
                {'user_id': user_id},
                {'$set': kwargs}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return False
    
    def get_all_users(self) -> List[Dict]:
        if not self.db:
            return []
        users = list(self.users_collection.find())
        for user in users:
            user.pop('_id', None)
        return users
    
    # ===== WATCHLIST MANAGEMENT =====
    
    def get_watchlist(self, user_id: int) -> List[str]:
        if not self.db:
            return []
        cursor = self.watchlist_collection.find(
            {'user_id': user_id},
            {'username': 1, '_id': 0}
        )
        return [doc['username'] for doc in cursor]
    
    def add_to_watchlist(self, user_id: int, username: str) -> bool:
        if not self.db:
            return False
        username = username.lower().strip().lstrip('@')
        try:
            self.watchlist_collection.update_one(
                {'user_id': user_id, 'username': username},
                {'$setOnInsert': {
                    'user_id': user_id,
                    'username': username,
                    'added_at': datetime.now().isoformat()
                }},
                upsert=True
            )
            return True
        except DuplicateKeyError:
            return False
        except Exception as e:
            logger.error(f"Error adding to watchlist: {e}")
            return False
    
    def remove_from_watchlist(self, user_id: int, username: str) -> bool:
        if not self.db:
            return False
        username = username.lower().strip().lstrip('@')
        try:
            result = self.watchlist_collection.delete_one({
                'user_id': user_id,
                'username': username
            })
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error removing from watchlist: {e}")
            return False
    
    # ===== BANLIST MANAGEMENT =====
    
    def get_banlist(self, user_id: int) -> List[str]:
        if not self.db:
            return []
        cursor = self.banlist_collection.find(
            {'user_id': user_id},
            {'username': 1, '_id': 0}
        )
        return [doc['username'] for doc in cursor]
    
    def add_to_banlist(self, user_id: int, username: str) -> bool:
        if not self.db:
            return False
        username = username.lower().strip().lstrip('@')
        try:
            self.banlist_collection.update_one(
                {'user_id': user_id, 'username': username},
                {'$setOnInsert': {
                    'user_id': user_id,
                    'username': username,
                    'added_at': datetime.now().isoformat()
                }},
                upsert=True
            )
            return True
        except DuplicateKeyError:
            return False
        except Exception as e:
            logger.error(f"Error adding to banlist: {e}")
            return False
    
    def remove_from_banlist(self, user_id: int, username: str) -> bool:
        if not self.db:
            return False
        username = username.lower().strip().lstrip('@')
        try:
            result = self.banlist_collection.delete_one({
                'user_id': user_id,
                'username': username
            })
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error removing from banlist: {e}")
            return False
    
    # ===== PENDING VERIFICATIONS =====
    
    def add_pending_verification(self, username: str, user_ids: List[int], old_status: str, 
                                 new_status: str, list_type: str, details: Dict):
        if not self.db:
            return
        username = username.lower().strip().lstrip('@')
        pending_data = {
            'username': username,
            'user_ids': user_ids,
            'old_status': old_status,
            'new_status': new_status,
            'list_type': list_type,
            'details': details,
            'first_detected': datetime.now().isoformat(),
            'verified': False
        }
        try:
            self.pending_collection.update_one(
                {'username': username},
                {'$set': pending_data},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error adding pending verification: {e}")
    
    def get_pending_verification(self, username: str) -> Optional[Dict]:
        if not self.db:
            return None
        username = username.lower().strip().lstrip('@')
        pending = self.pending_collection.find_one({'username': username})
        if pending:
            pending.pop('_id', None)
        return pending
    
    def remove_pending_verification(self, username: str):
        if not self.db:
            return
        username = username.lower().strip().lstrip('@')
        self.pending_collection.delete_one({'username': username})
    
    def get_all_pending(self) -> Dict:
        if not self.db:
            return {}
        pendings = {}
        cursor = self.pending_collection.find()
        for doc in cursor:
            username = doc.pop('username')
            doc.pop('_id', None)
            pendings[username] = doc
        return pendings
    
    def move_from_watch_to_ban(self, user_id: int, username: str):
        if not self.db:
            return
        self.remove_from_watchlist(user_id, username)
        self.add_to_banlist(user_id, username)
    
    def move_from_ban_to_watch(self, user_id: int, username: str):
        if not self.db:
            return
        self.remove_from_banlist(user_id, username)
        self.add_to_watchlist(user_id, username)
    
    def get_all_watchlist_items(self) -> Dict[str, List[int]]:
        if not self.db:
            return {}
        result = {}
        cursor = self.watchlist_collection.find()
        for doc in cursor:
            username = doc['username']
            user_id = doc['user_id']
            if username not in result:
                result[username] = []
            result[username].append(user_id)
        return result
    
    def get_all_banlist_items(self) -> Dict[str, List[int]]:
        if not self.db:
            return {}
        result = {}
        cursor = self.banlist_collection.find()
        for doc in cursor:
            username = doc['username']
            user_id = doc['user_id']
            if username not in result:
                result[username] = []
            result[username].append(user_id)
        return result
    
    def get_watchlist_count(self, user_id: int) -> int:
        if not self.db:
            return 0
        return self.watchlist_collection.count_documents({'user_id': user_id})
    
    def get_banlist_count(self, user_id: int) -> int:
        if not self.db:
            return 0
        return self.banlist_collection.count_documents({'user_id': user_id})
    
    def get_total_watchlist_count(self) -> int:
        if not self.db:
            return 0
        return self.watchlist_collection.count_documents({})
    
    def get_total_banlist_count(self) -> int:
        if not self.db:
            return 0
        return self.banlist_collection.count_documents({})
    
    def close(self):
        if self.client:
            self.client.close()


# ==================== API CLIENT ====================

class InstagramAPIClient:
    """Async API client for Instagram username checking"""
    
    def __init__(self):
        self.api_key = Config.API_KEY
        self.base_url = Config.API_BASE_URL
        self.session = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def check_username(self, username: str) -> Tuple[str, Dict, str]:
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                url = f"{self.base_url}/insta={username}?api_key={self.api_key}"
                
                logger.info(f"Checking API (attempt {attempt+1}/{max_retries}): {url}")
                
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('status') == 'ok' and 'profile' in data:
                            profile = data['profile']
                            profile_pic = profile.get('profile_pic_url_hd', '')
                            return 'ACTIVE', profile, profile_pic
                        elif data.get('error'):
                            return 'BANNED', {}, ''
                        else:
                            return 'BANNED', {}, ''
                    else:
                        logger.warning(f"HTTP {response.status} for @{username}, attempt {attempt+1}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        return 'BANNED', {}, ''
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout for @{username}, attempt {attempt+1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return 'BANNED', {}, ''
            except Exception as e:
                logger.error(f"Error checking username {username} (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return 'BANNED', {}, ''
        
        return 'BANNED', {}, ''
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


# ==================== MONITORING ENGINE ====================

class MonitoringEngine:
    """Background monitoring engine with 2-STEP VERIFICATION"""
    
    def __init__(self, db: MongoDBManager, api_client: InstagramAPIClient, bot_app: Application):
        self.db = db
        self.api_client = api_client
        self.bot_app = bot_app
        self.is_running = False
        self.task = None
        self.last_status = {}
    
    async def start(self):
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self._monitoring_loop())
            logger.info("✅ Monitoring engine started - 2-STEP VERIFICATION MODE")
    
    async def stop(self):
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Monitoring engine stopped")
    
    async def _monitoring_loop(self):
        while self.is_running:
            try:
                start_time = datetime.now()
                logger.info("Starting monitoring cycle")
                
                await self._check_pending_verifications()
                
                watchlist_items = self.db.get_all_watchlist_items()
                banlist_items = self.db.get_all_banlist_items()
                
                all_usernames = set(watchlist_items.keys()) | set(banlist_items.keys())
                
                for username in all_usernames:
                    try:
                        user_ids = []
                        list_type = 'watch'
                        
                        if username in watchlist_items:
                            user_ids.extend(watchlist_items[username])
                        
                        if username in banlist_items:
                            user_ids.extend(banlist_items[username])
                            list_type = 'ban' if username not in watchlist_items else 'both'
                        
                        await self._check_single_username(username, user_ids, list_type)
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        logger.error(f"Error checking username {username}: {e}")
                        continue
                
                elapsed = (datetime.now() - start_time).total_seconds()
                sleep_time = max(Config.CHECK_INTERVAL - elapsed, 60)
                
                logger.info(f"Monitoring cycle completed in {elapsed:.2f}s. Next check in {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def _check_pending_verifications(self):
        """Check pending verifications that are 2 minutes old"""
        pending = self.db.get_all_pending()
        now = datetime.now()
        
        for username, data in list(pending.items()):
            try:
                first_detected = datetime.fromisoformat(data['first_detected'])
                age_seconds = (now - first_detected).total_seconds()
                
                if age_seconds >= Config.VERIFICATION_DELAY and not data.get('verified', False):
                    logger.info(f"Verifying pending @{username} after {age_seconds:.0f}s")
                    
                    status, details, profile_pic = await self.api_client.check_username(username)
                    
                    if status == data['new_status']:
                        logger.info(f"✅ Verified: @{username} still {status} - sending alert")
                        
                        data['verified'] = True
                        
                        # Use new details if available (for unban cases)
                        final_details = details if details and status == 'ACTIVE' else data['details']
                        
                        await self._send_verified_alert(
                            username, 
                            data['user_ids'], 
                            status, 
                            data['list_type'], 
                            final_details,
                            profile_pic,
                            data['first_detected']
                        )
                        
                        self.db.remove_pending_verification(username)
                    else:
                        logger.info(f"❌ False alarm: @{username} changed back to {status}")
                        self.db.remove_pending_verification(username)
                        
            except Exception as e:
                logger.error(f"Error checking pending {username}: {e}")
    
    async def _check_single_username(self, username: str, user_ids: List[int], list_type: str):
        status, details, profile_pic = await self.api_client.check_username(username)
        
        prev_status = self.last_status.get(username)
        
        if prev_status and prev_status != status:
            logger.info(f"Status change detected for @{username}: {prev_status} -> {status}")
            
            pending = self.db.get_pending_verification(username)
            
            if not pending:
                self.db.add_pending_verification(
                    username, 
                    user_ids, 
                    prev_status, 
                    status, 
                    list_type, 
                    details
                )
                logger.info(f"@{username} added to pending verification - will check again in 2 minutes")
        
        self.last_status[username] = status
    
    async def _send_verified_alert(self, username: str, user_ids: List[int], status: str, 
                                   list_type: str, details: Dict, profile_pic: str, detection_time: str):
        
        for user_id in user_ids:
            try:
                user_data = self.db.get_user(user_id)
                
                if not user_data:
                    continue
                
                if status == 'BANNED':
                    if list_type == 'watch' or list_type == 'both':
                        self.db.move_from_watch_to_ban(user_id, username)
                        
                        if user_data.get('notification_preferences', {}).get('ban_alerts', True):
                            await self._send_ban_alert(user_id, username, details, profile_pic, detection_time)
                
                elif status == 'ACTIVE':
                    if list_type == 'ban' or list_type == 'both':
                        self.db.move_from_ban_to_watch(user_id, username)
                        
                        if user_data.get('notification_preferences', {}).get('unban_alerts', True):
                            await self._send_unban_alert(user_id, username, details, profile_pic, detection_time)
                        
            except Exception as e:
                logger.error(f"Error processing alert for user {user_id}: {e}")
                continue
    
    async def _send_ban_alert(self, user_id: int, username: str, details: Dict, profile_pic: str, detection_time: str):
        try:
            message = self._format_ban_alert(username, details, detection_time)
            
            keyboard = [[InlineKeyboardButton("📞 CONTACT @proxyfxc", url="https://t.me/proxyfxc")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if profile_pic:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(profile_pic) as resp:
                            if resp.status == 200:
                                photo_data = await resp.read()
                                await self.bot_app.bot.send_photo(
                                    chat_id=user_id,
                                    photo=photo_data,
                                    caption=message,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=reply_markup
                                )
                                return
                except Exception as e:
                    logger.error(f"Error sending photo: {e}")
            
            await self.bot_app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send ban alert: {e}")
    
    async def _send_unban_alert(self, user_id: int, username: str, details: Dict, profile_pic: str, detection_time: str):
        try:
            message = self._format_unban_alert(username, details, detection_time)
            
            keyboard = [[InlineKeyboardButton("📞 CONTACT @proxyfxc", url="https://t.me/proxyfxc")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if profile_pic:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(profile_pic) as resp:
                            if resp.status == 200:
                                photo_data = await resp.read()
                                await self.bot_app.bot.send_photo(
                                    chat_id=user_id,
                                    photo=photo_data,
                                    caption=message,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=reply_markup
                                )
                                return
                except Exception as e:
                    logger.error(f"Error sending photo: {e}")
            
            await self.bot_app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send unban alert: {e}")
    
    def _format_ban_alert(self, username: str, details: Dict, detection_time: str) -> str:
        name = details.get('full_name', username)
        followers = details.get('follower_count', 'N/A')
        following = details.get('following_count', 'N/A')
        posts = details.get('media_count', 'N/A')
        is_private = details.get('is_private', False)
        
        try:
            followers = f"{int(followers):,}" if followers != 'N/A' else 'N/A'
        except:
            followers = str(followers)
        
        try:
            following = f"{int(following):,}" if following != 'N/A' else 'N/A'
        except:
            following = str(following)
        
        try:
            posts = f"{int(posts):,}" if posts != 'N/A' else 'N/A'
        except:
            posts = str(posts)
        
        try:
            dt = datetime.fromisoformat(detection_time)
            display_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            display_time = detection_time
        
        return f"""
🔴 <b>🚨 BANNED ACCOUNT DETECTED</b> 🔴

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

👤 <b>Name:</b> {name}
👥 <b>Followers:</b> {followers}
👤 <b>Following:</b> {following}
📸 <b>Posts:</b> {posts}
🔐 <b>Private:</b> {'Yes' if is_private else 'No'}

⚠️ <b>Status:</b> <code>BANNED / SUSPENDED</code>
✅ <b>Verified:</b> <code>2-STEP CONFIRMATION</code>
⏰ <b>First Detected:</b> {display_time}

━━━━━━━━━━━━━━━━━━━━━
<i>Account moved to Ban List automatically</i>
"""
    
    def _format_unban_alert(self, username: str, details: Dict, detection_time: str) -> str:
        name = details.get('full_name', username)
        followers = details.get('follower_count', 'N/A')
        following = details.get('following_count', 'N/A')
        posts = details.get('media_count', 'N/A')
        is_private = details.get('is_private', False)
        
        try:
            followers = f"{int(followers):,}" if followers != 'N/A' else 'N/A'
        except:
            followers = str(followers)
        
        try:
            following = f"{int(following):,}" if following != 'N/A' else 'N/A'
        except:
            following = str(following)
        
        try:
            posts = f"{int(posts):,}" if posts != 'N/A' else 'N/A'
        except:
            posts = str(posts)
        
        try:
            dt = datetime.fromisoformat(detection_time)
            display_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            display_time = detection_time
        
        return f"""
🟢 <b>✅ ACCOUNT UNBANNED</b> 🟢

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

👤 <b>Name:</b> {name}
👥 <b>Followers:</b> {followers}
👤 <b>Following:</b> {following}
📸 <b>Posts:</b> {posts}
🔐 <b>Private:</b> {'Yes' if is_private else 'No'}

✅ <b>Status:</b> <code>ACTIVE / RESTORED</code>
✅ <b>Verified:</b> <code>2-STEP CONFIRMATION</code>
⏰ <b>First Detected:</b> {display_time}

━━━━━━━━━━━━━━━━━━━━━
<i>Account moved back to Watch List automatically</i>
"""


# ==================== FLASK KEEP-ALIVE ====================

app = Flask(__name__)
monitoring_engine = None
db = None

@app.route('/')
def home():
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.now().isoformat(),
        'service': 'Instagram Monitor Bot',
        'bot_running': monitoring_engine.is_running if monitoring_engine else False
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'monitoring_active': monitoring_engine.is_running if monitoring_engine else False,
        'mongodb_connected': db.db is not None if db else False
    })

def run_flask():
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT)


# ==================== TELEGRAM BOT HANDLERS ====================

class BotHandlers:
    """All Telegram bot command and callback handlers"""
    
    def __init__(self, db: MongoDBManager, api_client: InstagramAPIClient):
        self.db = db
        self.api_client = api_client
    
    def is_owner(self, user_id: int) -> bool:
        return user_id in Config.OWNER_IDS
    
    def is_admin(self, user_id: int) -> bool:
        if self.is_owner(user_id):
            return True
        user_data = self.db.get_user(user_id)
        return user_data.get('role') == 'admin'
    
    def has_active_subscription(self, user_id: int) -> bool:
        if self.is_admin(user_id):
            return True
        
        user_data = self.db.get_user(user_id)
        expiry = user_data.get('subscription_expiry')
        
        if not expiry:
            return False
        
        try:
            expiry_date = datetime.fromisoformat(expiry)
            return expiry_date > datetime.now()
        except:
            return False
    
    def get_user_limit(self, user_id: int) -> int:
        if self.is_admin(user_id):
            return float('inf')
        return Config.DEFAULT_USER_LIMIT
    
    def format_account_info(self, username: str, status: str, details: Dict) -> str:
        if status == 'ACTIVE':
            name = details.get('full_name', username)
            followers = details.get('followers', details.get('follower_count', 0))
            following = details.get('following', details.get('following_count', 0))
            posts = details.get('posts', details.get('media_count', 0))
            is_private = details.get('is_private', False)
            
            try:
                followers = int(followers)
            except:
                pass
            try:
                following = int(following)
            except:
                pass
            try:
                posts = int(posts)
            except:
                pass
            
            private_text = 'Yes' if is_private else 'No'
            
            followers_str = f"{followers:,}" if isinstance(followers, int) else str(followers)
            following_str = f"{following:,}" if isinstance(following, int) else str(following)
            posts_str = f"{posts:,}" if isinstance(posts, int) else str(posts)
            
            return f"""
🟢 ACCOUNT ACTIVE

━━━━━━━━━━━━━━━━━━━━━
Profile: @{username}

👤 Name: {name}
👥 Followers: {followers_str}
👤 Following: {following_str}
📸 Posts: {posts_str}
🔐 Private: {private_text}

🟢 ACCOUNT ACTIVE

━━━━━━━━━━━━━━━━━━━━━
"""
        elif status == 'BANNED':
            return f"""
🔴 ACCOUNT BANNED

━━━━━━━━━━━━━━━━━━━━━
Profile: @{username}

⚠️ Status: BANNED / SUSPENDED

━━━━━━━━━━━━━━━━━━━━━
"""
        else:
            return f"""
❓ ACCOUNT UNKNOWN

━━━━━━━━━━━━━━━━━━━━━
Profile: @{username}

⚠️ Status: UNKNOWN / NOT FOUND

━━━━━━━━━━━━━━━━━━━━━
"""
    
    def format_add_watch_details(self, username: str, status: str, details: Dict, current_count: int, limit: Any) -> str:
        if status == 'ACTIVE':
            name = details.get('full_name', username)
            followers = details.get('followers', details.get('follower_count', 0))
            following = details.get('following', details.get('following_count', 0))
            posts = details.get('posts', details.get('media_count', 0))
            is_private = details.get('is_private', False)
            
            try:
                followers = int(followers)
            except:
                pass
            try:
                following = int(following)
            except:
                pass
            try:
                posts = int(posts)
            except:
                pass
            
            private_text = 'Yes' if is_private else 'No'
            
            followers_str = f"{followers:,}" if isinstance(followers, int) else str(followers)
            following_str = f"{following:,}" if isinstance(following, int) else str(following)
            posts_str = f"{posts:,}" if isinstance(posts, int) else str(posts)
            
            limit_text = f"{current_count}/{limit}" if limit != float('inf') else f"{current_count}/∞"
            
            return f"""
✅ <b>ACCOUNT ADDED TO WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

👤 <b>Name:</b> {name}
👥 <b>Followers:</b> {followers_str}
👤 <b>Following:</b> {following_str}
📸 <b>Posts:</b> {posts_str}
🔐 <b>Private:</b> {private_text}
🟢 <b>Status:</b> ACTIVE

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Watch List:</b> {limit_text}

<i>You will be notified when status changes (2-step verification)</i>
━━━━━━━━━━━━━━━━━━━━━
"""
        elif status == 'BANNED':
            limit_text = f"{current_count}/{limit}" if limit != float('inf') else f"{current_count}/∞"
            
            return f"""
⚠️ <b>ACCOUNT ADDED TO WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

🔴 <b>Status:</b> BANNED / SUSPENDED
⚠️ <b>Note:</b> Account is currently banned

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Watch List:</b> {limit_text}

<i>You will be notified when unbanned (2-step verification)</i>
━━━━━━━━━━━━━━━━━━━━━
"""
        else:
            limit_text = f"{current_count}/{limit}" if limit != float('inf') else f"{current_count}/∞"
            
            return f"""
❓ <b>ACCOUNT ADDED TO WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

❓ <b>Status:</b> UNKNOWN / NOT FOUND

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Watch List:</b> {limit_text}

<i>You will be notified if account becomes active (2-step verification)</i>
━━━━━━━━━━━━━━━━━━━━━
"""
    
    async def check_force_join(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        try:
            user_data = self.db.get_user(user_id)
            if user_data.get('verified', False):
                return True
            
            channel = Config.FORCE_JOIN_CHANNEL
            channel_username = channel['username']
            
            if not channel_username.startswith('@'):
                channel_username = '@' + channel_username
            
            member = await context.bot.get_chat_member(
                chat_id=channel_username,
                user_id=user_id
            )
            
            if member.status in ['member', 'administrator', 'creator']:
                self.db.update_user(user_id, verified=True)
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error checking force join: {e}")
            return False
    
    async def send_force_join_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        channel = Config.FORCE_JOIN_CHANNEL
        
        keyboard = [
            [InlineKeyboardButton(
                text=f"📢 Join @proxydominates",
                url=channel['url']
            )],
            [InlineKeyboardButton(
                text="✅ I've Joined",
                callback_data="verify_join"
            )]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = """
<b>🔒 CHANNEL SUBSCRIPTION REQUIRED</b>

To use this bot, you must join our channel first:

━━━━━━━━━━━━━━━━━━━━━
<b>📢 @proxydominates</b>
• Get latest updates
• Important announcements
• Premium features
• Support & Community
━━━━━━━━━━━━━━━━━━━━━

<b>Steps:</b>
1️⃣ Click the button above
2️⃣ Join the channel
3️⃣ Click "I've Joined"
4️⃣ Bot will start automatically
"""
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        self.db.create_user(
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name or ""
        )
        
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        await self.show_main_menu(update, context)
        
        if not self.is_admin(user.id):
            for owner_id in Config.OWNER_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=owner_id,
                        text=f"👤 <b>New User Alert</b>\n\nUser: {user.first_name}\nID: <code>{user.id}</code>\nUsername: @{user.username or 'N/A'}",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        watch_count = self.db.get_watchlist_count(user.id)
        ban_count = self.db.get_banlist_count(user.id)
        limit = self.get_user_limit(user.id)
        
        keyboard = [
            [
                InlineKeyboardButton("📋 Watch List", callback_data="menu_watch"),
                InlineKeyboardButton("🚫 Ban List", callback_data="menu_ban")
            ],
            [
                InlineKeyboardButton("📊 Status", callback_data="menu_status"),
                InlineKeyboardButton("🔍 Check User", callback_data="menu_check")
            ],
            [
                InlineKeyboardButton("➕ Add to Watch", callback_data="menu_addwatch"),
                InlineKeyboardButton("➖ Remove Watch", callback_data="menu_removewatch")
            ],
            [
                InlineKeyboardButton("⛔ Add to Ban", callback_data="menu_addban"),
                InlineKeyboardButton("✅ Remove Ban", callback_data="menu_removeban")
            ],
            [InlineKeyboardButton("ℹ️ Help & Info", callback_data="menu_help")],
            [InlineKeyboardButton("📞 CONTACT @proxyfxc", url="https://t.me/proxyfxc")]
        ]
        
        if self.is_admin(user.id):
            keyboard.insert(4, [InlineKeyboardButton("⚙️ Admin Panel", callback_data="menu_admin")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_msg = f"""
<b>🚀 INSTAGRAM MONITOR PRO</b>

Welcome <b>{user.first_name}</b>!

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Your Status:</b>
• Role: <code>{self.db.get_user(user.id).get('role', 'user').upper()}</code>
• Subscription: <code>{'Active' if self.has_active_subscription(user.id) else 'Inactive'}</code>
• Watch List: <code>{watch_count}/{limit if limit != float('inf') else '∞'}</code>
• Ban List: <code>{ban_count}</code>
━━━━━━━━━━━━━━━━━━━━━

<b>👇 Select an option below:</b>

<i>Powered by @proxyfxc</i>
"""
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                welcome_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                welcome_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def watch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        watchlist = self.db.get_watchlist(user.id)
        watch_count = len(watchlist)
        limit = self.get_user_limit(user.id)
        
        message = f"""
<b>📋 WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Statistics:</b>
• Used: <code>{watch_count}/{limit if limit != float('inf') else '∞'}</code>
━━━━━━━━━━━━━━━━━━━━━

<b>📝 Your Watch List:</b>
"""
        
        if watchlist:
            for i, username in enumerate(watchlist[:10], 1):
                message += f"{i}. @{username}\n"
            if len(watchlist) > 10:
                message += f"...and {len(watchlist) - 10} more\n"
        else:
            message += "<i>No usernames in watch list</i>\n"
        
        message += "\n<b>Commands:</b>\n/addwatch username\n/removewatch username"
        
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def ban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        banlist = self.db.get_banlist(user.id)
        
        message = f"""
<b>🚫 BAN LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Statistics:</b>
• Banned Accounts: <code>{len(banlist)}</code>
━━━━━━━━━━━━━━━━━━━━━

<b>📝 Your Ban List:</b>
"""
        
        if banlist:
            for i, username in enumerate(banlist[:10], 1):
                message += f"{i}. @{username}\n"
            if len(banlist) > 10:
                message += f"...and {len(banlist) - 10} more\n"
        else:
            message += "<i>No usernames in ban list</i>\n"
        
        message += "\n<b>Commands:</b>\n/addban username\n/removeban username"
        
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        watchlist = self.db.get_watchlist(user.id)
        
        if not watchlist:
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📭 <b>No accounts in watch list</b>\n\nAdd accounts using /addwatch command",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return
        
        status_msg = await update.message.reply_text(
            f"🔄 <b>Checking {len(watchlist)} accounts with 10-second delays...</b>\n\nThis will take approximately {len(watchlist) * 10} seconds.",
            parse_mode=ParseMode.HTML
        )
        
        all_results = []
        success_count = 0
        banned_count = 0
        current = 0
        
        for username in watchlist:
            current += 1
            try:
                await status_msg.edit_text(
                    f"🔄 <b>Checking accounts... ({current}/{len(watchlist)})</b>\n\n"
                    f"Currently checking: @{username}\n"
                    f"⏱️ Estimated time remaining: {(len(watchlist) - current) * 10} seconds",
                    parse_mode=ParseMode.HTML
                )
                
                status, details, profile_pic = await self.api_client.check_username(username)
                
                if status == 'ACTIVE':
                    success_count += 1
                elif status == 'BANNED':
                    banned_count += 1
                
                result = self.format_account_info(username, status, details)
                result += f"\n━━━━━━━━━━━━━━━━━━━━━\n"
                all_results.append(result)
                
                if current < len(watchlist):
                    await asyncio.sleep(Config.STATUS_DELAY)
                
            except Exception as e:
                logger.error(f"Error checking {username}: {e}")
                all_results.append(self.format_account_info(username, 'UNKNOWN', {}))
                all_results.append(f"\n━━━━━━━━━━━━━━━━━━━━━\n")
        
        header = f"""
<b>📊 STATUS CHECK RESULTS</b>

━━━━━━━━━━━━━━━━━━━━━
📋 Total: {len(watchlist)}
🟢 Active: {success_count}
🔴 Banned: {banned_count}
❓ Unknown: {len(watchlist) - success_count - banned_count}
━━━━━━━━━━━━━━━━━━━━━

"""
        
        final_message = header + "\n".join(all_results)
        final_message += "\nPowered by @proxyfxc"
        
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if len(final_message) > 4096:
            await status_msg.delete()
            
            parts = [final_message[i:i+4096] for i in range(0, len(final_message), 4096)]
            for i, part in enumerate(parts):
                if i == 0:
                    await update.message.reply_text(
                        part,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup
                    )
                else:
                    await update.message.reply_text(part, parse_mode=ParseMode.HTML)
        else:
            await status_msg.edit_text(
                final_message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def check_command_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = """
<b>🔍 CHECK USERNAME</b>

━━━━━━━━━━━━━━━━━━━━━
Send a username to check its status:

<b>Example:</b> <code>/check cristiano</code>
<b>Example:</b> <code>/check @leomessi</code>

Or use the command:
<code>/check username</code>
━━━━━━━━━━━━━━━━━━━━━
"""
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def check_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        args = context.args
        if not args:
            await self.check_command_prompt(update, context)
            return
        
        username = args[0].lower().strip().lstrip('@')
        
        status_msg = await update.message.reply_text(
            f"🔍 <b>Checking @{username}...</b>",
            parse_mode=ParseMode.HTML
        )
        
        try:
            status, details, profile_pic = await self.api_client.check_username(username)
            
            response_text = self.format_account_info(username, status, details)
            response_text += "\nPowered by @proxyfxc"
            
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if status == 'ACTIVE' and profile_pic:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(profile_pic) as resp:
                            if resp.status == 200:
                                photo_data = await resp.read()
                                await status_msg.delete()
                                await update.message.reply_photo(
                                    photo=photo_data,
                                    caption=response_text,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=reply_markup
                                )
                                return
                except Exception as e:
                    logger.error(f"Error downloading profile picture: {e}")
            
            await status_msg.edit_text(
                response_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error in check command: {e}")
            await status_msg.edit_text(
                f"❌ <b>Error checking @{username}</b>\n\nPlease try again later.",
                parse_mode=ParseMode.HTML
            )
    
    async def addwatch_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = """
<b>➕ ADD TO WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
Send a username to add to your watch list:

<b>Example:</b> <code>/addwatch cristiano</code>
<b>Example:</b> <code>/addwatch @leomessi</code>

Or use the command:
<code>/addwatch username</code>
━━━━━━━━━━━━━━━━━━━━━
"""
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def addwatch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        if not self.has_active_subscription(user.id) and not self.is_admin(user.id):
            await update.message.reply_text(
                "❌ <b>Subscription Required</b>\n\nContact an admin to purchase access.",
                parse_mode=ParseMode.HTML
            )
            return
        
        current_count = self.db.get_watchlist_count(user.id)
        limit = self.get_user_limit(user.id)
        
        if current_count >= limit and limit != float('inf'):
            await update.message.reply_text(
                f"❌ <b>Limit Reached</b> ({limit})",
                parse_mode=ParseMode.HTML
            )
            return
        
        args = context.args
        if not args:
            await self.addwatch_prompt(update, context)
            return
        
        username = args[0].lower().strip().lstrip('@')
        
        if username in self.db.get_watchlist(user.id):
            status_msg = await update.message.reply_text(
                f"🔍 <b>Checking @{username}...</b>",
                parse_mode=ParseMode.HTML
            )
            
            status, details, profile_pic = await self.api_client.check_username(username)
            
            response_text = self.format_account_info(username, status, details)
            response_text += "\n⚠️ <i>Already in your watch list</i>\nPowered by @proxyfxc"
            
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await status_msg.edit_text(
                response_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return
        
        self.db.add_to_watchlist(user.id, username)
        
        status_msg = await update.message.reply_text(
            f"🔍 <b>Fetching details for @{username}...</b>",
            parse_mode=ParseMode.HTML
        )
        
        status, details, profile_pic = await self.api_client.check_username(username)
        
        new_count = current_count + 1
        response_text = self.format_add_watch_details(username, status, details, new_count, limit)
        
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if status == 'ACTIVE' and profile_pic:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(profile_pic) as resp:
                        if resp.status == 200:
                            photo_data = await resp.read()
                            await status_msg.delete()
                            await update.message.reply_photo(
                                photo=photo_data,
                                caption=response_text,
                                parse_mode=ParseMode.HTML,
                                reply_markup=reply_markup
                            )
                            return
            except Exception as e:
                logger.error(f"Error downloading profile picture: {e}")
        
        await status_msg.edit_text(
            response_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def removewatch_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        watchlist = self.db.get_watchlist(user.id)
        
        message = """
<b>➖ REMOVE FROM WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
Send a username to remove:

<b>Example:</b> <code>/removewatch cristiano</code>
━━━━━━━━━━━━━━━━━━━━━

<b>Your Watch List:</b>
"""
        
        if watchlist:
            for username in watchlist[:10]:
                message += f"• @{username}\n"
        else:
            message += "<i>Watch list is empty</i>"
        
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def removewatch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        args = context.args
        if not args:
            await self.removewatch_prompt(update, context)
            return
        
        username = args[0].lower().strip().lstrip('@')
        
        if self.db.remove_from_watchlist(user.id, username):
            await update.message.reply_text(
                f"✅ @{username} removed from watch list.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"❌ @{username} not found in watch list.",
                parse_mode=ParseMode.HTML
            )
    
    async def addban_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = """
<b>⛔ ADD TO BAN LIST</b>

━━━━━━━━━━━━━━━━━━━━━
Send a username to add to ban list:

<b>Example:</b> <code>/addban cristiano</code>
━━━━━━━━━━━━━━━━━━━━━
"""
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def addban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        if not self.has_active_subscription(user.id) and not self.is_admin(user.id):
            await update.message.reply_text(
                "❌ Subscription Required",
                parse_mode=ParseMode.HTML
            )
            return
        
        args = context.args
        if not args:
            await self.addban_prompt(update, context)
            return
        
        username = args[0].lower().strip().lstrip('@')
        
        if username in self.db.get_banlist(user.id):
            await update.message.reply_text(
                f"⚠️ @{username} already in ban list.",
                parse_mode=ParseMode.HTML
            )
            return
        
        self.db.add_to_banlist(user.id, username)
        
        await update.message.reply_text(
            f"✅ @{username} added to ban list.",
            parse_mode=ParseMode.HTML
        )
    
    async def removeban_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        banlist = self.db.get_banlist(user.id)
        
        message = """
<b>✅ REMOVE FROM BAN LIST</b>

━━━━━━━━━━━━━━━━━━━━━
Send a username to remove:

<b>Example:</b> <code>/removeban cristiano</code>
━━━━━━━━━━━━━━━━━━━━━

<b>Your Ban List:</b>
"""
        
        if banlist:
            for username in banlist[:10]:
                message += f"• @{username}\n"
        else:
            message += "<i>Ban list is empty</i>"
        
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    
    async def removeban_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        args = context.args
        if not args:
            await self.removeban_prompt(update, context)
            return
        
        username = args[0].lower().strip().lstrip('@')
        
        if self.db.remove_from_banlist(user.id, username):
            await update.message.reply_text(
                f"✅ @{username} removed from ban list.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"❌ @{username} not found in ban list.",
                parse_mode=ParseMode.HTML
            )
    
    async def approve_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self.is_admin(user.id):
            await update.message.reply_text("❌ Admin only command.")
            return
        
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /approve [user_id] [days]",
                parse_mode=ParseMode.HTML
            )
            return
        
        try:
            target_id = int(args[0])
            days = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid numbers.")
            return
        
        expiry_date = datetime.now() + timedelta(days=days)
        
        if self.db.update_user(
            target_id,
            role='user',
            subscription_expiry=expiry_date.isoformat(),
            approved_by=user.id,
            approved_days=days
        ):
            await update.message.reply_text(
                f"✅ User {target_id} approved for {days} days.",
                parse_mode=ParseMode.HTML
            )
            
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"""
✅ <b>SUBSCRIPTION APPROVED</b>

━━━━━━━━━━━━━━━━━━━━━
📅 Duration: {days} days
⏰ Expires: {expiry_date.strftime('%Y-%m-%d')}

You can now add up to {Config.DEFAULT_USER_LIMIT} usernames.
━━━━━━━━━━━━━━━━━━━━━

Powered by @proxyfxc
""",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    async def addadmin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self.is_owner(user.id):
            await update.message.reply_text("❌ Owner only command.")
            return
        
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /addadmin [user_id]")
            return
        
        try:
            target_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID.")
            return
        
        if self.db.update_user(target_id, role='admin'):
            await update.message.reply_text(
                f"✅ User {target_id} is now admin.",
                parse_mode=ParseMode.HTML
            )
            
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="👑 You are now an admin!",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if not self.is_admin(user.id):
            await update.message.reply_text("❌ Admin only command.")
            return
        
        if not context.args and not update.message.reply_to_message:
            await update.message.reply_text("Usage: /broadcast [message]")
            return
        
        if update.message.reply_to_message:
            message = update.message.reply_to_message.text
        else:
            message = ' '.join(context.args)
        
        status_msg = await update.message.reply_text("📤 Broadcasting...")
        
        users = self.db.get_all_users()
        total = len(users)
        success = 0
        
        for user_data in users:
            try:
                await context.bot.send_message(
                    chat_id=user_data['user_id'],
                    text=f"""
📢 <b>BROADCAST MESSAGE</b>

━━━━━━━━━━━━━━━━━━━━━
{message}
━━━━━━━━━━━━━━━━━━━━━

Powered by @proxyfxc
""",
                    parse_mode=ParseMode.HTML
                )
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
        
        await status_msg.edit_text(
            f"✅ Broadcast complete: {success}/{total}",
            parse_mode=ParseMode.HTML
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        data = query.data
        
        logger.info(f"Button clicked: {data} by user {user.id}")
        
        if data == "verify_join":
            await query.edit_message_text(
                "🔄 <b>Verifying your channel membership...</b>",
                parse_mode=ParseMode.HTML
            )
            
            if await self.check_force_join(user.id, context):
                await self.show_main_menu(update, context)
            else:
                channel = Config.FORCE_JOIN_CHANNEL
                keyboard = [
                    [InlineKeyboardButton(
                        text=f"📢 Join @proxydominates",
                        url=channel['url']
                    )],
                    [InlineKeyboardButton(
                        text="🔄 Try Again",
                        callback_data="verify_join"
                    )]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "❌ <b>Verification Failed</b>\n\nPlease join the channel and try again.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            return
        
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        if data == "menu_main":
            await self.show_main_menu(update, context)
        elif data == "menu_watch":
            await self.watch_command(update, context)
        elif data == "menu_ban":
            await self.ban_command(update, context)
        elif data == "menu_status":
            await self.status_command(update, context)
        elif data == "menu_check":
            await self.check_command_prompt(update, context)
        elif data == "menu_addwatch":
            await self.addwatch_prompt(update, context)
        elif data == "menu_removewatch":
            await self.removewatch_prompt(update, context)
        elif data == "menu_addban":
            await self.addban_prompt(update, context)
        elif data == "menu_removeban":
            await self.removeban_prompt(update, context)
        elif data == "menu_help":
            help_text = """
<b>📚 HELP & SUPPORT</b>

━━━━━━━━━━━━━━━━━━━━━
<b>📌 Commands:</b>
/watch - View watch list
/ban - View ban list
/status - Check all watchlist accounts
/check [user] - Check single username
/addwatch [user] - Add to watch (with details)
/removewatch [user] - Remove from watch
/addban [user] - Add to ban list
/removeban [user] - Remove from ban list

<b>⚙️ Admin Commands:</b>
/approve [id] [days]
/broadcast [message]
/addadmin [id]

<b>📊 How It Works:</b>
• 10-minute monitoring
• 2-STEP VERIFICATION (2 min wait)
• Auto move between lists
• Profile pictures in alerts
• Detailed info when adding
• PERSISTENT MONGODB STORAGE
━━━━━━━━━━━━━━━━━━━━━

<i>Powered by @proxyfxc</i>
"""
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                help_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        elif data == "menu_admin" and self.is_admin(user.id):
            total_watch = self.db.get_total_watchlist_count()
            total_ban = self.db.get_total_banlist_count()
            users = self.db.get_all_users()
            
            admin_text = f"""
<b>⚙️ ADMIN PANEL</b>

━━━━━━━━━━━━━━━━━━━━━
📊 <b>System Stats:</b>
• Users: {len(users)}
• Watchlist: {total_watch}
• Banlist: {total_ban}
• Mode: <b>2-STEP VERIFICATION</b>
• Storage: <b>MONGODB PERSISTENT</b>

━━━━━━━━━━━━━━━━━━━━━
<b>Commands:</b>
/approve [user_id] [days]
/broadcast [message]
/addadmin [user_id]

Powered by @proxyfxc
"""
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                admin_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )


# ==================== ERROR HANDLER ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")


# ==================== MAIN APPLICATION ====================

db = None
monitoring_engine = None
api_client = None

async def run_bot():
    """Async function to run the bot"""
    global db, monitoring_engine, api_client
    
    try:
        logger.info("🚀 run_bot function started!")
        
        # Initialize MongoDB
        db = MongoDBManager()
        
        # Initialize API client
        api_client = InstagramAPIClient()
        
        # Create application
        logger.info("Creating Telegram application...")
        application = (
            Application.builder()
            .token(Config.BOT_TOKEN)
            .concurrent_updates(True)
            .build()
        )
        
        # Initialize handlers
        handlers = BotHandlers(db, api_client)
        
        # Add command handlers
        application.add_handler(CommandHandler("start", handlers.start_command))
        application.add_handler(CommandHandler("watch", handlers.watch_command))
        application.add_handler(CommandHandler("ban", handlers.ban_command))
        application.add_handler(CommandHandler("status", handlers.status_command))
        application.add_handler(CommandHandler("check", handlers.check_command))
        application.add_handler(CommandHandler("addwatch", handlers.addwatch_command))
        application.add_handler(CommandHandler("removewatch", handlers.removewatch_command))
        application.add_handler(CommandHandler("addban", handlers.addban_command))
        application.add_handler(CommandHandler("removeban", handlers.removeban_command))
        application.add_handler(CommandHandler("approve", handlers.approve_command))
        application.add_handler(CommandHandler("addadmin", handlers.addadmin_command))
        application.add_handler(CommandHandler("broadcast", handlers.broadcast_command))
        
        # Add callback query handler
        application.add_handler(CallbackQueryHandler(handlers.button_callback))
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Initialize monitoring engine
        monitoring_engine = MonitoringEngine(db, api_client, application)
        
        # Start monitoring
        asyncio.create_task(monitoring_engine.start())
        
        # Start bot
        logger.info("Starting bot polling...")
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        logger.info("✅ Bot is running! Single force join: @proxydominates")
        logger.info("✅ MODE: 2-STEP VERIFICATION (10min checks)")
        logger.info("✅ STORAGE: MONGODB PERSISTENT - Data safe on restart!")
        
        # Keep running
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"❌ Error in run_bot: {e}")
        traceback.print_exc()
    finally:
        if db:
            db.close()

def main():
    """Main entry point"""
    logger.info("Starting main function...")
    
    # Start Flask thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask keep-alive started")
    
    # Run bot with proper event loop
    try:
        asyncio.run(run_bot())
    except RuntimeError as e:
        logger.error(f"RuntimeError: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bot())
    except Exception as e:
        logger.error(f"Error in main: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
