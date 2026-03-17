"""
Professional Instagram Username Monitor Bot
Single Channel Force Join - @proxydominates
All buttons working, subscription system, monitoring
Author: @proxyfxc
Version: 4.2.0 (UPDATED with Profile Pictures)
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

# Third-party imports
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
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
    API_KEY = 'PAID_INSTA_SELL187'  # Hardcoded API key
    API_BASE_URL = 'https://tg-user-id-to-number-4erk.onrender.com/api'  # Hardcoded base URL
    
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
    CONFIRMATION_THRESHOLD = 3  # 3 confirmations needed
    STATUS_DELAY = 10  # 10 seconds delay between status checks
    
    # Flask Keep-alive
    FLASK_HOST = '0.0.0.0'
    FLASK_PORT = int(os.getenv('PORT', 8080))
    
    # Database
    DATA_DIR = 'data'
    USERS_FILE = 'users.json'
    WATCHLIST_FILE = 'watchlist.json'
    BANLIST_FILE = 'banlist.json'
    CONFIRMATIONS_FILE = 'confirmations.json'


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
        self.confirmations_file = self.data_dir / Config.CONFIRMATIONS_FILE
        
        # Initialize data structures
        self.users = self._load_json(self.users_file, {})
        self.watchlist = self._load_json(self.watchlist_file, {})
        self.banlist = self._load_json(self.banlist_file, {})
        self.confirmations = self._load_json(self.confirmations_file, {})
        
        logger.info("Database initialized successfully")
    
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
        self._save_json(self.confirmations_file, self.confirmations)
    
    # User Management
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
                'joined_date': datetime.now().isoformat(),
                'approved_by': None,
                'approved_days': 0,
                'verified': False,  # For force join
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
    
    # Watchlist Management
    def get_watchlist(self, user_id: int) -> List[str]:
        return self.watchlist.get(str(user_id), [])
    
    def add_to_watchlist(self, user_id: int, username: str) -> bool:
        str_id = str(user_id)
        if str_id not in self.watchlist:
            self.watchlist[str_id] = []
        
        username = username.lower().strip().lstrip('@')
        if username not in self.watchlist[str_id]:
            self.watchlist[str_id].append(username)
            
            if username not in self.confirmations:
                self.confirmations[username] = {
                    'status': None,
                    'count': 0,
                    'last_check': None,
                    'details': {}
                }
            
            self.confirmations[username]['current_list'] = 'watch'
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
    
    # Banlist Management
    def get_banlist(self, user_id: int) -> List[str]:
        return self.banlist.get(str(user_id), [])
    
    def add_to_banlist(self, user_id: int, username: str) -> bool:
        str_id = str(user_id)
        if str_id not in self.banlist:
            self.banlist[str_id] = []
        
        username = username.lower().strip().lstrip('@')
        if username not in self.banlist[str_id]:
            self.banlist[str_id].append(username)
            
            if username not in self.confirmations:
                self.confirmations[username] = {
                    'status': None,
                    'count': 0,
                    'last_check': None,
                    'details': {}
                }
            
            self.confirmations[username]['current_list'] = 'ban'
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
    
    # Confirmation Management
    def update_confirmation(self, username: str, status: str, details: Dict = None) -> Tuple[bool, int]:
        username = username.lower().strip().lstrip('@')
        
        if username not in self.confirmations:
            self.confirmations[username] = {
                'status': None,
                'count': 0,
                'last_check': None,
                'details': {}
            }
        
        conf = self.confirmations[username]
        old_status = conf['status']
        
        conf['last_check'] = datetime.now().isoformat()
        
        if status == 'UNKNOWN' or (old_status and old_status != status):
            conf['count'] = 0
            conf['status'] = status if status != 'UNKNOWN' else None
            conf['details'] = details or {}
            self.save_all()
            return False, 0
        
        if old_status == status:
            conf['count'] += 1
            conf['details'] = details or {}
            self.save_all()
            
            if conf['count'] >= Config.CONFIRMATION_THRESHOLD:
                conf['count'] = 0
                self.save_all()
                return True, Config.CONFIRMATION_THRESHOLD
            return False, conf['count']
        
        conf['status'] = status
        conf['count'] = 1
        conf['details'] = details or {}
        self.save_all()
        return False, 1


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
        """
        Check username with the hardcoded API
        Returns: (status, profile_data, profile_pic_url)
        """
        try:
            session = await self._get_session()
            # Construct URL with hardcoded API key
            url = f"{self.base_url}/insta={username}?api_key={self.api_key}"
            
            logger.info(f"Checking API: {url}")
            
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    logger.info(f"API Response for @{username}: {json.dumps(data)[:200]}...")
                    
                    # Check if status is ok and profile exists
                    if data.get('status') == 'ok' and 'profile' in data:
                        profile = data['profile']
                        profile_pic = profile.get('profile_pic_url_hd', '')
                        return 'ACTIVE', profile, profile_pic
                    elif data.get('error'):
                        return 'BANNED', {}, ''
                    else:
                        return 'BANNED', {}, ''
                else:
                    logger.error(f"HTTP {response.status} for @{username}")
                    return 'BANNED', {}, ''
                        
        except asyncio.TimeoutError:
            logger.error(f"Timeout for @{username}")
            return 'BANNED', {}, ''
        except Exception as e:
            logger.error(f"Error checking username {username}: {e}")
            return 'BANNED', {}, ''
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


# ==================== MONITORING ENGINE ====================

class MonitoringEngine:
    """Background monitoring engine with confirmation system"""
    
    def __init__(self, db: DatabaseManager, api_client: InstagramAPIClient, bot_app: Application):
        self.db = db
        self.api_client = api_client
        self.bot_app = bot_app
        self.is_running = False
        self.task = None
    
    async def start(self):
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self._monitoring_loop())
            logger.info("Monitoring engine started")
    
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
                
                usernames_to_check = {}
                
                # Add watchlist items
                for user_id_str, usernames in self.db.watchlist.items():
                    for username in usernames:
                        if username not in usernames_to_check:
                            usernames_to_check[username] = {
                                'user_ids': [],
                                'list_type': 'watch'
                            }
                        usernames_to_check[username]['user_ids'].append(int(user_id_str))
                
                # Add banlist items
                for user_id_str, usernames in self.db.banlist.items():
                    for username in usernames:
                        if username not in usernames_to_check:
                            usernames_to_check[username] = {
                                'user_ids': [],
                                'list_type': 'ban'
                            }
                        usernames_to_check[username]['user_ids'].append(int(user_id_str))
                
                # Check each username
                for username, info in usernames_to_check.items():
                    try:
                        await self._check_single_username(username, info['user_ids'], info['list_type'])
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
    
    async def _check_single_username(self, username: str, user_ids: List[int], list_type: str):
        status, details, _ = await self.api_client.check_username(username)
        should_alert, count = self.db.update_confirmation(username, status, details)
        
        if should_alert:
            await self._process_alert(username, user_ids, status, list_type, details)
    
    async def _process_alert(self, username: str, user_ids: List[int], status: str, list_type: str, details: Dict):
        current_list = self.db.confirmations.get(username, {}).get('current_list', 'watch')
        
        for user_id in user_ids:
            try:
                user_data = self.db.get_user(user_id)
                
                if status == 'BANNED' and current_list == 'watch':
                    self.db.remove_from_watchlist(user_id, username)
                    self.db.add_to_banlist(user_id, username)
                    
                    if user_data.get('notification_preferences', {}).get('ban_alerts', True):
                        await self._send_ban_alert(user_id, username, details)
                        
                elif status == 'ACTIVE' and current_list == 'ban':
                    self.db.remove_from_banlist(user_id, username)
                    self.db.add_to_watchlist(user_id, username)
                    
                    if user_data.get('notification_preferences', {}).get('unban_alerts', True):
                        await self._send_unban_alert(user_id, username, details)
                        
            except Exception as e:
                logger.error(f"Error processing alert for user {user_id}: {e}")
                continue
    
    async def _send_ban_alert(self, user_id: int, username: str, details: Dict):
        try:
            message = self._format_ban_alert(username, details)
            await self.bot_app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send ban alert: {e}")
    
    async def _send_unban_alert(self, user_id: int, username: str, details: Dict):
        try:
            message = self._format_unban_alert(username, details)
            await self.bot_app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send unban alert: {e}")
    
    def _format_ban_alert(self, username: str, details: Dict) -> str:
        name = details.get('full_name', username)
        followers = details.get('follower_count', 'N/A')
        following = details.get('following_count', 'N/A')
        posts = details.get('media_count', 'N/A')
        is_private = details.get('is_private', False)
        
        return f"""
