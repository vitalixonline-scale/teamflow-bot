import os
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "8774731842:AAHHHaVy-X3LFYFQa-kRWBBcrkiSzb23NVw")
MANAGER_PASSWORD = os.environ.get("MANAGER_PASSWORD", "admin1234")
DATA_FILE = "data.json"
WEBSITE_URL = "https://vitalixonline-scale.github.io/teamflow-website"
TZ = pytz.timezone("Europe/Zurich")

TEAMS = ["Marketing Team", "Safe Offers Team", "ReSell Team", "Sales Team", "Warehouse Team"]
SUMMARY_TEAMS = ["Marketing Team", "ReSell Team", "Sales Team", "Warehouse Team"]

MOTIVATIONS = [
    "🌅 Good morning! Today is a new opportunity to do great work. Let's make it count! 💪",
    "🔥 Rise and shine! Every big achievement starts with the decision to try. Go get it!",
    "⚡ A new day, a new chance to crush your goals. Your team is counting on you!",
    "🚀 Success is built one day at a time. Start strong today!",
    "💡 Great things never come from comfort zones. Push yourself today!",
    "🎯 Focus on what matters. Small steps every day lead to big results.",
    "🌟 You've got what it takes. Make today your best day yet!",
]

DAILY_ROUTINES = {
    "Marketing Team": [
        "Ad account health check (active, no bans)",
        "Budget check per ad account",
        "Website/landing page validity check",
        "Launch campaigns on META",
        "Create new creatives",
        "Prepare assets (BM, Ad Accounts, ADS Power/MultiBrowser)",
        "Identify winning ads (best ROAS)",
        "Scaling check (scale up / turn off)",
        "Competitor check (Facebook Ad Library)",
        "Audience refresh",
        "Morning recap in group (spend, revenue, ROAS per account)",
        "Daily targets check per brand",
        "Pixel firing check",
        "Keitaro stats & redirect check",
        "Backup domain check",
        "Landing page speed check",
    ],
    "Safe Offers Team": [
        "White Page setup & test",
        "Cloaking setup & test",
        "Offer Page check (conversion, design)",
        "Domain health check (active, SSL valid)",
        "Pixel firing check (events working)",
        "Keitaro stats check (redirects, filters)",
        "IP/Bot filter check",
        "Facebook Policy compliance check",
        "Backup domain check for all campaigns",
        "Landing page speed (Core Web Vitals)",
        "Update domain table (whitepage, UTM, pixel, offer domain)",
        "New offer checklist completion",
    ],
    "ReSell Team": [
        "Review today's customer contact list",
        "Check hold orders — prioritize",
        "Follow-up check (yesterday's callbacks)",
        "Contact existing customers (calls/messages)",
        "Update customer status (renewed/not interested/callback)",
        "Track daily renewal targets",
        "Mark dead leads",
        "Log best contact times per customer",
        "Daily recap (contacted, renewed, conversion %)",
        "Coordinate with Warehouse for hold order status",
    ],
    "Sales Team": [
        "Review new orders from Shopify/WooCommerce",
        "Contact customers on WhatsApp (order confirmation)",
        "Confirm payment method (COD or Card)",
        "Approve or reject all orders (no undefined!)",
        "Check hold orders — new sales",
        "Track response time on new orders",
        "Check unanswered orders",
        "Blacklist check for problematic customers",
        "Track peak order hours",
        "EOD recap (orders, confirmed, rejected, COD/Card, delivery rate)",
        "Update order sheet (commission tracking)",
    ],
    "Warehouse Team": [
        "Receive approved orders from New Sales/ReSell",
        "Print shipping labels",
        "Pack orders",
        "Check low stock items",
        "EOD inventory update (shipped, returned to stock)",
        "Log returned orders + reason",
        "Log damaged items",
        "Log courier split (per courier count)",
        "Report unfulfilled orders + reason",
        "EOD report (fulfilled vs unfulfilled)",
    ],
}

SUMMARY_QUESTIONS = {
    "Marketing Team": "📢 *Marketing Team Daily Summary*\n\nPlease share:\n• Total spend today\n• Total revenue\n• Best ROAS account\n• Any issues?",
    "ReSell Team": "🔄 *ReSell Team Daily Summary*\n\nPlease share:\n• Customers contacted\n• Renewals closed\n• Conversion rate\n• Hold orders status",
    "Sales Team": "💼 *Sales Team Daily Summary*\n\nPlease share:\n• New orders received\n• Confirmed orders\n• Rejected orders\n• COD vs Card split\n• Delivery rate",
    "Warehouse Team": "📦 *Warehouse Team Daily Summary*\n\nPlease share:\n• Orders packed & shipped\n• Unfulfilled orders\n• Returns received\n• Low stock alerts",
}

def load():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {"users": {}, "sessions": {}, "todos": {}, "daily": {}, "managers": [],
                "groups": [], "group_teams": {}, "group_names": {}, "meetings": [],
                "stats": {}, "stock": {}, "domains": []}

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def today():
    return datetime.now(TZ).strftime("%Y-%m-%d")

def now_zurich():
    return datetime.now(TZ)

