import requests
import json
import base64
import uuid
import re
from datetime import datetime, timedelta
import os
import sys
import time
import logging
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import random
import string
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# ============== LOGGING SETUP ==============
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ModxPanBot")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["WDM_LOG"] = "0"

# ============== CONFIG & CONSTANTS ==============
DIVIDER         = "━━━━━━━━━━━━━━━"
BOT_NAME        = "✜ RIKPAN"

TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN", "8351257613:AAEHFk9QHATZtf_a-QFWxONMthPBCG2zceo")
OWNER_IDS       = {8428720091, 1612918900}
OWNER_USERNAME  = "@rikron"
SESSION_TIMEOUT = 180
MAINTENANCE_MODE = False
LOG_CHANNEL_ID  = -1003912638734
CHANNEL_USERNAME = "@Modxclusiveeee"
CHANNEL_LINK     = "https://t.me/+bpNDfTqsM-k4YjY1"
MUST_JOIN_CHANNEL = True

# Proxy details for Paisabazaar Selenium Automation
PROXY_HOST = "37.49.230.40"
PROXY_PORT = "80"
PROXY_USER = "19f6a86c928846c8889066c621e75870-cc-IN"
PROXY_PASS = "821512e250cf1fd5707fc4692de45dd8"
PLUGIN_DIR = os.path.abspath("proxy_auth_plugin")

LIMITED_PLANS = {
    'l1':    {'name': '1 Search',     'price': '$0.25'},
    'l5':    {'name': '5 Searches',    'price': '$1.00'},
    'l10':   {'name': '10 Searches',   'price': '$1.80'},
    'l20':   {'name': '20 Searches',   'price': '$3.00'},
    'l30':   {'name': '30 Searches',   'price': '$4.00'},
    'l50':   {'name': '50 Searches',   'price': '$6.00'},
    'l100':  {'name': '100 Searches',  'price': '$10.00'},
    'l200':  {'name': '200 Searches',  'price': '$18.00'},
    'l500':  {'name': '500 Searches',  'price': '$35.00'},
    'l1000': {'name': '1000 Searches', 'price': '$60.00'},
}

UNLIMITED_PLANS = {
    'u1d':   {'name': '1 Day Unlimited',    'price': '$1.50'},
    'u3d':   {'name': '3 Days Unlimited',   'price': '$3.00'},
    'u7d':   {'name': '7 Days Unlimited',   'price': '$6.00'},
    'u15d':  {'name': '15 Days Unlimited',  'price': '$10.00'},
    'u1m':   {'name': '1 Month Unlimited',  'price': '$18.00'},
    'u3m':   {'name': '3 Months Unlimited', 'price': '$35.00'},
    'u6m':   {'name': '6 Months Unlimited', 'price': '$50.00'},
    'u12m':  {'name': '1 Year Unlimited',   'price': '$75.00'},
    'ulife': {'name': 'Lifetime Unlimited', 'price': '$99.00'},
}



# User-Agent Pool for Selenium
USER_AGENTS = [
    {
        'label': 'Chrome 124 / Windows 11',
        'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'platform': 'Win32',
        'vendor': 'Google Inc.',
        'languages': ['en-US', 'en']
    },
    {
        'label': 'Chrome 123 / Windows 10',
        'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'platform': 'Win32',
        'vendor': 'Google Inc.',
        'languages': ['en-US', 'en']
    }
]

# ============== PROXY EXTENSION BUILDER ==============
def create_proxy_plugin(host, port, user, pwd):
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """
    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{
                scheme: "http",
                host: "{host}",
                port: parseInt({port})
            }},
            bypassList: ["localhost"]
        }}
    }};
    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
    function callbackFn(details) {{
        return {{
            authCredentials: {{
                username: "{user}",
                password: "{pwd}"
            }}
        }};
    }}
    chrome.webRequest.onAuthRequired.addListener(
        callbackFn,
        {{urls: ["<all_urls>"]}},
        ['blocking']
    );
    """
    with open(os.path.join(PLUGIN_DIR, "manifest.json"), "w") as f:
        f.write(manifest_json.strip())
    with open(os.path.join(PLUGIN_DIR, "background.js"), "w") as f:
        f.write(background_js.strip())
    return PLUGIN_DIR

# ============== MONGO DB SRV DOH RESOLVER ==============
def _resolve_mongo_srv_via_doh(srv_uri: str) -> str:
    m = re.match(r'^mongodb\+srv://([^:@]+):([^@]+)@([^/?]+)(.*)?$', srv_uri)
    if not m:
        return srv_uri
    user, pwd, host, rest = m.group(1), m.group(2), m.group(3), m.group(4) or ''
    srv_query = f'_mongodb._tcp.{host}'
    try:
        resp = requests.get(f'https://dns.google/resolve?name={srv_query}&type=SRV', timeout=8)
        data = resp.json()
        answers = data.get('Answer', [])
        if not answers:
            return srv_uri
        hosts = []
        for ans in answers:
            parts = ans.get('data', '').split()
            if len(parts) == 4:
                port = parts[2]
                target = parts[3].rstrip('.')
                hosts.append(f'{target}:{port}')
        if not hosts:
            return srv_uri
        txt_resp = requests.get(f'https://dns.google/resolve?name={host}&type=TXT', timeout=8)
        txt_data = txt_resp.json()
        auth_source = 'admin'
        replicaset = None
        for txt_ans in txt_data.get('Answer', []):
            txt_val = txt_ans.get('data', '').strip('"')
            for part in txt_val.split('&'):
                if part.startswith('authSource='):
                    auth_source = part.split('=', 1)[1]
                elif part.startswith('replicaSet='):
                    replicaset = part.split('=', 1)[1]
        hosts_str = ','.join(hosts)
        qs_parts = [f'authSource={auth_source}', 'tls=true']
        if replicaset:
            qs_parts.append(f'replicaSet={replicaset}')
        std_uri = f'mongodb://{user}:{pwd}@{hosts_str}/?{"&".join(qs_parts)}'
        return std_uri
    except Exception as e:
        logger.warning(f"DoH SRV resolution note: {e}")
        return srv_uri

# ============== MONGO DB SETUP ==============
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://mouktikchalia59109d_db_user:KaQ6Mi2WXCWcBg5O@cluster0.msffrmy.mongodb.net/?appName=Cluster0")
MONGO_URI = _resolve_mongo_srv_via_doh(MONGO_URI)

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000, tls=True)
    db = mongo_client["modxpan_bot"]

    users_col = db["users"]
    keys_collection = db["redeem_keys"]
    settings_col = db["settings"]
    logs_col = db["activity_logs"]
    mongo_client.admin.command('ping')
    logger.info("Connected to MongoDB successfully!")
except Exception as e:
    logger.warning(f"MongoDB connection failed ({e}) — running with local memory storage fallback.")
    class LocalCollection:
        def __init__(self): self.data = {}
        def find_one(self, query):
            q_id = query.get("_id")
            if q_id: return self.data.get(str(q_id))
            for k, v in self.data.items():
                if all(v.get(qk) == qv for qk, qv in query.items() if not qk.startswith('$')):
                    return v
            return None
        def insert_one(self, doc): self.data[str(doc["_id"])] = doc
        def update_one(self, query, update):
            doc = self.find_one(query)
            if doc:
                if "$set" in update: doc.update(update["$set"])
                if "$inc" in update:
                    for ik, iv in update["$inc"].items():
                        doc[ik] = doc.get(ik, 0) + iv
                if "$unset" in update:
                    for uk in update["$unset"]: doc.pop(uk, None)
        def find(self, query): return list(self.data.values())
        def count_documents(self, query): return len(self.find(query))

    users_col = LocalCollection()
    keys_collection = LocalCollection()
    settings_col = LocalCollection()
    logs_col = LocalCollection()

# Load Settings
setting = settings_col.find_one({"_id": "config"})
if not setting:
    settings_col.insert_one({"_id": "config", "maintenance_mode": False, "must_join": True})
    MAINTENANCE_MODE = False
    MUST_JOIN_CHANNEL = True
else:
    MAINTENANCE_MODE = setting.get("maintenance_mode", False)
    MUST_JOIN_CHANNEL = setting.get("must_join", True)

# ============== IN-MEMORY USER CACHE & ASYNC LOGGING ==============
USER_CACHE = {}
CACHE_TTL = 15
cache_lock = threading.Lock()
log_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="log_worker")

def get_cached_user(user_id_str):
    with cache_lock:
        if user_id_str in USER_CACHE:
            doc, ts = USER_CACHE[user_id_str]
            if time.time() - ts < CACHE_TTL:
                return doc
    return None

def set_cached_user(user_id_str, user_doc):
    with cache_lock:
        if user_doc:
            USER_CACHE[str(user_id_str)] = (user_doc, time.time())

def invalidate_cached_user(user_id_str):
    with cache_lock:
        USER_CACHE.pop(str(user_id_str), None)

def log_activity(chat_id, action, status, duration=0.0, error=None):
    def _async_log():
        try:
            log_doc = {
                "timestamp": datetime.now(),
                "chat_id": str(chat_id),
                "action": action,
                "status": status,
                "duration": float(duration),
                "error": error
            }
            logs_col.insert_one(log_doc)
        except Exception:
            pass
    log_executor.submit(_async_log)

def get_user_log_tag(user_id):
    try:
        uid = str(user_id)
        u = get_user(uid)
        if u:
            username = u.get('username')
            first_name = u.get('first_name')
            clean_f = re.sub(r'[^\x00-\x7F]+', '', first_name).strip() if first_name else ''
            clean_u = re.sub(r'[^\x00-\x7F]+', '', username).strip() if username else ''
            parts = []
            if clean_f and clean_f.lower() != "unknown": parts.append(clean_f)
            if clean_u: parts.append(f"@{clean_u}")
            if parts: return f"[{uid} {' '.join(parts)}]"
            return f"[{uid}]"
    except Exception:
        pass
    return f"[{user_id}]"

def ensure_user(user_id, referrer_id=None, first_name=None, last_name=None, username=None):
    uid = str(user_id)
    user = users_col.find_one({"_id": uid})
    if user is None:
        full_name = f"{first_name or ''} {last_name or ''}".strip() or "Unknown"
        new_user = {
            "_id": uid,
            "first_name": full_name,
            "username": username,
            "credits": 2,
            "lifetime": False,
            "referred_by": str(referrer_id) if referrer_id else None,
            "referral_count": 0,
            "searches": 0,
            "joined": datetime.now().isoformat()
        }
        users_col.insert_one(new_user)
        if referrer_id:
            rid = str(referrer_id)
            if rid != uid:
                users_col.update_one(
                    {"_id": rid},
                    {"$inc": {"credits": 1, "referral_count": 1}}
                )
                try:
                    ref_user = get_user(rid)
                    new_ref_credits = ref_user.get('credits', 0)
                    cr_display = "Lifetime" if ref_user.get('lifetime') else f"{int(new_ref_credits)} Credits"
                    referral_name = full_name
                    referral_uname_str = f" (@{username})" if username else ""
                    
                    send_message(
                        int(rid),
                        f"🎁 <b>Referral Reward!</b>\n"
                        f"{DIVIDER}\n"
                        f"👤 <b>{referral_name}</b>{referral_uname_str} has joined using your link!\n\n"
                        f"◆ <b>Reward:</b> <code>+1 Free Search</code>\n"
                        f"◆ <b>New Balance:</b> <code>{cr_display}</code>\n\n"
                        f"<i>Keep sharing your referral link to earn more free searches!</i>"
                    )
                except Exception as ex:
                    logger.debug(f"Referrer notification error: {ex}")

        try:
            uname_str = f"@{username}" if username else "N/A"
            msg = (
                f"🟢 <b>NEW USER ALERT</b>\n"
                f"{DIVIDER}\n"
                f"👤 <b>Name:</b> {full_name}\n"
                f"👨‍💻 <b>User:</b> {uname_str}\n"
                f"🆔 <b>ID:</b> <code>{uid}</code>"
            )
            if referrer_id:
                referrer = users_col.find_one({"_id": str(referrer_id)})
                ref_uname = f"@{referrer.get('username')}" if referrer and referrer.get('username') else "Unknown"
                msg += f"\n🔗 <b>Referred By:</b> {ref_uname} (<code>{referrer_id}</code>)"
            send_log(msg)
        except Exception:
            pass
        return True
    else:
        current_first = user.get('first_name')
        current_user = user.get('username')
        full_name = f"{first_name or ''} {last_name or ''}".strip() or None
        upd = {}
        if full_name and full_name != current_first: upd['first_name'] = full_name
        if username != current_user: upd['username'] = username
        if upd:
            users_col.update_one({"_id": uid}, {"$set": upd})
    return False

def get_user(user_id):
    uid = str(user_id)
    cached = get_cached_user(uid)
    if cached: return cached
    doc = users_col.find_one({"_id": uid})
    if doc: set_cached_user(uid, doc)
    return doc

def check_expiry(user):
    if user and user.get('expiry'):
        try:
            if datetime.fromisoformat(user['expiry']) > datetime.now():
                return True
        except Exception:
            pass
    return False

