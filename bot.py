import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "8774731842:AAHHHaVy-X3LFYFQa-kRWBBcrkiSzb23NVw")
MANAGER_PASSWORD = os.environ.get("MANAGER_PASSWORD", "admin1234")
DATA_FILE = "data.json"
WEBSITE_URL = "https://vitalixonline-scale.github.io/teamflow-website"
TZ = pytz.timezone("Europe/Zurich")

TEAMS = ["Marketing Team", "Safe Offers Team", "ReSell Team", "New Sales Team", "Warehouse Team"]
SUMMARY_TEAMS = ["Marketing Team", "ReSell Team", "New Sales Team", "Warehouse Team"]

MOTIVATIONS = [
    "🌅 Good morning! Today is a new opportunity to do great work. Let's make it count! 💪",
    "🔥 Rise and shine! Every big achievement starts with the decision to try. Go get it!",
    "⚡ A new day, a new chance to crush your goals. Your team is counting on you!",
    "🚀 Success is built one day at a time. Start strong today!",
    "💡 Great things never come from comfort zones. Push yourself today!",
    "🎯 Focus on what matters. Small steps every day lead to big results.",
    "🌟 You've got what it takes. Make today your best day yet!",
]

SUMMARY_QUESTIONS = {
    "Marketing Team": "📢 *Marketing Team Daily Summary*\n\nPlease share:\n• Campaigns running today\n• Leads generated\n• Any blockers?",
    "ReSell Team": "🔄 *ReSell Team Daily Summary*\n\nPlease share:\n• Items relisted today\n• Sales closed\n• Pending follow-ups?",
    "New Sales Team": "💼 *New Sales Team Daily Summary*\n\nPlease share:\n• Prospects contacted\n• Deals in progress\n• Closes today?",
    "Warehouse Team": "📦 *Warehouse Team Daily Summary*\n\nPlease share:\n• Orders processed\n• Stock issues\n• Shipments sent?",
}

def load():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {"users": {}, "sessions": {}, "todos": {}, "daily": {}, "managers": [], "groups": [], "group_teams": {}, "group_names": {}}

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

