"""
Professional Instagram Username Monitor Bot
Single Channel Force Join - @proxydominates
All buttons working, subscription system, monitoring
Author: @proxyfxc
Version: 7.0.0 (FINAL - FIXED TIMING + DETAILS + 2-STEP VERIFICATION)
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

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================

class Config:
    """Central configuration management"""
    
    # Bot Configuration
    BOT_TOKEN = os.getenv('BOT_TOKEN', '7728850256:AAFhVPRzSANY905UESCad1al2RsJtqQDmCw')
    API_KEY = 'PAID_INSTA_SELL187'
    API_BASE_URL = 'https://tg-username-to-num.onrender.com/api'
    
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
    CHECK_INTERVAL = 300  # 5 minutes
    VERIFICATION_DELAY = 120  # 2 minutes
    STATUS_DELAY = 10  # 10 seconds
    
    # Flask Keep-alive
    FLASK_HOST = '0.0.0.0'
    FLASK_PORT = int(os.getenv('PORT', 8080))
    
    # Database
    DATA_DIR = 'data'
    USERS_FILE = 'users.json'
    WATCHLIST_FILE = 'watchlist.json'
    BANLIST_FILE = 'banlist.json'
    PENDING_FILE = 'pending.json'
    TIME_FORMAT = '%Y-%m-%d %H:%M:%S'


# ==================== LOGGING SETUP ====================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ==================== DATABASE MANAGER ====================

class DatabaseManager:
    """Persistent JSON storage manager with thread-safe operations"""
    
    def __init__(self):
        self.data_dir = Path(Config.DATA_DIR)
        self.data_dir.mkdir(exist_ok=True)
        
        self.users_file = self.data_dir / Config.USERS_FILE
        self.watchlist_file = self.data_dir / Config.WATCHLIST_FILE
        self.banlist_file = self.data_dir / Config.BANLIST_FILE
        self.pending_file = self.data_dir / Config.PENDING_FILE
        
        # Initialize data structures
        self.users = self._load_json(self.users_file, {})
        self.watchlist = self._load_json(self.watchlist_file, {})
        self.banlist = self._load_json(self.banlist_file, {})
        self.pending = self._load_json(self.pending_file, {})
        
        # Track last status
        self.last_status = {}
        
        logger.info("✅ Database initialized successfully")
    
    def _load_json(self, file_path: Path, default: Any) -> Any:
        try:
            if file_path.exists():
                with open(file_path, 'r') as f:
                    return json.load(f)
            return default
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return default
    
    def _save_json(self, file_path: Path, data: Any) -> bool:
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving {file_path}: {e}")
            return False
    
    def save_all(self):
        self._save_json(self.users_file, self.users)
        self._save_json(self.watchlist_file, self.watchlist)
        self._save_json(self.banlist_file, self.banlist)
        self._save_json(self.pending_file, self.pending)
    
    # ===== USER MANAGEMENT =====
    
    def get_user(self, user_id: int) -> Dict:
        return self.users.get(str(user_id), {})
    
    def create_user(self, user_id: int, username: str = "", first_name: str = "") -> Dict:
        str_id = str(user_id)
        if str_id not in self.users:
            self.users[str_id] = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'role': 'user',
                'subscription_expiry': None,
                'joined_date': datetime.now().strftime(Config.TIME_FORMAT),
                'approved_by': None,
                'approved_days': 0,
                'verified': False,
                'notification_preferences': {
                    'ban_alerts': True,
                    'unban_alerts': True
                }
            }
            self.save_all()
        return self.users[str_id]
    
    def update_user(self, user_id: int, **kwargs) -> bool:
        str_id = str(user_id)
        if str_id in self.users:
            self.users[str_id].update(kwargs)
            self.save_all()
            return True
        return False
    
    def get_all_users(self) -> Dict:
        return self.users
    
    # ===== WATCHLIST MANAGEMENT =====
    
    def get_watchlist(self, user_id: int) -> List[str]:
        return self.watchlist.get(str(user_id), [])
    
    def add_to_watchlist(self, user_id: int, username: str) -> bool:
        str_id = str(user_id)
        if str_id not in self.watchlist:
            self.watchlist[str_id] = []
        
        username = username.lower().strip().lstrip('@')
        if username not in self.watchlist[str_id]:
            self.watchlist[str_id].append(username)
            self.save_all()
            return True
        return False
    
    def remove_from_watchlist(self, user_id: int, username: str) -> bool:
        str_id = str(user_id)
        if str_id in self.watchlist:
            username = username.lower().strip().lstrip('@')
            if username in self.watchlist[str_id]:
                self.watchlist[str_id].remove(username)
                self.save_all()
                return True
        return False
    
    def get_all_watchlist_items(self) -> Dict[str, List[int]]:
        """Get all watchlist items grouped by username"""
        result = {}
        for user_id_str, usernames in self.watchlist.items():
            for username in usernames:
                if username not in result:
                    result[username] = []
                result[username].append(int(user_id_str))
        return result
    
    def get_watchlist_count(self, user_id: int) -> int:
        return len(self.watchlist.get(str(user_id), []))
    
    def get_total_watchlist_count(self) -> int:
        total = 0
        for usernames in self.watchlist.values():
            total += len(usernames)
        return total
    
    # ===== BANLIST MANAGEMENT =====
    
    def get_banlist(self, user_id: int) -> List[str]:
        return self.banlist.get(str(user_id), [])
    
    def add_to_banlist(self, user_id: int, username: str) -> bool:
        str_id = str(user_id)
        if str_id not in self.banlist:
            self.banlist[str_id] = []
        
        username = username.lower().strip().lstrip('@')
        if username not in self.banlist[str_id]:
            self.banlist[str_id].append(username)
            self.save_all()
            return True
        return False
    
    def remove_from_banlist(self, user_id: int, username: str) -> bool:
        str_id = str(user_id)
        if str_id in self.banlist:
            username = username.lower().strip().lstrip('@')
            if username in self.banlist[str_id]:
                self.banlist[str_id].remove(username)
                self.save_all()
                return True
        return False
    
    def get_all_banlist_items(self) -> Dict[str, List[int]]:
        """Get all banlist items grouped by username"""
        result = {}
        for user_id_str, usernames in self.banlist.items():
            for username in usernames:
                if username not in result:
                    result[username] = []
                result[username].append(int(user_id_str))
        return result
    
    def get_banlist_count(self, user_id: int) -> int:
        return len(self.banlist.get(str(user_id), []))
    
    def get_total_banlist_count(self) -> int:
        total = 0
        for usernames in self.banlist.values():
            total += len(usernames)
        return total
    
    def move_from_watch_to_ban(self, user_id: int, username: str):
        """Move username from watchlist to banlist"""
        self.remove_from_watchlist(user_id, username)
        self.add_to_banlist(user_id, username)
    
    def move_from_ban_to_watch(self, user_id: int, username: str):
        """Move username from banlist to watchlist"""
        self.remove_from_banlist(user_id, username)
        self.add_to_watchlist(user_id, username)
    
    # ===== PENDING VERIFICATIONS =====
    
    def add_pending(self, username: str, user_ids: List[int], old_status: str, new_status: str, list_type: str, details: Dict):
        """Add username to pending verification"""
        username = username.lower().strip().lstrip('@')
        self.pending[username] = {
            'user_ids': user_ids,
            'old_status': old_status,
            'new_status': new_status,
            'list_type': list_type,
            'details': details,
            'first_detected': datetime.now().strftime(Config.TIME_FORMAT),
            'verified': False
        }
        self.save_all()
        logger.info(f"➕ Added @{username} to pending: {old_status} → {new_status}")
    
    def get_pending(self, username: str) -> Optional[Dict]:
        username = username.lower().strip().lstrip('@')
        return self.pending.get(username)
    
    def remove_pending(self, username: str):
        username = username.lower().strip().lstrip('@')
        if username in self.pending:
            del self.pending[username]
            self.save_all()
    
    def get_all_pending(self) -> Dict:
        return self.pending


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
        """Check username with retry logic"""
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                session = await self._get_session()
                url = f"{self.base_url}/insta={username}?api_key={self.api_key}"
                
                logger.info(f"🔍 Checking API (attempt {attempt+1}): {url}")
                
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
                        logger.warning(f"⚠️ HTTP {response.status} for @{username}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        return 'BANNED', {}, ''
                        
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout for @{username}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return 'BANNED', {}, ''
            except Exception as e:
                logger.error(f"❌ Error checking {username}: {e}")
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
    
    def __init__(self, db: DatabaseManager, api_client: InstagramAPIClient, bot_app: Application):
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
            logger.info("✅ Monitoring engine started - 2-STEP VERIFICATION")
    
    async def stop(self):
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️ Monitoring engine stopped")
    
    async def _monitoring_loop(self):
        while self.is_running:
            try:
                start_time = datetime.now()
                logger.info("🔄 Starting monitoring cycle")
                
                # Check pending verifications
                await self._check_pending()
                
                # Get all items
                watchlist_items = self.db.get_all_watchlist_items()
                banlist_items = self.db.get_all_banlist_items()
                
                all_usernames = set(watchlist_items.keys()) | set(banlist_items.keys())
                
                # Check each username
                for username in all_usernames:
                    try:
                        user_ids = []
                        list_type = 'watch'
                        
                        if username in watchlist_items:
                            user_ids.extend(watchlist_items[username])
                        
                        if username in banlist_items:
                            user_ids.extend(banlist_items[username])
                            list_type = 'ban' if username not in watchlist_items else 'both'
                        
                        await self._check_single(username, user_ids, list_type)
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        logger.error(f"❌ Error checking {username}: {e}")
                        continue
                
                elapsed = (datetime.now() - start_time).total_seconds()
                sleep_time = max(Config.CHECK_INTERVAL - elapsed, 60)
                
                logger.info(f"✅ Cycle complete in {elapsed:.1f}s. Next in {sleep_time:.1f}s")
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _check_pending(self):
        """Check pending verifications after 2 minutes"""
        now = datetime.now()
        
        for username, data in list(self.db.get_all_pending().items()):
            try:
                first_detected = datetime.strptime(data['first_detected'], Config.TIME_FORMAT)
                age = (now - first_detected).total_seconds()
                
                if age >= Config.VERIFICATION_DELAY and not data.get('verified', False):
                    logger.info(f"⏱️ Verifying @{username} after {age:.0f}s")
                    
                    status, details, pic = await self.api_client.check_username(username)
                    
                    if status == data['new_status']:
                        logger.info(f"✅ Verified: @{username} still {status}")
                        
                        data['verified'] = True
                        
                        # ✅ FIX: Use new details for ACTIVE/unban
                        if status == 'ACTIVE' and details:
                            final_details = details
                            logger.info(f"📸 Using NEW details for @{username}")
                        else:
                            final_details = data['details']
                        
                        await self._send_alert(
                            username,
                            data['user_ids'],
                            status,
                            data['list_type'],
                            final_details,
                            pic,
                            data['first_detected']
                        )
                        
                        self.db.remove_pending(username)
                    else:
                        logger.info(f"❌ False alarm: @{username} changed back")
                        self.db.remove_pending(username)
                        
            except Exception as e:
                logger.error(f"❌ Error checking pending {username}: {e}")
    
    async def _check_single(self, username: str, user_ids: List[int], list_type: str):
        """Check single username"""
        status, details, pic = await self.api_client.check_username(username)
        
        prev = self.last_status.get(username)
        
        if prev and prev != status:
            logger.info(f"⚠️ Status change: @{username} {prev} → {status}")
            
            if not self.db.get_pending(username):
                self.db.add_pending(
                    username, user_ids, prev, status, list_type, details
                )
                logger.info(f"⏳ Added to pending - will recheck in 2 min")
        
        self.last_status[username] = status
    
    async def _send_alert(self, username: str, user_ids: List[int], status: str, 
                         list_type: str, details: Dict, pic: str, detection_time: str):
        """Send verified alert"""
        
        for user_id in user_ids:
            try:
                user = self.db.get_user(user_id)
                
                if status == 'BANNED' and (list_type == 'watch' or list_type == 'both'):
                    self.db.move_from_watch_to_ban(user_id, username)
                    
                    if user.get('notification_preferences', {}).get('ban_alerts', True):
                        await self._send_ban_alert(user_id, username, details, pic, detection_time)
                
                elif status == 'ACTIVE' and (list_type == 'ban' or list_type == 'both'):
                    self.db.move_from_ban_to_watch(user_id, username)
                    
                    if user.get('notification_preferences', {}).get('unban_alerts', True):
                        await self._send_unban_alert(user_id, username, details, pic, detection_time)
                        
            except Exception as e:
                logger.error(f"❌ Error alerting user {user_id}: {e}")
    
    async def _send_ban_alert(self, user_id: int, username: str, details: Dict, pic: str, detection_time: str):
        """Send ban alert with correct timing"""
        try:
            # Format numbers
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
            
            message = f"""
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
⏰ <b>Ban Time:</b> {detection_time} IST