def check_and_notify_expiry(chat_id):
    u = get_user(chat_id)
    if not u: return
    expiry_str = u.get('expiry')
    if expiry_str and not u.get('lifetime'):
        try:
            expiry_dt = datetime.fromisoformat(expiry_str)
            now = datetime.now()
            if now < expiry_dt <= (now + timedelta(hours=1)) and not u.get('expiry_warning_notified'):
                users_col.update_one({"_id": str(chat_id)}, {"$set": {"expiry_warning_notified": True}})
                invalidate_cached_user(chat_id)
                send_message(chat_id, "⏳ <b>Unlimited Plan Expiring Soon!</b>\n\nYour Unlimited plan will expire in 1 hour. Tap /buy to extend your access!")
                send_log(f"🔔 <b>1-HOUR REMINDER SENT</b>\n👤 User ID: <code>{chat_id}</code>")

            if expiry_dt <= now and not u.get('expiry_notified'):
                users_col.update_one({"_id": str(chat_id)}, {"$set": {"expiry_notified": True}})
                invalidate_cached_user(chat_id)
                balance = int(u.get('credits', 0))
                send_message(chat_id, f"⏰ <b>Plan Expired</b>\n\nYour Unlimited plan has ended.\n◈ <b>Restored Balance:</b> <code>{balance}</code> Searches\n\n<i>Tap /buy to top-up again! 🚀</i>")
                send_log(f"⏰ <b>UNLIMITED PLAN EXPIRED</b>\n👤 User: <code>{chat_id}</code>")
        except Exception:
            pass

def get_credits(user_id):
    u = get_user(user_id)
    if u is None: return 0
    if u.get('lifetime') or check_expiry(u): return float('inf')
    return u.get('credits', 0)

def is_lifetime(user_id):
    u = get_user(user_id)
    return (u.get('lifetime', False) or check_expiry(u)) if u else False

def has_credits(user_id):
    return get_credits(user_id) > 0

def add_credits(user_id, amount, make_lifetime=False):
    uid = str(user_id)
    user = get_user(user_id)
    if user is None:
        ensure_user(user_id)
    if make_lifetime:
        users_col.update_one({"_id": uid}, {"$set": {"lifetime": True, "is_premium": True}})
    else:
        users_col.update_one({"_id": uid}, {"$inc": {"credits": amount}, "$set": {"is_premium": True}})
    invalidate_cached_user(uid)

def deduct_credit(user_id):
    uid = str(user_id)
    user = get_user(user_id)
    if user:
        upd = {"$inc": {"searches": 1}}
        if not user.get('lifetime') and not check_expiry(user):
            new_credits = max(0, user.get('credits', 0) - 1)
            upd["$set"] = {"credits": new_credits}
        users_col.update_one({"_id": uid}, upd)
        invalidate_cached_user(uid)

# ============== SESSION MANAGEMENT ==============
user_sessions   = {}
_sessions_lock  = threading.Lock()

def get_session(chat_id):
    with _sessions_lock:
        return user_sessions.get(chat_id, {'step': 'main', 'data': {}, 'last_activity': time.time()})

def set_session(chat_id, step, data=None):
    with _sessions_lock:
        existing = user_sessions.get(chat_id, {})
        d = data if data is not None else existing.get('data', {})
        user_sessions[chat_id] = {'step': step, 'data': d, 'last_activity': time.time()}

def update_session_data(chat_id, key, value):
    with _sessions_lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = {'step': 'main', 'data': {}, 'last_activity': time.time()}
        user_sessions[chat_id]['data'][key] = value
        user_sessions[chat_id]['last_activity'] = time.time()

def clear_session(chat_id):
    with _sessions_lock:
        user_sessions[chat_id] = {'step': 'main', 'data': {}, 'last_activity': time.time()}

def touch_session(chat_id):
    with _sessions_lock:
        if chat_id in user_sessions:
            user_sessions[chat_id]['last_activity'] = time.time()

# ============== TELEGRAM HTTP HELPERS ==============
_telegram_session = requests.Session()

def send_message(chat_id, text, reply_markup=None, disable_web_page_preview=True):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': disable_web_page_preview}
    if reply_markup: data['reply_markup'] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup
    try:
        res = _telegram_session.post(url, json=data, timeout=10).json()
        return res
    except Exception as e:
        logger.error(f"send_message error: {e}")
        return None

def send_photo(chat_id, photo, caption="", reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = {'chat_id': chat_id, 'parse_mode': 'HTML'}
    if caption: data['caption'] = caption
    if reply_markup: data['reply_markup'] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup
    try:
        if isinstance(photo, bytes):
            files = {'photo': ('image.png', photo, 'image/png')}
            return _telegram_session.post(url, data=data, files=files, timeout=20).json()
        else:
            data['photo'] = photo
            return _telegram_session.post(url, data=data, timeout=20).json()
    except Exception as e:
        logger.error(f"send_photo error: {e}")
        return None

def edit_message(chat_id, message_id, text, reply_markup=None, disable_web_page_preview=True):
    if not message_id: return send_message(chat_id, text, reply_markup, disable_web_page_preview)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    data = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': disable_web_page_preview}
    if reply_markup: data['reply_markup'] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup
    try:
        res = _telegram_session.post(url, json=data, timeout=10).json()
        if not res.get('ok'):
            return send_message(chat_id, text, reply_markup, disable_web_page_preview)
        return res
    except Exception as e:
        logger.error(f"edit_message error: {e}")
        return None

def copy_message(chat_id, from_chat_id, message_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/copyMessage"
    data = {'chat_id': chat_id, 'from_chat_id': from_chat_id, 'message_id': message_id}
    try:
        return _telegram_session.post(url, json=data, timeout=10).json()
    except Exception:
        return None

def send_log(text):
    if LOG_CHANNEL_ID:
        send_message(LOG_CHANNEL_ID, text)

# ============== CHANNEL MEMBERSHIP GATE ==============
def is_channel_member(user_id):
    try:
        r = _telegram_session.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChatMember",
            params={'chat_id': CHANNEL_USERNAME, 'user_id': user_id},
            timeout=6
        ).json()
        if r.get('ok'):
            return r['result']['status'] in ('member', 'administrator', 'creator')
    except Exception as e:
        logger.error(f"Channel membership check error: {e}")
    return False

def get_join_keyboard():
    return {
        'inline_keyboard': [
            [{'text': '📢 Join Channel', 'url': CHANNEL_LINK}],
            [{'text': '🔄 Verified / Try Again', 'callback_data': 'check_join'}]
        ]
    }

def channel_gate(chat_id):
    if chat_id in OWNER_IDS: return True
    if not is_channel_member(chat_id):
        send_message(
            chat_id,
            f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
            f"⚠️ <b>Must Join Channel</b>\n\n"
            f"You must join our updates channel to use this bot.\n\n"
            f"📢 Channel: {CHANNEL_USERNAME}",
            reply_markup=get_join_keyboard()
        )
        return False
    return True


def credit_gate(chat_id):
    if has_credits(chat_id): return True
    kb = {'inline_keyboard': [[{'text': '🛒 Buy Credits', 'callback_data': 'buy_menu'}]]}
    send_message(
        chat_id,
        f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
        f"❌ <b>Insufficient Balance</b>\n\n"
        f"You have <code>0</code> credits remaining.\n"
        f"Refer friends via /referral or purchase credits to continue.",
        reply_markup=kb
    )
    return False

# ============== KEYBOARDS ==============
def get_main_keyboard(user_id=None):
    kb = [
        ['◆  Get Pan Card'],
        ['◇  Credits', '◇  Buy Credits'],
        ['◇  Referral', '◇  About Bot']
    ]
    return {'keyboard': [[{'text': b} for b in row] for row in kb], 'resize_keyboard': True}



def get_cancel_keyboard():
    return {'inline_keyboard': [[{'text': '✗  Cancel', 'callback_data': 'cancel_action'}]]}

# ============== UI MENUS & FORMATTING ==============
def show_start_menu(chat_id, first_name):
    u = get_user(chat_id)
    cr_str = "♾️ Unlimited" if (u.get('lifetime') or check_expiry(u)) else f"{int(u.get('credits', 0))} Credits"
    text = (
        f"<b>{BOT_NAME}</b>\n\n"
        f"👋 Welcome, <b>{first_name}</b>!\n"
        f"⚡️ PAN extraction engine is active & ready.\n\n"
        f"💰 <b>Your Balance:</b> <code>{cr_str}</code>\n"
        f"{DIVIDER}\n"
        f"<i>Choose an action to proceed:</i>"
    )
    send_message(chat_id, text, reply_markup=get_main_keyboard(chat_id))


def show_credits_info(chat_id, message_id=None):
    u = get_user(chat_id)
    searches = u.get('searches', 0)
    cr_str = "♾️ Lifetime Unlimited" if u.get('lifetime') else ("♾️ Unlimited" if check_expiry(u) else f"{int(u.get('credits', 0))} Credits")
    text = (
        f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
        f"<b>[ 👤 YOUR PROFILE & BALANCE ]</b>\n\n"
        f"◆ <b>User ID:</b> <code>{chat_id}</code>\n"
        f"◆ <b>Balance:</b> <code>{cr_str}</code>\n"
        f"◆ <b>Searches Done:</b> <code>{searches}</code>\n"
        f"◆ <b>Referrals:</b> <code>{u.get('referral_count', 0)}</code>\n\n"
        f"<i>Use /redeem &lt;KEY&gt; to add credits or activate plans.</i>"
    )
    owner_clean = OWNER_USERNAME.replace("@", "")
    kb = {
        'inline_keyboard': [
            [
                {'text': '💳 Buy Credits', 'callback_data': 'buy'},
                {'text': '💬 Support', 'url': f'https://t.me/{owner_clean}'}
            ]
        ]
    }
    if message_id:
        edit_message(chat_id, message_id, text, reply_markup=kb)
    else:
        send_message(chat_id, text, reply_markup=kb)


def track_buy_interest(chat_id, plan_info=None):
    """Tracks buy menu interactions.
    Triggers Admin Log Alert ONLY when a user clicks buy buttons at least 3 times today / checks out a plan.
    Enforces a strict max 1 alert per user per 24 hours to prevent spam."""
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        user_doc = users_col.find_one({"_id": str(chat_id)})
        if not user_doc:
            return

        click_date = user_doc.get("buy_click_date")
        clicks = user_doc.get("buy_clicks_count", 0)
        last_logged_date = user_doc.get("last_buy_log_date")

        if click_date != today_str:
            clicks = 1
            click_date = today_str
        else:
            clicks += 1

        users_col.update_one(
            {"_id": str(chat_id)},
            {"$set": {"buy_click_date": click_date, "buy_clicks_count": clicks}}
        )

        is_checkout = plan_info is not None
        should_trigger = (clicks >= 2) and (last_logged_date != today_str)

        if should_trigger:
            users_col.update_one(
                {"_id": str(chat_id)},
                {"$set": {"last_buy_log_date": today_str}}
            )
            name = user_doc.get("first_name", "Unknown")
            username = user_doc.get("username")
            uname_str = f" (@{username})" if username else ""
            plan_str = f"<b>{plan_info['name']}</b> ({plan_info['price']})" if plan_info else "Browsing Payment Plans"
            
            send_log(
                f"🛒 <b>PURCHASE INTEREST ALERT</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"◆ User   — <b>{name}</b>{uname_str}\n"
                f"◆ ID     — <code>{chat_id}</code>\n"
                f"◆ Plan   — {plan_str}\n"
                f"◆ Clicks — <b>{clicks} buy actions today</b>\n\n"
                f"<i>💡 User is actively checking out payment plans. Contact them to offer help!</i>"
            )
    except Exception as e:
        logger.debug(f"track_buy_interest error: {e}")

def show_buy_menu(chat_id, message_id=None):
    track_buy_interest(chat_id)
    kb = {
        'inline_keyboard': [
            [{'text': '🔢 Limited Search Plans', 'callback_data': 'buy_menu_limited'}],
            [{'text': '♾ Unlimited Plans', 'callback_data': 'buy_menu_unlimited'}],
            [{'text': '⬅️ Back to Profile', 'callback_data': 'credits'}]
        ]
    }
    if message_id:
        edit_message(
            chat_id, message_id,
            f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
            f"💳 <b>Choose your plan type:</b>\n\n"
            f"💡 <i>Need help? Contact admin:</i> {OWNER_USERNAME}",
            reply_markup=kb
        )
    else:
        send_message(
            chat_id,
            f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
            f"💳 <b>Choose your plan type:</b>\n\n"
            f"💡 <i>Need help? Contact admin:</i> {OWNER_USERNAME}",
            reply_markup=kb
        )


def show_referral_info(chat_id):
    u = get_user(chat_id)
    ref_count = u.get('referral_count', 0)
    ref_link = f"https://t.me/{get_bot_username()}?start=ref_{chat_id}"
    text = (
        f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
        f"<b>[ 🎁 REFERRAL SYSTEM ]</b>\n\n"
        f"Earn <b>+1 Free Credit</b> for every user who joins using your link!\n\n"
        f"👥 <b>Total Referrals:</b> <code>{ref_count}</code>\n"
        f"🔗 <b>Your Link:</b>\n<code>{ref_link}</code>\n\n"
        f"<i>Share your link and get free searches instantly!</i>"
    )
    send_message(chat_id, text, reply_markup=get_main_keyboard(chat_id))

def show_about_bot(chat_id):
    text = (
        f"<b>✦ {BOT_NAME} — ᴀʙᴏᴜᴛ & ᴜsᴇʀ ɢᴜɪᴅᴇ ✦</b>\n"
        f"{DIVIDER}\n\n"
        f"<blockquote><b>Welcome to {BOT_NAME}!</b>\n"
        f"Your premium automation platform for instant, high-speed PAN profile verification & data extraction.</blockquote>\n\n"
        f"<b>❖ 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬 & 𝐒𝐞𝐚𝐫𝐜𝐡 𝐌𝐨𝐝𝐞𝐬</b>\n"
        f"◈ <b>PAN Search</b> — Find PAN Card number, owner name, address & profile details instantly via mobile authentication.\n"
        f"◈ <b>Secure Engine</b> — 100% accurate extraction powered by isolated headless browser technology.\n\n"
        f"<b>❖ 𝐇𝐨𝐰 𝐓𝐨 𝐔𝐬𝐞 (𝐒𝐭𝐞𝐩-𝐛𝐲-𝐒𝐭𝐞𝐩)</b>\n"
        f"<blockquote>1. Select <b>◆  Get Pan Card</b> from the bottom menu.\n"
        f"2. Enter target's 10-digit Mobile Number.\n"
        f"3. Submit the verification OTP.\n"
        f"4. Receive complete PAN profile instantly!</blockquote>\n\n"
        f"<b>❖ 𝐂𝐫𝐞𝐝𝐢𝐭𝐬 & 𝐑𝐞𝐟𝐞𝐫𝐫𝐚𝐥𝐬</b>\n"
        f"• <b>◇ Credits</b> — Check active plan & search balance.\n"
        f"• <b>◇ Referral</b> — Share your link & earn free searches.\n"
        f"• <b>◇ Buy Credits</b> — Purchase top-up credits or Unlimited plans.\n\n"
        f"<b>❖ 𝐒𝐮𝐩𝐩𝐨𝐫𝐭 & 𝐀𝐝𝐦𝐢𝐧</b>\n"
        f"<blockquote>👑 <b>Admin:</b> {OWNER_USERNAME}\n"
        f"📢 <b>Channel:</b> {CHANNEL_LINK}\n"
        f"💬 Contact <b>{OWNER_USERNAME}</b> for custom plans & bulk usage.</blockquote>\n"
        f"{DIVIDER}"
    )
    kb = {
        'inline_keyboard': [
            [
                {'text': '💬 Contact Admin', 'url': f'https://t.me/{OWNER_USERNAME.lstrip("@")}'},
                {'text': '📢 Official Channel', 'url': CHANNEL_LINK}
            ]
        ]
    }
    send_message(chat_id, text, reply_markup=kb)


def get_bot_username():
    try:
        res = _telegram_session.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=5).json()
        if res.get('ok'): return res['result']['username']
    except Exception:
        pass
    return "ModxPanBot"


