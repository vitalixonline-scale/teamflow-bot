import os
import json
import logging
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

# ─── DATA ────────────────────────────────────────────────────────────────────
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

def now_str():
    return datetime.now().strftime("%H:%M")

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

# ─── /start ──────────────────────────────────────────────────────────────────
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
        "/report — Tvoj sedmični report\n"
        "/manager — Admin prijava",
        parse_mode="Markdown"
    )

# ─── /register ───────────────────────────────────────────────────────────────
async def register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    args = ctx.args

    if not args:
        await update.message.reply_text("❌ Napiši: `/register Ime Prezime`", parse_mode="Markdown")
        return

    name = " ".join(args)

    if uid in data["users"]:
        await update.message.reply_text(f"✅ Već si registriran/a kao *{data['users'][uid]['name']}*", parse_mode="Markdown")
        return

    data["users"][uid] = {
        "name": name,
        "registered": today(),
        "clocked_in": False,
        "clock_start": None
    }
    if uid not in data["sessions"]:
        data["sessions"][uid] = []
    if uid not in data["todos"]:
        data["todos"][uid] = []
    if uid not in data["daily"]:
        data["daily"][uid] = []

    save(data)
    await update.message.reply_text(
        f"✅ Registriran/a si kao *{name}*!\n\n"
        f"Sad možeš koristiti sve komande. Počni s `/clockin` kad počneš raditi! 🚀",
        parse_mode="Markdown"
    )

# ─── /clockin ────────────────────────────────────────────────────────────────
async def clockin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)

    if not user:
        await update.message.reply_text("❌ Nisi registriran/a. Napiši `/register Ime Prezime`", parse_mode="Markdown")
        return

    if user["clocked_in"]:
        start_time = user["clock_start"]
        await update.message.reply_text(
            f"⚠️ Već si prijavljen/a od *{start_time}*.\n"
            f"Napiši `/clockout` za odjavu.",
            parse_mode="Markdown"
        )
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

# ─── /clockout ───────────────────────────────────────────────────────────────
async def clockout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)

    if not user:
        await update.message.reply_text("❌ Nisi registriran/a. Napiši `/register Ime Prezime`", parse_mode="Markdown")
        return

    if not user["clocked_in"]:
        await update.message.reply_text("⚠️ Nisi prijavljen/a na rad. Napiši `/clockin` za početak.", parse_mode="Markdown")
        return

    now = datetime.now()
    start_ts = user["clock_start_ts"]
    duration = now.timestamp() - start_ts
    start_time = user["clock_start"]

    session = {
        "date": today(),
        "start": start_time,
        "end": now.strftime("%H:%M"),
        "duration_sec": duration
    }
    data["sessions"][uid].append(session)
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

# ─── /status ─────────────────────────────────────────────────────────────────
async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)

    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return

    today_sessions = [s for s in data["sessions"].get(uid, []) if s["date"] == today()]
    today_sec = sum(s["duration_sec"] for s in today_sessions)

    if user["clocked_in"]:
        current = datetime.now().timestamp() - user["clock_start_ts"]
        today_sec += current
        status_txt = f"🟢 *Online* — radi od {user['clock_start']}"
    else:
        status_txt = "🔴 *Offline*"

    todos = data["todos"].get(uid, [])
    done = sum(1 for t in todos if t.get("done"))

    await update.message.reply_text(
        f"📊 *Status — {user['name']}*\n\n"
        f"{status_txt}\n"
        f"⏱ Danas: *{fmt_dur(today_sec)}*\n"
        f"📋 Sesija danas: *{len(today_sessions) + (1 if user['clocked_in'] else 0)}*\n"
        f"✅ Zadaci: *{done}/{len(todos)}*",
        parse_mode="Markdown"
    )