━━━━━━━━━━━━━━━━━━━━━
<i>Account moved to Ban List automatically</i>

Powered by @proxyfxc
"""
            
            keyboard = [[InlineKeyboardButton("📞 CONTACT @proxyfxc", url="https://t.me/proxyfxc")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if pic:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(pic) as resp:
                            if resp.status == 200:
                                photo = await resp.read()
                                await self.bot_app.bot.send_photo(
                                    chat_id=user_id,
                                    photo=photo,
                                    caption=message,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=reply_markup
                                )
                                return
                except:
                    pass
            
            await self.bot_app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"❌ Failed to send ban alert: {e}")
    
    async def _send_unban_alert(self, user_id: int, username: str, details: Dict, pic: str, detection_time: str):
        """Send unban alert with correct timing and FULL details"""
        try:
            # Format numbers - details will be from API when unbanned
            name = details.get('full_name', username)
            followers = details.get('follower_count', 'N/A')
            following = details.get('following_count', 'N/A')
            posts = details.get('media_count', 'N/A')
            is_private = details.get('is_private', False)
            
            # Convert to int for formatting if possible
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
            
            message = f"""
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
⏰ <b>Unban Time:</b> {detection_time} IST

━━━━━━━━━━━━━━━━━━━━━
<i>Account moved back to Watch List automatically</i>

