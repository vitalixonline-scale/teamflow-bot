import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
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
    uid = str(uid)
    if uid not in data["users"]:
        return None
    return data["users"][uid]

def is_manager(data, uid):
    return str(uid) in data.get("managers", [])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Dobrodošao/la u *TeamFlow Scale Bot!*\n\n"
        "Da se registriraš, napiši:\n"
        "`/register Ime Prezime`\n\n"
        "Npr: `/register Ana Kovač`\n\n"
        "📋 *Dostupne komande:*\n"
        "/clockin — Prijava početka rada\n"
        "/clockout — Odjava i zapis vremena\n"
        "/status — Tvoj trenutni status\n"
        "/tasks — Tvoji zadaci\n"
        "/addtask — Dodaj zadatak\n"
        "/daily — Dnevne rutine\n"
        "/adddaily — Dodaj dnevnu rutinu\n"
        "/report — Tvoj sedmični report\n"
        "/manager — Admin prijava",
        parse_mode="Markdown"
    )

async def register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not ctx.args:
        await update.message.reply_text("❌ Napiši: `/register Ime Prezime`", parse_mode="Markdown")
        return
    name = " ".join(ctx.args)
    if uid in data["users"]:
        await update.message.reply_text(f"✅ Već si registriran/a kao *{data['users'][uid]['name']}*", parse_mode="Markdown")
        return
    data["users"][uid] = {"name": name, "registered": today(), "clocked_in": False, "clock_start": None}
    data["sessions"][uid] = []
    data["todos"][uid] = []
    data["daily"][uid] = []
    save(data)
    await update.message.reply_text(
        f"✅ Registriran/a si kao *{name}*!\n\nPočni s `/clockin` kad počneš raditi! 🚀",
        parse_mode="Markdown"
    )

async def clockin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Nisi registriran/a. Napiši `/register Ime Prezime`", parse_mode="Markdown")
        return
    if user["clocked_in"]:
        await update.message.reply_text(f"⚠️ Već si prijavljen/a od *{user['clock_start']}*.\nNapiši `/clockout` za odjavu.", parse_mode="Markdown")
        return
    now = datetime.now()
    data["users"][uid]["clocked_in"] = True
    data["users"][uid]["clock_start"] = now.strftime("%H:%M")
    data["users"][uid]["clock_start_ts"] = now.timestamp()
    save(data)
    await update.message.reply_text(
        f"▶️ *Prijavljeni ste!*\n\n"
        f"👤 {user['name']}\n"
        f"🕐 Početak: *{now.strftime('%H:%M')}*\n"
        f"📅 Datum: {today()}\n\n"
        f"Napiši `/clockout` kad završiš. Sretan rad! 💪",
        parse_mode="Markdown"
    )

async def clockout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return
    if not user["clocked_in"]:
        await update.message.reply_text("⚠️ Nisi prijavljen/a. Napiši `/clockin`", parse_mode="Markdown")
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
        f"■ *Odjavljeni ste!*\n\n"
        f"👤 {user['name']}\n"
        f"🕐 {start_time} → {now.strftime('%H:%M')}\n"
        f"⏱ Ukupno: *{fmt_dur(duration)}*\n\n"
        f"Odličan rad! Vidimo se sutra. 👋",
        parse_mode="Markdown"
    )

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return
    today_sessions = [s for s in data["sessions"].get(uid, []) if s["date"] == today()]
    today_sec = sum(s["duration_sec"] for s in today_sessions)
    if user["clocked_in"] and user.get("clock_start_ts"):
        today_sec += datetime.now().timestamp() - user["clock_start_ts"]
        st = f"🟢 *Online* — radi od {user['clock_start']}"
    else:
        st = "🔴 *Offline*"
    todos = data["todos"].get(uid, [])
    done = sum(1 for t in todos if t.get("done"))
    await update.message.reply_text(
        f"📊 *Status — {user['name']}*\n\n"
        f"{st}\n"
        f"⏱ Danas: *{fmt_dur(today_sec)}*\n"
        f"📋 Sesija danas: *{len(today_sessions) + (1 if user['clocked_in'] else 0)}*\n"
        f"✅ Zadaci: *{done}/{len(todos)}*",
        parse_mode="Markdown"
    )

