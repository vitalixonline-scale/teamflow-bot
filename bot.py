import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
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

def load():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {"users": {}, "sessions": {}, "todos": {}, "daily": {}, "managers": []}

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def today():
    return datetime.now().strftime("%Y-%m-%d")

def fmt_dur(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"

def get_user(data, uid):
    return data["users"].get(str(uid))

def is_manager(data, uid):
    return str(uid) in data.get("managers", [])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *TeamFlow Scale Bot!*\n\n"
        "To get started, type:\n"
        "`/register Your Name`\n\n"
        "Example: `/register Marcus`\n\n"
        "📋 *Commands:*\n"
        "/clockin — Clock in\n"
        "/clockout — Clock out\n"
        "/status — Your status\n"
        "/tasks — Your tasks\n"
        "/addtask — Add a task\n"
        "/daily — Daily routines\n"
        "/adddaily — Add routine\n"
        "/report — Weekly report",
        parse_mode="Markdown"
    )

async def register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not ctx.args:
        await update.message.reply_text("❌ Type: `/register Your Name`\n\nExample: `/register Marcus`", parse_mode="Markdown")
        return
    name = " ".join(ctx.args)
    if uid in data["users"]:
        await update.message.reply_text(
            f"✅ Already registered as *{data['users'][uid]['name']}*!\n\nType `/clockin` to start working.",
            parse_mode="Markdown"
        )
        return
    data["users"][uid] = {
        "name": name,
        "registered": today(),
        "clocked_in": False,
        "clock_start": None,
        "clock_start_ts": None
    }
    data["sessions"][uid] = []
    data["todos"][uid] = []
    data["daily"][uid] = []
    save(data)
    await update.message.reply_text(
        f"✅ Welcome, *{name}*! 🎉\n\n"
        f"You're all set. Here's what you can do:\n\n"
        f"▶️ `/clockin` — Start your workday\n"
        f"■ `/clockout` — End your workday\n"
        f"📋 `/tasks` — Manage your tasks\n"
        f"📊 `/report` — See your stats",
        parse_mode="Markdown"
    )

async def clockin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered yet.\n\nType `/register Your Name` to get started.", parse_mode="Markdown")
        return
    if user["clocked_in"]:
        await update.message.reply_text(f"⚠️ Already clocked in since *{user['clock_start']}*.\nType `/clockout` to clock out.", parse_mode="Markdown")
        return
    now = datetime.now()
    data["users"][uid]["clocked_in"] = True
    data["users"][uid]["clock_start"] = now.strftime("%H:%M")
    data["users"][uid]["clock_start_ts"] = now.timestamp()
    save(data)
    await update.message.reply_text(
        f"▶️ *Clocked in!*\n\n"
        f"👤 {user['name']}\n"
        f"🕐 Start: *{now.strftime('%H:%M')}*\n"
        f"📅 {today()}\n\n"
        f"Good work! Type `/clockout` when done. 💪",
        parse_mode="Markdown"
    )