# ============== ADMIN PANEL UI ==============
def build_admin_panel_text():
    total_u = users_col.count_documents({})
    active_keys = keys_collection.count_documents({"used": False})

    mm_status = "ON 🟢" if MAINTENANCE_MODE else "OFF 🔴"
    text = (
        f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
        f"<b>[ ⚙️ ADMIN CONTROL PANEL ]</b>\n\n"
        f"◆ <b>Total Registered Users:</b> <code>{total_u}</code>\n"
        f"◆ <b>Unused Keys:</b> <code>{active_keys}</code>\n"
        f"◆ <b>Maintenance Mode:</b> {mm_status}\n"
        f"{DIVIDER}"
    )
    kb = {
        'inline_keyboard': [
            [
                {'text': '👥 Active Users', 'callback_data': 'panel_users_0'},
                {'text': '🔍 Search User', 'callback_data': 'panel_search_user'}
            ],
            [
                {'text': '🎟 Generate Key', 'callback_data': 'panel_gen_key'},
                {'text': '🚫 Revoke User', 'callback_data': 'panel_revoke'}
            ],
            [
                {'text': '📣 Broadcast', 'callback_data': 'panel_broadcast'},
                {'text': f'🔧 Maint: {mm_status}', 'callback_data': 'panel_toggle_mm'}
            ]
        ]
    }
    return text, kb


PAGE_SIZE = 10

def format_plan_display(u, days_left=None):
    if u.get('lifetime'):
        return "Lifetime Unlimited"
        
    unlim_days = u.get('unlimited_days')
    if unlim_days:
        try:
            d = int(unlim_days)
            if d == 1: return "1 Day Unlimited"
            if 6 <= d <= 8: return "1 Week Unlimited"
            if 13 <= d <= 15: return "2 Weeks Unlimited"
            if 27 <= d <= 31: return "1 Month Unlimited"
            if 56 <= d <= 62 or d == 60: return "2 Months Unlimited"
            if 85 <= d <= 93 or d == 90: return "3 Months Unlimited"
            if 170 <= d <= 185 or d == 180: return "6 Months Unlimited"
            if 350 <= d <= 370 or d == 365: return "12 Months Unlimited"
            if d % 30 == 0:
                m = d // 30
                return f"{m} Month{'s' if m > 1 else ''} Unlimited"
            if d % 7 == 0:
                w = d // 7
                return f"{w} Week{'s' if w > 1 else ''} Unlimited"
            return f"{d} Days Unlimited"
        except Exception:
            pass

    if days_left is not None and days_left >= 0:
        d = days_left
        if d <= 1: return "1 Day Unlimited"
        if 5 <= d <= 8: return "1 Week Unlimited"
        if 12 <= d <= 16: return "2 Weeks Unlimited"
        if 20 <= d <= 32: return "1 Month Unlimited"
        if 50 <= d <= 65: return "2 Months Unlimited"
        if 80 <= d <= 95: return "3 Months Unlimited"
        if 160 <= d <= 190: return "6 Months Unlimited"
        if 340 <= d <= 370: return "12 Months Unlimited"
        if d % 30 == 0:
            m = d // 30
            return f"{m} Month{'s' if m > 1 else ''} Unlimited"
        if d % 7 == 0:
            w = d // 7
            return f"{w} Week{'s' if w > 1 else ''} Unlimited"
        return f"{d} Days Unlimited"

    cr = u.get('credits', 0)
    if cr > 0:
        return f"{int(cr)} Credits"
    return "Unlimited"