# ─── /tasks ──────────────────────────────────────────────────────────────────
async def tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)

    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return

    todos = data["todos"].get(uid, [])
    if not todos:
        await update.message.reply_text(
            "📋 Nemaš zadataka.\n\nDodaj prvi: `/addtask Naziv zadatka`",
            parse_mode="Markdown"
        )
        return

    pri_emoji = {"h": "🔴", "m": "🟡", "l": "🟢"}
    lines = [f"📋 *Tvoji zadaci — {user['name']}*\n"]
    for i, t in enumerate(todos):
        check = "✅" if t.get("done") else "⬜"
        pri = pri_emoji.get(t.get("pri", "m"), "🟡")
        lines.append(f"{check} {pri} {t['text']}")

    keyboard = []
    for i, t in enumerate(todos):
        label = f"{'✅' if t.get('done') else '⬜'} {t['text'][:30]}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"toggle_{i}")])
    keyboard.append([InlineKeyboardButton("🗑 Obriši završene", callback_data="delete_done")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── /addtask ────────────────────────────────────────────────────────────────
async def addtask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)

    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return

    if not ctx.args:
        await update.message.reply_text(
            "❌ Napiši: `/addtask Naziv zadatka`\n\nZa prioritet dodaj na kraju: `#visoki` `#srednji` `#niski`",
            parse_mode="Markdown"
        )
        return

    text = " ".join(ctx.args)
    pri = "m"
    if "#visoki" in text:
        pri = "h"; text = text.replace("#visoki", "").strip()
    elif "#niski" in text:
        pri = "l"; text = text.replace("#niski", "").strip()
    elif "#srednji" in text:
        pri = "m"; text = text.replace("#srednji", "").strip()

    data["todos"][uid].append({"text": text, "pri": pri, "done": False, "created": today()})
    save(data)

    pri_txt = {"h": "🔴 Visoki", "m": "🟡 Srednji", "l": "🟢 Niski"}
    await update.message.reply_text(
        f"✅ Zadatak dodan!\n\n📝 *{text}*\n{pri_txt[pri]} prioritet",
        parse_mode="Markdown"
    )

# ─── CALLBACK: toggle task ───────────────────────────────────────────────────
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
            status = "✅ Završeno" if todos[idx]["done"] else "⬜ Označeno kao nije završeno"
            await query.edit_message_text(
                f"{status}: *{todos[idx]['text']}*\n\nNapiši /tasks za cijelu listu.",
                parse_mode="Markdown"
            )

    elif query.data == "delete_done":
        todos = data["todos"].get(uid, [])
        before = len(todos)
        data["todos"][uid] = [t for t in todos if not t.get("done")]
        after = len(data["todos"][uid])
        save(data)
        await query.edit_message_text(f"🗑 Obrisano {before - after} završenih zadataka.")

    elif query.data.startswith("daily_"):
        idx = int(query.data.split("_")[1])
        daily = data["daily"].get(uid, [])
        if idx < len(daily):
            t = today()
            if daily[idx].get("done_date") == t:
                daily[idx]["done_date"] = None
            else:
                daily[idx]["done_date"] = t
            save(data)
            done = sum(1 for d in daily if d.get("done_date") == t)
            await query.edit_message_text(
                f"📋 Rutina ažurirana! {done}/{len(daily)} završeno danas.\n\nNapiši /daily za cijelu listu.",
                parse_mode="Markdown"
            )

# ─── /daily ──────────────────────────────────────────────────────────────────
async def daily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)

    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return

    daily_list = data["daily"].get(uid, [])
    t = today()

    if not daily_list:
        await update.message.reply_text(
            "📋 Nemaš dnevnih rutina.\n\nDodaj: `/adddaily Naziv rutine`",
            parse_mode="Markdown"
        )
        return

    done = sum(1 for d in daily_list if d.get("done_date") == t)
    pct = int(done / len(daily_list) * 100) if daily_list else 0
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)

    lines = [f"📋 *Dnevne rutine — {user['name']}*\n"]
    lines.append(f"`{bar}` {pct}% ({done}/{len(daily_list)})\n")

    keyboard = []
    for i, d in enumerate(daily_list):
        check = "✅" if d.get("done_date") == t else "⬜"
        lines.append(f"{check} {d['text']}")
        label = f"{check} {d['text'][:35]}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"daily_{i}")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ─── /adddaily ───────────────────────────────────────────────────────────────
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