async def tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return
    todos = data["todos"].get(uid, [])
    if not todos:
        await update.message.reply_text("📋 Nemaš zadataka.\n\nDodaj: `/addtask Naziv`", parse_mode="Markdown")
        return
    pri = {"h": "🔴", "m": "🟡", "l": "🟢"}
    lines = [f"📋 *Zadaci — {user['name']}*\n"]
    keyboard = []
    for i, t in enumerate(todos):
        check = "✅" if t.get("done") else "⬜"
        lines.append(f"{check} {pri.get(t.get('pri','m'),'🟡')} {t['text']}")
        keyboard.append([InlineKeyboardButton(f"{check} {t['text'][:35]}", callback_data=f"toggle_{i}")])
    keyboard.append([InlineKeyboardButton("🗑 Obriši završene", callback_data="delete_done")])
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def addtask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("❌ Napiši: `/addtask Naziv #visoki/#srednji/#niski`", parse_mode="Markdown")
        return
    text = " ".join(ctx.args)
    pri = "m"
    if "#visoki" in text:
        pri = "h"
        text = text.replace("#visoki", "").strip()
    elif "#niski" in text:
        pri = "l"
        text = text.replace("#niski", "").strip()
    elif "#srednji" in text:
        text = text.replace("#srednji", "").strip()
    data["todos"][uid].append({"text": text, "pri": pri, "done": False, "created": today()})
    save(data)
    pri_txt = {"h": "🔴 Visoki", "m": "🟡 Srednji", "l": "🟢 Niski"}
    await update.message.reply_text(f"✅ Zadatak dodan: *{text}*\n{pri_txt[pri]} prioritet", parse_mode="Markdown")

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
            s = "✅ Završeno" if todos[idx]["done"] else "⬜ Nije završeno"
            await query.edit_message_text(f"{s}: *{todos[idx]['text']}*\n\nNapiši /tasks za listu.", parse_mode="Markdown")
    elif query.data == "delete_done":
        before = len(data["todos"].get(uid, []))
        data["todos"][uid] = [t for t in data["todos"].get(uid, []) if not t.get("done")]
        save(data)
        await query.edit_message_text(f"🗑 Obrisano {before - len(data['todos'][uid])} zadataka.")
    elif query.data.startswith("daily_"):
        idx = int(query.data.split("_")[1])
        daily = data["daily"].get(uid, [])
        if idx < len(daily):
            daily[idx]["done_date"] = None if daily[idx].get("done_date") == today() else today()
            save(data)
            done = sum(1 for d in daily if d.get("done_date") == today())
            await query.edit_message_text(f"📋 {done}/{len(daily)} završeno danas.\n\nNapiši /daily za listu.", parse_mode="Markdown")

async def daily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return
    daily_list = data["daily"].get(uid, [])
    if not daily_list:
        await update.message.reply_text("📋 Nemaš rutina.\n\nDodaj: `/adddaily Naziv`", parse_mode="Markdown")
        return
    t = today()
    done = sum(1 for d in daily_list if d.get("done_date") == t)
    pct = int(done / len(daily_list) * 100)
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    lines = [f"📋 *Rutine — {user['name']}*\n`{bar}` {pct}%\n"]
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
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text("❌ Napiši: `/adddaily Naziv rutine`", parse_mode="Markdown")
        return
    text = " ".join(ctx.args)
    data["daily"][uid].append({"text": text, "done_date": None})
    save(data)
    await update.message.reply_text(f"✅ Rutina dodana: *{text}*", parse_mode="Markdown")