def show_user_profile_admin(chat_id, target_uid, message_id=None):
    user_doc = get_user(target_uid)
    if not user_doc:
        send_message(chat_id, f"❌ User {target_uid} not found.")
        return
        
    uid = str(user_doc.get('_id', target_uid))
    first_name = user_doc.get('first_name', 'Unknown')
    username = user_doc.get('username')
    username_display = f"@{username}" if username else "N/A"
    searches = user_doc.get('searches', 0)
    
    now = datetime.now()
    expiry_str = user_doc.get('expiry')
    expiry_dt = None
    days_left = None
    if expiry_str and not user_doc.get('lifetime'):
        try:
            expiry_dt = datetime.fromisoformat(expiry_str)
            if expiry_dt > now:
                days_left = max(1, int(((expiry_dt - now).total_seconds() + 86399) // 86400))
        except Exception:
            pass

    plan_name = format_plan_display(user_doc, days_left)
    
    if user_doc.get('banned'):
        subscription_display = "Banned"
    elif user_doc.get('lifetime'):
        subscription_display = "Lifetime Unlimited\n<b>Expiry:</b> Forever (No Expiry)"
    elif expiry_dt and expiry_dt > now:
        formatted_exp = expiry_dt.strftime("%d-%b-%Y at %I:%M %p")
        subscription_display = f"<b>{plan_name}</b>\n<b>Expiry:</b> {formatted_exp} ({days_left}d left)"
    else:
        cr = user_doc.get('credits', 0)
        subscription_display = f"{int(cr)} Searches"

    text = (
        f"── <b>PROFILE OVERVIEW</b> ──\n\n"
        f"<b>Name:</b> {first_name}\n"
        f"<b>Username:</b> {username_display}\n"
        f"<b>User ID:</b> <code>{uid}</code>\n"
        f"<b>Total Searches:</b> {searches}\n"
        f"<b>Subscription:</b> {subscription_display}\n"
        f"<b>Referrals:</b> {user_doc.get('referral_count', 0)}"
    )
    
    kb = {
        'inline_keyboard': [
            [{'text': '✏️  Edit User', 'callback_data': f'edit_user_{uid}'}],
            [{'text': '⬅️  Back to Panel', 'callback_data': 'panel_back'}]
        ]
    }
    
    if message_id:
        edit_message(chat_id, message_id, text, reply_markup=kb)
    else:
        send_message(chat_id, text, reply_markup=kb)

def show_users_page(chat_id, page=0, message_id=None):
    now = datetime.now()
    now_iso = now.isoformat()

    all_docs = list(users_col.find({}).sort("joined", -1))
    
    def _user_sort_key(u):
        if u.get('lifetime'): return 0
        exp = u.get('expiry')
        if exp and not u.get('lifetime'):
            try:
                if datetime.fromisoformat(exp) > now: return 1
            except Exception: pass
        if u.get('credits', 0) > 0: return 2
        return 3

    all_docs.sort(key=_user_sort_key)

    total = len(all_docs)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = all_docs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines = [
        f"👥 <b>Total Users: {total}</b>\n"
    ]

    for i, u in enumerate(chunk, start=page * PAGE_SIZE + 1):
        uid  = u['_id']
        name = u.get('first_name', 'Unknown')
        uname = u.get('username')
        uname_str = f" (@{uname})" if uname else ""

        expiry_str = u.get('expiry')
        expiry_dt = None
        if expiry_str and not u.get('lifetime'):
            try:
                expiry_dt = datetime.fromisoformat(expiry_str)
            except Exception:
                pass

        is_unlimited = u.get('lifetime') or (expiry_dt and expiry_dt > now)
        plan_str = "Unlimited" if is_unlimited else f"{int(u.get('credits', 0))} searches"

        if u.get('lifetime'):
            exp_str = "Lifetime"
        elif expiry_dt and expiry_dt > now:
            exp_str = expiry_dt.strftime("%d-%b-%Y")
        else:
            exp_str = "Lifetime"

        lines.append(f"{i}. <b>{name}</b>{uname_str}")
        lines.append(f"    → ID: <code>{uid}</code> | Plan: {plan_str} | Exp: {exp_str}")

    lines.append(f"\nPage {page + 1} of {total_pages}")

    nav = []
    if page > 0:
        nav.append({'text': '⬅️ Prev', 'callback_data': f'panel_users_{page - 1}'})
    if page < total_pages - 1:
        nav.append({'text': 'Next ➡️', 'callback_data': f'panel_users_{page + 1}'})

    kb = {
        'inline_keyboard': [
            nav,
            [{'text': '⬅️  Back to Panel', 'callback_data': 'panel_back'}]
        ]
    }

    edit_message(chat_id, message_id, "\n".join(lines), reply_markup=kb)


def run_background_broadcast(admin_chat_id, status_msg_id, broadcast_msg_id=None, message_text=None, photo_file_id=None):
    users = list(users_col.find({}, {"_id": 1}))
    total_targets = len(users)
    if total_targets == 0:
        total_targets = 1

    u_success = 0
    u_failed = 0
    processed = 0
    last_update_time = 0.0

    def get_progress_bar(percent, length=10):
        filled_length = int(length * percent // 100)
        filled_length = min(max(filled_length, 0), length)
        return '█' * filled_length + '░' * (length - filled_length)

    def send_to_user(user_id):
        try:
            if broadcast_msg_id:
                res = copy_message(user_id, admin_chat_id, broadcast_msg_id)
            elif photo_file_id:
                res = send_photo(user_id, photo_file_id, caption=message_text or "")
            else:
                res = send_message(user_id, message_text or "<b>🔊 Broadcast</b>")

            return res and res.get('ok')
        except Exception:
            return False

    max_workers = min(30, len(users) if users else 1)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(send_to_user, str(doc["_id"])): str(doc["_id"]) for doc in users}
        
        for future in as_completed(futures):
            success = future.result()
            if success:
                u_success += 1
            else:
                u_failed += 1
                
            processed += 1
            
            now = time.time()
            if now - last_update_time >= 3.0 or processed == total_targets:
                last_update_time = now
                progress = (processed / total_targets) * 100
                bar = get_progress_bar(progress)
                status_text = (
                    f"📢 <b>Broadcast in Progress</b>\n"
                    f"{DIVIDER}\n"
                    f"⏳ <b>Progress:</b> <code>{progress:.1f}%</code>\n"
                    f"└ <code>[{bar}]</code>\n\n"
                    f"👤 <b>Users:</b>\n"
                    f"├ 📈 Sent: <code>{u_success}</code>\n"
                    f"└ 📉 Failed: <code>{u_failed}</code>\n\n"
                    f"📊 <b>Processed:</b> <code>{processed}/{total_targets}</code>"
                )
                try:
                    edit_message(admin_chat_id, status_msg_id, status_text)
                except Exception as e:
                    logger.error(f"Error updating broadcast progress: {e}")

    bar = get_progress_bar(100.0)
    report = (
        f"✅ <b>Broadcast Complete</b>\n"
        f"{DIVIDER}\n"
        f"⏳ <b>Progress:</b> <code>100.0%</code>\n"
        f"└ <code>[{bar}]</code>\n\n"
        f"👤 <b>Users:</b>\n"
        f"├ 📈 Sent: <code>{u_success}</code>\n"
        f"└ 📉 Failed: <code>{u_failed}</code>\n\n"
        f"📊 <b>Total Success:</b> <code>{u_success}</code>"
    )
    edit_message(admin_chat_id, status_msg_id, report)

def handle_owner_command(chat_id, cmd_text):
    parts = cmd_text.strip().split()
    cmd = parts[0].lower()

    if cmd in ('/admin', '/panel'):
        text, kb = build_admin_panel_text()
        send_message(chat_id, text, reply_markup=kb)
        return True

    # /send USERID AMOUNT
    if cmd == '/send' and len(parts) == 3:
        try:
            target_id = int(parts[1])
            amount    = int(parts[2])
            if amount == -1:
                add_credits(target_id, 0, make_lifetime=True)
                send_message(chat_id, f"{BOT_NAME}\n{DIVIDER}\n<b>[ done ]</b>\n\n◆  Granted Lifetime to <code>{target_id}</code>")
                send_message(target_id,
                    f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                    f"<b>[ credits received ]</b>\n\n"
                    f"◆  Plan     —  Lifetime\n"
                    f"◆  Status   —  Active\n\n"
                    f"{DIVIDER}",
                    reply_markup=get_main_keyboard()
                )
            else:
                add_credits(target_id, amount)
                send_message(chat_id, f"{BOT_NAME}\n{DIVIDER}\n<b>[ done ]</b>\n\n◆  Sent {amount} credits to <code>{target_id}</code>")
                send_message(target_id,
                    f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                    f"<b>[ credits received ]</b>\n\n"
                    f"◆  Credits  —  +{amount}\n"
                    f"◆  Balance  —  {int(get_credits(target_id))}\n\n"
                    f"{DIVIDER}",
                    reply_markup=get_main_keyboard()
                )
        except ValueError:
            send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n✗  Usage: /send USERID AMOUNT\n(-1 for lifetime)")
        return True

    # /balance USERID
    if cmd == '/balance' and len(parts) == 2:
        try:
            uid = int(parts[1])
            cr  = get_credits(uid)
            cr_display = "Lifetime" if cr == float('inf') else str(int(cr))
            send_message(chat_id, f"{BOT_NAME}\n{DIVIDER}\n<b>[ balance ]</b>\n\n◆  User    —  <code>{uid}</code>\n◆  Credits —  {cr_display}\n\n{DIVIDER}")
        except ValueError:
            send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n✗  Usage: /balance USERID")
        return True

    # /key — Ask Credits or Lifetime key choice
    if cmd == '/key':
        try:
            amount = int(parts[1]) if len(parts) >= 2 else 1
        except ValueError:
            amount = 1
        set_session(chat_id, 'key_type', {'key_amount': amount})
        type_kb = {
            'inline_keyboard': [
                [{'text': '🔢  Limited (Credits)', 'callback_data': f'key_limited_{amount}'}],
                [{'text': '♾️  Unlimited (Lifetime)', 'callback_data': f'key_unlimited_{amount}'}],
                [{'text': '⬅️  Back to Panel', 'callback_data': 'panel_back'}]
            ]
        }
        send_message(
            chat_id,
            f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
            f"<b>[ generate key ]</b>\n\n"
            f"◆  Amount — {amount} key(s)\n\n"
            f"Select key type:",
            reply_markup=type_kb
        )
        return True

    # /broadcast [MESSAGE]
    if cmd == '/broadcast':
        msg_text = cmd_text[10:].strip()
        if msg_text:
            status_res = send_message(
                chat_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"⏳ <b>Starting Broadcast...</b>\n"
                f"<i>Preparing to send message to all users.</i>"
            )
            status_msg_id = status_res.get('result', {}).get('message_id') if status_res and status_res.get('ok') else None
            t = threading.Thread(
                target=run_background_broadcast,
                args=(chat_id, status_msg_id, None, msg_text, None),
                daemon=True
            )
            t.start()
        else:
            set_session(chat_id, 'awaiting_broadcast_target_choice', {})
            target_kb = {
                'inline_keyboard': [
                    [{'text': '📢 All Users', 'callback_data': 'broadcast_select_all'}],
                    [{'text': '👤 Single User', 'callback_data': 'broadcast_select_single'}],
                    [{'text': '⬅️  Back to Panel', 'callback_data': 'panel_back'}]
                ]
            }
            send_message(
                chat_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ 📣 Send Broadcast To ]</b>\n\n"
                f"Choose broadcast target:\n\n"
                f"📢 <b>All Users</b> — Send to everyone in the database\n"
                f"👤 <b>Single User</b> — Send to one specific user (by ID or @username)",
                reply_markup=target_kb
            )
        return True

    # /rm
    if cmd == '/rm':
        banned_users = list(users_col.find({"banned": True}))
        total_banned = len(banned_users)
        lines = [
            "🚫 <b>REVOKED / BANNED USERS</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"📊 Total Banned: {total_banned}",
            "━━━━━━━━━━━━━━━━━━\n"
        ]
        for idx, u in enumerate(banned_users, 1):
            name = u.get('first_name', 'Unknown')
            username = u.get('username')
            username_str = f"@{username}" if username else "No Username"
            uid = u.get('_id')
            lines.append(f"{idx}. {name} | {username_str}\n    🆔 <code>{uid}</code>\n")
        send_message(chat_id, "\n".join(lines))
        return True

    # /pr
    if cmd == '/pr':
        now = datetime.now()
        all_users_list = list(users_col.find({"banned": {"$ne": True}, "is_premium": True}))
        
        lifetime_users_list = []
        timed_users_list = []
        credits_users_list = []
        
        for u in all_users_list:
            if u.get('lifetime'):
                lifetime_users_list.append(u)
                continue
                
            expiry_str = u.get('expiry')
            has_valid_expiry = False
            if expiry_str:
                try:
                    expiry_dt = datetime.fromisoformat(expiry_str)
                    if expiry_dt > now:
                        has_valid_expiry = True
                except Exception:
                    pass
            
            if has_valid_expiry:
                timed_users_list.append(u)
                continue
                
            cr = u.get('credits', 0)
            if cr > 1:
                credits_users_list.append(u)
                
        total_lifetime = len(lifetime_users_list)
        total_timed = len(timed_users_list)
        total_credits = len(credits_users_list)
        total_premium = total_lifetime + total_timed + total_credits
        
        lines = [
            f"💎 <b>Active Premium Users: {total_premium}</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"♾️ Lifetime: {total_lifetime} | ⏳ Timed: {total_timed} | 🔢 Credits: {total_credits}",
            "━━━━━━━━━━━━━━━━━━\n"
        ]
        
        item_index = 1
        for u in lifetime_users_list:
            name = u.get('first_name', 'Unknown')
            username = u.get('username')
            username_str = f" (@{username})" if username else " (No Username)"
            uid = u.get('_id')
            lines.append(
                f"♾️ {item_index}. {name}{username_str}\n"
                f"    🆔 {uid}\n"
                f"    📦 Lifetime Unlimited\n"
                f"    📅 Lifetime\n"
            )
            item_index += 1
            
        for u in timed_users_list:
            name = u.get('first_name', 'Unknown')
            username = u.get('username')
            username_str = f" (@{username})" if username else " (No Username)"
            uid = u.get('_id')
            expiry_dt = datetime.fromisoformat(u.get('expiry'))
            delta = expiry_dt - now
            days_left = max(0, delta.days)
            icon = "🟢" if days_left > 3 else "🟡"
            date_str = expiry_dt.strftime("%d-%b-%Y at %I:%M %p")
            lines.append(
                f"{icon} {item_index}. {name}{username_str}\n"
                f"    🆔 {uid}\n"
                f"    📦 Unlimited\n"
                f"    📅 {date_str} ({days_left}d left)\n"
            )
            item_index += 1
            
        for u in credits_users_list:
            name = u.get('first_name', 'Unknown')
            username = u.get('username')
            username_str = f" (@{username})" if username else " (No Username)"
            uid = u.get('_id')
            cr = int(u.get('credits', 0))
            lines.append(
                f"🔢 {item_index}. {name}{username_str}\n"
                f"    🆔 {uid}\n"
                f"    📦 {cr} Credits\n"
                f"    📅 Active\n"
            )
            item_index += 1
            
        message_body = "\n".join(lines)
        if len(message_body) > 4000:
            for chunk in [message_body[i:i+4000] for i in range(0, len(message_body), 4000)]:
                send_message(chat_id, chunk)
        else:
            send_message(chat_id, message_body)
        return True

    return False


# ============== SELENIUM PAISABAZAAR EXTRACTOR ENGINE ==============
def get_driver():
    profile = random.choice(USER_AGENTS)
    plugin_dir = create_proxy_plugin(PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASS)
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--load-extension={plugin_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument(f"--user-agent={profile['ua']}")
    options.add_argument(f"--lang={profile['languages'][0]}")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("--disable-logging")

    service = Service(log_output=os.devnull)
    driver = webdriver.Chrome(options=options, service=service)

    js_interceptor = """
    (function() {
        window.__CAPTURED_APIS__ = window.__CAPTURED_APIS__ || {};
        var origFetch = window.fetch;
        if (origFetch) {
            window.fetch = async function() {
                var args = arguments;
                var res = await origFetch.apply(this, args);
                try {
                    var u = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
                    if (u && (u.includes('creditReport') || u.includes('customer') || u.includes('bureau') || u.includes('overview'))) {
                        var clone = res.clone();
                        var json = await clone.json();
                        window.__CAPTURED_APIS__[u] = json;
                    }
                } catch(e){}
                return res;
            };
        }
    })();
    """
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": js_interceptor})
    except Exception:
        pass
    return driver

def initiate_paisabazaar_login(driver, mobile):
    url = "https://creditreport.paisabazaar.com/credit-report/apply"
    driver.get(url)
    mobile_field = None
    start_wait = time.time()
    
    while time.time() - start_wait < 15:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for idx, iframe in enumerate(iframes):
            try:
                driver.switch_to.frame(iframe)
                mobile_field = driver.find_element(
                    By.XPATH,
                    "//input[contains(@placeholder,'Mobile') or @type='tel' or @name='mobile' or @name='phone']"
                )
                break
            except NoSuchElementException:
                driver.switch_to.default_content()
        
        if mobile_field:
            break
            
        try:
            mobile_field = driver.find_element(
                By.XPATH,
                "//input[contains(@placeholder,'Mobile') or @type='tel' or @name='mobile' or @name='phone']"
            )
            break
        except NoSuchElementException:
            pass
            
        time.sleep(1)

    if not mobile_field:
        return False, "Mobile input field not found on portal."


    try:
        mobile_field.click()
        mobile_field.send_keys(Keys.CONTROL + "a")
        mobile_field.send_keys(Keys.BACKSPACE)
        mobile_field.send_keys(mobile)
        driver.execute_script("""
            var el = arguments[0];
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
        """, mobile_field)
    except Exception as e:
        return False, f"Mobile input error: {e}"

    try: mobile_field.send_keys(Keys.ENTER)
    except Exception: pass

    try:
        btn = driver.find_element(
            By.XPATH,
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'get otp')"
            " or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]"
        )
        driver.execute_script("arguments[0].click();", btn)
    except Exception: pass

    return True, "OTP Sent"

def submit_paisabazaar_otp_and_extract(driver, otp):
    try:
        otp_boxes = driver.find_elements(By.CSS_SELECTOR, "input[maxlength='1'], input.otp")
        if len(otp_boxes) >= len(otp):
            for i, ch in enumerate(otp):
                otp_boxes[i].click()
                otp_boxes[i].send_keys(ch)
        else:
            otp_field = driver.find_element(
                By.XPATH,
                "//input[@type='tel' or @name='otp' or @id='otp' or contains(@placeholder,'OTP') or contains(@placeholder,'otp')]"
            )
            otp_field.clear()
            otp_field.send_keys(otp)
            otp_field.send_keys(Keys.ENTER)

        try:
            verify = driver.find_element(
                By.XPATH,
                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verify')"
                " or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')"
                " or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]"
            )
            driver.execute_script("arguments[0].click();", verify)
        except Exception:
            pass
    except Exception as e:
        return False, f"OTP submission failed: {e}"

    time.sleep(2)
    driver.switch_to.default_content()
    driver.get("https://creditreport.paisabazaar.com/bureau/report-analysis")

    profile = None
    start_time = time.time()
    while time.time() - start_time < 10:
        try:
            captured = driver.execute_script("""
                var res = window.__CAPTURED_APIS__ || {};
                res.__INITIAL_STATE__ = window.__INITIAL_STATE__ || null;
                return res;
            """)
            if captured:
                found = find_customer_profile(captured)
                if found:
                    profile = found
                    break
        except Exception:
            pass

        try:
            local_data = driver.execute_script("""
                var result = {};
                for (var i = 0; i < localStorage.length; i++) {
                    var k = localStorage.key(i);
                    try { result[k] = JSON.parse(localStorage.getItem(k)); }
                    catch(e) { result[k] = localStorage.getItem(k); }
                }
                return result;
            """)
            found = find_customer_profile(local_data)
            if found:
                profile = found
                break
        except Exception:
            pass
        time.sleep(1)

    # ── Strategy 2: Direct Python Request to api2.paisabazaar.com ──
    if not profile:
        try:
            cookies = {c['name']: c['value'] for c in driver.get_cookies()}
            cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            
            pb_access_token = cookies.get("pb-access-token", "") or driver.execute_script("return localStorage.getItem('pb-access-token') || localStorage.getItem('ssoToken') || '';")
            pb_pass_token = cookies.get("pb-pass-token", "") or cookies.get("PB_GLSS_TOKEN", "") or driver.execute_script("return localStorage.getItem('pb-pass-token') || '';")
            visit_id = cookies.get("visitId", "") or driver.execute_script("return localStorage.getItem('visitId') || '';")

            req_headers = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "User-Agent": driver.execute_script("return navigator.userAgent;"),
                "Origin": "https://creditreport.paisabazaar.com",
                "Referer": "https://creditreport.paisabazaar.com/",
                "non-app": "true",
                "site-origin": "BUREAU_WEB_MOBILE",
                "Cookie": cookie_header
            }
            if pb_access_token:
                req_headers["pb-access-token"] = pb_access_token
            if pb_pass_token:
                req_headers["pb-pass-token"] = pb_pass_token
            if visit_id:
                req_headers["visitid"] = visit_id

            target_url = "https://api2.paisabazaar.com/BSP/api/v1/customer/creditReport/overview"
            req = urllib.request.Request(target_url, headers=req_headers, method="GET")

            with urllib.request.urlopen(req, timeout=10) as response:
                resp_bytes = response.read()
                try:
                    resp_text = gzip.decompress(resp_bytes).decode("utf-8")
                except Exception:
                    resp_text = resp_bytes.decode("utf-8")

                parsed = json.loads(resp_text)
                found = find_customer_profile(parsed)
                if found:
                    profile = found
        except Exception as e:
            logger.debug(f"Direct Python request fallback note: {e}")

    # ── Strategy 3: Check LocalStorage Dump (Deep Check) ──
    if not profile:
        try:
            local_data = driver.execute_script("""
                var result = {};
                for (var i = 0; i < localStorage.length; i++) {
                    var k = localStorage.key(i);
                    try {
                        result[k] = JSON.parse(localStorage.getItem(k));
                    } catch(e) {
                        result[k] = localStorage.getItem(k);
                    }
                }
                return result;
            """)
            found = find_customer_profile(local_data)
            if found:
                profile = found
        except Exception:
            pass

    if profile:
        ordered_result = {
            "firstName": profile.get("firstName", ""),
            "lastName": profile.get("lastName", ""),
            "dob": profile.get("dob", ""),
            "emailId": profile.get("emailId", ""),
            "mobileNumber": profile.get("mobileNumber", ""),
            "panCard": profile.get("panCard", ""),
            "addressLine1": profile.get("addressLine1", "")
        }
        return True, ordered_result
    return False, "Customer profile data not found."