🔴 <b>BANNED ACCOUNT DETECTED</b> 🔴

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

👤 <b>Name:</b> {name}
👥 <b>Followers:</b> {followers:,}
👤 <b>Following:</b> {following:,}
📸 <b>Posts:</b> {posts:,}
🔐 <b>Private:</b> {'Yes' if is_private else 'No'}

⚠️ <b>Status:</b> <code>BANNED</code>
⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━
<i>Account moved to Ban List</i>

Powered by @proxyfxc
"""
    
    def _format_unban_alert(self, username: str, details: Dict) -> str:
        name = details.get('full_name', username)
        followers = details.get('follower_count', 'N/A')
        following = details.get('following_count', 'N/A')
        posts = details.get('media_count', 'N/A')
        is_private = details.get('is_private', False)
        
        return f"""
🟢 <b>ACCOUNT UNBANNED</b> 🟢

━━━━━━━━━━━━━━━━━━━━━
📸 <b>Profile:</b> @{username}

👤 <b>Name:</b> {name}
👥 <b>Followers:</b> {followers:,}
👤 <b>Following:</b> {following:,}
📸 <b>Posts:</b> {posts:,}
🔐 <b>Private:</b> {'Yes' if is_private else 'No'}

✅ <b>Status:</b> <code>ACTIVE</code>
⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━
<i>Account moved to Watch List</i>