Powered by @proxyfxc
"""
            
            keyboard = [[InlineKeyboardButton("📞 CONTACT @proxyfxc", url="https://t.me/proxyfxc")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if pic:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(pic) as resp:
                            if resp.status == 200:
                                photo = await resp.read()
                                await self.bot_app.bot.send_photo(
                                    chat_id=user_id,
                                    photo=photo,
                                    caption=message,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=reply_markup
                                )
                                return
                except:
                    pass
            
            await self.bot_app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"❌ Failed to send unban alert: {e}")


# ==================== FLASK KEEP-ALIVE ====================

app = Flask(__name__)
monitoring_engine = None
db = None

@app.route('/')
def home():
    return jsonify({
        'status': 'alive',
        'time': datetime.now().strftime(Config.TIME_FORMAT),
        'service': 'Instagram Monitor Bot'
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'time': datetime.now().strftime(Config.TIME_FORMAT),
        'monitoring': monitoring_engine.is_running if monitoring_engine else False
    })

def run_flask():
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT)


# ==================== TELEGRAM BOT HANDLERS ====================

class BotHandlers:
    """All Telegram bot command and callback handlers"""
    
    def __init__(self, db: DatabaseManager, api_client: InstagramAPIClient):
        self.db = db
        self.api_client = api_client
    
    def is_owner(self, user_id: int) -> bool:
        return user_id in Config.OWNER_IDS
    
    def is_admin(self, user_id: int) -> bool:
        if self.is_owner(user_id):
            return True
        user = self.db.get_user(user_id)
        return user.get('role') == 'admin'
    
    def has_subscription(self, user_id: int) -> bool:
        if self.is_admin(user_id):
            return True
        
        user = self.db.get_user(user_id)
        expiry = user.get('subscription_expiry')
        
        if not expiry:
            return False
        
        try:
            exp_date = datetime.strptime(expiry, Config.TIME_FORMAT)
            return exp_date > datetime.now()
        except:
            return False
    
    def get_limit(self, user_id: int) -> int:
        if self.is_admin(user_id):
            return float('inf')
        return Config.DEFAULT_USER_LIMIT
    
    def format_account(self, username: str, status: str, details: Dict) -> str:
        """Format account info"""
        if status == 'ACTIVE':
            name = details.get('full_name', username)
            followers = details.get('follower_count', 0)
            following = details.get('following_count', 0)
            posts = details.get('media_count', 0)
            private = details.get('is_private', False)
            
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
            
            followers = f"{followers:,}" if isinstance(followers, int) else str(followers)
            following = f"{following:,}" if isinstance(following, int) else str(following)
            posts = f"{posts:,}" if isinstance(posts, int) else str(posts)
            
            return f"""