async def clockout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered. Type `/register Your Name`", parse_mode="Markdown")
        return
    if not user["clocked_in"]:
        await update.message.reply_text("⚠️ Not clocked in. Type `/clockin` to start.", parse_mode="Markdown")
        return
    now = datetime.now()
    start_time = user["clock_start"]
    duration = now.timestamp() - user["clock_start_ts"]
    data["sessions"][uid].append({
        "date": today(),
        "start": start_time,
        "end": now.strftime("%H:%M"),
        "duration_sec": duration
    })
    data["users"][uid]["clocked_in"] = False
    data["users"][uid]["clock_start"] = None
    data["users"][uid]["clock_start_ts"] = None
    save(data)
    await update.message.reply_text(
        f"■ *Clocked out!*\n\n"
        f"👤 {user['name']}\n"
        f"🕐 {start_time} → {now.strftime('%H:%M')}\n"
        f"⏱ Duration: *{fmt_dur(duration)}*\n\n"
        f"Great work! See you tomorrow. 👋",
        parse_mode="Markdown"
    )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered. Type `/register Your Name`", parse_mode="Markdown")
        return
    today_sessions = [s for s in data["sessions"].get(uid, []) if s["date"] == today()]
    today_sec = sum(s["duration_sec"] for s in today_sessions)
    if user["clocked_in"] and user.get("clock_start_ts"):
        today_sec += datetime.now().timestamp() - user["clock_start_ts"]
        st = f"🟢 *Online* — since {user['clock_start']}"
    else:
        st = "🔴 *Offline*"
    todos = data["todos"].get(uid, [])
    done = sum(1 for t in todos if t.get("done"))
    await update.message.reply_text(
        f"📊 *{user['name']}*\n\n"
        f"{st}\n"
        f"⏱ Today: *{fmt_dur(today_sec)}*\n"
        f"📋 Sessions: *{len(today_sessions) + (1 if user['clocked_in'] else 0)}*\n"
        f"✅ Tasks: *{done}/{len(todos)}*",
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
        await update.message.reply_text("📋 No tasks yet.\n\nAdd one: `/addtask Task name`", parse_mode="Markdown")
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

async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load()
    uid = str(query.from_user.id)
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
        daily = data["daily"].get(uid, [])
        if idx < len(daily):
            daily[idx]["done_date"] = None if daily[idx].get("done_date") == today() else today()
            save(data)
            done = sum(1 for d in daily if d.get("done_date") == today())
            await query.edit_message_text(f"📋 {done}/{len(daily)} completed today.\n\nType /daily for list.", parse_mode="Markdown")

async def daily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Not registered.", parse_mode="Markdown")
        return
    daily_list = data["daily"].get(uid, [])
    if not daily_list:
        await update.message.reply_text("📋 No routines yet.\n\nAdd one: `/adddaily Routine name`", parse_mode="Markdown")
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
    today_sec = sum(s["duration_sec"] for s in sessions if s["date"] == today())
    week_sec = sum(s["duration_sec"] for s in sessions if s["date"] >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
    total_sec = sum(s["duration_sec"] for s in sessions)
    if user["clocked_in"] and user.get("clock_start_ts"):
        extra = datetime.now().timestamp() - user["clock_start_ts"]
        today_sec += extra; week_sec += extra; total_sec += extra
    todos = data["todos"].get(uid, [])
    done_tasks = sum(1 for t in todos if t.get("done"))
    daily_list = data["daily"].get(uid, [])
    daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
    await update.message.reply_text(
        f"📊 *Report — {user['name']}*\n📅 {today()}\n\n"
        f"⏱ *Working Hours*\n"
        f"• Today: {fmt_dur(today_sec)}\n"
        f"• This week: {fmt_dur(week_sec)}\n"
        f"• Total: {fmt_dur(total_sec)}\n\n"
        f"✅ *Tasks*\n"
        f"• Completed: {done_tasks}/{len(todos)}\n\n"
        f"📋 *Daily Routines*\n"
        f"• {daily_done}/{len(daily_list)} done today",
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
        "/teamstatus — All members status\n"
        "/teamreport — Weekly report\n"
        "/timelog — Time log",
        parse_mode="Markdown"
    )

async def teamstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ No admin access. Type `/manager PASSWORD`", parse_mode="Markdown")
        return
    if not data["users"]:
        await update.message.reply_text("👥 No registered members yet.", parse_mode="Markdown")
        return
    online = sum(1 for u in data["users"].values() if u.get("clocked_in"))
    lines = [f"👥 *Team Status — {today()}*\n🟢 Online: {online}/{len(data['users'])}\n"]
    for uid_m, user in data["users"].items():
        is_on = user.get("clocked_in", False)
        sec = sum(s["duration_sec"] for s in data["sessions"].get(uid_m, []) if s["date"] == today())
        if is_on and user.get("clock_start_ts"):
            sec += datetime.now().timestamp() - user["clock_start_ts"]
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        icon = "🟢" if is_on else "🔴"
        lines.append(f"{icon} *{user['name']}*\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def teamreport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ No admin access.", parse_mode="Markdown")
        return
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [f"📊 *Weekly Team Report*\n📅 {week_ago} → {today()}\n"]
    total = 0
    for uid_m, user in data["users"].items():
        sec = sum(s["duration_sec"] for s in data["sessions"].get(uid_m, []) if s["date"] >= week_ago)
        total += sec
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        pct = f"{int(done/len(todos)*100)}%" if todos else "—"
        lines.append(f"👤 *{user['name']}*\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)} ({pct})")
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
            sessions.append({"start": user["clock_start"], "end": "● now", "duration_sec": datetime.now().timestamp() - user["clock_start_ts"]})
        if sessions:
            found = True
            lines.append(f"👤 *{user['name']}*")
            for s in sessions:
                lines.append(f"   {s['start']} → {s['end']} | {fmt_dur(s['duration_sec'])}")
    if not found:
        lines.append("No sessions today.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def run():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("clockin", clockin))
    app.add_handler(CommandHandler("clockout", clockout))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("addtask", addtask))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("adddaily", adddaily))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("manager", manager_login))
    app.add_handler(CommandHandler("teamstatus", teamstatus))
    app.add_handler(CommandHandler("teamreport", teamreport))
    app.add_handler(CommandHandler("timelog", timelog))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("✅ TeamFlow bot started!")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run())