def fmt_dur(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"

def get_user(data, uid):
    return data["users"].get(str(uid))

def is_manager(data, uid):
    return str(uid) in data.get("managers", [])

def is_weekday():
    return now_zurich().weekday() < 5

def get_today_sec(data, uid):
    u = data["users"].get(str(uid), {})
    sec = sum(s["duration_sec"] for s in data["sessions"].get(str(uid), []) if s["date"] == today())
    if u.get("clocked_in") and u.get("clock_start_ts"):
        sec += now_zurich().timestamp() - u["clock_start_ts"]
    return sec

def get_user_team(data, uid):
    user = data["users"].get(str(uid), {})
    return user.get("team", "")

def init_stats(data, uid):
    if str(uid) not in data.get("stats", {}):
        data.setdefault("stats", {})[str(uid)] = {}
    if today() not in data["stats"][str(uid)]:
        data["stats"][str(uid)][today()] = {}
    return data["stats"][str(uid)][today()]

# ─── BASIC COMMANDS ───────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🌐 Open TeamFlow Website", url=WEBSITE_URL)]]
    await update.message.reply_text(
        "👋 Welcome to *TeamFlow Scale Bot!*\n\n"
        "To get started: `/register Your Name`\n\n"
        "📋 *Member commands:*\n"
        "/clockin /clockout /status\n"
        "/tasks /addtask /daily /goals /report\n\n"
        "📊 *Team tracking:*\n"
        "/recap — Marketing recap\n"
        "/orders — New Sales orders\n"
        "/resell — ReSell stats\n"
        "/shipped — Warehouse shipped\n"
        "/newoffer — Safe Offers checklist\n\n"
        "📅 /meetings — Today's meetings\n"
        "🔐 /manager — Admin login",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def setup_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Groups only.")
        return
    data = load()
    chat_id = str(update.effective_chat.id)
    chat_name = update.effective_chat.title or "Unknown"
    if chat_id not in data.get("groups", []):
        data.setdefault("groups", []).append(chat_id)
        data.setdefault("group_names", {})[chat_id] = chat_name
        save(data)
        await update.message.reply_text(
            f"✅ *{chat_name}* registered!\n\n"
            f"• 🌅 Morning motivation (9:00)\n"
            f"• 📋 Daily summaries (14:00, Mon-Fri)\n"
            f"• 📊 Weekly reports (Sunday 16:00)\n\n"
            f"Admin: /setgroupteam to assign teams.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"✅ *{chat_name}* already registered!", parse_mode="Markdown")

async def set_group_team(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Groups only.")
        return
    keyboard = [[InlineKeyboardButton(t, callback_data=f"gteam_{update.effective_chat.id}_{t}")] for t in TEAMS]
    keyboard.append([InlineKeyboardButton("🌍 All Teams", callback_data=f"gteam_{update.effective_chat.id}_ALL")])
    await update.message.reply_text("Select team for this group:", reply_markup=InlineKeyboardMarkup(keyboard))

async def register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not ctx.args:
        await update.message.reply_text("❌ Type: `/register Your Name`", parse_mode="Markdown")
        return
    name = " ".join(ctx.args)
    if uid in data["users"]:
        await update.message.reply_text(f"✅ Already registered as *{data['users'][uid]['name']}*!", parse_mode="Markdown")
        return
    data["users"][uid] = {"name": name, "registered": today(), "clocked_in": False,
                          "clock_start": None, "clock_start_ts": None, "team": "", "goals": [], "goals_date": ""}
    data["sessions"][uid] = []
    data["todos"][uid] = []
    data["daily"][uid] = []
    save(data)
    keyboard = [[InlineKeyboardButton(t, callback_data=f"setteam_{t}")] for t in TEAMS]
    await update.message.reply_text(f"✅ Welcome, *{name}*! 🎉\n\n🏷 Select your team:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def clockin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered. Type `/register Your Name`", parse_mode="Markdown")
        return
    if user["clocked_in"]:
        await update.message.reply_text(f"⚠️ Already clocked in since *{user['clock_start']}*.", parse_mode="Markdown")
        return
    now = now_zurich()
    data["users"][uid].update({"clocked_in": True, "clock_start": now.strftime("%H:%M"), "clock_start_ts": now.timestamp()})
    save(data)
    await update.message.reply_text(
        f"▶️ *Clocked in!*\n\n👤 {user['name']}\n🕐 *{now.strftime('%H:%M')}* (Zurich)\n📅 {today()}\n\nGood work! 💪",
        parse_mode="Markdown"
    )

async def clockout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not user["clocked_in"]:
        await update.message.reply_text("⚠️ Not clocked in.", parse_mode="Markdown")
        return
    now = now_zurich()
    duration = now.timestamp() - user["clock_start_ts"]
    data["sessions"][uid].append({"date": today(), "start": user["clock_start"], "end": now.strftime("%H:%M"), "duration_sec": duration})
    data["users"][uid].update({"clocked_in": False, "clock_start": None, "clock_start_ts": None})
    save(data)
    await update.message.reply_text(
        f"■ *Clocked out!*\n\n👤 {user['name']}\n🕐 {user['clock_start']} → {now.strftime('%H:%M')}\n⏱ *{fmt_dur(duration)}*\n\nGreat work! 👋",
        parse_mode="Markdown"
    )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    today_sec = get_today_sec(data, uid)
    st = f"🟢 *Online* — since {user['clock_start']}" if user["clocked_in"] else "🔴 *Offline*"
    todos = data["todos"].get(uid, [])
    done = sum(1 for t in todos if t.get("done"))
    team = user.get("team", "No team")
    daily_list = data["daily"].get(uid, [])
    daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
    await update.message.reply_text(
        f"📊 *{user['name']}*\n🏷 {team}\n\n{st}\n"
        f"⏱ Today: *{fmt_dur(today_sec)}*\n"
        f"✅ Tasks: *{done}/{len(todos)}*\n"
        f"📋 Routines: *{daily_done}/{len(daily_list)}*",
        parse_mode="Markdown"
    )

async def tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    todos = data["todos"].get(uid, [])
    if not todos:
        await update.message.reply_text("📋 No tasks.\n\nAdd: `/addtask Task name`", parse_mode="Markdown")
        return
    pri = {"h": "🔴", "m": "🟡", "l": "🟢"}
    lines = [f"📋 *Tasks — {user['name']}*\n"]
    keyboard = []
    for i, t in enumerate(todos):
        check = "✅" if t.get("done") else "⬜"
        lines.append(f"{check} {pri.get(t.get('pri','m'),'🟡')} {t['text']}")
        keyboard.append([InlineKeyboardButton(f"{check} {t['text'][:35]}", callback_data=f"toggle_{i}")])
    keyboard.append([InlineKeyboardButton("🗑 Delete completed", callback_data="delete_done")])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def addtask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("❌ Type: `/addtask Task name #high/#medium/#low`", parse_mode="Markdown")
        return
    text = " ".join(ctx.args)
    pri = "m"
    if "#high" in text: pri = "h"; text = text.replace("#high", "").strip()
    elif "#low" in text: pri = "l"; text = text.replace("#low", "").strip()
    elif "#medium" in text: text = text.replace("#medium", "").strip()
    data["todos"][uid].append({"text": text, "pri": pri, "done": False, "created": today()})
    save(data)
    pri_txt = {"h": "🔴 High", "m": "🟡 Medium", "l": "🟢 Low"}
    await update.message.reply_text(f"✅ Task added: *{text}*\n{pri_txt[pri]}", parse_mode="Markdown")

async def goals_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if ctx.args:
        goal = " ".join(ctx.args)
        if data["users"][uid].get("goals_date") != today():
            data["users"][uid]["goals"] = []
            data["users"][uid]["goals_date"] = today()
        data["users"][uid].setdefault("goals", []).append(goal)
        save(data)
        await update.message.reply_text(f"🎯 Goal set: *{goal}* 💪", parse_mode="Markdown")
    else:
        goals = data["users"][uid].get("goals", []) if data["users"][uid].get("goals_date") == today() else []
        if not goals:
            await update.message.reply_text("🎯 No goals today.\n\nSet one: `/goals Your goal`", parse_mode="Markdown")
        else:
            lines = ["🎯 *Today's Goals*\n"] + [f"• {g}" for g in goals]
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def daily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    team = user.get("team", "")
    daily_list = data["daily"].get(uid, [])

    # Auto-populate from team routines if empty
    if not daily_list and team in DAILY_ROUTINES:
        for routine in DAILY_ROUTINES[team]:
            daily_list.append({"text": routine, "done_date": None})
        data["daily"][uid] = daily_list
        save(data)

    if not daily_list:
        await update.message.reply_text("📋 No routines.\n\nAdd: `/adddaily Routine name`", parse_mode="Markdown")
        return

    t = today()
    done = sum(1 for d in daily_list if d.get("done_date") == t)
    pct = int(done / len(daily_list) * 100)
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    lines = [f"📋 *Daily Routines — {user['name']}*\n🏷 {team}\n`{bar}` {pct}%\n"]
    keyboard = []
    for i, d in enumerate(daily_list):
        check = "✅" if d.get("done_date") == t else "⬜"
        lines.append(f"{check} {d['text']}")
        keyboard.append([InlineKeyboardButton(f"{check} {d['text'][:35]}", callback_data=f"daily_{i}")])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def adddaily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("❌ Type: `/adddaily Routine name`", parse_mode="Markdown")
        return
    text = " ".join(ctx.args)
    data["daily"][uid].append({"text": text, "done_date": None})
    save(data)
    await update.message.reply_text(f"✅ Routine added: *{text}*", parse_mode="Markdown")

async def report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    sessions = data["sessions"].get(uid, [])
    today_sec = get_today_sec(data, uid)
    week_sec = sum(s["duration_sec"] for s in sessions if s["date"] >= (now_zurich() - timedelta(days=7)).strftime("%Y-%m-%d"))
    total_sec = sum(s["duration_sec"] for s in sessions)
    todos = data["todos"].get(uid, [])
    done_tasks = sum(1 for t in todos if t.get("done"))
    daily_list = data["daily"].get(uid, [])
    daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
    team_stats = data.get("stats", {}).get(uid, {}).get(today(), {})
    stats_lines = ""
    if team_stats:
        stats_lines = "\n\n📊 *Today's Stats:*\n" + "\n".join([f"• {k}: {v}" for k, v in team_stats.items()])
    await update.message.reply_text(
        f"📊 *Report — {user['name']}*\n🏷 {user.get('team','')}\n📅 {today()}\n\n"
        f"⏱ Today: {fmt_dur(today_sec)}\n⏱ This week: {fmt_dur(week_sec)}\n⏱ Total: {fmt_dur(total_sec)}\n\n"
        f"✅ Tasks: {done_tasks}/{len(todos)}\n📋 Routines: {daily_done}/{len(daily_list)}{stats_lines}",
        parse_mode="Markdown"
    )

# ─── TEAM TRACKING COMMANDS ───────────────────────────────────────────────────

async def recap_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Marketing Team: /recap [spend] [revenue] [roas] [account_name]"""
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text(
            "📊 *Marketing Recap*\n\nUsage:\n`/recap [spend€] [revenue€] [roas] [account]`\n\nExample:\n`/recap 500 2000 4.0 AccountX`",
            parse_mode="Markdown"
        )
        return
    spend = ctx.args[0].replace("€","").replace("eur","")
    revenue = ctx.args[1].replace("€","").replace("eur","")
    roas = ctx.args[2]
    account = " ".join(ctx.args[3:]) if len(ctx.args) > 3 else "General"
    stats = init_stats(data, uid)
    stats["spend"] = f"{spend}€"
    stats["revenue"] = f"{revenue}€"
    stats["roas"] = roas
    stats["account"] = account
    save(data)
    msg = (
        f"📢 *Marketing Recap — {today()}*\n"
        f"👤 {user['name']}\n\n"
        f"📱 Account: *{account}*\n"
        f"💸 Spend: *{spend}€*\n"
        f"💰 Revenue: *{revenue}€*\n"
        f"📈 ROAS: *{roas}*\n\n"
        f"🌐 [TeamFlow Dashboard]({WEBSITE_URL})"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    # Send to groups
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def orders_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sales Team: /orders [total] [confirmed] [rejected] [cod] [card]"""
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text(
            "💼 *New Sales Orders*\n\nUsage:\n`/orders [total] [confirmed] [rejected] [cod] [card]`\n\nExample:\n`/orders 45 38 7 25 13`",
            parse_mode="Markdown"
        )
        return
    total = ctx.args[0]
    confirmed = ctx.args[1]
    rejected = ctx.args[2]
    cod = ctx.args[3] if len(ctx.args) > 3 else "—"
    card = ctx.args[4] if len(ctx.args) > 4 else "—"
    try:
        conf_rate = round(int(confirmed)/int(total)*100, 1)
    except:
        conf_rate = "—"
    stats = init_stats(data, uid)
    stats.update({"total_orders": total, "confirmed": confirmed, "rejected": rejected, "cod": cod, "card": card, "confirm_rate": f"{conf_rate}%"})
    save(data)
    msg = (
        f"💼 *New Sales Report — {today()}*\n"
        f"👤 {user['name']}\n\n"
        f"📦 Total orders: *{total}*\n"
        f"✅ Confirmed: *{confirmed}* ({conf_rate}%)\n"
        f"❌ Rejected: *{rejected}*\n"
        f"💵 COD: *{cod}* | 💳 Card: *{card}*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def resell_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ReSell Team: /resell [contacted] [renewed] [revenue]"""
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text(
            "🔄 *ReSell Stats*\n\nUsage:\n`/resell [contacted] [renewed] [revenue€]`\n\nExample:\n`/resell 45 12 2400`",
            parse_mode="Markdown"
        )
        return
    contacted = ctx.args[0]
    renewed = ctx.args[1]
    revenue = ctx.args[2].replace("€","") if len(ctx.args) > 2 else "—"
    try:
        conv_rate = round(int(renewed)/int(contacted)*100, 1)
    except:
        conv_rate = "—"
    stats = init_stats(data, uid)
    stats.update({"contacted": contacted, "renewed": renewed, "revenue": f"{revenue}€", "conversion": f"{conv_rate}%"})
    save(data)
    msg = (
        f"🔄 *ReSell Report — {today()}*\n"
        f"👤 {user['name']}\n\n"
        f"📞 Contacted: *{contacted}*\n"
        f"✅ Renewed: *{renewed}*\n"
        f"📈 Conversion: *{conv_rate}%*\n"
        f"💰 Revenue: *{revenue}€*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def shipped_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Warehouse Team: /shipped [shipped] [returned] [unfulfilled]"""
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text(
            "📦 *Warehouse Report*\n\nUsage:\n`/shipped [shipped] [returned] [unfulfilled]`\n\nExample:\n`/shipped 85 5 3`",
            parse_mode="Markdown"
        )
        return
    shipped = ctx.args[0]
    returned = ctx.args[1] if len(ctx.args) > 1 else "0"
    unfulfilled = ctx.args[2] if len(ctx.args) > 2 else "0"
    stats = init_stats(data, uid)
    stats.update({"shipped": shipped, "returned": returned, "unfulfilled": unfulfilled})
    save(data)
    msg = (
        f"📦 *Warehouse Report — {today()}*\n"
        f"👤 {user['name']}\n\n"
        f"✅ Shipped: *{shipped}*\n"
        f"🔙 Returned: *{returned}*\n"
        f"⚠️ Unfulfilled: *{unfulfilled}*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def stock_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Warehouse: /stock [product] [quantity]"""
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 2:
        stock = data.get("stock", {})
        if not stock:
            await update.message.reply_text("📦 No stock items.\n\nAdd: `/stock ProductName 50`", parse_mode="Markdown")
            return
        lines = ["📦 *Current Stock:*\n"]
        for product, qty in stock.items():
            emoji = "🔴" if int(qty) < 10 else "🟡" if int(qty) < 30 else "🟢"
            lines.append(f"{emoji} {product}: *{qty}* units")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return
    product = ctx.args[0]
    qty = ctx.args[1]
    data.setdefault("stock", {})[product] = qty
    save(data)
    emoji = "🔴" if int(qty) < 10 else "🟡" if int(qty) < 30 else "🟢"
    await update.message.reply_text(f"📦 Stock updated:\n{emoji} *{product}*: {qty} units", parse_mode="Markdown")
    if int(qty) < 10:
        alert = f"🚨 *LOW STOCK ALERT!*\n\n📦 {product}: only *{qty}* units left!\n\n⚠️ Reorder needed!"
        for mgr_uid in data.get("managers", []):
            try:
                await ctx.bot.send_message(chat_id=int(mgr_uid), text=alert, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Could not DM manager: {e}")

async def newoffer_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Safe Offers: /newoffer [brand_name] — shows checklist"""
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    brand = " ".join(ctx.args) if ctx.args else "New Offer"
    checklist = [
        "White Page created & tested",
        "Cloaking configured in Keitaro",
        "Offer Page ready & converting",
        "Domain health check passed (SSL ✅)",
        "Pixel firing correctly",
        "UTM parameters set",
        "IP/Bot filters active",
        "Facebook Policy compliant",
        "Backup domain ready",
        "Landing page speed OK",
        "Domain table updated",
        "Marketing Team notified ✅"
    ]
    offer_key = f"offer_{brand.replace(' ','_')}_{today()}"
    data.setdefault("offers", {})[offer_key] = {"brand": brand, "date": today(), "user": uid, "checklist": [False] * len(checklist)}
    save(data)
    keyboard = []
    for i, item in enumerate(checklist):
        keyboard.append([InlineKeyboardButton(f"⬜ {item}", callback_data=f"offer_{offer_key}_{i}")])
    await update.message.reply_text(
        f"🎯 *New Offer Checklist — {brand}*\n\nComplete all steps before handing to Marketing Team:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def checklinks_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Marketing/Safe Offers: /checklinks — checks all registered domains"""
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    domains = data.get("domains", [])
    if not domains:
        await update.message.reply_text(
            "🌐 No domains registered.\n\nAdd: `/adddomain https://example.com Brand`",
            parse_mode="Markdown"
        )
        return
    await update.message.reply_text(f"🔍 Checking {len(domains)} domains...", parse_mode="Markdown")
    results = []
    async with aiohttp.ClientSession() as session:
        for d in domains:
            url = d.get("url", "")
            brand = d.get("brand", url)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as resp:
                    if resp.status == 200:
                        results.append(f"✅ *{brand}* — OK ({resp.status})")
                    else:
                        results.append(f"⚠️ *{brand}* — Status {resp.status}")
            except Exception:
                results.append(f"🔴 *{brand}* — UNREACHABLE ❌")
    msg = f"🌐 *Link Check Results — {today()}*\n\n" + "\n".join(results)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def adddomain_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Add domain for link checking: /adddomain https://url.com BrandName"""
    data = load()
    uid = str(update.effective_user.id)
    if not ctx.args or len(ctx.args) < 1:
        await update.message.reply_text("❌ Type: `/adddomain https://url.com BrandName`", parse_mode="Markdown")
        return
    url = ctx.args[0]
    brand = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else url
    data.setdefault("domains", []).append({"url": url, "brand": brand, "added": today()})
    save(data)
    await update.message.reply_text(f"✅ Domain added: *{brand}*\n🌐 {url}", parse_mode="Markdown")

async def delivery_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """New Sales: /delivery [rate%]"""
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("❌ Type: `/delivery 92` (delivery rate %)", parse_mode="Markdown")
        return
    rate = ctx.args[0].replace("%","")
    stats = init_stats(data, uid)
    stats["delivery_rate"] = f"{rate}%"
    save(data)
    emoji = "🟢" if int(rate) >= 90 else "🟡" if int(rate) >= 75 else "🔴"
    await update.message.reply_text(f"🚚 Delivery rate logged: {emoji} *{rate}%*", parse_mode="Markdown")

# ─── MANAGER COMMANDS ────────────────────────────────────────────────────────

async def manager_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not ctx.args or ctx.args[0] != MANAGER_PASSWORD:
        await update.message.reply_text("🔐 Type: `/manager PASSWORD`", parse_mode="Markdown")
        return
    data = load()
    if uid not in data.get("managers", []):
        data.setdefault("managers", []).append(uid)
        save(data)
    await update.message.reply_text(
        "✅ *Admin access granted!*\n\n"
        "/teamstatus — Live team status\n"
        "/teamreport — Weekly report\n"
        "/timelog — Time log\n"
        "/dailystats — Today's team stats\n"
        "/listgroups — Registered groups\n"
        "/meeting — Manage meetings",
        parse_mode="Markdown"
    )

async def teamstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ No admin access.", parse_mode="Markdown")
        return
    if not data["users"]:
        await update.message.reply_text("👥 No members yet.", parse_mode="Markdown")
        return
    online = sum(1 for u in data["users"].values() if u.get("clocked_in"))
    lines = [f"👥 *Team Status — {today()}*\n🟢 Online: {online}/{len(data['users'])}\n"]
    for uid_m, user in data["users"].items():
        is_on = user.get("clocked_in", False)
        sec = get_today_sec(data, uid_m)
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        daily_list = data["daily"].get(uid_m, [])
        daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
        icon = "🟢" if is_on else "🔴"
        lines.append(f"{icon} *{user['name']}* — {user.get('team','')}\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)} | 📋 {daily_done}/{len(daily_list)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def daily_stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Manager: see all team stats for today"""
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ No admin access.", parse_mode="Markdown")
        return
    lines = [f"📊 *Daily Stats — {today()}*\n"]
    found = False
    for uid_m, user in data["users"].items():
        stats = data.get("stats", {}).get(uid_m, {}).get(today(), {})
        if stats:
            found = True
            lines.append(f"👤 *{user['name']}* — {user.get('team','')}")
            for k, v in stats.items():
                lines.append(f"   • {k}: {v}")
    if not found:
        lines.append("No stats logged today yet.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def teamreport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ No admin access.", parse_mode="Markdown")
        return
    week_ago = (now_zurich() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [f"📊 *Weekly Team Report*\n📅 {week_ago} → {today()}\n"]
    total = 0
    for uid_m, user in data["users"].items():
        sec = sum(s["duration_sec"] for s in data["sessions"].get(uid_m, []) if s["date"] >= week_ago)
        total += sec
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        pct = f"{int(done/len(todos)*100)}%" if todos else "—"
        lines.append(f"👤 *{user['name']}* — {user.get('team','')}\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)} ({pct})")
    lines.append(f"\n⏱ *Total team: {fmt_dur(total)}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def timelog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ No admin access.", parse_mode="Markdown")
        return
    lines = [f"⏱ *Time Log — {today()}*\n"]
    found = False
    for uid_m, user in data["users"].items():
        sessions = [s for s in data["sessions"].get(uid_m, []) if s["date"] == today()]
        if user.get("clocked_in") and user.get("clock_start_ts"):
            sessions.append({"start": user["clock_start"], "end": "● now", "duration_sec": now_zurich().timestamp() - user["clock_start_ts"]})
        if sessions:
            found = True
            lines.append(f"👤 *{user['name']}* — {user.get('team','')}")
            for s in sessions:
                lines.append(f"   {s['start']} → {s['end']} | {fmt_dur(s['duration_sec'])}")
    if not found:
        lines.append("No sessions today.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def list_groups(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ No admin access.", parse_mode="Markdown")
        return
    groups = data.get("groups", [])
    if not groups:
        await update.message.reply_text("No groups registered.", parse_mode="Markdown")
        return
    lines = ["📋 *Registered Groups:*\n"]
    for gid in groups:
        lines.append(f"• *{data.get('group_names',{}).get(gid,gid)}* — {data.get('group_teams',{}).get(gid,'All')}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def meeting_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Managers only.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text(
            "📅 *Meeting commands:*\n\n"
            "`/meeting 14:00 Sales Call` — Add\n"
            "`/meeting list` — Today's list\n"
            "`/meeting delete 1` — Delete",
            parse_mode="Markdown"
        )
        return
    if ctx.args[0].lower() == "list":
        meetings = [m for m in data.get("meetings", []) if m.get("date") == today()]
        if not meetings:
            await update.message.reply_text("📅 No meetings today.", parse_mode="Markdown")
            return
        lines = ["📅 *Today's Meetings:*\n"]
        for i, m in enumerate(sorted(meetings, key=lambda x: x["time"])):
            lines.append(f"{i+1}. 🕐 *{m['time']}* — {m['title']}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return
    if ctx.args[0].lower() == "delete" and len(ctx.args) > 1:
        try:
            idx = int(ctx.args[1]) - 1
            meetings = data.get("meetings", [])
            if 0 <= idx < len(meetings):
                removed = meetings.pop(idx)
                data["meetings"] = meetings
                save(data)
                await update.message.reply_text(f"🗑 Deleted: *{removed['title']}*", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Type: `/meeting delete 1`", parse_mode="Markdown")
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("❌ Type: `/meeting 14:00 Title`", parse_mode="Markdown")
        return
    time_str = ctx.args[0]
    title = " ".join(ctx.args[1:])
    try:
        datetime.strptime(time_str, "%H:%M")
    except:
        await update.message.reply_text("❌ Time must be HH:MM", parse_mode="Markdown")
        return
    data.setdefault("meetings", []).append({"time": time_str, "title": title, "date": today()})
    save(data)
    meet_h, meet_m = int(time_str.split(":")[0]), int(time_str.split(":")[1])
    meet_time = now_zurich().replace(hour=meet_h, minute=meet_m, second=0, microsecond=0)
    remind_time = meet_time - timedelta(minutes=30)
    reminder_msg = ""
    if remind_time > now_zurich():
        delay = (remind_time - now_zurich()).total_seconds()
        t_copy, time_copy = title, time_str
        async def reminder(c):
            msg = f"⏰ *Meeting in 30 minutes!*\n\n📋 *{t_copy}*\n🕐 Starting at *{time_copy}* (Zurich)\n\nGet ready! 🚀"
            d = load()
            for gid in d.get("groups", []):
                try:
                    await c.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
                except: pass
        ctx.application.job_queue.run_once(reminder, when=delay)
        reminder_msg = f"\n⏰ Reminder at *{remind_time.strftime('%H:%M')}*"
    await update.message.reply_text(f"✅ Meeting added!\n\n🕐 *{time_str}* — {title}{reminder_msg}", parse_mode="Markdown")

async def meetings_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    meetings = [m for m in data.get("meetings", []) if m.get("date") == today()]
    if not meetings:
        await update.message.reply_text("📅 No meetings today.", parse_mode="Markdown")
        return
    lines = ["📅 *Today's Meetings:*\n"]
    for m in sorted(meetings, key=lambda x: x["time"]):
        lines.append(f"🕐 *{m['time']}* — {m['title']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── CALLBACKS ───────────────────────────────────────────────────────────────

async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load()
    uid = str(query.from_user.id)

    if query.data.startswith("setteam_"):
        team = query.data.replace("setteam_", "")
        if uid in data["users"]:
            data["users"][uid]["team"] = team
            # Auto-populate daily routines
            if team in DAILY_ROUTINES:
                data["daily"][uid] = [{"text": r, "done_date": None} for r in DAILY_ROUTINES[team]]
            save(data)
            await query.edit_message_text(
                f"✅ Team set to *{team}*!\n\n"
                f"📋 Your daily routines have been loaded automatically.\n"
                f"Type `/daily` to see them.\n\n"
                f"Type `/clockin` to start! 🚀",
                parse_mode="Markdown"
            )
        return

    if query.data.startswith("gteam_"):
        parts = query.data.split("_", 2)
        chat_id, team = parts[1], parts[2]
        data.setdefault("group_teams", {})[chat_id] = team
        save(data)
        await query.edit_message_text(f"✅ Group assigned to *{team}*!", parse_mode="Markdown")
        return

    if query.data.startswith("offer_"):
        parts = query.data.split("_", 3)
        if len(parts) >= 4:
            offer_key = parts[1] + "_" + parts[2]
            idx = int(parts[3])
            offers = data.get("offers", {})
            if offer_key in offers:
                checklist = offers[offer_key]["checklist"]
                checklist[idx] = not checklist[idx]
                data["offers"][offer_key]["checklist"] = checklist
                save(data)
                done = sum(checklist)
                total = len(checklist)
                if done == total:
                    await query.edit_message_text(
                        f"🎉 *Offer Ready!* — {offers[offer_key]['brand']}\n\n✅ All {total} steps completed!\n\nNotify Marketing Team to start campaigns! 🚀",
                        parse_mode="Markdown"
                    )
                else:
                    await query.answer(f"✅ {done}/{total} steps done")
        return

    if query.data.startswith("toggle_"):
        idx = int(query.data.split("_")[1])
        todos = data["todos"].get(uid, [])
        if idx < len(todos):
            todos[idx]["done"] = not todos[idx]["done"]
            save(data)
            s = "✅ Done" if todos[idx]["done"] else "⬜ Undone"
            await query.edit_message_text(f"{s}: *{todos[idx]['text']}*\n\nType /tasks for list.", parse_mode="Markdown")
    elif query.data == "delete_done":
        before = len(data["todos"].get(uid, []))
        data["todos"][uid] = [t for t in data["todos"].get(uid, []) if not t.get("done")]
        deleted = before - len(data["todos"][uid])
        save(data)
        await query.edit_message_text(f"🗑 Deleted {deleted} completed tasks.")
    elif query.data.startswith("daily_"):
        idx = int(query.data.split("_")[1])
        daily_list = data["daily"].get(uid, [])
        if idx < len(daily_list):
            daily_list[idx]["done_date"] = None if daily_list[idx].get("done_date") == today() else today()
            save(data)
            done = sum(1 for d in daily_list if d.get("done_date") == today())
            await query.answer(f"📋 {done}/{len(daily_list)} done today")

# ─── SCHEDULED JOBS ──────────────────────────────────────────────────────────

async def job_morning_motivation(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    import random
    motivation = random.choice(MOTIVATIONS)
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=f"{motivation}\n\n☀️ *New day, new goals — let's go team!*", parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def job_morning_meetings(ctx: ContextTypes.DEFAULT_TYPE):
    """8:30 — Post today's meetings in group"""
    if not is_weekday(): return
    data = load()
    meetings = [m for m in data.get("meetings", []) if m.get("date") == today()]
    if not meetings: return
    lines = ["📅 *Today's Meetings:*\n"]
    for m in sorted(meetings, key=lambda x: x["time"]):
        lines.append(f"🕐 *{m['time']}* — {m['title']}")
    msg = "\n".join(lines)
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def job_clockin_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    for uid, user in data["users"].items():
        if not user.get("clocked_in"):
            today_sessions = [s for s in data["sessions"].get(uid, []) if s["date"] == today()]
            if not today_sessions:
                try:
                    await ctx.bot.send_message(chat_id=int(uid), text=f"⏰ Hey *{user['name']}*, you haven't clocked in yet!\n\nType `/clockin` to start. 💪", parse_mode="Markdown")
                except Exception as e:
                    logger.warning(f"DM error: {e}")

async def job_manager_late_alert(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    late = []
    for uid, user in data["users"].items():
        if not user.get("clocked_in"):
            if not [s for s in data["sessions"].get(uid, []) if s["date"] == today()]:
                late.append(f"• {user['name']} — {user.get('team','')}")
    if late:
        msg = f"🚨 *Late Alert — 10:30*\n\nNot clocked in yet:\n\n" + "\n".join(late)
        for mgr_uid in data.get("managers", []):
            try:
                await ctx.bot.send_message(chat_id=int(mgr_uid), text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Manager DM error: {e}")

async def job_daily_summary_groups(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    for gid in data.get("groups", []):
        assigned_team = data.get("group_teams", {}).get(gid, "ALL")
        teams_to_post = SUMMARY_TEAMS if assigned_team == "ALL" else ([assigned_team] if assigned_team in SUMMARY_TEAMS else [])
        for team in teams_to_post:
            question = SUMMARY_QUESTIONS.get(team, f"📋 *{team} Daily Summary*\n\nPlease share your update!")
            try:
                await ctx.bot.send_message(chat_id=int(gid), text=question, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Group error: {e}")

async def job_overdue_tasks(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    for uid, user in data["users"].items():
        todos = data["todos"].get(uid, [])
        overdue = [t for t in todos if not t.get("done") and t.get("pri") == "h"]
        if overdue:
            task_list = "\n".join([f"• 🔴 {t['text']}" for t in overdue[:5]])
            try:
                await ctx.bot.send_message(chat_id=int(uid), text=f"⚠️ *{user['name']}*, *{len(overdue)}* high priority task(s) pending:\n\n{task_list}\n\nType `/tasks` to manage! 💪", parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"DM error: {e}")

async def job_eod_personal_summary(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    for uid, user in data["users"].items():
        today_sec = get_today_sec(data, uid)
        todos = data["todos"].get(uid, [])
        done_tasks = sum(1 for t in todos if t.get("done"))
        daily_list = data["daily"].get(uid, [])
        daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
        goals = user.get("goals", []) if user.get("goals_date") == today() else []
        goals_txt = "\n".join([f"• {g}" for g in goals]) if goals else "No goals set today"
        stats = data.get("stats", {}).get(uid, {}).get(today(), {})
        stats_txt = "\n".join([f"• {k}: {v}" for k, v in stats.items()]) if stats else "No stats logged"
        try:
            await ctx.bot.send_message(
                chat_id=int(uid),
                text=f"🌆 *End of Day — {user['name']}*\n📅 {today()}\n\n"
                     f"⏱ *{fmt_dur(today_sec)}* worked\n"
                     f"✅ Tasks: *{done_tasks}/{len(todos)}*\n"
                     f"📋 Routines: *{daily_done}/{len(daily_list)}*\n\n"
                     f"🎯 *Goals:*\n{goals_txt}\n\n"
                     f"📊 *Stats:*\n{stats_txt}\n\n"
                     f"Don't forget `/clockout` if still working! 👋",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"DM error: {e}")

async def job_clockout_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    for uid, user in data["users"].items():
        if user.get("clocked_in"):
            try:
                await ctx.bot.send_message(chat_id=int(uid), text=f"🔔 *{user['name']}*, still clocked in!\n\n🕐 Since: {user['clock_start']}\n\nType `/clockout`! 👋", parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"DM error: {e}")

async def job_manager_daily_digest(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    if not data["users"]: return
    online = sum(1 for u in data["users"].values() if u.get("clocked_in"))
    total_sec = sum(get_today_sec(data, uid) for uid in data["users"])
    total_tasks = sum(len(data["todos"].get(uid, [])) for uid in data["users"])
    done_tasks = sum(sum(1 for t in data["todos"].get(uid, []) if t.get("done")) for uid in data["users"])
    lines = [
        f"📊 *Daily Manager Digest — {today()}*\n",
        f"👥 {len(data['users'])} members | 🟢 {online} still online",
        f"⏱ Total hours: *{fmt_dur(total_sec)}*",
        f"✅ Tasks: *{done_tasks}/{total_tasks}*\n",
        "*Individual:*"
    ]
    for uid, user in data["users"].items():
        sec = get_today_sec(data, uid)
        todos = data["todos"].get(uid, [])
        done = sum(1 for t in todos if t.get("done"))
        daily_list = data["daily"].get(uid, [])
        daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
        is_on = "🟢" if user.get("clocked_in") else "🔴"
        lines.append(f"{is_on} *{user['name']}* — {user.get('team','')}")
        lines.append(f"   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)} | 📋 {daily_done}/{len(daily_list)}")
        stats = data.get("stats", {}).get(uid, {}).get(today(), {})
        if stats:
            for k, v in stats.items():
                lines.append(f"   📊 {k}: {v}")
    msg = "\n".join(lines)
    for mgr_uid in data.get("managers", []):
        try:
            await ctx.bot.send_message(chat_id=int(mgr_uid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Manager DM error: {e}")

async def job_weekly_personal_report(ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    week_ago = (now_zurich() - timedelta(days=7)).strftime("%Y-%m-%d")
    for uid, user in data["users"].items():
        week_sec = sum(s["duration_sec"] for s in data["sessions"].get(uid, []) if s["date"] >= week_ago)
        todos = data["todos"].get(uid, [])
        done = sum(1 for t in todos if t.get("done"))
        try:
            await ctx.bot.send_message(
                chat_id=int(uid),
                text=f"📅 *Weekly Recap — {user['name']}*\n🏷 {user.get('team','')}\n\n"
                     f"⏱ Hours last week: *{fmt_dur(week_sec)}*\n"
                     f"✅ Tasks completed: *{done}/{len(todos)}*\n\n"
                     f"New week, new goals! 🚀\n`/goals Your goal this week`",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"DM error: {e}")

async def job_weekly_report_groups(ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    week_ago = (now_zurich() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [f"📊 *Weekly Team Report*\n📅 {week_ago} → {today()}\n"]
    total = 0
    for uid_m, user in data["users"].items():
        sec = sum(s["duration_sec"] for s in data["sessions"].get(uid_m, []) if s["date"] >= week_ago)
        total += sec
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        pct = f"{int(done/len(todos)*100)}%" if todos else "—"
        lines.append(f"👤 *{user['name']}* — {user.get('team','')}\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)} ({pct})")
    lines.append(f"\n⏱ *Total team: {fmt_dur(total)}*")
    msg = "\n".join(lines)
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")
    for mgr_uid in data.get("managers", []):
        try:
            await ctx.bot.send_message(chat_id=int(mgr_uid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Manager DM error: {e}")

async def job_warehouse_monday_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    """Monday 15:30 — Warehouse weekly call reminder"""
    data = load()
    msg = "📦 *Warehouse Weekly Call in 30 minutes!*\n\n🕐 16:00 (Zurich)\n\n📋 Prepare:\n• Last week stock summary\n• Items below minimum\n• 30-day order quantity\n• Returns & damages\n\nGet ready! 🚀"
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")
    for uid, user in data["users"].items():
        if user.get("team") == "Warehouse Team":
            try:
                await ctx.bot.send_message(chat_id=int(uid), text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"DM error: {e}")

# ─── MAIN ────────────────────────────────────────────────────────────────────

async def run():
    app = Application.builder().token(TOKEN).build()

    # Member commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("clockin", clockin))
    app.add_handler(CommandHandler("clockout", clockout))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("adddaily", adddaily))
    app.add_handler(CommandHandler("goals", goals_cmd))
    app.add_handler(CommandHandler("report", report))

    # Team tracking
    app.add_handler(CommandHandler("recap", recap_cmd))
    app.add_handler(CommandHandler("orders", orders_cmd))
    app.add_handler(CommandHandler("resell", resell_cmd))
    app.add_handler(CommandHandler("shipped", shipped_cmd))
    app.add_handler(CommandHandler("stock", stock_cmd))
    app.add_handler(CommandHandler("newoffer", newoffer_cmd))
    app.add_handler(CommandHandler("checklinks", checklinks_cmd))
    app.add_handler(CommandHandler("adddomain", adddomain_cmd))
    app.add_handler(CommandHandler("delivery", delivery_cmd))

    # Meetings
    app.add_handler(CommandHandler("meeting", meeting_cmd))
    app.add_handler(CommandHandler("meetings", meetings_today))

    # Manager
    app.add_handler(CommandHandler("manager", manager_login))
    app.add_handler(CommandHandler("teamstatus", teamstatus))
    app.add_handler(CommandHandler("teamreport", teamreport))
    app.add_handler(CommandHandler("timelog", timelog))
    app.add_handler(CommandHandler("dailystats", daily_stats_cmd))
    app.add_handler(CommandHandler("listgroups", list_groups))

    # Group setup
    app.add_handler(CommandHandler("setup", setup_group))
    app.add_handler(CommandHandler("setgroupteam", set_group_team))

    app.add_handler(CallbackQueryHandler(button_callback))

    # Scheduled jobs
    jq = app.job_queue
    jq.run_daily(job_morning_motivation,      time=datetime.strptime("09:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_morning_meetings,        time=datetime.strptime("08:30", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_clockin_reminder,        time=datetime.strptime("10:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_manager_late_alert,      time=datetime.strptime("10:30", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_daily_summary_groups,    time=datetime.strptime("14:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_overdue_tasks,           time=datetime.strptime("16:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_eod_personal_summary,    time=datetime.strptime("17:30", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_clockout_reminder,       time=datetime.strptime("18:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_manager_daily_digest,    time=datetime.strptime("18:30", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_weekly_personal_report,  time=datetime.strptime("08:00", "%H:%M").replace(tzinfo=TZ).timetz(), days=(0,))
    jq.run_daily(job_weekly_report_groups,    time=datetime.strptime("16:00", "%H:%M").replace(tzinfo=TZ).timetz(), days=(6,))
    jq.run_daily(job_warehouse_monday_reminder, time=datetime.strptime("15:30", "%H:%M").replace(tzinfo=TZ).timetz(), days=(0,))

    print("✅ TeamFlow bot started with all scheduled jobs!")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run())