🟢 ACCOUNT ACTIVE

━━━━━━━━━━━━━━━━━━━━━
Profile: @{username}

👤 Name: {name}
👥 Followers: {followers}
👤 Following: {following}
📸 Posts: {posts}
🔐 Private: {'Yes' if private else 'No'}

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
    
    def format_add_watch(self, username: str, status: str, details: Dict, count: int, limit: Any) -> str:
        """Format add to watch message"""
        if status == 'ACTIVE':
            name = details.get('full_name', username)
            followers = details.get('follower_count', 0)
            following = details.get('following_count', 0)
            posts = details.get('media_count', 0)
            private = details.get('is_private', False)
            
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
            
            followers = f"{followers:,}" if isinstance(followers, int) else str(followers)
            following = f"{following:,}" if isinstance(following, int) else str(following)
            posts = f"{posts:,}" if isinstance(posts, int) else str(posts)
            
            limit_text = f"{count}/{limit}" if limit != float('inf') else f"{count}/∞"
            
            return f"""
✅ <b>ACCOUNT ADDED TO WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

👤 <b>Name:</b> {name}
👥 <b>Followers:</b> {followers}
👤 <b>Following:</b> {following}
📸 <b>Posts:</b> {posts}
🔐 <b>Private:</b> {'Yes' if private else 'No'}
🟢 <b>Status:</b> ACTIVE

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Watch List:</b> {limit_text}

<i>2-step verification active - will confirm before alerts</i>
━━━━━━━━━━━━━━━━━━━━━
"""
        elif status == 'BANNED':
            limit_text = f"{count}/{limit}" if limit != float('inf') else f"{count}/∞"
            
            return f"""
⚠️ <b>ACCOUNT ADDED TO WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

🔴 <b>Status:</b> BANNED / SUSPENDED
⚠️ <b>Note:</b> Currently banned - will notify when unbanned

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Watch List:</b> {limit_text}

<i>2-step verification active</i>
━━━━━━━━━━━━━━━━━━━━━
"""
        else:
            limit_text = f"{count}/{limit}" if limit != float('inf') else f"{count}/∞"
            
            return f"""
❓ <b>ACCOUNT ADDED TO WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

❓ <b>Status:</b> UNKNOWN / NOT FOUND

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Watch List:</b> {limit_text}

<i>Will notify if account becomes active</i>
━━━━━━━━━━━━━━━━━━━━━
"""
    
    # ===== FORCE JOIN =====
    
    async def check_join(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if user joined @proxydominates"""
        try:
            user = self.db.get_user(user_id)
            if user.get('verified', False):
                return True
            
            channel = Config.FORCE_JOIN_CHANNEL['username']
            if not channel.startswith('@'):
                channel = '@' + channel
            
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            
            if member.status in ['member', 'administrator', 'creator']:
                self.db.update_user(user_id, verified=True)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Force join error: {e}")
            return False
    
    async def send_join_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send force join message"""
        channel = Config.FORCE_JOIN_CHANNEL
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join @proxydominates", url=channel['url'])],
            [InlineKeyboardButton("✅ I've Joined", callback_data="verify_join")]
        ])
        
        msg = """
<b>🔒 CHANNEL REQUIRED</b>

Join @proxydominates to use bot:

━━━━━━━━━━━━━━━━━━━━━
<b>📢 @proxydominates</b>
• Updates
• Support
• Community
━━━━━━━━━━━━━━━━━━━━━

Click below to verify
"""
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, 
                                       reply_markup=keyboard, disable_web_page_preview=True)
    
    # ===== COMMANDS =====
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start"""
        user = update.effective_user
        self.db.create_user(user.id, user.username or "", user.first_name or "")
        
        if not await self.check_join(user.id, context):
            await self.send_join_message(update, context)
            return
        
        await self.main_menu(update, context)
        
        if not self.is_admin(user.id):
            for owner in Config.OWNER_IDS:
                try:
                    await context.bot.send_message(
                        owner,
                        f"👤 <b>New User</b>\n\nName: {user.first_name}\nID: <code>{user.id}</code>\nUsername: @{user.username or 'N/A'}",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
    
    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu"""
        user = update.effective_user
        watch = self.db.get_watchlist_count(user.id)
        ban = self.db.get_banlist_count(user.id)
        limit = self.get_limit(user.id)
        
        keyboard = [
            [InlineKeyboardButton("📋 Watch List", callback_data="menu_watch"),
             InlineKeyboardButton("🚫 Ban List", callback_data="menu_ban")],
            [InlineKeyboardButton("📊 Status", callback_data="menu_status"),
             InlineKeyboardButton("🔍 Check", callback_data="menu_check")],
            [InlineKeyboardButton("➕ Add Watch", callback_data="menu_addwatch"),
             InlineKeyboardButton("➖ Remove Watch", callback_data="menu_removewatch")],
            [InlineKeyboardButton("⛔ Add Ban", callback_data="menu_addban"),
             InlineKeyboardButton("✅ Remove Ban", callback_data="menu_removeban")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="menu_help")],
            [InlineKeyboardButton("📞 CONTACT @proxyfxc", url="https://t.me/proxyfxc")]
        ]
        
        if self.is_admin(user.id):
            keyboard.insert(4, [InlineKeyboardButton("⚙️ Admin", callback_data="menu_admin")])
        
        reply = InlineKeyboardMarkup(keyboard)
        
        role = self.db.get_user(user.id).get('role', 'user').upper()
        sub = '✅ Active' if self.has_subscription(user.id) else '❌ Inactive'
        watch_text = f"{watch}/{limit if limit != float('inf') else '∞'}"
        
        msg = f"""
<b>🚀 INSTAGRAM MONITOR PRO</b>

Welcome <b>{user.first_name}</b>!

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Status:</b>
• Role: <code>{role}</code>
• Subscription: <code>{sub}</code>
• Watch List: <code>{watch_text}</code>
• Ban List: <code>{ban}</code>
━━━━━━━━━━━━━━━━━━━━━

<i>Powered by @proxyfxc</i>
"""
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
        else:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show watch list"""
        user = update.effective_user
        watch = self.db.get_watchlist(user.id)
        count = len(watch)
        limit = self.get_limit(user.id)
        
        msg = f"""