def find_customer_profile(obj):
    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            return find_customer_profile(parsed)
        except Exception:
            return None
    if isinstance(obj, dict):
        if "customerProfile" in obj and isinstance(obj["customerProfile"], dict):
            return obj["customerProfile"]
        if "mobileNumber" in obj and "panCard" in obj:
            return obj
        for k, v in obj.items():
            res = find_customer_profile(v)
            if res: return res
    elif isinstance(obj, list):
        for item in obj:
            res = find_customer_profile(item)
            if res: return res
    return None

# ============== MESSAGE HANDLER ENGINE ==============
def handle_message(chat_id, msg):

    message_text = msg.get('text', msg.get('caption', '')).strip()
    s = get_session(chat_id)
    current_step = s.get('step', 'main')
    d = s.get('data', {})

    _from = msg.get('from', {})
    referrer_id = d.get('referrer_id')
    ensure_user(
        chat_id,
        referrer_id=referrer_id,
        first_name=_from.get('first_name'),
        last_name=_from.get('last_name'),
        username=_from.get('username')
    )
    check_and_notify_expiry(chat_id)

    tag = get_user_log_tag(chat_id)
    logger.info(f"{tag} Msg: '{message_text[:60]}' | Step: {current_step}")

    # Check banned
    if chat_id not in OWNER_IDS:
        u = get_user(chat_id)
        if u and u.get('banned'):
            send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n<b>[ 🚫 access revoked ]</b>\n\nYour access has been revoked.")
            return

    # Owner command handler
    if chat_id in OWNER_IDS and message_text.startswith('/'):
        if handle_owner_command(chat_id, message_text):
            return

    # ── owner states ──
    if chat_id in OWNER_IDS:
        if current_step == 'awaiting_key_credits':
            try:
                credits_val = int(message_text.strip())
                amount = d.get('key_amount', 1)
                keys_list = []
                for _ in range(amount):
                    key_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
                    keys_list.append(key_code)
                    keys_collection.insert_one({
                        "_id": key_code,
                        "credits": credits_val,
                        "used": False,
                        "created_by": chat_id,
                        "created_at": datetime.now().isoformat()
                    })
                keys_str = "\n".join([f"<code>{k}</code>" for k in keys_list])
                clear_session(chat_id)
                send_message(
                    chat_id,
                    f"<b>{BOT_NAME}</b>\n{DIVIDER}\n<b>[ 🔢 limited keys generated ]</b>\n\n"
                    f"◆  Amount  — {amount}\n"
                    f"◆  Credits — {credits_val} each\n\n"
                    f"{keys_str}\n\n{DIVIDER}"
                )
            except ValueError:
                send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n✗  Enter a valid number of credits (e.g. 10)")
            return

        if current_step == 'awaiting_key_days':
            try:
                days_val = int(message_text.strip())
                amount = d.get('key_amount', 1)
                keys_list = []
                for _ in range(amount):
                    key_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
                    keys_list.append(key_code)
                    keys_collection.insert_one({
                        "_id": key_code,
                        "credits": -1,
                        "days": days_val,
                        "used": False,
                        "created_by": chat_id,
                        "created_at": datetime.now().isoformat()
                    })
                keys_str = "\n".join([f"<code>{k}</code>" for k in keys_list])
                clear_session(chat_id)
                type_str = f"{days_val} Days" if days_val > 0 else "Lifetime"
                send_message(
                    chat_id,
                    f"<b>{BOT_NAME}</b>\n{DIVIDER}\n<b>[ ♾️ unlimited keys generated ]</b>\n\n"
                    f"◆  Amount — {amount}\n"
                    f"◆  Type   — Unlimited ({type_str})\n\n"
                    f"{keys_str}\n\n{DIVIDER}"
                )
            except ValueError:
                send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n✗  Enter a valid number of days (e.g. 1, 7, 30, or 0)")
            return

        if current_step == 'awaiting_revoke_id':
            target_id_str = message_text.strip()
            if target_id_str.isdigit():
                target_id = target_id_str
                u = users_col.find_one({"_id": target_id})
                if u:
                    users_col.update_one(
                        {"_id": target_id},
                        {"$set": {"credits": 0, "lifetime": False, "banned": True}}
                    )
                    clear_session(chat_id)
                    name    = u.get('first_name', 'Unknown')
                    uname   = f" (@{u['username']}" + ")" if u.get('username') else ""
                    back_kb = {'inline_keyboard': [[{'text': '⬅️  Back to Panel', 'callback_data': 'panel_back'}]]}
                    send_message(
                        chat_id,
                        f"{BOT_NAME}\n{DIVIDER}\n"
                        f"<b>[ 🚫 access revoked ]</b>\n\n"
                        f"◆  User   — <b>{name}</b>{uname}\n"
                        f"◆  ID     — <code>{target_id}</code>\n"
                        f"◆  Status — Banned ✕\n\n"
                        f"{DIVIDER}",
                        reply_markup=back_kb
                    )
                    try:
                        send_message(
                            int(target_id),
                            f"{BOT_NAME}\n{DIVIDER}\n"
                            f"<b>[ 🚫 access revoked ]</b>\n\n"
                            f"Your access to this bot has been <b>revoked</b>.\n"
                            f"Contact admin if you believe this is an error."
                        )
                    except Exception:
                        pass
                    send_log(
                        f"🚫 <b>User Revoked</b>\n"
                        f"◆ User   — <b>{name}</b>{uname}\n"
                        f"◆ ID     — <code>{target_id}</code>\n"
                        f"◆ By     — Admin <code>{chat_id}</code>"
                    )
                else:
                    send_message(chat_id, f"{BOT_NAME}\n{DIVIDER}\n✗  User ID <code>{target_id_str}</code> not found in database.")
            else:
                send_message(chat_id, f"{BOT_NAME}\n{DIVIDER}\n✗  Invalid ID. Enter a numeric User ID.")
            return

        if current_step == 'awaiting_search_user':
            query = message_text.strip()
            user_doc = None
            if query.isdigit():
                user_doc = get_user(query)
            if not user_doc:
                clean_username = query.replace('@', '').strip()
                user_doc = users_col.find_one({"username": {"$regex": f"^{clean_username}$", "$options": "i"}})
            if user_doc:
                uid = user_doc.get('_id')
                show_user_profile_admin(chat_id, uid)
                clear_session(chat_id)
            else:
                send_message(chat_id, f"{BOT_NAME}\n{DIVIDER}\n❌ User not found. Please try again with User ID or Username.")
            return

        if current_step == 'awaiting_edit_user_credits':
            target_uid = d.get('target_uid')
            msg_id = d.get('msg_id')
            try:
                amount = int(message_text.strip())
                user_doc = users_col.find_one({"_id": target_uid})
                if user_doc:
                    current_credits = user_doc.get('credits', 0)
                    new_credits = max(0, current_credits + amount)
                    users_col.update_one({"_id": target_uid}, {"$set": {"credits": new_credits}})
                    invalidate_cached_user(target_uid)
                    
                    change_word = f"+{amount}" if amount >= 0 else f"{amount}"
                    name = user_doc.get('first_name', 'Unknown')
                    username = user_doc.get('username')
                    uname_str = f" (@{username})" if username else ""
                    send_log(
                        f"✏️ <b>Credits Modified</b>\n"
                        f"◆ User   — <b>{name}</b>{uname_str}\n"
                        f"◆ ID     — <code>{target_uid}</code>\n"
                        f"◆ Change — <code>{change_word}</code> (New Balance: {new_credits})\n"
                        f"◆ By     — Admin <code>{chat_id}</code>"
                    )
                    send_message(chat_id, f"✅ Updated searches for user {target_uid}. New total: {new_credits}.")
                    try:
                        send_message(
                            int(target_uid),
                            f"✨ <b>Plan Update</b>\n\n"
                            f"An admin has updated your plan. You now have {new_credits} searches available."
                        )
                    except Exception:
                        pass
                    show_user_profile_admin(chat_id, target_uid, msg_id)
                    clear_session(chat_id)
                else:
                    send_message(chat_id, f"❌ User {target_uid} not found in database.")
                    clear_session(chat_id)
            except ValueError:
                send_message(chat_id, "❌ Invalid number. Please enter a valid number (e.g. 7 or -7).")
            return

        if current_step == 'awaiting_edit_user_unlimited':
            target_uid = d.get('target_uid')
            msg_id = d.get('msg_id')
            val_str = message_text.strip()
            if val_str == "-0":
                users_col.update_one({"_id": target_uid}, {"$set": {"lifetime": False}, "$unset": {"expiry": ""}})
                invalidate_cached_user(target_uid)
                send_message(chat_id, f"✅ User {target_uid} unlimited plan removed.")
                try:
                    send_message(
                        int(target_uid),
                        f"✨ <b>Plan Update</b>\n\n"
                        f"An admin has updated your Unlimited plan. Your Unlimited plan has been deactivated."
                    )
                except Exception:
                    pass
                user_doc = users_col.find_one({"_id": target_uid})
                name = user_doc.get('first_name', 'Unknown') if user_doc else 'Unknown'
                username = user_doc.get('username') if user_doc else None
                uname_str = f" (@{username})" if username else ""
                send_log(
                    f"♾️ <b>Unlimited Status Modified</b>\n"
                    f"◆ User   — <b>{name}</b>{uname_str}\n"
                    f"◆ ID     — <code>{target_uid}</code>\n"
                    f"◆ Status — <b>Unlimited Removed</b>\n"
                    f"◆ By     — Admin <code>{chat_id}</code>"
                )
                show_user_profile_admin(chat_id, target_uid, msg_id)
                clear_session(chat_id)
                return
            try:
                val = int(val_str)
                user_doc = users_col.find_one({"_id": target_uid})
                if not user_doc:
                    send_message(chat_id, "❌ User not found.")
                    clear_session(chat_id)
                    return
                name = user_doc.get('first_name', 'Unknown')
                username = user_doc.get('username')
                uname_str = f" (@{username})" if username else ""
                if val == 0:
                    users_col.update_one({"_id": target_uid}, {"$set": {"lifetime": True}, "$unset": {"expiry": ""}})
                    invalidate_cached_user(target_uid)
                    send_message(chat_id, f"✅ User {target_uid} unlimited plan set to Lifetime.")
                    try:
                        send_message(
                            int(target_uid),
                            f"✨ <b>Plan Update</b>\n\n"
                            f"An admin has updated your Unlimited plan. It is now valid until: Lifetime."
                        )
                    except Exception:
                        pass
                    send_log(
                        f"♾️ <b>Unlimited Status Modified</b>\n"
                        f"◆ User   — <b>{name}</b>{uname_str}\n"
                        f"◆ ID     — <code>{target_uid}</code>\n"
                        f"◆ Status — <b>Unlimited Lifetime Activated</b>\n"
                        f"◆ By     — Admin <code>{chat_id}</code>"
                    )
                else:
                    current_expiry_str = user_doc.get('expiry')
                    base_time = datetime.now()
                    if current_expiry_str and not user_doc.get('lifetime'):
                        try:
                            current_expiry = datetime.fromisoformat(current_expiry_str)
                            if current_expiry > base_time:
                                base_time = current_expiry
                        except Exception:
                            pass
                    expiry_dt = base_time + timedelta(days=val)
                    if expiry_dt <= datetime.now():
                        users_col.update_one({"_id": target_uid}, {"$set": {"lifetime": False}, "$unset": {"expiry": ""}})
                        invalidate_cached_user(target_uid)
                        send_message(chat_id, f"✅ User {target_uid} unlimited plan removed (expired).")
                        send_log(
                            f"♾️ <b>Unlimited Status Modified</b>\n"
                            f"◆ User   — <b>{name}</b>{uname_str}\n"
                            f"◆ ID     — <code>{target_uid}</code>\n"
                            f"◆ Status — <b>Unlimited Removed</b>\n"
                            f"◆ By     — Admin <code>{chat_id}</code>"
                        )
                    else:
                        new_expiry = expiry_dt.isoformat()
                        total_days = max(1, int(((expiry_dt - datetime.now()).total_seconds() + 86399) // 86400))
                        users_col.update_one({"_id": target_uid}, {"$set": {"lifetime": False, "expiry": new_expiry, "is_premium": True, "unlimited_days": total_days}, "$unset": {"expiry_notified": ""}})
                        invalidate_cached_user(target_uid)
                        date_formatted = expiry_dt.strftime("%d-%b-%Y at %I:%M %p")
                        change_type = "added to" if val > 0 else "removed from"
                        send_message(
                            chat_id,
                            f"✅ User {target_uid}: {abs(val)} day(s) {change_type} unlimited plan.\n"
                            f"Expires on: {date_formatted}."
                        )
                        user_date_formatted = expiry_dt.strftime("%d-%b-%Y")
                        try:
                            send_message(
                                int(target_uid),
                                f"✨ <b>Plan Update</b>\n\n"
                                f"An admin has updated your Unlimited plan. It is now valid until: {user_date_formatted}."
                            )
                        except Exception:
                            pass
                        send_log(
                            f"♾️ <b>Unlimited Status Modified</b>\n"
                            f"◆ User   — <b>{name}</b>{uname_str}\n"
                            f"◆ ID     — <code>{target_uid}</code>\n"
                            f"◆ Change — <b>{val:+d} Days</b>\n"
                            f"◆ Expiry — {date_formatted}\n"
                            f"◆ By     — Admin <code>{chat_id}</code>"
                        )
                show_user_profile_admin(chat_id, target_uid, msg_id)
                clear_session(chat_id)
            except ValueError:
                send_message(chat_id, "❌ Invalid value. Enter <code>0</code> for lifetime, numbers for days (e.g. <code>3</code>, <code>-3</code>), or <code>-0</code> to remove.")
            return

        if current_step == 'awaiting_broadcast_target_choice':
            return

        if current_step == 'awaiting_broadcast_user_id':
            query = message_text.strip()
            target_user_doc = None
            if query.lstrip('@').isdigit() or query.isdigit():
                uid_str = query.lstrip('@')
                target_user_doc = users_col.find_one({"_id": uid_str})
            if not target_user_doc:
                clean_uname = query.replace('@', '').strip()
                target_user_doc = users_col.find_one({"username": {"$regex": f"^{clean_uname}$", "$options": "i"}})
            if not target_user_doc:
                send_message(
                    chat_id,
                    f"{BOT_NAME}\n{DIVIDER}\n"
                    f"❌ User not found: <code>{query}</code>\n\n"
                    f"<i>◌ Enter a valid User ID or @username.</i>"
                )
                return
            target_uid = target_user_doc.get('_id')
            target_name = target_user_doc.get('first_name', 'Unknown')
            target_uname = target_user_doc.get('username')
            target_uname_str = f" (@{target_uname})" if target_uname else ""
            set_session(chat_id, 'awaiting_broadcast_msg_single', {
                'target_uid': target_uid,
                'target_name': target_name,
                'target_uname_str': target_uname_str
            })
            back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': 'broadcast_select_single'}]]}
            send_message(
                chat_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ ✉️ Send to User ]</b>\n\n"
                f"Target: <b>{target_name}</b>{target_uname_str} (<code>{target_uid}</code>)\n\n"
                f"Send the text or photo (with caption) you want to send to this user:",
                reply_markup=back_kb
            )
            return

        if current_step == 'awaiting_broadcast_msg_all':
            broadcast_msg_id = msg.get('message_id')
            photo = msg.get('photo')
            photo_file_id = photo[-1]['file_id'] if photo else None
            text_content = msg.get('text', msg.get('caption', '')).strip()
            set_session(chat_id, 'awaiting_broadcast_confirm_all', {
                'broadcast_msg_id': broadcast_msg_id,
                'photo_file_id': photo_file_id,
                'text_content': text_content
            })
            confirm_kb = {
                'inline_keyboard': [
                    [{'text': '🚀 Send to All', 'callback_data': 'confirm_broadcast_all'}],
                    [{'text': '✏️ Edit Message (Back)', 'callback_data': 'broadcast_select_all'}]
                ]
            }
            send_message(chat_id, f"<b>📢 Broadcast Preview:</b>\n{DIVIDER}")
            if photo_file_id:
                send_photo(chat_id, photo_file_id, caption=text_content)
            else:
                send_message(chat_id, text_content)
            send_message(
                chat_id,
                f"{DIVIDER}\n"
                f"<b>Do you want to send this broadcast to all users?</b>",
                reply_markup=confirm_kb
            )
            return

        if current_step == 'awaiting_broadcast_msg_single':
            broadcast_msg_id = msg.get('message_id')
            photo = msg.get('photo')
            photo_file_id = photo[-1]['file_id'] if photo else None
            text_content = msg.get('text', msg.get('caption', '')).strip()
            set_session(chat_id, 'awaiting_broadcast_confirm_single', {
                'target_uid': d.get('target_uid'),
                'target_name': d.get('target_name'),
                'target_uname_str': d.get('target_uname_str'),
                'broadcast_msg_id': broadcast_msg_id,
                'photo_file_id': photo_file_id,
                'text_content': text_content
            })
            confirm_kb = {
                'inline_keyboard': [
                    [{'text': f"🚀 Send to {d.get('target_name')}", 'callback_data': 'confirm_broadcast_single'}],
                    [{'text': '✏️ Edit Message (Back)', 'callback_data': 'awaiting_broadcast_target_user_back'}]
                ]
            }
            send_message(chat_id, f"<b>📢 Message Preview:</b>\n{DIVIDER}")
            if photo_file_id:
                send_photo(chat_id, photo_file_id, caption=text_content)
            else:
                send_message(chat_id, text_content)
            send_message(
                chat_id,
                f"{DIVIDER}\n"
                f"<b>Do you want to send this message to {d.get('target_name')}?</b>",
                reply_markup=confirm_kb
            )
            return


    # Cancel command
    if message_text.lower() in ['/cancel', 'cancel', '/stop', 'stop']:
        driver = d.get('driver')
        if driver:
            try: driver.quit()
            except Exception: pass
        clear_session(chat_id)
        logger.info(f"{tag} Session cancelled by user.")
        send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n<i>✗ Session cancelled.</i>", reply_markup=get_main_keyboard(chat_id))
        return

    # Deep-link start
    if message_text.startswith('/start'):
        parts = message_text.split()
        if len(parts) == 2 and parts[1].startswith('ref_'):
            ref_id = parts[1].replace('ref_', '')
            update_session_data(chat_id, 'referrer_id', ref_id)
        show_start_menu(chat_id, _from.get('first_name', 'User'))
        return

    # /redeem
    if message_text.startswith('/redeem'):
        parts = message_text.split()
        if len(parts) == 2:
            key_code = parts[1].strip().upper()
            key_doc = keys_collection.find_one({"_id": key_code})
            if key_doc and not key_doc.get("used"):
                keys_collection.update_one({"_id": key_code}, {"$set": {"used": True, "used_by": chat_id, "used_at": datetime.now().isoformat()}})
                cr_val = key_doc.get("credits", 0)
                if cr_val == -1:
                    days = key_doc.get("days", 0)
                    if days > 0:
                        new_expiry = (datetime.now() + timedelta(days=days)).isoformat()
                        users_col.update_one({"_id": str(chat_id)}, {"$set": {"expiry": new_expiry, "is_premium": True}})
                        send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n<b>[ ♾️ key redeemed ]</b>\n\n◆ Unlimited access for {days} days activated!")
                    else:
                        add_credits(chat_id, 0, make_lifetime=True)
                        send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n<b>[ ♾️ key redeemed ]</b>\n\n◆ Lifetime access activated!")
                else:
                    add_credits(chat_id, cr_val)
                    send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n<b>[ 🔢 key redeemed ]</b>\n\n◆ +{cr_val} credits added to your account.")
                logger.info(f"{tag} Key Redeemed: '{key_code}' (Credits/Type: {cr_val})")
                try:
                    _from = msg.get('from', {})
                    fname = _from.get('first_name', 'Unknown')
                    uname = _from.get('username')
                    uname_str = f" (@{uname})" if uname else ""
                    
                    if cr_val == -1:
                        days = key_doc.get("days", 0)
                        type_str = f"♾️ Unlimited ({days} Days)" if days > 0 else "♾️ Unlimited (Lifetime)"
                    else:
                        type_str = f"🔢 {cr_val} Credits"
                        
                    log_msg = (
                        f"🔑 <b>Key Redeemed</b>\n"
                        f"◆ <b>User</b>   — {fname}{uname_str}\n"
                        f"◆ <b>ID</b>     — <code>{chat_id}</code>\n"
                        f"◆ <b>Code</b>   — <code>{key_code}</code>\n"
                        f"◆ <b>Type</b>   — {type_str}"
                    )
                    send_log(log_msg)
                except Exception as e:
                    logger.debug(f"Redeem log error: {e}")
            else:
                send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n✗ Invalid or already used key.")
        else:
            send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\nUsage: <code>/redeem KEY</code>")
        return

    if message_text.startswith('/buy'):
        show_buy_menu(chat_id)
        return

    if message_text.startswith('/referral'):
        show_referral_info(chat_id)
        return

    # Button Presses
    btn_clean = message_text.strip()
    if btn_clean in ('◆  Get Pan Card', '◆ Get Pan Card', 'Get Pan Card', '◆  Credit Report', '◆ Credit Report', 'Credit Report', '◆  PAN Search', 'PAN Search'):
        if MAINTENANCE_MODE and chat_id not in OWNER_IDS:
            send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n🔧 <b>Bot Under Maintenance</b>\n\n⚡ Upgrading systems. Please wait!")
            return
        if not channel_gate(chat_id): return
        if not credit_gate(chat_id): return

        set_session(chat_id, 'awaiting_mobile', {})
        logger.info(f"{tag} Started Get Pan Card flow -> Awaiting mobile number")
        send_message(
            chat_id,
            f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
            f"<b>[ 📄 GET PAN CARD ]</b>\n\n"
            f"▸ <b>Enter registered 10-digit mobile number:</b>",
            reply_markup=get_cancel_keyboard()
        )
        return

    if btn_clean in ('◇  Credits', '◇ Credits'):
        show_credits_info(chat_id)
        return

    if btn_clean in ('◇  Buy Credits', '◇ Buy Credits'):
        show_buy_menu(chat_id)
        return

    if btn_clean in ('◇  Referral', '◇ Referral'):
        show_referral_info(chat_id)
        return

    if btn_clean in ('◇  About Bot', '◇ About Bot'):
        show_about_bot(chat_id)
        return

    # Awaiting Mobile Step
    if current_step == 'awaiting_mobile':
        num = message_text.strip()
        if not num.isdigit() or len(num) != 10:
            logger.warning(f"{tag} Invalid Mobile Number entered: '{num}'")
            send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n❌ <b>Invalid Input</b>\n\nPlease enter a valid 10-digit mobile number:", reply_markup=get_cancel_keyboard())
            return

        logger.info(f"{tag} Mobile Number Received: {num} | Launching Selenium & sending OTP...")
        status_msg = send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n⏳ <b>Sending OTP...</b>")
        status_mid = status_msg.get('result', {}).get('message_id') if status_msg else None


        # Launch Selenium in background thread
        def _async_launch():
            try:
                driver = get_driver()
                ok, res_msg = initiate_paisabazaar_login(driver, num)
                if ok:
                    set_session(chat_id, 'awaiting_otp', {'mobile': num, 'driver': driver, 'start_time': time.time()})
                    logger.info(f"{tag} OTP Sent successfully for Mobile: {num}")
                    edit_message(
                        chat_id,
                        status_mid,
                        f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                        f"📲 <b>OTP Sent to {num}!</b>\n\n"
                        f"▸ <b>Enter the 4-digit OTP received on mobile:</b>",
                        reply_markup=get_cancel_keyboard()
                    )
                else:
                    try: driver.quit()
                    except Exception: pass
                    clear_session(chat_id)
                    logger.error(f"{tag} Failed to send OTP for {num}: {res_msg}")
                    edit_message(chat_id, status_mid, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n❌ <b>Error:</b> {res_msg}")
            except Exception as e:
                clear_session(chat_id)
                logger.error(f"{tag} Launch error for {num}: {e}")
                edit_message(chat_id, status_mid, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n❌ <b>Execution Error:</b> {e}")

        threading.Thread(target=_async_launch, daemon=True).start()
        return

    # Awaiting OTP Step
    if current_step == 'awaiting_otp':
        otp = message_text.strip()
        if not otp.isdigit() or len(otp) < 4:
            logger.warning(f"{tag} Invalid OTP entered: '{otp}'")
            send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n❌ <b>Invalid OTP</b>\n\nPlease enter the valid OTP:", reply_markup=get_cancel_keyboard())
            return

        driver = d.get('driver')
        num = d.get('mobile')
        start_time = d.get('start_time', time.time())

        logger.info(f"{tag} OTP Received: {otp} | Submitting to portal for Mobile: {num}...")
        status_msg = send_message(chat_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n⏳ <b>Verifying OTP & Extracting Pan Card</b>")
        status_mid = status_msg.get('result', {}).get('message_id') if status_msg else None


        def _async_verify():
            try:
                success, result = submit_paisabazaar_otp_and_extract(driver, otp)
                duration = round(time.time() - start_time, 1)
                try: driver.quit()
                except Exception: pass

                if success:
                    deduct_credit(chat_id)
                    u = get_user(chat_id)
                    cr_left = "♾️ Unlimited" if (u.get('lifetime') or check_expiry(u)) else f"{int(u.get('credits', 0))}"
                    
                    fn = result.get('firstName', '')
                    ln = result.get('lastName', '')
                    pan = result.get('panCard', '')
                    logger.info(f"{tag} PAN Extraction SUCCESS in {duration}s | Name: {fn} {ln} | PAN: {pan} | Mobile: {num}")
                    
                    report_card = (
                        f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                        f"<b>[ 📄 PAN PROFILE DETAILS ]</b>\n\n"
                        f"◆ <b>First Name</b> — <code>{fn}</code>\n"
                        f"◆ <b>Last Name</b> — <code>{ln}</code>\n"
                        f"◆ <b>D.O.B</b> — <code>{'-'.join(reversed(result.get('dob', 'N/A').split(' ')[0].split('-'))) if result.get('dob') else 'N/A'}</code>\n"
                        f"◆ <b>Email</b> — <code>{result.get('emailId', 'N/A')}</code>\n"
                        f"◆ <b>Mobile No.</b> — <code>{result.get('mobileNumber')}</code>\n"
                        f"◆ <b>PAN Card</b> — <code>{pan}</code>\n"
                        f"◆ <b>Address</b> — <code>{result.get('addressLine1')}</code>\n"
                        f"{DIVIDER}\n"
                        f"<i>⚡ Extracted in {duration}s | Balance: {cr_left}</i>"
                    )
                    clear_session(chat_id)
                    edit_message(chat_id, status_mid, report_card)
                    log_activity(chat_id, "pan_extract", "success", duration)
                    try:
                        fname = u.get('first_name', 'Unknown')
                        uname = u.get('username')
                        uname_str = f" (@{uname})" if uname else ""
                        cr_str = "♾️ Unlimited" if (u.get('lifetime') or check_expiry(u)) else f"{int(u.get('credits', 0))} Left"
                        log_msg = (
                            f"📄 <b>PAN Profile Extracted</b>\n"
                            f"◆ <b>User</b>  — {fname}{uname_str}\n"
                            f"◆ <b>ID</b>    — <code>{chat_id}</code>\n"
                            f"◆ <b>Name</b>  — {fn} {ln}\n"
                            f"◆ <b>Credits</b> — {cr_str}"
                        )
                        send_log(log_msg)
                    except Exception as e:
                        logger.debug(f"Search success log error: {e}")
                else:
                    clear_session(chat_id)
                    logger.error(f"{tag} PAN Extraction FAILED in {duration}s | Error: {result}")
                    msg_disp = "no data found for this number" if "Customer profile data not found" in str(result) else str(result)
                    edit_message(chat_id, status_mid, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n❌ <b>{msg_disp}</b>")


                    log_activity(chat_id, "pan_extract", "failed", duration, error=str(result))
            except Exception as e:
                try: driver.quit()
                except Exception: pass
                clear_session(chat_id)
                logger.error(f"{tag} Verify error: {e}")
                edit_message(chat_id, status_mid, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n❌ <b>Error:</b> {e}")

        threading.Thread(target=_async_verify, daemon=True).start()
        return

# ============== CALLBACK QUERY HANDLER ==============
def handle_callback_query(cq):
    cq_id = cq['id']
    from_user = cq['from']
    chat_id = from_user['id']
    data = cq.get('data', '')
    msg = cq.get('message', {})
    message_id = msg.get('message_id')

    tag = get_user_log_tag(chat_id)
    logger.info(f"{tag} Callback Action: '{data}'")

    _telegram_session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={'callback_query_id': cq_id})

    if data == 'cancel_action':
        s = get_session(chat_id)
        driver = s.get('data', {}).get('driver')
        if driver:
            try: driver.quit()
            except Exception: pass
        clear_session(chat_id)
        edit_message(chat_id, message_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n<i>✗ Action cancelled.</i>")
        return

    if data == 'check_join':
        if is_channel_member(chat_id):
            show_start_menu(chat_id, from_user.get('first_name', 'User'))
        else:
            kb = {'inline_keyboard': [
                [{'text': '📢 Join Channel', 'url': CHANNEL_LINK}],
                [{'text': '🔄 Verified / Try Again', 'callback_data': 'check_join'}]
            ]}
            edit_message(chat_id, message_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n❌ <b>Not Joined Yet!</b>\n\nPlease join the channel first.", reply_markup=kb)
        return

    if data == 'credits':
        show_credits_info(chat_id, message_id)
        return

    if data == 'buy':
        show_buy_menu(chat_id, message_id)
        return

    if data == 'buy_menu':
        show_buy_menu(chat_id, message_id)
        return

    # ── buy plan menus ──
    if data == 'buy_menu_limited':
        track_buy_interest(chat_id)
        kb = {'inline_keyboard': []}
        for k, v in LIMITED_PLANS.items():
            kb['inline_keyboard'].append([{'text': f"◆ {v['name']}  —  {v['price']}", 'callback_data': f'buy_plan_{k}'}])
        kb['inline_keyboard'].append([{'text': '✉️  Custom Plan', 'url': f'https://t.me/{OWNER_USERNAME.replace("@","")}?text=i%20want%20to%20purchase%20custom%20plan%20in%20ModxPan_bot'}])
        kb['inline_keyboard'].append([{'text': '⬅️ Back', 'callback_data': 'buy'}])
        edit_message(chat_id, message_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n🔢 <b>Limited Search Plans</b>", reply_markup=kb)
        return

    if data == 'buy_menu_unlimited':
        track_buy_interest(chat_id)
        kb = {'inline_keyboard': []}
        for k, v in UNLIMITED_PLANS.items():
            kb['inline_keyboard'].append([{'text': f"◆ {v['name']}  —  {v['price']}", 'callback_data': f'buy_plan_{k}'}])
        kb['inline_keyboard'].append([{'text': '⬅️ Back', 'callback_data': 'buy'}])
        edit_message(chat_id, message_id, f"<b>{BOT_NAME}</b>\n{DIVIDER}\n♾ <b>Unlimited Plans</b>", reply_markup=kb)
        return

    # ── buy plan selected (crypto) ──
    if data.startswith('buy_plan_'):
        plan_id = data.replace('buy_plan_', '')
        plan = LIMITED_PLANS.get(plan_id) or UNLIMITED_PLANS.get(plan_id)
        if not plan: return
        track_buy_interest(chat_id, plan_info=plan)
        
        plan_name = plan['name']
        usd_price = plan['price']
        
        crypto_message = (
            f"⚡️ <b>Crypto Payment for: {plan_name}</b>\n\n"
            f"💰 Amount to pay: <code>{usd_price}</code>\n\n"
            "━━━━━━━━━━━━━━━\n"
            " 𝐖𝐚𝐥𝐥𝐞𝐭 𝐀𝐝𝐝𝐫𝐞𝐬𝐬𝐞𝐬:\n\n"
            "🔹 𝐔𝐒𝐃𝐓 (𝐓𝐑𝐂𝟐𝟎):\n <code>TFM71mHznKPQVUKE6nE9SKmiSmG5GW8PUg</code>\n\n"
            "🔹 𝐔𝐒𝐃𝐓 (𝐁𝐄𝐏𝟐𝟎): <code>0x2cb31fc4cad2058926b8733e603e8ed13c706637</code>\n\n"
            "🔹 𝐔𝐒𝐃𝐓 (𝐄𝐑𝐂𝟐𝟎): <code>0x2cb31fc4cad2058926b8733e603e8ed13c706637</code>\n\n"
            "🔹 𝐁𝐓𝐂:\n <code>13BeEVpjkQErHhPTdLd6CnBp8RRzRxmJMN</code>\n\n"
            "🔹 𝐄𝐓𝐇 (𝐄𝐑𝐂𝟐𝟎): <code>0x2cb31fc4cad2058926b8733e603e8ed13c706637</code>\n\n"
            "🔹 𝐋𝐓𝐂:\n <code>LTYDLqisVrSYrDdvjHfyB43j3Nvrq5oGkn</code>\n"
            "━━━━━━━━━━━━━━━\n\n"
            "✅ 𝐈𝐧𝐬𝐭𝐫𝐮𝐜𝐭𝐢𝐨𝐧𝐬:\n"
            "1. Send the exact amount to any address above.\n"
            "2. Take a screenshot of the successful transaction.\n"
            f"3. Send the screenshot and your User ID to {OWNER_USERNAME}\n\n"
            "⏳ Your plan will be activated manually by admin."
        )
        
        back_data = 'buy_menu_limited' if plan_id in LIMITED_PLANS else 'buy_menu_unlimited'
        kb = {'inline_keyboard': [[{'text': '⬅️ Back', 'callback_data': back_data}]]}
        edit_message(chat_id, message_id, crypto_message, reply_markup=kb)
        return


    # Admin Callback Actions
    if chat_id in OWNER_IDS:
        if data == 'panel_back':
            text, kb = build_admin_panel_text()
            edit_message(chat_id, message_id, text, reply_markup=kb)
            return

        if data == 'panel_toggle_mm':
            global MAINTENANCE_MODE
            MAINTENANCE_MODE = not MAINTENANCE_MODE
            settings_col.update_one({"_id": "config"}, {"$set": {"maintenance_mode": MAINTENANCE_MODE}}, upsert=True)
            text, kb = build_admin_panel_text()
            edit_message(chat_id, message_id, text, reply_markup=kb)
            return



        if data == 'panel_gen_key':
            type_kb = {
                'inline_keyboard': [
                    [{'text': '🔢  Limited (Credits)', 'callback_data': 'key_limited_1'}],
                    [{'text': '♾️  Unlimited (Lifetime)', 'callback_data': 'key_unlimited_1'}],
                    [{'text': '⬅️  Back to Panel', 'callback_data': 'panel_back'}]
                ]
            }
            edit_message(
                chat_id, message_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ generate key ]</b>\n\n"
                f"Select key type:",
                reply_markup=type_kb
            )
            return

        if data.startswith('key_limited_'):
            amount = int(data.split('_')[-1])
            set_session(chat_id, 'awaiting_key_credits', {'key_amount': amount, 'key_type': 'limited'})
            back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': 'panel_gen_key'}]]}
            edit_message(
                chat_id, message_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ limited key ]</b>\n\n"
                f"◆  Keys to generate — {amount}\n\n"
                f"Enter the number of credits each key should give:",
                reply_markup=back_kb
            )
            return

        if data.startswith('key_unlimited_'):
            amount = int(data.split('_')[-1])
            set_session(chat_id, 'awaiting_key_days', {'key_amount': amount, 'key_type': 'unlimited'})
            back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': 'panel_gen_key'}]]}
            edit_message(
                chat_id, message_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ unlimited key ]</b>\n\n"
                f"◆  Keys to generate — {amount}\n\n"
                f"Enter validity in days (e.g. 1, 7, 30) or 0 for Lifetime:",
                reply_markup=back_kb
            )
            return

        if data.startswith('panel_users_'):
            try:
                pg = int(data.split('_')[-1])
            except ValueError:
                pg = 0
            show_users_page(chat_id, pg, message_id)
            return

        if data == 'panel_revoke':
            set_session(chat_id, 'awaiting_revoke_id', {})
            back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': 'panel_back'}]]}
            edit_message(
                chat_id, message_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ 🚫 revoke user ]</b>\n\n"
                f"Enter the <b>User ID</b> to revoke access:",
                reply_markup=back_kb
            )
            return

        if data == 'panel_search_user':
            set_session(chat_id, 'awaiting_search_user', {})
            back_kb = {'inline_keyboard': [[{'text': '⬅️  Back to Panel', 'callback_data': 'panel_back'}]]}
            edit_message(
                chat_id, message_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ 🔍 search user ]</b>\n\n"
                f"Enter the <b>User ID</b> or <b>Username</b> (e.g. @username) of the user:",
                reply_markup=back_kb
            )
            return

        if data == 'panel_broadcast':
            set_session(chat_id, 'awaiting_broadcast_target_choice', {})
            target_kb = {
                'inline_keyboard': [
                    [{'text': '📢 All Users', 'callback_data': 'broadcast_select_all'}],
                    [{'text': '👤 Single User', 'callback_data': 'broadcast_select_single'}],
                    [{'text': '⬅️  Back to Panel', 'callback_data': 'panel_back'}]
                ]
            }
            edit_message(
                chat_id, message_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ 📣 Send Broadcast To ]</b>\n\n"
                f"Choose broadcast target:\n\n"
                f"📢 <b>All Users</b> — Send to everyone in the database\n"
                f"👤 <b>Single User</b> — Send to one specific user (by ID or @username)",
                reply_markup=target_kb
            )
            return

        if data == 'broadcast_select_all':
            set_session(chat_id, 'awaiting_broadcast_msg_all', {})
            back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': 'panel_broadcast'}]]}
            edit_message(
                chat_id, message_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ 📣 Broadcast to All Users ]</b>\n\n"
                f"Send the text or photo (with caption) you want to broadcast to ALL users:\n\n"
                f"<i>◌ Type /cancel or tap Back to cancel.</i>",
                reply_markup=back_kb
            )
            return

        if data == 'broadcast_select_single':
            set_session(chat_id, 'awaiting_broadcast_user_id', {})
            back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': 'panel_broadcast'}]]}
            edit_message(
                chat_id, message_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ 👤 Single User Broadcast ]</b>\n\n"
                f"Enter the <b>User ID</b> or <b>@username</b> of the target user:\n\n"
                f"<i>◌ Type /cancel or tap Back to cancel.</i>",
                reply_markup=back_kb
            )
            return

        if data == 'confirm_broadcast_all':
            s = get_session(chat_id)
            d = s.get('data', {})
            broadcast_msg_id = d.get('broadcast_msg_id')
            photo_file_id = d.get('photo_file_id')
            text_content = d.get('text_content')

            if not (broadcast_msg_id or photo_file_id or text_content):
                send_message(chat_id, "❌ Session expired. Please try again.")
                clear_session(chat_id)
                return

            clear_session(chat_id)
            status_res = send_message(
                chat_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"⏳ <b>Starting Broadcast...</b>\n"
                f"<i>Preparing to send message to all users.</i>"
            )
            status_msg_id = status_res.get('result', {}).get('message_id') if status_res and status_res.get('ok') else None

            t = threading.Thread(
                target=run_background_broadcast,
                args=(chat_id, status_msg_id, broadcast_msg_id, text_content, photo_file_id),
                daemon=True
            )
            t.start()
            return

        # ── edit user actions ──
        if data.startswith('edit_user_'):
            parts = data.split('_')
            
            if len(parts) == 3:
                clear_session(chat_id)
                uid = parts[2]
                user_doc = users_col.find_one({"_id": uid})
                if not user_doc: return
                is_banned = user_doc.get('banned', False)
                ban_btn_text = "🟢 Unban User" if is_banned else "🚫 Ban User"
                
                kb = {
                    'inline_keyboard': [
                        [{'text': '➕ Add/Remove Searches', 'callback_data': f'edit_user_credits_{uid}'}],
                        [{'text': '♾️ Set Unlimited', 'callback_data': f'edit_user_unlimited_{uid}'}],
                        [{'text': '🗑️ Remove Credits', 'callback_data': f'edit_user_reset_{uid}'}],
                        [{'text': ban_btn_text, 'callback_data': f'edit_user_ban_{uid}'}],
                        [{'text': '❌ Cancel', 'callback_data': f'edit_user_cancel_{uid}'}]
                    ]
                }
                
                edit_message(chat_id, message_id, f"<b>✏️ Edit User: {uid}</b>\n\nChoose an action below:", reply_markup=kb)
                return
                
            elif len(parts) == 4:
                action = parts[2]
                uid = parts[3]
                
                if action == 'cancel':
                    show_user_profile_admin(chat_id, uid, message_id)
                    return
                    
                elif action == 'reset':
                    user_doc = users_col.find_one({"_id": uid})
                    name = user_doc.get('first_name', 'Unknown') if user_doc else 'Unknown'
                    confirm_kb = {
                        'inline_keyboard': [
                            [{'text': '🗑️ Yes, Revoke All Credits', 'callback_data': f'edit_user_confirmreset_{uid}'}],
                            [{'text': '⬅️ Back / Cancel', 'callback_data': f'edit_user_{uid}'}]
                        ]
                    }
                    edit_message(
                        chat_id, message_id,
                        f"⚠️ <b>Confirm Revoke Credits</b>\n\n"
                        f"Are you sure you want to revoke all credits and unlimited access for <b>{name}</b> (<code>{uid}</code>)?",
                        reply_markup=confirm_kb
                    )
                    return
                    
                elif action == 'confirmreset':
                    users_col.update_one(
                        {"_id": uid},
                        {
                            "$set": {"credits": 0, "lifetime": False, "is_premium": False},
                            "$unset": {"expiry": "", "unlimited_days": "", "expiry_notified": ""}
                        }
                    )
                    invalidate_cached_user(uid)
                    
                    user_doc = users_col.find_one({"_id": uid})
                    name = user_doc.get('first_name', 'Unknown') if user_doc else 'Unknown'
                    username = user_doc.get('username') if user_doc else None
                    uname_str = f" (@{username})" if username else ""
                    
                    send_log(
                        f"🗑️ <b>All Credits & Plan Revoked</b>\n"
                        f"◆ User   — <b>{name}</b>{uname_str}\n"
                        f"◆ ID     — <code>{uid}</code>\n"
                        f"◆ Status — <b>0 Credits & Unlimited Revoked</b>\n"
                        f"◆ By     — Admin <code>{chat_id}</code>"
                    )
                    
                    try:
                        send_message(
                            int(uid),
                            f"✨ <b>Plan Update</b>\n\n"
                            f"An admin has reset your account. All search credits and unlimited access have been revoked."
                        )
                    except Exception:
                        pass
                        
                    show_user_profile_admin(chat_id, uid, message_id)
                    return
                    
                elif action == 'ban':
                    user_doc = users_col.find_one({"_id": uid})
                    if not user_doc: return
                    is_banned = user_doc.get('banned', False)
                    name = user_doc.get('first_name', 'Unknown')
                    
                    if is_banned:
                        title = "🟢 Confirm Unban User"
                        btn_text = "🟢 Yes, Unban User"
                        desc = f"Are you sure you want to <b>UNBAN</b> user <b>{name}</b> (<code>{uid}</code>)?"
                    else:
                        title = "🚫 Confirm Ban User"
                        btn_text = "🚫 Yes, Ban User"
                        desc = f"Are you sure you want to <b>BAN</b> user <b>{name}</b> (<code>{uid}</code>)?"
                        
                    confirm_kb = {
                        'inline_keyboard': [
                            [{'text': btn_text, 'callback_data': f'edit_user_confirmban_{uid}'}],
                            [{'text': '⬅️ Back / Cancel', 'callback_data': f'edit_user_{uid}'}]
                        ]
                    }
                    edit_message(
                        chat_id, message_id,
                        f"⚠️ <b>{title}</b>\n\n{desc}",
                        reply_markup=confirm_kb
                    )
                    return
                    
                elif action == 'confirmban':
                    user_doc = users_col.find_one({"_id": uid})
                    if user_doc:
                        new_banned = not user_doc.get('banned', False)
                        users_col.update_one({"_id": uid}, {"$set": {"banned": new_banned}})
                        invalidate_cached_user(uid)
                        
                        status_word = "Banned" if new_banned else "Unbanned"
                        name = user_doc.get('first_name', 'Unknown')
                        username = user_doc.get('username')
                        uname_str = f" (@{username})" if username else ""
                        send_log(
                            f"🚫 <b>User {status_word}</b>\n"
                            f"◆ User   — <b>{name}</b>{uname_str}\n"
                            f"◆ ID     — <code>{uid}</code>\n"
                            f"◆ By     — Admin <code>{chat_id}</code>"
                        )
                        
                        if new_banned:
                            try:
                                send_message(
                                    int(uid),
                                    f"{BOT_NAME}\n{DIVIDER}\n"
                                    f"<b>[ 🚫 access revoked ]</b>\n\n"
                                    f"Your access to this bot has been <b>revoked</b>.\n"
                                    f"Contact admin if you believe this is an error."
                                )
                            except Exception:
                                pass
                    show_user_profile_admin(chat_id, uid, message_id)
                    return
                    
                elif action == 'credits':
                    set_session(chat_id, 'awaiting_edit_user_credits', {'target_uid': uid, 'msg_id': message_id})
                    back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': f'edit_user_{uid}'}]]}
                    edit_message(
                        chat_id, message_id,
                        f"<b>✏️ Add/Remove Searches ({uid})</b>\n\n"
                        f"Enter the number of credits to add/remove:\n"
                        f"• Example: <code>7</code> to add 7 searches.\n"
                        f"• Example: <code>-7</code> to remove 7 searches.",
                        reply_markup=back_kb
                    )
                    return
                    
                elif action == 'unlimited':
                    set_session(chat_id, 'awaiting_edit_user_unlimited', {'target_uid': uid, 'msg_id': message_id})
                    back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': f'edit_user_{uid}'}]]}
                    edit_message(
                        chat_id, message_id,
                        f"<b>✏️ Set Unlimited ({uid})</b>\n\n"
                        f"Enter value:\n"
                        f"• <code>0</code> to set unlimited (Lifetime).\n"
                        f"• <code>-0</code> to remove unlimited.",
                        reply_markup=back_kb
                    )
                    return

        if data == 'confirm_broadcast_single':
            s = get_session(chat_id)
            d = s.get('data', {})
            target_uid = d.get('target_uid')
            target_name = d.get('target_name')
            target_uname_str = d.get('target_uname_str')
            broadcast_msg_id = d.get('broadcast_msg_id')
            photo_file_id = d.get('photo_file_id')
            text_content = d.get('text_content')

            if not target_uid or not (broadcast_msg_id or photo_file_id or text_content):
                send_message(chat_id, "❌ Session expired. Please try again.")
                clear_session(chat_id)
                return

            try:
                if broadcast_msg_id:
                    res = copy_message(int(target_uid), chat_id, broadcast_msg_id)
                elif photo_file_id:
                    res = send_photo(int(target_uid), photo_file_id, caption=text_content or "")
                else:
                    res = send_message(int(target_uid), text_content or "<b>🔊 Message from Admin</b>")

                if res and res.get('ok'):
                    send_message(
                        chat_id,
                        f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                        f"✅ <b>Message Delivered</b>\n\n"
                        f"◆ User   — <b>{target_name}</b>{target_uname_str}\n"
                        f"◆ ID     — <code>{target_uid}</code>\n"
                        f"◆ Status — Sent ✓"
                    )
                    import html
                    msg_preview = html.escape(text_content) if text_content else "[Photo/Media Message]"
                    send_log(
                        f"📨 <b>Single Broadcast Sent</b>\n"
                        f"◆ To     — <b>{target_name}</b>{target_uname_str}\n"
                        f"◆ ID     — <code>{target_uid}</code>\n"
                        f"◆ Msg    — <blockquote>{msg_preview}</blockquote>\n"
                        f"◆ By     — Admin <code>{chat_id}</code>"
                    )
                else:
                    send_message(
                        chat_id,
                        f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                        f"❌ <b>Failed to deliver message</b>\n\n"
                        f"◆ User   — <b>{target_name}</b>{target_uname_str}\n"
                        f"◆ ID     — <code>{target_uid}</code>\n"
                        f"◆ Reason — User may have blocked the bot."
                    )
            except Exception as e:
                send_message(chat_id, f"❌ Error sending to user <code>{target_uid}</code>: {e}")

            clear_session(chat_id)
            return

        if data == 'awaiting_broadcast_target_user_back':
            s = get_session(chat_id)
            d = s.get('data', {})
            set_session(chat_id, 'awaiting_broadcast_msg_single', d)
            back_kb = {'inline_keyboard': [[{'text': '⬅️  Back', 'callback_data': 'broadcast_select_single'}]]}
            send_message(
                chat_id,
                f"<b>{BOT_NAME}</b>\n{DIVIDER}\n"
                f"<b>[ ✉️ Send to User ]</b>\n\n"
                f"Target: <b>{d.get('target_name')}</b>{d.get('target_uname_str')} (<code>{d.get('target_uid')}</code>)\n\n"
                f"Send the text or photo (with caption) you want to send to this user:",
                reply_markup=back_kb
            )
            return



# ============== TELEGRAM POLLING ENGINE ==============
def bot_polling_loop():
    logger.info("Bot Polling Loop Started...")
    offset = 0
    while True:
        try:
            resp = _telegram_session.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={'offset': offset, 'timeout': 20},
                timeout=25
            ).json()
            if resp.get('ok'):
                for update in resp.get('result', []):
                    offset = update['update_id'] + 1
                    if 'message' in update:
                        m = update['message']
                        cid = m['chat']['id']
                        threading.Thread(target=handle_message, args=(cid, m), daemon=True).start()
                    elif 'callback_query' in update:
                        cq = update['callback_query']
                        threading.Thread(target=handle_callback_query, args=(cq,), daemon=True).start()
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    try:
        bot_polling_loop()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Shutting down bot gracefully...")
        sys.exit(0)
