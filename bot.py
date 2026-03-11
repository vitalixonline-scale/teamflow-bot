import os
import json
import logging
import asyncio
import aiohttp
import requests
from datetime import datetime, timedelta
import pytz
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── CONFIG ─────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN", "8774731842:AAHHHaVy-X3LFYFQa-kRWBBcrkiSzb23NVw")
MANAGER_PASSWORD = os.environ.get("MANAGER_PASSWORD", "admin1234")
DATA_FILE = "data.json"
WEBSITE_URL = "https://vitalixonline-scale.github.io/teamflow-website"
TZ = pytz.timezone("Europe/Zurich")

TEAMS = ["Marketing Team", "Safe Offers Team", "ReSell Team", "Sales Team", "Warehouse Team"]
BRAND_TARGETS = {"VSmedic": 5000, "Vitalix IT": 5000, "Vitalix EU": 0}
ROAS_MINIMUM = 3.5

DAILY_ROUTINES = {
    "Marketing Team": ["Ad account health check","Budget check per ad account","Website/landing page check","Launch campaigns on META","Create new creatives","Identify winning ads (best ROAS)","Scaling check","Morning recap (spend, revenue, ROAS)","Daily targets check per brand","Pixel firing check","Keitaro stats check","Backup domain check"],
    "Safe Offers Team": ["White Page setup & test","Cloaking setup & test","Offer Page check","Domain health check (SSL)","Pixel firing check","Keitaro stats check","IP/Bot filter check","Facebook Policy check","Backup domain check","Update domain table","New offer checklist"],
    "ReSell Team": ["Review contact list","Check hold orders","Follow-up callbacks","Contact existing customers","Update customer status","Track daily renewal targets","Daily recap"],
    "Sales Team": ["Review new orders","Contact customers on WhatsApp","Confirm payment (COD or Card)","Approve or reject orders","Check hold orders","EOD recap"],
    "Warehouse Team": ["Receive approved orders","Print shipping labels","Pack orders","Check low stock items","EOD inventory update","Log returned orders","Report unfulfilled orders"],
}

OFFER_CHECKLIST = [
    "White Page created & tested", "Cloaking configured in Keitaro", "Offer Page ready",
    "Domain health check passed (SSL)", "Pixel firing correctly", "UTM parameters set",
    "IP/Bot filters active", "Facebook Policy compliant", "Backup domain ready",
    "Landing page speed OK", "Domain table updated", "Marketing Team notified"
]

MOTIVATIONS = [
    "🔥 *Today is your day — make it count!*",
    "💪 *Champions show up every day. Be a champion!*",
    "🚀 *Small actions daily = big results monthly!*",
    "⚡ *Your competition is working right now. Are you?*",
    "🎯 *Focus. Execute. Win. That's the formula!*",
]

SUMMARY_QUESTIONS = {
    "Marketing Team": "📊 *Marketing Team — Daily Update*\n\n💰 Spend today?\n📈 Revenue today?\n📊 ROAS?\n🎯 Best performing ad?",
    "Safe Offers Team": "🛡️ *Safe Offers — Daily Update*\n\n🌐 Domains checked?\n🔗 New offers live?\n⚠️ Any issues?",
    "ReSell Team": "🔄 *ReSell Team — Daily Update*\n\n📞 Contacts made?\n✅ Renewals today?\n💰 Revenue?",
    "Sales Team": "💼 *Sales Team — Daily Update*\n\n📦 Orders total?\n✅ Confirmed?\n❌ Rejected?\n🚚 Delivery rate?",
    "Warehouse Team": "📦 *Warehouse — Daily Update*\n\n📦 Shipped today?\n↩️ Returns?\n⚠️ Low stock items?",
}

# ── DATA ───────────────────────────────────────────────────────────────────
def load():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {}
    except:
        data = {}
    data.setdefault("users", {})
    data.setdefault("sessions", {})
    data.setdefault("todos", {})
    data.setdefault("daily", {})
    data.setdefault("stats", {})
    data.setdefault("meetings", [])
    data.setdefault("groups", [])
    data.setdefault("managers", [])
    data.setdefault("domains", [])
    data.setdefault("offers", {})
    data.setdefault("stock", {})
    data.setdefault("group_teams", {})
    return data

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def today():
    return datetime.now(TZ).strftime("%Y-%m-%d")

def now_zurich():
    return datetime.now(TZ)

def is_weekday():
    return now_zurich().weekday() < 5