<b>📋 WATCH LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📊 Used: <code>{count}/{limit if limit != float('inf') else '∞'}</code>
━━━━━━━━━━━━━━━━━━━━━

<b>📝 Your List:</b>
"""
        
        if watch:
            for i, u in enumerate(watch[:10], 1):
                msg += f"{i}. @{u}\n"
            if len(watch) > 10:
                msg += f"...and {len(watch) - 10} more\n"
        else:
            msg += "<i>Empty</i>\n"
        
        msg += "\n/addwatch /removewatch"
        
        keyboard = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
        else:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show ban list"""
        user = update.effective_user
        ban = self.db.get_banlist(user.id)
        
        msg = f"""
<b>🚫 BAN LIST</b>

━━━━━━━━━━━━━━━━━━━━━
📊 Banned: <code>{len(ban)}</code>
━━━━━━━━━━━━━━━━━━━━━

<b>📝 Your List:</b>
"""
        
        if ban:
            for i, u in enumerate(ban[:10], 1):
                msg += f"{i}. @{u}\n"
            if len(ban) > 10:
                msg += f"...and {len(ban) - 10} more\n"
        else:
            msg += "<i>Empty</i>\n"
        
        msg += "\n/addban /removeban"
        
        keyboard = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
        else:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check all watchlist accounts"""
        user = update.effective_user
        
        if not await self.check_join(user.id, context):
            await self.send_join_message(update, context)
            return
        
        watch = self.db.get_watchlist(user.id)
        
        if not watch:
            kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
            await update.message.reply_text("📭 No accounts", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
            return
        
        status = await update.message.reply_text(f"🔄 Checking {len(watch)} accounts...", parse_mode=ParseMode.HTML)
        
        results = []
        active = banned = 0
        current = 0
        
        for username in watch:
            current += 1
            await status.edit_text(f"🔄 {current}/{len(watch)}: @{username}", parse_mode=ParseMode.HTML)
            
            try:
                s, d, _ = await self.api_client.check_username(username)
                
                if s == 'ACTIVE':
                    active += 1
                elif s == 'BANNED':
                    banned += 1
                
                results.append(self.format_account(username, s, d) + "\n━━━━━━━━━━━━━━━━━━━━━\n")
                
                if current < len(watch):
                    await asyncio.sleep(Config.STATUS_DELAY)
                
            except Exception as e:
                logger.error(f"Status error {username}: {e}")
                results.append(self.format_account(username, 'UNKNOWN', {}) + "\n━━━━━━━━━━━━━━━━━━━━━\n")
        
        header = f"""