Powered by @proxyfxc
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
        'service': 'Instagram Monitor Bot'
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'monitoring_active': monitoring_engine.is_running if monitoring_engine else False
    })

def run_flask():
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT)


# ==================== TELEGRAM BOT HANDLERS ====================

class BotHandlers:
    """All Telegram bot command and callback handlers"""
    
    def __init__(self, db: DatabaseManager, api_client: InstagramAPIClient):
        self.db = db
        self.api_client = api_client
    
    # ===== UTILITY FUNCTIONS =====
    
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
    
    # ===== FORMATTING FUNCTIONS =====
    
    def format_account_info(self, username: str, status: str, details: Dict) -> str:
        """Format account information with the exact style requested"""
        
        if status == 'ACTIVE':
            name = details.get('full_name', username)
            followers = details.get('followers', details.get('follower_count', 0))
            following = details.get('following', details.get('following_count', 0))
            posts = details.get('posts', details.get('media_count', 0))
            is_private = details.get('is_private', False)
            
            # Convert to int if they're strings
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
            
            # Format numbers with commas if they're integers
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
    
    # ===== SINGLE CHANNEL FORCE JOIN - @proxydominates ONLY =====
    
    async def check_force_join(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if user has joined @proxydominates"""
        try:
            # Check if already verified
            user_data = self.db.get_user(user_id)
            if user_data.get('verified', False):
                return True
            
            channel = Config.FORCE_JOIN_CHANNEL
            channel_username = channel['username']
            
            # Ensure @ is present
            if not channel_username.startswith('@'):
                channel_username = '@' + channel_username
            
            # Get chat member
            member = await context.bot.get_chat_member(
                chat_id=channel_username,
                user_id=user_id
            )
            
            # Check if user is member, admin, or creator
            if member.status in ['member', 'administrator', 'creator']:
                # Mark as verified
                self.db.update_user(user_id, verified=True)
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error checking force join: {e}")
            return False
    
    async def send_force_join_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send force join message for @proxydominates"""
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

<i>Powered by @proxyfxc</i>
"""
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    
    # ===== COMMAND HANDLERS =====
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Create or get user
        self.db.create_user(
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name or ""
        )
        
        # Check force join
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        # Show main menu
        await self.show_main_menu(update, context)
        
        # Notify owner about new user
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
        """Show main menu with all buttons"""
        user = update.effective_user
        watch_count = len(self.db.get_watchlist(user.id))
        ban_count = len(self.db.get_banlist(user.id))
        limit = self.get_user_limit(user.id)
        
        # Main menu keyboard - ALL BUTTONS WORKING
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
            [InlineKeyboardButton("ℹ️ Help & Info", callback_data="menu_help")]
        ]
        
        # Add admin panel button for admins
        if self.is_admin(user.id):
            keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="menu_admin")])
        
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
        """Show watch list"""
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
        """Show ban list"""
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
        """Show user status and check all watchlist accounts with 10-second delays"""
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
        
        # Send initial status message
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
                # Update progress
                await status_msg.edit_text(
                    f"🔄 <b>Checking accounts... ({current}/{len(watchlist)})</b>\n\n"
                    f"Currently checking: @{username}\n"
                    f"⏱️ Estimated time remaining: {(len(watchlist) - current) * 10} seconds",
                    parse_mode=ParseMode.HTML
                )
                
                # Check username
                status, details, profile_pic = await self.api_client.check_username(username)
                
                if status == 'ACTIVE':
                    success_count += 1
                elif status == 'BANNED':
                    banned_count += 1
                
                # Format the result
                result = self.format_account_info(username, status, details)
                result += f"\n━━━━━━━━━━━━━━━━━━━━━\n"
                all_results.append(result)
                
                # 10-second delay between checks (except for last one)
                if current < len(watchlist):
                    await asyncio.sleep(Config.STATUS_DELAY)
                
            except Exception as e:
                logger.error(f"Error checking {username}: {e}")
                all_results.append(self.format_account_info(username, 'UNKNOWN', {}))
                all_results.append(f"\n━━━━━━━━━━━━━━━━━━━━━\n")
        
        # Combine all results
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
        
        # Split message if too long
        if len(final_message) > 4096:
            # Send in parts
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
        """Prompt for username to check"""
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
        """Handle /check command with profile picture"""
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
            # Check username
            status, details, profile_pic = await self.api_client.check_username(username)
            
            # Format response
            response_text = self.format_account_info(username, status, details)
            response_text += "\nPowered by @proxyfxc"
            
            # Send with profile picture if available
            if status == 'ACTIVE' and profile_pic:
                try:
                    # Download the profile picture
                    async with aiohttp.ClientSession() as session:
                        async with session.get(profile_pic) as resp:
                            if resp.status == 200:
                                photo_data = await resp.read()
                                
                                # Send photo with caption
                                await status_msg.delete()
                                await update.message.reply_photo(
                                    photo=photo_data,
                                    caption=response_text,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=InlineKeyboardMarkup([[
                                        InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")
                                    ]])
                                )
                                return
                except Exception as e:
                    logger.error(f"Error downloading profile picture: {e}")
                    # Fall back to text message
            
            # If no profile picture or download failed, send text message
            keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
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
        """Prompt for username to add to watchlist"""
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
        """Handle /addwatch command"""
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
        
        current_count = len(self.db.get_watchlist(user.id))
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
            await update.message.reply_text(
                f"⚠️ @{username} already in watch list.",
                parse_mode=ParseMode.HTML
            )
            return
        
        self.db.add_to_watchlist(user.id, username)
        
        keyboard = [[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ <b>@{username} added to watch list</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def removewatch_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for username to remove from watchlist"""
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
        """Handle /removewatch command"""
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
                f"❌ @{username} not found.",
                parse_mode=ParseMode.HTML
            )
    
    async def addban_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for username to add to banlist"""
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
        """Handle /addban command"""
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
        """Prompt for username to remove from banlist"""
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
        """Handle /removeban command"""
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
                f"❌ @{username} not found.",
                parse_mode=ParseMode.HTML
            )
    
    # ===== ADMIN COMMANDS =====
    
    async def approve_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /approve command"""
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
        """Handle /addadmin command"""
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
        """Handle /broadcast command"""
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
        
        for user_id_str in users:
            try:
                await context.bot.send_message(
                    chat_id=int(user_id_str),
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
    
    # ===== CALLBACK HANDLER - ALL BUTTONS WORKING =====
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        data = query.data
        
        logger.info(f"Button clicked: {data} by user {user.id}")
        
        # Handle verify join button
        if data == "verify_join":
            await query.edit_message_text(
                "🔄 <b>Verifying your channel membership...</b>",
                parse_mode=ParseMode.HTML
            )
            
            if await self.check_force_join(user.id, context):
                # Success - show main menu
                await self.show_main_menu(update, context)
            else:
                # Failed - show channel button again
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
        
        # Check force join for all other actions
        if not await self.check_force_join(user.id, context):
            await self.send_force_join_message(update, context)
            return
        
        # Handle all menu buttons
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
/addwatch [user] - Add to watch
/removewatch [user] - Remove from watch
/addban [user] - Add to ban list
/removeban [user] - Remove from ban list

<b>⚙️ Admin Commands:</b>
/approve [id] [days]
/broadcast [message]
/addadmin [id]

<b>📊 How It Works:</b>
• 5-minute monitoring
• 3 confirmations for alerts
• Auto move between lists
• Real-time notifications
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
            admin_text = f"""
<b>⚙️ ADMIN PANEL</b>

━━━━━━━━━━━━━━━━━━━━━
📊 <b>System Stats:</b>
• Users: {len(self.db.get_all_users())}
• Watchlist: {sum(len(items) for items in self.db.watchlist.values())}
• Banlist: {sum(len(items) for items in self.db.banlist.values())}

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

# Global variables
db = None
monitoring_engine = None
api_client = None

async def run_bot():
    """Async function to run the bot"""
    global db, monitoring_engine, api_client
    
    try:
        # Initialize database
        db = DatabaseManager()
        
        # Initialize API client (no need for params now)
        api_client = InstagramAPIClient()
        
        # Create application
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
        logger.info("Starting bot...")
        
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        logger.info("Bot is running! Single force join: @proxydominates")
        
        # Keep running
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"Error in run_bot: {e}")
        traceback.print_exc()

def main():
    """Main entry point"""
    logger.info("Starting main function...")
    
    # Start Flask thread
    import threading
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask keep-alive started")
    
    # Run bot with proper event loop
    try:
        asyncio.run(run_bot())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(run_bot())
        else:
            loop.run_until_complete(run_bot())
    except Exception as e:
        logger.error(f"Error in main: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