def fmt_dur(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"

def fmt_time(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%H:%M")

def get_today_sec(data, uid):
    return sum(s.get("duration_sec", 0) for s in data["sessions"].get(uid, []) if s.get("date") == today())

def is_manager(data, uid):
    return uid in data.get("managers", [])

# ── START / REGISTER ───────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🌐 Open TeamFlow Website", url=WEBSITE_URL)]]
    await update.message.reply_text(
        "👋 Welcome to *TeamFlow Scale Bot!*\n\n"
        "📝 To get started: `/register Your Name`\n\n"
        "📋 *Member commands:*\n"
        "/clockin /clockout /status\n"
        "/tasks /addtask /daily /report\n\n"
        "📊 *Team tracking:*\n"
        "/recap — Marketing KPIs\n"
        "/orders — Sales orders\n"
        "/resell — ReSell stats\n"
        "/shipped — Warehouse\n\n"
        "Or open the website to use the full dashboard 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    name = " ".join(ctx.args) if ctx.args else update.effective_user.first_name
    data = load()
    if uid in data["users"]:
        user = data["users"][uid]
        await update.message.reply_text(
            f"✅ Already registered as *{user['name']}* — {user.get('team','no team')}!\n\n"
            f"Use `/status` to see your info.",
            parse_mode="Markdown"
        )
        return
    data["users"][uid] = {"name": name, "team": "", "clocked_in": False, "clock_start": None, "goals": [], "goals_date": ""}
    save(data)
    keyboard = [[InlineKeyboardButton(t, callback_data=f"setteam_{t}")] for t in TEAMS]
    await update.message.reply_text(
        f"👋 Welcome *{name}*!\n\nChoose your team:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── CLOCK ──────────────────────────────────────────────────────────────────
async def clockin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered. Use `/register Your Name`", parse_mode="Markdown")
        return
    user = data["users"][uid]
    if user.get("clocked_in"):
        since = user.get("clock_start_fmt", "unknown")
        await update.message.reply_text(f"⚠️ Already clocked in since *{since}*!", parse_mode="Markdown")
        return
    ts = datetime.now(TZ).timestamp()
    user["clocked_in"] = True
    user["clock_start"] = ts
    user["clock_start_fmt"] = fmt_time(ts)
    save(data)
    await update.message.reply_text(
        f"✅ *{user['name']}* clocked in at *{fmt_time(ts)}* 🟢\n\n"
        f"🏷 Team: {user.get('team','—')}\n"
        f"Have a productive day! 💪",
        parse_mode="Markdown"
    )

async def clockout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered. Use `/register Your Name`", parse_mode="Markdown")
        return
    user = data["users"][uid]
    if not user.get("clocked_in"):
        await update.message.reply_text("⚠️ Not clocked in!", parse_mode="Markdown")
        return
    end_ts = datetime.now(TZ).timestamp()
    start_ts = user.get("clock_start", end_ts)
    duration_sec = int(end_ts - start_ts)
    session = {"date": today(), "start": start_ts, "end": end_ts, "duration_sec": duration_sec, "member": user["name"], "team": user.get("team", "")}
    data["sessions"].setdefault(uid, []).append(session)
    user["clocked_in"] = False
    user["clock_start"] = None
    save(data)
    today_sec = get_today_sec(data, uid)
    await update.message.reply_text(
        f"🔴 *{user['name']}* clocked out at *{fmt_time(end_ts)}*\n\n"
        f"⏱ Session: *{fmt_dur(duration_sec)}*\n"
        f"📅 Today total: *{fmt_dur(today_sec)}*\n\n"
        f"Good work! See you tomorrow 👋",
        parse_mode="Markdown"
    )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered. Use `/register Your Name`", parse_mode="Markdown")
        return
    user = data["users"][uid]
    today_sec = get_today_sec(data, uid)
    todos = data["todos"].get(uid, [])
    done_tasks = sum(1 for t in todos if t.get("done"))
    daily_list = data["daily"].get(uid, [])
    daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
    status_icon = "🟢 Online" if user.get("clocked_in") else "🔴 Offline"
    clock_info = f"Since {user.get('clock_start_fmt','—')}" if user.get("clocked_in") else f"Total today: {fmt_dur(today_sec)}"
    await update.message.reply_text(
        f"📊 *{user['name']}* — {user.get('team','—')}\n\n"
        f"{status_icon}\n"
        f"⏱ {clock_info}\n"
        f"✅ Tasks: {done_tasks}/{len(todos)}\n"
        f"📋 Daily: {daily_done}/{len(daily_list)}",
        parse_mode="Markdown"
    )

# ── TASKS ──────────────────────────────────────────────────────────────────
async def tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    todos = data["todos"].get(uid, [])
    if not todos:
        await update.message.reply_text("📋 No tasks yet!\n\nAdd one: `/addtask Buy milk`", parse_mode="Markdown")
        return
    pri_icon = {"h": "🔴", "m": "🟡", "l": "🟢"}
    lines = ["📋 *Your Tasks:*\n"]
    keyboard = []
    for i, t in enumerate(todos):
        icon = "✅" if t.get("done") else pri_icon.get(t.get("pri","m"), "⬜")
        lines.append(f"{icon} {t['text']}")
        keyboard.append([InlineKeyboardButton(f"{'Undo' if t.get('done') else 'Done'}: {t['text'][:25]}", callback_data=f"toggle_{i}")])
    keyboard.append([InlineKeyboardButton("🗑 Clear completed", callback_data="delete_done")])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def addtask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: `/addtask [h/m/l] Task description`\n\nExample: `/addtask h Call client`", parse_mode="Markdown")
        return
    pri = "m"
    text_parts = ctx.args
    if ctx.args[0].lower() in ["h","m","l"]:
        pri = ctx.args[0].lower()
        text_parts = ctx.args[1:]
    text = " ".join(text_parts)
    if not text:
        await update.message.reply_text("❌ Task text cannot be empty.", parse_mode="Markdown")
        return
    data["todos"].setdefault(uid, []).append({"text": text, "pri": pri, "done": False})
    save(data)
    pri_label = {"h":"🔴 High","m":"🟡 Medium","l":"🟢 Low"}
    await update.message.reply_text(f"✅ Task added: *{text}*\nPriority: {pri_label[pri]}", parse_mode="Markdown")

# ── DAILY ──────────────────────────────────────────────────────────────────
async def daily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    daily_list = data["daily"].get(uid, [])
    if not daily_list:
        await update.message.reply_text("📋 No daily routines!\n\nUse `/adddaily Task name` to add.", parse_mode="Markdown")
        return
    done = sum(1 for d in daily_list if d.get("done_date") == today())
    pct = round(done/len(daily_list)*100)
    bar = "█" * (pct//10) + "░" * (10 - pct//10)
    lines = [f"📋 *Daily Routines — {today()}*\n`{bar}` {pct}%\n"]
    keyboard = []
    for i, d in enumerate(daily_list):
        done_today = d.get("done_date") == today()
        icon = "✅" if done_today else "⬜"
        lines.append(f"{icon} {d['text']}")
        keyboard.append([InlineKeyboardButton(f"{'Undo' if done_today else '✓'}: {d['text'][:30]}", callback_data=f"daily_{i}")])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def adddaily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"] or not ctx.args:
        await update.message.reply_text("Usage: `/adddaily Task name`", parse_mode="Markdown")
        return
    text = " ".join(ctx.args)
    data["daily"].setdefault(uid, []).append({"text": text, "done_date": None})
    save(data)
    await update.message.reply_text(f"✅ Added to daily: *{text}*", parse_mode="Markdown")

# ── GOALS / REPORT ─────────────────────────────────────────────────────────
async def goals_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    user = data["users"][uid]
    if not ctx.args:
        goals = user.get("goals", []) if user.get("goals_date") == today() else []
        if not goals:
            await update.message.reply_text("🎯 No goals set today.\n\nSet goals: `/goals Goal 1 | Goal 2`", parse_mode="Markdown")
        else:
            lines = ["🎯 *Today's Goals:*\n"] + [f"• {g}" for g in goals]
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return
    goals_text = " ".join(ctx.args)
    goals = [g.strip() for g in goals_text.split("|") if g.strip()]
    user["goals"] = goals
    user["goals_date"] = today()
    save(data)
    lines = ["🎯 *Goals set for today:*\n"] + [f"• {g}" for g in goals]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    user = data["users"][uid]
    week_ago = (now_zurich() - timedelta(days=7)).strftime("%Y-%m-%d")
    week_sec = sum(s.get("duration_sec",0) for s in data["sessions"].get(uid,[]) if s.get("date","") >= week_ago)
    todos = data["todos"].get(uid, [])
    done = sum(1 for t in todos if t.get("done"))
    daily_list = data["daily"].get(uid, [])
    daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
    await update.message.reply_text(
        f"📈 *Weekly Report — {user['name']}*\n"
        f"🏷 {user.get('team','—')}\n\n"
        f"⏱ Hours (7 days): *{fmt_dur(week_sec)}*\n"
        f"✅ Tasks: *{done}/{len(todos)}*\n"
        f"📋 Daily today: *{daily_done}/{len(daily_list)}*",
        parse_mode="Markdown"
    )

# ── TEAM KPIs ──────────────────────────────────────────────────────────────
async def recap_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Marketing: /recap spend revenue roas account"""
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 3:
        await update.message.reply_text(
            "📊 *Marketing Recap*\n\nUsage: `/recap spend revenue roas account`\n\nExample: `/recap 500 2000 4.0 VSmedic`",
            parse_mode="Markdown"
        )
        return
    try:
        spend = float(ctx.args[0])
        revenue = float(ctx.args[1])
        roas = float(ctx.args[2])
        account = ctx.args[3] if len(ctx.args) > 3 else "General"
    except ValueError:
        await update.message.reply_text("❌ Invalid numbers. Example: `/recap 500 2000 4.0 VSmedic`", parse_mode="Markdown")
        return
    data["stats"].setdefault(uid, {}).setdefault(today(), {}).update({"spend": f"{spend:.0f}€", "revenue": f"{revenue:.0f}€", "roas": f"{roas:.2f}", "account": account})
    save(data)
    roas_icon = "✅" if roas >= ROAS_MINIMUM else "🚨"
    target = BRAND_TARGETS.get(account, 0)
    target_txt = f"\n🎯 Target: *{target:,}€*\n📈 Achievement: *{round(revenue/target*100)}%*" if target > 0 else ""
    msg = (
        f"📊 *Marketing Recap — {today()}*\n"
        f"👤 {data['users'][uid]['name']}\n\n"
        f"💸 Spend: *{spend:,.0f}€*\n"
        f"💰 Revenue: *{revenue:,.0f}€*\n"
        f"📈 ROAS: *{roas:.2f}* {roas_icon}"
        f"{target_txt}\n\n"
        f"🏷 Account: *{account}*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
    # ROAS alert to groups
    if roas < ROAS_MINIMUM:
        alert = f"🚨 *ROAS ALERT!*\n\n📉 ROAS: *{roas:.2f}* (min: {ROAS_MINIMUM})\n💸 Spend: {spend:,.0f}€\n💰 Revenue: {revenue:,.0f}€\n🏷 Account: {account}\n👤 {data['users'][uid]['name']}\n\n⚠️ Action needed!"
        for gid in data.get("groups", []):
            try:
                await ctx.bot.send_message(chat_id=int(gid), text=alert, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Group error: {e}")

async def orders_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sales: /orders total confirmed rejected cod card"""
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("Usage: `/orders total confirmed rejected cod card`\n\nExample: `/orders 45 38 7 25 13`", parse_mode="Markdown")
        return
    try:
        vals = [int(x) for x in ctx.args[:5]]
        while len(vals) < 5:
            vals.append(0)
        total, confirmed, rejected, cod, card = vals
    except ValueError:
        await update.message.reply_text("❌ Use numbers only. Example: `/orders 45 38 7 25 13`", parse_mode="Markdown")
        return
    data["stats"].setdefault(uid, {}).setdefault(today(), {}).update({"total": total, "confirmed": confirmed, "rejected": rejected, "cod": cod, "card": card})
    save(data)
    conf_rate = round(confirmed/total*100) if total else 0
    await update.message.reply_text(
        f"💼 *Sales Orders — {today()}*\n\n"
        f"📦 Total: *{total}*\n"
        f"✅ Confirmed: *{confirmed}* ({conf_rate}%)\n"
        f"❌ Rejected: *{rejected}*\n"
        f"💵 COD: *{cod}* | 💳 Card: *{card}*",
        parse_mode="Markdown"
    )

async def delivery_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sales: /delivery rate"""
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"] or not ctx.args:
        await update.message.reply_text("Usage: `/delivery 92`", parse_mode="Markdown")
        return
    try:
        rate = float(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Use a number. Example: `/delivery 92`", parse_mode="Markdown")
        return
    data["stats"].setdefault(uid, {}).setdefault(today(), {})["delivery_rate"] = f"{rate}%"
    save(data)
    icon = "✅" if rate >= 85 else "⚠️" if rate >= 70 else "🚨"
    await update.message.reply_text(f"🚚 Delivery rate logged: *{rate}%* {icon}", parse_mode="Markdown")

async def resell_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ReSell: /resell contacted renewed revenue"""
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("Usage: `/resell contacted renewed revenue`\n\nExample: `/resell 45 12 2400`", parse_mode="Markdown")
        return
    try:
        contacted = int(ctx.args[0])
        renewed = int(ctx.args[1])
        revenue = float(ctx.args[2]) if len(ctx.args) > 2 else 0
    except ValueError:
        await update.message.reply_text("❌ Use numbers only.", parse_mode="Markdown")
        return
    conv = round(renewed/contacted*100) if contacted else 0
    data["stats"].setdefault(uid, {}).setdefault(today(), {}).update({"contacted": contacted, "renewed": renewed, "revenue": f"{revenue:.0f}€", "conversion": f"{conv}%"})
    save(data)
    await update.message.reply_text(
        f"🔄 *ReSell Stats — {today()}*\n\n"
        f"📞 Contacted: *{contacted}*\n"
        f"✅ Renewed: *{renewed}* ({conv}%)\n"
        f"💰 Revenue: *{revenue:,.0f}€*",
        parse_mode="Markdown"
    )

async def shipped_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Warehouse: /shipped shipped returned unfulfilled"""
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: `/shipped shipped returned unfulfilled`\n\nExample: `/shipped 85 5 3`", parse_mode="Markdown")
        return
    try:
        vals = [int(x) for x in ctx.args[:3]]
        while len(vals) < 3:
            vals.append(0)
        shipped, returned, unfulfilled = vals
    except ValueError:
        await update.message.reply_text("❌ Use numbers only.", parse_mode="Markdown")
        return
    data["stats"].setdefault(uid, {}).setdefault(today(), {}).update({"shipped": shipped, "returned": returned, "unfulfilled": unfulfilled})
    save(data)
    await update.message.reply_text(
        f"📦 *Warehouse — {today()}*\n\n"
        f"📤 Shipped: *{shipped}*\n"
        f"↩️ Returned: *{returned}*\n"
        f"⚠️ Unfulfilled: *{unfulfilled}*",
        parse_mode="Markdown"
    )

async def stock_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Warehouse: /stock product qty"""
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 2:
        # Show stock
        stock = data.get("stock", {})
        if not stock:
            await update.message.reply_text("📦 No stock data.\n\nAdd: `/stock ProductName 50`", parse_mode="Markdown")
            return
        lines = ["📦 *Current Stock:*\n"]
        low = []
        for product, qty in stock.items():
            icon = "🔴" if qty < 10 else "🟡" if qty < 30 else "🟢"
            lines.append(f"{icon} {product}: *{qty}*")
            if qty < 10:
                low.append(product)
        if low:
            lines.append(f"\n⚠️ *Low stock alert:* {', '.join(low)}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return
    product = ctx.args[0]
    try:
        qty = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("❌ Quantity must be a number.", parse_mode="Markdown")
        return
    data["stock"][product] = qty
    save(data)
    icon = "🔴" if qty < 10 else "🟡" if qty < 30 else "🟢"
    await update.message.reply_text(f"📦 Stock updated: *{product}* = *{qty}* {icon}", parse_mode="Markdown")
    # Alert managers if low
    if qty < 10:
        alert = f"🚨 *Low Stock Alert!*\n\n📦 *{product}*: only *{qty}* left!\n\nReorder needed!"
        for mgr_uid in data.get("managers", []):
            try:
                await ctx.bot.send_message(chat_id=int(mgr_uid), text=alert, parse_mode="Markdown")
            except:
                pass

# ── SAFE OFFERS ────────────────────────────────────────────────────────────
async def newoffer_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Safe Offers: /newoffer BrandName"""
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: `/newoffer BrandName`\n\nExample: `/newoffer VSmedic`", parse_mode="Markdown")
        return
    brand = " ".join(ctx.args)
    key = f"{brand}_{today()}"
    data["offers"][key] = {"brand": brand, "date": today(), "checklist": [False] * len(OFFER_CHECKLIST)}
    save(data)
    lines = [f"🎯 *New Offer Checklist — {brand}*\n"]
    keyboard = []
    for i, item in enumerate(OFFER_CHECKLIST):
        lines.append(f"⬜ {i+1}. {item}")
        keyboard.append([InlineKeyboardButton(f"✓ {item[:35]}", callback_data=f"offer_{brand}_{today()}_{i}")])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def adddomain_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Safe Offers/Marketing: /adddomain brand https://url"""
    uid = str(update.effective_user.id)
    data = load()
    if uid not in data["users"]:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text("Usage: `/adddomain Brand https://url`\n\nExample: `/adddomain VSmedic https://vsmarket.online`", parse_mode="Markdown")
        return
    brand = ctx.args[0]
    url = ctx.args[1]
    data["domains"].append({"brand": brand, "url": url, "added": today(), "status": "unknown"})
    save(data)
    await update.message.reply_text(f"✅ Domain added: *{brand}* — {url}", parse_mode="Markdown")

async def checklinks_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Check all registered domains"""
    data = load()
    domains = data.get("domains", [])
    if not domains:
        await update.message.reply_text("🌐 No domains registered.\n\nAdd: `/adddomain Brand https://url`", parse_mode="Markdown")
        return
    await update.message.reply_text(f"🔍 Checking *{len(domains)}* domains...", parse_mode="Markdown")
    results = []
    async with aiohttp.ClientSession() as session:
        for d in domains:
            try:
                async with session.head(d["url"], timeout=aiohttp.ClientTimeout(total=8), allow_redirects=True) as resp:
                    icon = "✅" if resp.status < 400 else "❌"
                    results.append(f"{icon} *{d['brand']}* — {d['url']}\n   Status: {resp.status}")
                    d["status"] = "ok" if resp.status < 400 else "error"
            except Exception as e:
                results.append(f"❌ *{d['brand']}* — {d['url']}\n   Error: unreachable")
                d["status"] = "error"
    save(data)
    await update.message.reply_text("🌐 *Domain Check Results:*\n\n" + "\n\n".join(results), parse_mode="Markdown")

# ── MEETINGS ───────────────────────────────────────────────────────────────
async def meeting_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Manager: /meeting 14:00 Title | Team (optional)"""
    uid = str(update.effective_user.id)
    data = load()
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Only managers can add meetings.", parse_mode="Markdown")
        return
    if not ctx.args or len(ctx.args) < 2:
        await update.message.reply_text(
            "📅 *Add Meeting:*\n\nUsage: `/meeting 14:00 Title`\nWith team: `/meeting 14:00 Title | Sales Team`",
            parse_mode="Markdown"
        )
        return
    time_str = ctx.args[0]
    rest = " ".join(ctx.args[1:])
    if "|" in rest:
        parts = rest.split("|")
        title = parts[0].strip()
        team = parts[1].strip()
    else:
        title = rest
        team = "All"
    data["meetings"].append({"id": int(datetime.now().timestamp()), "date": today(), "time": time_str, "title": title, "team": team})
    save(data)
    await update.message.reply_text(f"✅ Meeting added: *{time_str}* — {title}\n👥 Team: *{team}*", parse_mode="Markdown")

async def meetings_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    user_team = data["users"].get(uid, {}).get("team", "") if uid in data["users"] else ""
    meetings = [m for m in data.get("meetings", []) if m.get("date") == today() and (is_manager(data, uid) or m.get("team") == "All" or m.get("team") == user_team)]
    if not meetings:
        await update.message.reply_text("📅 No meetings today.", parse_mode="Markdown")
        return
    lines = ["📅 *Today's Meetings:*\n"]
    for m in sorted(meetings, key=lambda x: x.get("time","")):
        team_tag = f" ({m.get('team','')})" if m.get("team") and m.get("team") != "All" else ""
        lines.append(f"🕐 *{m['time']}* — {m['title']}{team_tag}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── MANAGER COMMANDS ───────────────────────────────────────────────────────
async def manager_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if not ctx.args:
        await update.message.reply_text("Usage: `/manager PASSWORD`", parse_mode="Markdown")
        return
    if ctx.args[0] != MANAGER_PASSWORD:
        await update.message.reply_text("❌ Wrong password.", parse_mode="Markdown")
        return
    if uid not in data["managers"]:
        data["managers"].append(uid)
        save(data)
    await update.message.reply_text(
        "🔐 *Manager access granted!*\n\n"
        "📋 *Manager commands:*\n"
        "/teamstatus — Live team status\n"
        "/teamreport — Weekly report\n"
        "/timelog — Time log\n"
        "/dailystats — Today's KPIs\n"
        "/meeting — Add meeting\n"
        "/announce — Announce to groups\n"
        "/targets — ADS targets\n"
        "/listgroups — Registered groups",
        parse_mode="Markdown"
    )

async def teamstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Manager only.", parse_mode="Markdown")
        return
    if not data["users"]:
        await update.message.reply_text("No members registered yet.", parse_mode="Markdown")
        return
    online = [u for u in data["users"].values() if u.get("clocked_in")]
    offline = [u for u in data["users"].values() if not u.get("clocked_in")]
    lines = [f"👥 *Team Live Status — {today()}*\n"]
    if online:
        lines.append(f"🟢 *Online ({len(online)}):*")
        for u in online:
            sec = get_today_sec(data, [k for k,v in data["users"].items() if v==u][0])
            lines.append(f"  • {u['name']} — {u.get('team','—')} ({fmt_dur(sec)})")
    if offline:
        lines.append(f"\n🔴 *Offline ({len(offline)}):*")
        for u in offline:
            lines.append(f"  • {u['name']} — {u.get('team','—')}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def teamreport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Manager only.", parse_mode="Markdown")
        return
    week_ago = (now_zurich() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [f"📊 *Weekly Team Report*\n📅 {week_ago} → {today()}\n"]
    total_sec = 0
    for uid_m, user in data["users"].items():
        sec = sum(s.get("duration_sec",0) for s in data["sessions"].get(uid_m,[]) if s.get("date","") >= week_ago)
        total_sec += sec
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        lines.append(f"👤 *{user['name']}* — {user.get('team','')}\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)}")
    lines.append(f"\n⏱ *Total team: {fmt_dur(total_sec)}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def timelog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Manager only.", parse_mode="Markdown")
        return
    all_sessions = []
    for uid_m, user in data["users"].items():
        for s in data["sessions"].get(uid_m, []):
            if s.get("date") == today():
                all_sessions.append({**s, "member": user["name"], "team": user.get("team","")})
    if not all_sessions:
        await update.message.reply_text(f"⏱ No sessions logged today ({today()}).", parse_mode="Markdown")
        return
    lines = [f"⏱ *Time Log — {today()}*\n"]
    for s in sorted(all_sessions, key=lambda x: x.get("start",0)):
        lines.append(f"👤 *{s['member']}* — {s['team']}\n   {fmt_time(s['start'])} → {fmt_time(s['end'])} ({fmt_dur(s['duration_sec'])})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def daily_stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Manager only.", parse_mode="Markdown")
        return
    lines = [f"📈 *Today's KPIs — {today()}*\n"]
    for uid_m, user in data["users"].items():
        stats = data.get("stats", {}).get(uid_m, {}).get(today(), {})
        if stats:
            lines.append(f"👤 *{user['name']}* — {user.get('team','')}")
            for k, v in stats.items():
                lines.append(f"   • {k}: *{v}*")
    if len(lines) == 1:
        lines.append("No KPIs logged today yet.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def targets_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    lines = [f"🎯 *Daily ADS Targets — {today()}*\n"]
    for brand, target in BRAND_TARGETS.items():
        if target == 0:
            continue
        lines.append(f"📊 *{brand}*: Target *{target:,}€/day*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def announce_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Only managers can send announcements.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("Usage: `/announce Your message here`", parse_mode="Markdown")
        return
    message = " ".join(ctx.args)
    msg = f"📣 *Announcement from Management*\n\n{message}"
    sent = 0
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
            sent += 1
        except Exception as e:
            logger.warning(f"Group error: {e}")
    await update.message.reply_text(f"✅ Sent to *{sent}* group(s)!", parse_mode="Markdown")

async def list_groups(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    data = load()
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Manager only.", parse_mode="Markdown")
        return
    groups = data.get("groups", [])
    if not groups:
        await update.message.reply_text("No groups registered yet.\n\nAdd bot to a group and use `/setup`.", parse_mode="Markdown")
        return
    lines = [f"🏢 *Registered Groups ({len(groups)}):*\n"]
    for gid in groups:
        team = data.get("group_teams", {}).get(gid, "ALL")
        lines.append(f"• ID: `{gid}` — Team: *{team}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── GROUP SETUP ────────────────────────────────────────────────────────────
async def setup_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command is for groups only.", parse_mode="Markdown")
        return
    gid = str(update.effective_chat.id)
    data = load()
    if gid not in data["groups"]:
        data["groups"].append(gid)
        save(data)
        await update.message.reply_text(
            f"✅ Group registered!\n\n"
            f"Group ID: `{gid}`\n\n"
            f"Use `/setgroupteam` to assign a specific team.\n"
            f"Default: ALL teams.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"✅ Group already registered! ID: `{gid}`", parse_mode="Markdown")

async def set_group_team(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command is for groups only.", parse_mode="Markdown")
        return
    gid = str(update.effective_chat.id)
    data = load()
    keyboard = [[InlineKeyboardButton("All Teams", callback_data=f"gteam_{gid}_ALL")]]
    for t in TEAMS:
        keyboard.append([InlineKeyboardButton(t, callback_data=f"gteam_{gid}_{t}")])
    await update.message.reply_text("Select which team this group is for:", reply_markup=InlineKeyboardMarkup(keyboard))

# ── CALLBACKS ──────────────────────────────────────────────────────────────
async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load()
    uid = str(query.from_user.id)

    if query.data.startswith("setteam_"):
        team = query.data.replace("setteam_", "")
        if uid in data["users"]:
            data["users"][uid]["team"] = team
            if team in DAILY_ROUTINES:
                data["daily"][uid] = [{"text": r, "done_date": None} for r in DAILY_ROUTINES[team]]
            save(data)
            await query.edit_message_text(
                f"✅ Team set to *{team}*!\n\n📋 Daily routines loaded.\n\nType `/clockin` to start! 🚀",
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
            brand_date_key = parts[1] + "_" + parts[2]
            idx = int(parts[3])
            offers = data.get("offers", {})
            if brand_date_key in offers:
                offers[brand_date_key]["checklist"][idx] = not offers[brand_date_key]["checklist"][idx]
                save(data)
                done = sum(offers[brand_date_key]["checklist"])
                total = len(offers[brand_date_key]["checklist"])
                if done == total:
                    await query.edit_message_text(f"🎉 *Offer Ready!* — {offers[brand_date_key]['brand']}\n\n✅ All {total} steps completed!\n\nNotify Marketing Team to start campaigns! 🚀", parse_mode="Markdown")
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
            await query.edit_message_text(f"{s}: *{todos[idx]['text']}*\n\nType /tasks to see all.", parse_mode="Markdown")
        return

    if query.data == "delete_done":
        before = len(data["todos"].get(uid, []))
        data["todos"][uid] = [t for t in data["todos"].get(uid, []) if not t.get("done")]
        deleted = before - len(data["todos"].get(uid, []))
        save(data)
        await query.edit_message_text(f"🗑 Deleted *{deleted}* completed task(s).", parse_mode="Markdown")
        return

    if query.data.startswith("daily_"):
        idx = int(query.data.split("_")[1])
        daily_list = data["daily"].get(uid, [])
        if idx < len(daily_list):
            daily_list[idx]["done_date"] = None if daily_list[idx].get("done_date") == today() else today()
            save(data)
            done = sum(1 for d in daily_list if d.get("done_date") == today())
            await query.answer(f"📋 {done}/{len(daily_list)} done today")
        return

# ── SCHEDULED JOBS ─────────────────────────────────────────────────────────
async def job_morning_motivation(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    motivation = random.choice(MOTIVATIONS)
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=f"{motivation}\n\n☀️ *New day, new goals — let's go team!*", parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def job_morning_meetings(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    meetings = [m for m in data.get("meetings", []) if m.get("date") == today()]
    if not meetings: return
    lines = ["📅 *Today's Meetings:*\n"]
    for m in sorted(meetings, key=lambda x: x.get("time","")):
        team_tag = f" ({m.get('team','')})" if m.get("team") and m.get("team") != "All" else ""
        lines.append(f"🕐 *{m['time']}* — {m['title']}{team_tag}")
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
            today_sessions = [s for s in data["sessions"].get(uid, []) if s.get("date") == today()]
            if not today_sessions:
                try:
                    await ctx.bot.send_message(chat_id=int(uid), text=f"⏰ Hey *{user['name']}*, don't forget to clock in!\n\nType `/clockin` to start. 💪", parse_mode="Markdown")
                except Exception as e:
                    logger.warning(f"DM error: {e}")
    keyboard = [[InlineKeyboardButton("▶️ Start Working", url="https://t.me/teamflow_scale_bot")]]
    msg = "⏰ *Good morning, team!*\n\nIf you haven't clocked in yet — now is the time! 💪"
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def job_manager_late_alert(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    late = []
    for uid, user in data["users"].items():
        if not user.get("clocked_in"):
            if not [s for s in data["sessions"].get(uid, []) if s.get("date") == today()]:
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
        teams_to_post = list(SUMMARY_QUESTIONS.keys()) if assigned_team == "ALL" else ([assigned_team] if assigned_team in SUMMARY_QUESTIONS else [])
        for team in teams_to_post:
            question = SUMMARY_QUESTIONS[team]
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
        try:
            await ctx.bot.send_message(
                chat_id=int(uid),
                text=f"🌆 *End of Day — {user['name']}*\n📅 {today()}\n\n"
                     f"⏱ *{fmt_dur(today_sec)}* worked\n"
                     f"✅ Tasks: *{done_tasks}/{len(todos)}*\n"
                     f"📋 Routines: *{daily_done}/{len(daily_list)}*\n\n"
                     f"Don't forget `/clockout` if still working! 👋",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"DM error: {e}")

async def job_clockout_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    keyboard = [[InlineKeyboardButton("■ Clock Out Now", url="https://t.me/teamflow_scale_bot")]]
    msg = "🔔 *End of Day Reminder!*\n\nIf you're still working — don't forget to clock out! 👋"
    for uid, user in data["users"].items():
        if user.get("clocked_in"):
            try:
                await ctx.bot.send_message(chat_id=int(uid), text=f"🔔 *{user['name']}*, you're still clocked in!\n\nDon't forget to `/clockout`! 👋", parse_mode="Markdown")
            except:
                pass
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.warning(f"Group error: {e}")

async def job_manager_daily_digest(ctx: ContextTypes.DEFAULT_TYPE):
    if not is_weekday(): return
    data = load()
    if not data["users"]: return
    online = sum(1 for u in data["users"].values() if u.get("clocked_in"))
    total_sec = sum(get_today_sec(data, uid) for uid in data["users"])
    lines = [f"📊 *Daily Manager Digest — {today()}*\n", f"👥 {len(data['users'])} members | 🟢 {online} online", f"⏱ Total hours: *{fmt_dur(total_sec)}*\n", "*Individual:*"]
    for uid, user in data["users"].items():
        sec = get_today_sec(data, uid)
        todos = data["todos"].get(uid, [])
        done = sum(1 for t in todos if t.get("done"))
        daily_list = data["daily"].get(uid, [])
        daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
        is_on = "🟢" if user.get("clocked_in") else "🔴"
        lines.append(f"{is_on} *{user['name']}* — {user.get('team','')}")
        lines.append(f"   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)} | 📋 {daily_done}/{len(daily_list)}")
    msg = "\n".join(lines)
    for mgr_uid in data.get("managers", []):
        try:
            await ctx.bot.send_message(chat_id=int(mgr_uid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Manager DM error: {e}")

async def job_weekly_report_groups(ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    week_ago = (now_zurich() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [f"📊 *Weekly Team Report*\n📅 {week_ago} → {today()}\n"]
    total = 0
    for uid_m, user in data["users"].items():
        sec = sum(s.get("duration_sec",0) for s in data["sessions"].get(uid_m,[]) if s.get("date","") >= week_ago)
        total += sec
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        lines.append(f"👤 *{user['name']}* — {user.get('team','')}\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)}")
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
    data = load()
    msg = "📦 *Warehouse Weekly Call in 30 minutes!*\n\n🕐 16:00 (Zurich)\n\n📋 Prepare:\n• Last week stock summary\n• Items below minimum\n• Returns & damages\n\nGet ready! 🚀"
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
        except:
            pass
    for uid, user in data["users"].items():
        if user.get("team") == "Warehouse Team":
            try:
                await ctx.bot.send_message(chat_id=int(uid), text=msg, parse_mode="Markdown")
            except:
                pass

# ── MAIN ───────────────────────────────────────────────────────────────────
async def run():
    app = Application.builder().token(TOKEN).build()

    # Handlers
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
    app.add_handler(CommandHandler("recap", recap_cmd))
    app.add_handler(CommandHandler("orders", orders_cmd))
    app.add_handler(CommandHandler("delivery", delivery_cmd))
    app.add_handler(CommandHandler("resell", resell_cmd))
    app.add_handler(CommandHandler("shipped", shipped_cmd))
    app.add_handler(CommandHandler("stock", stock_cmd))
    app.add_handler(CommandHandler("newoffer", newoffer_cmd))
    app.add_handler(CommandHandler("adddomain", adddomain_cmd))
    app.add_handler(CommandHandler("checklinks", checklinks_cmd))
    app.add_handler(CommandHandler("meeting", meeting_cmd))
    app.add_handler(CommandHandler("meetings", meetings_today))
    app.add_handler(CommandHandler("announce", announce_cmd))
    app.add_handler(CommandHandler("targets", targets_cmd))
    app.add_handler(CommandHandler("manager", manager_login))
    app.add_handler(CommandHandler("teamstatus", teamstatus))
    app.add_handler(CommandHandler("teamreport", teamreport))
    app.add_handler(CommandHandler("timelog", timelog))
    app.add_handler(CommandHandler("dailystats", daily_stats_cmd))
    app.add_handler(CommandHandler("listgroups", list_groups))
    app.add_handler(CommandHandler("setup", setup_group))
    app.add_handler(CommandHandler("setgroupteam", set_group_team))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Scheduled jobs
    jq = app.job_queue
    jq.run_daily(job_morning_motivation,       time=datetime.strptime("09:00","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_morning_meetings,         time=datetime.strptime("08:30","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_clockin_reminder,         time=datetime.strptime("10:00","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_manager_late_alert,       time=datetime.strptime("10:30","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_daily_summary_groups,     time=datetime.strptime("14:00","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_overdue_tasks,            time=datetime.strptime("16:00","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_eod_personal_summary,     time=datetime.strptime("17:30","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_clockout_reminder,        time=datetime.strptime("18:00","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_manager_daily_digest,     time=datetime.strptime("18:30","%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_weekly_report_groups,     time=datetime.strptime("16:00","%H:%M").replace(tzinfo=TZ).timetz(), days=(6,))
    jq.run_daily(job_warehouse_monday_reminder,time=datetime.strptime("15:30","%H:%M").replace(tzinfo=TZ).timetz(), days=(0,))

    # Set bot commands
    default_cmds = [BotCommand("start","👋 Open TeamFlow"), BotCommand("register","📝 Register"), BotCommand("manager","🔐 Admin login")]
    member_cmds = [
        BotCommand("start","👋 Open TeamFlow"), BotCommand("clockin","▶️ Clock in"), BotCommand("clockout","■ Clock out"),
        BotCommand("status","📊 My status"), BotCommand("tasks","✅ My tasks"), BotCommand("addtask","➕ Add task"),
        BotCommand("daily","📋 Daily routines"), BotCommand("goals","🎯 Set goals"), BotCommand("report","📈 My report"),
        BotCommand("meetings","📅 Today's meetings"), BotCommand("targets","🎯 ADS targets"),
    ]
    team_extra = {
        "Marketing Team": [BotCommand("recap","📢 Log marketing KPIs"), BotCommand("checklinks","🌐 Check domains"), BotCommand("adddomain","➕ Add domain")],
        "Safe Offers Team": [BotCommand("newoffer","🎯 New offer checklist"), BotCommand("checklinks","🌐 Check domains"), BotCommand("adddomain","➕ Add domain")],
        "ReSell Team": [BotCommand("resell","🔄 Log ReSell stats")],
        "Sales Team": [BotCommand("orders","💼 Log orders"), BotCommand("delivery","🚚 Delivery rate")],
        "Warehouse Team": [BotCommand("shipped","📦 Log shipped"), BotCommand("stock","📦 Stock update")],
    }
    mgr_cmds = [
        BotCommand("start","👋 Open TeamFlow"), BotCommand("teamstatus","👥 Team status"),
        BotCommand("teamreport","📊 Weekly report"), BotCommand("timelog","⏱ Time log"),
        BotCommand("dailystats","📈 Today's KPIs"), BotCommand("meeting","📅 Add meeting"),
        BotCommand("meetings","📅 Today's meetings"), BotCommand("announce","📣 Announce"),
        BotCommand("listgroups","🏢 Groups"), BotCommand("targets","🎯 ADS targets"),
        BotCommand("clockin","▶️ Clock in"), BotCommand("clockout","■ Clock out"),
    ]

    print("✅ TeamFlow bot starting...")
    async with app:
        await app.bot.set_my_commands(default_cmds, scope=BotCommandScopeDefault())
        data = load()
        for uid, user in data["users"].items():
            team = user.get("team","")
            cmds = member_cmds + team_extra.get(team, [])
            try:
                await app.bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=int(uid)))
            except Exception as e:
                logger.warning(f"Could not set commands for {uid}: {e}")
        for mgr_uid in data.get("managers", []):
            try:
                await app.bot.set_my_commands(mgr_cmds, scope=BotCommandScopeChat(chat_id=int(mgr_uid)))
            except Exception as e:
                logger.warning(f"Could not set manager commands: {e}")
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
    except:
        pass
    asyncio.run(run())