<b>📊 RESULTS</b>

━━━━━━━━━━━━━━━━━━━━━
📋 Total: {len(watch)}
🟢 Active: {active}
🔴 Banned: {banned}
❓ Unknown: {len(watch) - active - banned}
━━━━━━━━━━━━━━━━━━━━━

"""
        
        final = header + "".join(results) + "\nPowered by @proxyfxc"
        kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(kb)
        
        if len(final) > 4096:
            await status.delete()
            parts = [final[i:i+4096] for i in range(0, len(final), 4096)]
            for i, p in enumerate(parts):
                if i == 0:
                    await update.message.reply_text(p, parse_mode=ParseMode.HTML, reply_markup=reply)
                else:
                    await update.message.reply_text(p, parse_mode=ParseMode.HTML)
        else:
            await status.edit_text(final, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def check_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for check"""
        kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(kb)
        
        msg = """
<b>🔍 CHECK USERNAME</b>

━━━━━━━━━━━━━━━━━━━━━
Send username:

<code>/check cristiano</code>
<code>/check @username</code>
━━━━━━━━━━━━━━━━━━━━━
"""
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check single username"""
        user = update.effective_user
        
        if not await self.check_join(user.id, context):
            await self.send_join_message(update, context)
            return
        
        if not context.args:
            await self.check_prompt(update, context)
            return
        
        username = context.args[0].lower().strip().lstrip('@')
        msg = await update.message.reply_text(f"🔍 Checking @{username}...", parse_mode=ParseMode.HTML)
        
        try:
            status, details, pic = await self.api_client.check_username(username)
            
            text = self.format_account(username, status, details) + "\nPowered by @proxyfxc"
            kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
            reply = InlineKeyboardMarkup(kb)
            
            if status == 'ACTIVE' and pic:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(pic) as r:
                            if r.status == 200:
                                photo = await r.read()
                                await msg.delete()
                                await update.message.reply_photo(photo=photo, caption=text, 
                                                               parse_mode=ParseMode.HTML, reply_markup=reply)
                                return
                except:
                    pass
            
            await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply)
            
        except Exception as e:
            logger.error(f"Check error: {e}")
            await msg.edit_text("❌ Error", parse_mode=ParseMode.HTML)
    
    async def addwatch_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for add watch"""
        kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(kb)
        
        msg = """
<b>➕ ADD TO WATCH</b>

━━━━━━━━━━━━━━━━━━━━━
Send username:

<code>/addwatch cristiano</code>
<code>/addwatch @username</code>
━━━━━━━━━━━━━━━━━━━━━
"""
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def addwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add to watchlist"""
        user = update.effective_user
        
        if not await self.check_join(user.id, context):
            await self.send_join_message(update, context)
            return
        
        if not self.has_subscription(user.id) and not self.is_admin(user.id):
            await update.message.reply_text("❌ Subscription required", parse_mode=ParseMode.HTML)
            return
        
        count = self.db.get_watchlist_count(user.id)
        limit = self.get_limit(user.id)
        
        if count >= limit and limit != float('inf'):
            await update.message.reply_text(f"❌ Limit {limit}", parse_mode=ParseMode.HTML)
            return
        
        if not context.args:
            await self.addwatch_prompt(update, context)
            return
        
        username = context.args[0].lower().strip().lstrip('@')
        
        if username in self.db.get_watchlist(user.id):
            # Already exists - show current status
            msg = await update.message.reply_text(f"🔍 Checking @{username}...", parse_mode=ParseMode.HTML)
            status, details, _ = await self.api_client.check_username(username)
            text = self.format_account(username, status, details) + "\n⚠️ <i>Already in watch list</i>"
            kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
            await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
            return
        
        # Add to watchlist
        self.db.add_to_watchlist(user.id, username)
        
        # Get details
        msg = await update.message.reply_text(f"🔍 Fetching @{username}...", parse_mode=ParseMode.HTML)
        status, details, pic = await self.api_client.check_username(username)
        
        new_count = count + 1
        text = self.format_add_watch(username, status, details, new_count, limit)
        kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(kb)
        
        if status == 'ACTIVE' and pic:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(pic) as r:
                        if r.status == 200:
                            photo = await r.read()
                            await msg.delete()
                            await update.message.reply_photo(photo=photo, caption=text, 
                                                           parse_mode=ParseMode.HTML, reply_markup=reply)
                            return
            except:
                pass
        
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def removewatch_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for remove watch"""
        user = update.effective_user
        watch = self.db.get_watchlist(user.id)
        
        msg = """
<b>➖ REMOVE FROM WATCH</b>

━━━━━━━━━━━━━━━━━━━━━
Send username to remove:

<code>/removewatch cristiano</code>
━━━━━━━━━━━━━━━━━━━━━

<b>Your List:</b>
"""
        
        if watch:
            for u in watch[:10]:
                msg += f"• @{u}\n"
        else:
            msg += "<i>Empty</i>"
        
        kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(kb)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def removewatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove from watchlist"""
        user = update.effective_user
        
        if not await self.check_join(user.id, context):
            await self.send_join_message(update, context)
            return
        
        if not context.args:
            await self.removewatch_prompt(update, context)
            return
        
        username = context.args[0].lower().strip().lstrip('@')
        
        if self.db.remove_from_watchlist(user.id, username):
            await update.message.reply_text(f"✅ @{username} removed", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ @{username} not found", parse_mode=ParseMode.HTML)
    
    async def addban_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for add ban"""
        kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(kb)
        
        msg = """
<b>⛔ ADD TO BAN</b>

━━━━━━━━━━━━━━━━━━━━━
Send username:

<code>/addban cristiano</code>
━━━━━━━━━━━━━━━━━━━━━
"""
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def addban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add to banlist"""
        user = update.effective_user
        
        if not await self.check_join(user.id, context):
            await self.send_join_message(update, context)
            return
        
        if not self.has_subscription(user.id) and not self.is_admin(user.id):
            await update.message.reply_text("❌ Subscription required", parse_mode=ParseMode.HTML)
            return
        
        if not context.args:
            await self.addban_prompt(update, context)
            return
        
        username = context.args[0].lower().strip().lstrip('@')
        
        if username in self.db.get_banlist(user.id):
            await update.message.reply_text(f"⚠️ @{username} already in ban list", parse_mode=ParseMode.HTML)
            return
        
        self.db.add_to_banlist(user.id, username)
        await update.message.reply_text(f"✅ @{username} added to ban list", parse_mode=ParseMode.HTML)
    
    async def removeban_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for remove ban"""
        user = update.effective_user
        ban = self.db.get_banlist(user.id)
        
        msg = """
<b>✅ REMOVE FROM BAN</b>

━━━━━━━━━━━━━━━━━━━━━
Send username:

<code>/removeban cristiano</code>
━━━━━━━━━━━━━━━━━━━━━

<b>Your List:</b>
"""
        
        if ban:
            for u in ban[:10]:
                msg += f"• @{u}\n"
        else:
            msg += "<i>Empty</i>"
        
        kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
        reply = InlineKeyboardMarkup(kb)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply)
    
    async def removeban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove from banlist"""
        user = update.effective_user
        
        if not await self.check_join(user.id, context):
            await self.send_join_message(update, context)
            return
        
        if not context.args:
            await self.removeban_prompt(update, context)
            return
        
        username = context.args[0].lower().strip().lstrip('@')
        
        if self.db.remove_from_banlist(user.id, username):
            await update.message.reply_text(f"✅ @{username} removed from ban list", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ @{username} not found", parse_mode=ParseMode.HTML)
    
    # ===== ADMIN COMMANDS =====
    
    async def approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Approve user"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /approve [user_id] [days]", parse_mode=ParseMode.HTML)
            return
        
        try:
            target = int(context.args[0])
            days = int(context.args[1])
        except:
            await update.message.reply_text("❌ Invalid numbers")
            return
        
        exp = (datetime.now() + timedelta(days=days)).strftime(Config.TIME_FORMAT)
        
        if self.db.update_user(target, role='user', subscription_expiry=exp, approved_days=days):
            await update.message.reply_text(f"✅ User {target} approved for {days} days", parse_mode=ParseMode.HTML)
            
            try:
                await context.bot.send_message(
                    target,
                    f"✅ <b>APPROVED</b>\n\n📅 {days} days\n⏰ Expires: {exp}\n\nLimit: {Config.DEFAULT_USER_LIMIT}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    async def addadmin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add admin"""
        if not self.is_owner(update.effective_user.id):
            await update.message.reply_text("❌ Owner only")
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /addadmin [user_id]")
            return
        
        try:
            target = int(context.args[0])
        except:
            await update.message.reply_text("❌ Invalid ID")
            return
        
        if self.db.update_user(target, role='admin'):
            await update.message.reply_text(f"✅ User {target} is now admin", parse_mode=ParseMode.HTML)
            
            try:
                await context.bot.send_message(target, "👑 You are now admin!", parse_mode=ParseMode.HTML)
            except:
                pass
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Admin only")
            return
        
        if not context.args and not update.message.reply_to_message:
            await update.message.reply_text("Usage: /broadcast [message]")
            return
        
        if update.message.reply_to_message:
            msg = update.message.reply_to_message.text
        else:
            msg = ' '.join(context.args)
        
        status = await update.message.reply_text("📤 Broadcasting...")
        
        users = self.db.get_all_users()
        total = len(users)
        success = 0
        
        for uid in users:
            try:
                await context.bot.send_message(
                    int(uid),
                    f"📢 <b>BROADCAST</b>\n\n━━━━━━━━━━━━━━━━━━━━━\n{msg}\n━━━━━━━━━━━━━━━━━━━━━\n\nPowered by @proxyfxc",
                    parse_mode=ParseMode.HTML
                )
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
        
        await status.edit_text(f"✅ Broadcast: {success}/{total}", parse_mode=ParseMode.HTML)
    
    # ===== CALLBACK =====
    
    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all callbacks"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        data = query.data
        
        logger.info(f"Button: {data} by {user.id}")
        
        if data == "verify_join":
            await query.edit_message_text("🔄 Verifying...", parse_mode=ParseMode.HTML)
            
            if await self.check_join(user.id, context):
                await self.main_menu(update, context)
            else:
                channel = Config.FORCE_JOIN_CHANNEL
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join", url=channel['url'])],
                    [InlineKeyboardButton("🔄 Try Again", callback_data="verify_join")]
                ])
                await query.edit_message_text(
                    "❌ Verification failed\n\nPlease join and try again",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb
                )
            return
        
        if not await self.check_join(user.id, context):
            await self.send_join_message(update, context)
            return
        
        # Menu handling
        if data == "menu_main":
            await self.main_menu(update, context)
        elif data == "menu_watch":
            await self.watch(update, context)
        elif data == "menu_ban":
            await self.ban(update, context)
        elif data == "menu_status":
            await self.status(update, context)
        elif data == "menu_check":
            await self.check_prompt(update, context)
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
<b>📚 HELP</b>