async def report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)
    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return
    sessions = data["sessions"].get(uid, [])
    today_sec = sum(s["duration_sec"] for s in sessions if s["date"] == today())
    week_sec = sum(s["duration_sec"] for s in sessions if s["date"] >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
    total_sec = sum(s["duration_sec"] for s in sessions)
    if user["clocked_in"] and user.get("clock_start_ts"):
        extra = datetime.now().timestamp() - user["clock_start_ts"]
        today_sec += extra
        week_sec += extra
        total_sec += extra
    todos = data["todos"].get(uid, [])
    done_tasks = sum(1 for t in todos if t.get("done"))
    daily_list = data["daily"].get(uid, [])
    daily_done = sum(1 for d in daily_list if d.get("done_date") == today())
    await update.message.reply_text(
        f"📊 *Report — {user['name']}*\n📅 {today()}\n\n"
        f"⏱ *Radno Vrijeme*\n"
        f"• Danas: {fmt_dur(today_sec)}\n"
        f"• Ovaj tjedan: {fmt_dur(week_sec)}\n"
        f"• Ukupno: {fmt_dur(total_sec)}\n\n"
        f"✅ *Zadaci*\n"
        f"• Završeno: {done_tasks}/{len(todos)}\n\n"
        f"📋 *Dnevne Rutine Danas*\n"
        f"• {daily_done}/{len(daily_list)} završeno",
        parse_mode="Markdown"
    )

async def manager_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or ctx.args[0] != MANAGER_PASSWORD:
        await update.message.reply_text("🔐 Napiši: `/manager LOZINKA`", parse_mode="Markdown")
        return
    data = load()
    uid = str(update.effective_user.id)
    if uid not in data.get("managers", []):
        data.setdefault("managers", []).append(uid)
        save(data)
    await update.message.reply_text(
        "✅ *Admin pristup odobren!*\n\n"
        "/teamstatus — Status cijelog tima\n"
        "/teamreport — Sedmični report tima\n"
        "/timelog — Evidencija radnog vremena",
        parse_mode="Markdown"
    )

async def teamstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Nemaš admin pristup.", parse_mode="Markdown")
        return
    if not data["users"]:
        await update.message.reply_text("👥 Nema registriranih članova.", parse_mode="Markdown")
        return
    online = sum(1 for u in data["users"].values() if u.get("clocked_in"))
    lines = [f"👥 *Status Tima — {today()}*\n🟢 Online: {online}/{len(data['users'])}\n"]
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
        await update.message.reply_text("❌ Nemaš admin pristup.", parse_mode="Markdown")
        return
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [f"📊 *Sedmični Report Tima*\n📅 {week_ago} → {today()}\n"]
    total = 0
    for uid_m, user in data["users"].items():
        sec = sum(s["duration_sec"] for s in data["sessions"].get(uid_m, []) if s["date"] >= week_ago)
        total += sec
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        pct = f"{int(done/len(todos)*100)}%" if todos else "—"
        lines.append(f"👤 *{user['name']}*\n   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)} ({pct})")
    lines.append(f"\n⏱ *Ukupno tim: {fmt_dur(total)}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def timelog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Nemaš admin pristup.", parse_mode="Markdown")
        return
    lines = [f"⏱ *Evidencija — {today()}*\n"]
    found = False
    for uid_m, user in data["users"].items():
        sessions = [s for s in data["sessions"].get(uid_m, []) if s["date"] == today()]
        if user.get("clocked_in") and user.get("clock_start_ts"):
            sessions.append({
                "start": user["clock_start"],
                "end": "● sada",
                "duration_sec": datetime.now().timestamp() - user["clock_start_ts"]
            })
        if sessions:
            found = True
            lines.append(f"👤 *{user['name']}*")
            for s in sessions:
                lines.append(f"   {s['start']} → {s['end']} | {fmt_dur(s['duration_sec'])}")
    if not found:
        lines.append("Nema sesija danas.")
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
    print("✅ TeamFlow bot pokrenut!")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(run())