# ─── /report ─────────────────────────────────────────────────────────────────
async def report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    user = get_user(data, uid)

    if not user:
        await update.message.reply_text("❌ Nisi registriran/a.", parse_mode="Markdown")
        return

    sessions = data["sessions"].get(uid, [])
    total_sec = sum(s["duration_sec"] for s in sessions)
    today_sec = sum(s["duration_sec"] for s in sessions if s["date"] == today())

    if user["clocked_in"] and user.get("clock_start_ts"):
        today_sec += datetime.now().timestamp() - user["clock_start_ts"]

    todos = data["todos"].get(uid, [])
    done_tasks = sum(1 for t in todos if t.get("done"))
    daily_list = data["daily"].get(uid, [])
    daily_done = sum(1 for d in daily_list if d.get("done_date") == today())

    # Sessions this week
    week_sessions = [s for s in sessions if s["date"] >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")]
    week_sec = sum(s["duration_sec"] for s in week_sessions)

    await update.message.reply_text(
        f"📊 *Tvoj Report — {user['name']}*\n"
        f"📅 {today()}\n\n"
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

# ─── /manager ────────────────────────────────────────────────────────────────
async def manager_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or ctx.args[0] != MANAGER_PASSWORD:
        await update.message.reply_text(
            "🔐 Za admin pristup napiši:\n`/manager TVOJA_LOZINKA`\n\nLozinku postavi u Render environment varijablu.",
            parse_mode="Markdown"
        )
        return

    data = load()
    uid = str(update.effective_user.id)
    if uid not in data.get("managers", []):
        data.setdefault("managers", []).append(uid)
        save(data)

    await update.message.reply_text(
        "✅ *Admin pristup odobren!*\n\n"
        "📊 Dostupne komande:\n"
        "/teamstatus — Status cijelog tima\n"
        "/teamreport — Sedmični report tima\n"
        "/timelog — Evidencija radnog vremena",
        parse_mode="Markdown"
    )

# ─── /teamstatus ─────────────────────────────────────────────────────────────
async def teamstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)

    if not is_manager(data, uid):
        await update.message.reply_text("❌ Nemaš admin pristup. Napiši `/manager LOZINKA`", parse_mode="Markdown")
        return

    if not data["users"]:
        await update.message.reply_text("👥 Nema registriranih članova.", parse_mode="Markdown")
        return

    lines = [f"👥 *Status Tima — {today()}*\n"]
    online_count = 0

    for uid_m, user in data["users"].items():
        is_on = user.get("clocked_in", False)
        if is_on:
            online_count += 1

        today_sessions = [s for s in data["sessions"].get(uid_m, []) if s["date"] == today()]
        today_sec = sum(s["duration_sec"] for s in today_sessions)
        if is_on and user.get("clock_start_ts"):
            today_sec += datetime.now().timestamp() - user["clock_start_ts"]

        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        status_icon = "🟢" if is_on else "🔴"

        lines.append(
            f"{status_icon} *{user['name']}*\n"
            f"   ⏱ {fmt_dur(today_sec)} | ✅ {done}/{len(todos)} zadataka"
        )

    lines.insert(1, f"🟢 Online: {online_count}/{len(data['users'])}\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── /teamreport ─────────────────────────────────────────────────────────────
async def teamreport(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)

    if not is_manager(data, uid):
        await update.message.reply_text("❌ Nemaš admin pristup.", parse_mode="Markdown")
        return

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [f"📊 *Sedmični Report Tima*\n📅 {week_ago} → {today()}\n"]
    total_team_sec = 0

    for uid_m, user in data["users"].items():
        sessions = [s for s in data["sessions"].get(uid_m, []) if s["date"] >= week_ago]
        sec = sum(s["duration_sec"] for s in sessions)
        total_team_sec += sec
        todos = data["todos"].get(uid_m, [])
        done = sum(1 for t in todos if t.get("done"))
        pct = f"{int(done/len(todos)*100)}%" if todos else "—"

        lines.append(
            f"👤 *{user['name']}*\n"
            f"   ⏱ {fmt_dur(sec)} | ✅ {done}/{len(todos)} ({pct})"
        )

    lines.append(f"\n⏱ *Ukupno tim: {fmt_dur(total_team_sec)}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── /timelog ────────────────────────────────────────────────────────────────
async def timelog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)

    if not is_manager(data, uid):
        await update.message.reply_text("❌ Nemaš admin pristup.", parse_mode="Markdown")
        return

    lines = [f"⏱ *Evidencija Radnog Vremena — {today()}*\n"]
    found = False

    for uid_m, user in data["users"].items():
        today_sessions = [s for s in data["sessions"].get(uid_m, []) if s["date"] == today()]
        if user.get("clocked_in"):
            sec = datetime.now().timestamp() - user["clock_start_ts"]
            today_sessions.append({
                "start": user["clock_start"], "end": "● sada",
                "duration_sec": sec
            })
        if today_sessions:
            found = True
            lines.append(f"👤 *{user['name']}*")
            for s in today_sessions:
                lines.append(f"   {s['start']} → {s['end']} | {fmt_dur(s['duration_sec'])}")

    if not found:
        lines.append("Nema zabilježenih sesija danas.")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).updater(None).build()

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

    print("✅ TeamFlow bot je pokrenut!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