# ─── COMMANDS ────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🌐 Open TeamFlow Website", url=WEBSITE_URL)]]
    await update.message.reply_text(
        "👋 Welcome to *TeamFlow Scale Bot!*\n\n"
        "To get started, type:\n`/register Your Name`\n\n"
        "📋 *Commands:*\n"
        "/clockin — Clock in\n/clockout — Clock out\n"
        "/status — Your status\n/tasks — Your tasks\n"
        "/addtask — Add a task\n/daily — Daily routines\n"
        "/adddaily — Add routine\n/report — Weekly report\n"
        "/goals — Set daily goals\n\n"
        "🔐 Admin: /manager PASSWORD",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def setup_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ This command only works in groups.")
        return
    data = load()
    chat_id = str(update.effective_chat.id)
    chat_name = update.effective_chat.title or "Unknown Group"
    if chat_id not in data.get("groups", []):
        data.setdefault("groups", []).append(chat_id)
        data.setdefault("group_names", {})[chat_id] = chat_name
        save(data)
        await update.message.reply_text(
            f"✅ *{chat_name}* registered!\n\n"
            f"This group will receive:\n"
            f"• 🌅 Morning motivation (9:00)\n"
            f"• 📋 Daily team summaries (14:00, Mon-Fri)\n"
            f"• 📊 Weekly reports (Sunday 16:00)\n\n"
            f"Admin: use /setgroupteam to assign teams.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"✅ *{chat_name}* is already registered!", parse_mode="Markdown")

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
    data["users"][uid] = {"name": name, "registered": today(), "clocked_in": False, "clock_start": None, "clock_start_ts": None, "team": "", "goals": [], "goals_date": ""}
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
    data["users"][uid]["clocked_in"] = True
    data["users"][uid]["clock_start"] = now.strftime("%H:%M")
    data["users"][uid]["clock_start_ts"] = now.timestamp()
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
        await update.message.reply_text("⚠️ Not clocked in. Type `/clockin`", parse_mode="Markdown")
        return
    now = now_zurich()
    start_time = user["clock_start"]
    duration = now.timestamp() - user["clock_start_ts"]
    data["sessions"][uid].append({"date": today(), "start": start_time, "end": now.strftime("%H:%M"), "duration_sec": duration})
    data["users"][uid]["clocked_in"] = False
    data["users"][uid]["clock_start"] = None
    data["users"][uid]["clock_start_ts"] = None
    save(data)
    await update.message.reply_text(
        f"■ *Clocked out!*\n\n👤 {user['name']}\n🕐 {start_time} → {now.strftime('%H:%M')}\n⏱ Duration: *{fmt_dur(duration)}*\n\nGreat work! 👋",
        parse_mode="Markdown"
    )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    today_sessions = [s for s in data["sessions"].get(uid, []) if s["date"] == today()]
    today_sec = get_today_sec(data, uid)
    st = f"🟢 *Online* — since {user['clock_start']}" if user["clocked_in"] else "🔴 *Offline*"
    todos = data["todos"].get(uid, [])
    done = sum(1 for t in todos if t.get("done"))
    await update.message.reply_text(
        f"📊 *{user['name']}*\n🏷 {user.get('team','No team')}\n\n{st}\n⏱ Today: *{fmt_dur(today_sec)}*\n✅ Tasks: *{done}/{len(todos)}*",
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
        await update.message.reply_text("📋 No tasks yet.\n\nAdd: `/addtask Task name`", parse_mode="Markdown")
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
    await update.message.reply_text(f"✅ Task added: *{text}*\n{pri_txt[pri]} priority", parse_mode="Markdown")

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
        await update.message.reply_text(f"🎯 Goal set: *{goal}*\n\nYou've got this! 💪", parse_mode="Markdown")
    else:
        goals = data["users"][uid].get("goals", [])
        if not goals:
            await update.message.reply_text("🎯 No goals yet.\n\nSet one: `/goals Your goal today`", parse_mode="Markdown")
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
    daily_list = data["daily"].get(uid, [])
    if not daily_list:
        await update.message.reply_text("📋 No routines.\n\nAdd: `/adddaily Routine name`", parse_mode="Markdown")
        return
    t = today()
    done = sum(1 for d in daily_list if d.get("done_date") == t)
    pct = int(done / len(daily_list) * 100)
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    lines = [f"📋 *Daily Routines — {user['name']}*\n`{bar}` {pct}%\n"]
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
    await update.message.reply_text(
        f"📊 *Report — {user['name']}*\n🏷 {user.get('team','')}\n📅 {today()}\n\n"
        f"⏱ Today: {fmt_dur(today_sec)}\n⏱ This week: {fmt_dur(week_sec)}\n⏱ Total: {fmt_dur(total_sec)}\n\n"
        f"✅ Tasks: {done_tasks}/{len(todos)}\n📋 Routines today: {daily_done}/{len(daily_list)}",
        parse_mode="Markdown"
    )

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
        "/teamstatus — Team status\n/teamreport — Weekly report\n"
        "/timelog — Time log\n/listgroups — Registered groups",
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
        icon = "🟢" if is_on else "🔴"
        lines.append(f"{icon} *{user['name']}* — {user.get('team','')}\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)}")
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
    names = data.get("group_names", {})
    teams = data.get("group_teams", {})
    lines = ["📋 *Registered Groups:*\n"]
    for gid in groups:
        lines.append(f"• *{names.get(gid, gid)}* — {teams.get(gid, 'All teams')}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load()
    uid = str(query.from_user.id)

    if query.data.startswith("setteam_"):
        team = query.data.replace("setteam_", "")
        if uid in data["users"]:
            data["users"][uid]["team"] = team
            save(data)
            await query.edit_message_text(f"✅ Team set to *{team}*!\n\nType `/clockin` to start! 🚀", parse_mode="Markdown")
        return

    if query.data.startswith("gteam_"):
        parts = query.data.split("_", 2)
        chat_id = parts[1]
        team = parts[2]
        data.setdefault("group_teams", {})[chat_id] = team
        save(data)
        await query.edit_message_text(f"✅ Group assigned to *{team}*!", parse_mode="Markdown")
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
            await query.edit_message_text(f"📋 {done}/{len(daily_list)} completed today.\n\nType /daily for list.", parse_mode="Markdown")

# ─── SCHEDULED JOBS ──────────────────────────────────────────────────────────

async def job_morning_motivation(ctx: ContextTypes.DEFAULT_TYPE):
    """9:00 Zurich — Morning motivation to group only"""
    if not is_weekday():
        return
    data = load()
    import random
    motivation = random.choice(MOTIVATIONS)
    for gid in data.get("groups", []):
        try:
            await ctx.bot.send_message(
                chat_id=int(gid),
                text=f"{motivation}\n\n☀️ *New day, new goals — let's go team!*",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not post to group {gid}: {e}")

async def job_clockin_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    """10:00 Zurich — Private DM to those who haven't clocked in"""
    if not is_weekday():
        return
    data = load()
    for uid, user in data["users"].items():
        if not user.get("clocked_in"):
            today_sessions = [s for s in data["sessions"].get(uid, []) if s["date"] == today()]
            if not today_sessions:
                try:
                    await ctx.bot.send_message(
                        chat_id=int(uid),
                        text=f"⏰ Hey *{user['name']}*, you haven't clocked in yet!\n\nType `/clockin` to start tracking. 💪",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Could not DM {uid}: {e}")

async def job_manager_late_alert(ctx: ContextTypes.DEFAULT_TYPE):
    """10:30 Zurich — Alert manager about who hasn't clocked in"""
    if not is_weekday():
        return
    data = load()
    late = []
    for uid, user in data["users"].items():
        if not user.get("clocked_in"):
            today_sessions = [s for s in data["sessions"].get(uid, []) if s["date"] == today()]
            if not today_sessions:
                late.append(f"• {user['name']} — {user.get('team','')}")
    if late:
        msg = f"🚨 *Late Clock-in Alert — 10:30*\n\nThese members haven't started yet:\n\n" + "\n".join(late)
        for mgr_uid in data.get("managers", []):
            try:
                await ctx.bot.send_message(chat_id=int(mgr_uid), text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Could not DM manager {mgr_uid}: {e}")

async def job_daily_summary_groups(ctx: ContextTypes.DEFAULT_TYPE):
    """14:00 Zurich — Daily summary prompts to groups"""
    if not is_weekday():
        return
    data = load()
    for gid in data.get("groups", []):
        assigned_team = data.get("group_teams", {}).get(gid, "ALL")
        teams_to_post = SUMMARY_TEAMS if assigned_team == "ALL" else ([assigned_team] if assigned_team in SUMMARY_TEAMS else [])
        for team in teams_to_post:
            question = SUMMARY_QUESTIONS.get(team, f"📋 *{team} Daily Summary*\n\nPlease share your update!")
            try:
                await ctx.bot.send_message(chat_id=int(gid), text=question, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Could not post to group {gid}: {e}")

async def job_overdue_tasks(ctx: ContextTypes.DEFAULT_TYPE):
    """16:00 Zurich — Private DM about high priority pending tasks"""
    if not is_weekday():
        return
    data = load()
    for uid, user in data["users"].items():
        todos = data["todos"].get(uid, [])
        overdue = [t for t in todos if not t.get("done") and t.get("pri") == "h"]
        if overdue:
            task_list = "\n".join([f"• 🔴 {t['text']}" for t in overdue[:5]])
            try:
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=f"⚠️ *{user['name']}*, you have *{len(overdue)}* high priority task(s) pending:\n\n{task_list}\n\nType `/tasks` to manage them! 💪",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not DM {uid}: {e}")

async def job_eod_personal_summary(ctx: ContextTypes.DEFAULT_TYPE):
    """17:30 Zurich — End of day personal summary DM"""
    if not is_weekday():
        return
    data = load()
    for uid, user in data["users"].items():
        today_sec = get_today_sec(data, uid)
        todos = data["todos"].get(uid, [])
        done_tasks = sum(1 for t in todos if t.get("done"))
        daily_list = data["daily"].get(uid, [])
        daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
        goals = user.get("goals", []) if user.get("goals_date") == today() else []
        goals_txt = "\n".join([f"• {g}" for g in goals]) if goals else "No goals set today"
        try:
            await ctx.bot.send_message(
                chat_id=int(uid),
                text=f"🌆 *End of Day Summary — {user['name']}*\n📅 {today()}\n\n"
                     f"⏱ Hours worked: *{fmt_dur(today_sec)}*\n"
                     f"✅ Tasks completed: *{done_tasks}/{len(todos)}*\n"
                     f"📋 Routines done: *{daily_done}/{len(daily_list)}*\n\n"
                     f"🎯 *Today's Goals:*\n{goals_txt}\n\n"
                     f"Great work today! Don't forget to `/clockout` if you haven't! 👋",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not DM {uid}: {e}")

async def job_clockout_reminder(ctx: ContextTypes.DEFAULT_TYPE):
    """18:00 Zurich — Private DM to those still clocked in"""
    if not is_weekday():
        return
    data = load()
    for uid, user in data["users"].items():
        if user.get("clocked_in"):
            try:
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=f"🔔 *{user['name']}*, you're still clocked in!\n\n🕐 Started: {user['clock_start']}\n\nDon't forget to `/clockout`! 👋",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not DM {uid}: {e}")

async def job_manager_daily_digest(ctx: ContextTypes.DEFAULT_TYPE):
    """18:30 Zurich — Daily digest DM to manager"""
    if not is_weekday():
        return
    data = load()
    if not data["users"]:
        return
    online = sum(1 for u in data["users"].values() if u.get("clocked_in"))
    total_sec = sum(get_today_sec(data, uid) for uid in data["users"])
    total_tasks = sum(len(data["todos"].get(uid, [])) for uid in data["users"])
    done_tasks = sum(sum(1 for t in data["todos"].get(uid, []) if t.get("done")) for uid in data["users"])

    lines = [
        f"📊 *Daily Manager Digest — {today()}*\n",
        f"👥 Members: {len(data['users'])} | Still online: {online}",
        f"⏱ Total team hours: *{fmt_dur(total_sec)}*",
        f"✅ Tasks: *{done_tasks}/{total_tasks}*\n",
        "*Individual breakdown:*"
    ]
    for uid, user in data["users"].items():
        sec = get_today_sec(data, uid)
        todos = data["todos"].get(uid, [])
        done = sum(1 for t in todos if t.get("done"))
        is_on = "🟢" if user.get("clocked_in") else "🔴"
        lines.append(f"{is_on} *{user['name']}* — {fmt_dur(sec)} | {done}/{len(todos)} tasks")

    msg = "\n".join(lines)
    for mgr_uid in data.get("managers", []):
        try:
            await ctx.bot.send_message(chat_id=int(mgr_uid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Could not DM manager {mgr_uid}: {e}")

async def job_weekly_personal_report(ctx: ContextTypes.DEFAULT_TYPE):
    """Monday 8:00 Zurich — Personal weekly recap DM"""
    data = load()
    week_ago = (now_zurich() - timedelta(days=7)).strftime("%Y-%m-%d")
    for uid, user in data["users"].items():
        sessions = data["sessions"].get(uid, [])
        week_sec = sum(s["duration_sec"] for s in sessions if s["date"] >= week_ago)
        todos = data["todos"].get(uid, [])
        done = sum(1 for t in todos if t.get("done"))
        try:
            await ctx.bot.send_message(
                chat_id=int(uid),
                text=f"📅 *Weekly Recap — {user['name']}*\n🏷 {user.get('team','')}\n\n"
                     f"⏱ Hours last week: *{fmt_dur(week_sec)}*\n"
                     f"✅ Tasks completed: *{done}/{len(todos)}*\n\n"
                     f"New week, new goals! 🚀\nSet yours: `/goals Your goal this week`",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not DM {uid}: {e}")

async def job_weekly_report_groups(ctx: ContextTypes.DEFAULT_TYPE):
    """Sunday 16:00 Zurich — Weekly report to groups + manager"""
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
            logger.warning(f"Could not post to group {gid}: {e}")

    for mgr_uid in data.get("managers", []):
        try:
            await ctx.bot.send_message(chat_id=int(mgr_uid), text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Could not DM manager {mgr_uid}: {e}")

# ─── MAIN ────────────────────────────────────────────────────────────────────

async def run():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setup", setup_group))
    app.add_handler(CommandHandler("setgroupteam", set_group_team))
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
    app.add_handler(CommandHandler("manager", manager_login))
    app.add_handler(CommandHandler("teamstatus", teamstatus))
    app.add_handler(CommandHandler("teamreport", teamreport))
    app.add_handler(CommandHandler("timelog", timelog))
    app.add_handler(CommandHandler("listgroups", list_groups))
    app.add_handler(CallbackQueryHandler(button_callback))

    jq = app.job_queue
    # Group jobs
    jq.run_daily(job_morning_motivation,   time=datetime.strptime("09:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_daily_summary_groups, time=datetime.strptime("14:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_weekly_report_groups, time=datetime.strptime("16:00", "%H:%M").replace(tzinfo=TZ).timetz(), days=(6,))

    # Personal DM jobs
    jq.run_daily(job_clockin_reminder,     time=datetime.strptime("10:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_overdue_tasks,        time=datetime.strptime("16:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_eod_personal_summary, time=datetime.strptime("17:30", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_clockout_reminder,    time=datetime.strptime("18:00", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_weekly_personal_report, time=datetime.strptime("08:00", "%H:%M").replace(tzinfo=TZ).timetz(), days=(0,))

    # Manager jobs
    jq.run_daily(job_manager_late_alert,   time=datetime.strptime("10:30", "%H:%M").replace(tzinfo=TZ).timetz())
    jq.run_daily(job_manager_daily_digest, time=datetime.strptime("18:30", "%H:%M").replace(tzinfo=TZ).timetz())

    print("✅ TeamFlow bot started with all scheduled jobs!")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run())