━━━━━━━━━━━━━━━━━━━━━
<b>Commands:</b>
/watch - View watch list
/ban - View ban list
/status - Check all
/check [user] - Check one
/addwatch [user] - Add to watch
/removewatch [user] - Remove from watch
/addban [user] - Add to ban
/removeban [user] - Remove from ban

<b>Admin:</b>
/approve [id] [days]
/broadcast [message]
/addadmin [id]

<b>How it works:</b>
• 5-min checks
• 2-step verification (2 min wait)
• Auto move lists
• Indian time (IST)
• No fake alerts
━━━━━━━━━━━━━━━━━━━━━
"""
            kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
            await query.edit_message_text(help_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        
        elif data == "menu_admin" and self.is_admin(user.id):
            users = len(self.db.get_all_users())
            watch = self.db.get_total_watchlist_count()
            ban = self.db.get_total_banlist_count()
            
            text = f"""
<b>⚙️ ADMIN</b>

━━━━━━━━━━━━━━━━━━━━━
📊 <b>Stats:</b>
• Users: {users}
• Watchlist: {watch}
• Banlist: {ban}
• Mode: 2-STEP
━━━━━━━━━━━━━━━━━━━━━

<b>Commands:</b>
/approve [id] [days]
/broadcast [message]
/addadmin [id]
"""
            kb = [[InlineKeyboardButton("🔙 Main", callback_data="menu_main")]]
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))


# ==================== ERROR HANDLER ====================

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused {context.error}")


# ==================== MAIN ====================

db = None
monitor = None
api = None

async def run():
    """Run bot"""
    global db, monitor, api
    
    try:
        logger.info("🚀 Starting bot...")
        
        db = DatabaseManager()
        api = InstagramAPIClient()
        
        app = Application.builder().token(Config.BOT_TOKEN).concurrent_updates(True).build()
        
        handlers = BotHandlers(db, api)
        
        # Commands
        app.add_handler(CommandHandler("start", handlers.start))
        app.add_handler(CommandHandler("watch", handlers.watch))
        app.add_handler(CommandHandler("ban", handlers.ban))
        app.add_handler(CommandHandler("status", handlers.status))
        app.add_handler(CommandHandler("check", handlers.check))
        app.add_handler(CommandHandler("addwatch", handlers.addwatch))
        app.add_handler(CommandHandler("removewatch", handlers.removewatch))
        app.add_handler(CommandHandler("addban", handlers.addban))
        app.add_handler(CommandHandler("removeban", handlers.removeban))
        app.add_handler(CommandHandler("approve", handlers.approve))
        app.add_handler(CommandHandler("addadmin", handlers.addadmin))
        app.add_handler(CommandHandler("broadcast", handlers.broadcast))
        
        app.add_handler(CallbackQueryHandler(handlers.callback))
        app.add_error_handler(error)
        
        monitor = MonitoringEngine(db, api, app)
        asyncio.create_task(monitor.start())
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
        logger.info("✅ Bot is running!")
        logger.info("✅ 5-min checks | 2-step verification | IST time")
        
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"❌ Fatal: {e}")
        traceback.print_exc()

def main():
    logger.info("Starting main...")
    
    # Flask thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Flask started")
    
    # Run bot
    try:
        asyncio.run(run())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run())
    except Exception as e:
        logger.error(f"Main error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
