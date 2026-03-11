import os
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
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

# Daily revenue targets per brand
BRAND_TARGETS = {
    "VSmedic": 5000,
    "Vitalix IT": 5000,
    "Vitalix EU": 0,
}
ROAS_MINIMUM = 3.5

async def announce_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Manager only: /announce Message — sends to all groups"""
    data = load()
    uid = str(update.effective_user.id)
    if not is_manager(data, uid):
        await update.message.reply_text("❌ Only managers can send announcements.", parse_mode="Markdown")
        return
    if not ctx.args:
        await update.message.reply_text(
            "📣 *Announce to all groups:*\n\n`/announce Your message here`\n\nExample:\n`/announce Meeting today at 15:00!`",
            parse_mode="Markdown"
        )
        return
    message = " ".join(ctx.args)
    groups = data.get("groups", [])
    if not groups:
        await update.message.reply_text("❌ No groups registered.", parse_mode="Markdown")
        return
    msg = f"📣 *Announcement from Management*\n\n{message}"
    sent = 0
    for gid in groups:
        try:
            await ctx.bot.send_message(chat_id=int(gid), text=msg, parse_mode="Markdown")
            sent += 1
        except Exception as e:
            logger.warning(f"Group error: {e}")
    await update.message.reply_text(f"✅ Sent to *{sent}* group(s)!", parse_mode="Markdown")

async def targets_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Anyone can check daily brand targets"""
    data = load()
    uid = str(update.effective_user.id)
    
    # Get today's marketing KPIs to show progress
    today_recap = {}
    for uid_m, user in data["users"].items():
        if user.get("team") == "Marketing Team":
            stats = data.get("stats", {}).get(uid_m, {}).get(today(), {})
            if stats.get("revenue"):
                brand = stats.get("account", "General")
                rev = stats.get("revenue", "0").replace("€","")
                try:
                    today_recap[brand] = float(rev)
                except:
                    pass
    
    lines = [f"🎯 *Daily ADS Targets — {today()}*\n"]
    for brand, target in BRAND_TARGETS.items():
        actual = today_recap.get(brand, 0)
        pct = round(actual/target*100) if target > 0 else 0
        bar = "█" * min(10, pct//10) + "░" * max(0, 10 - pct//10)
        status = "✅" if pct >= 100 else "🔥" if pct >= 70 else "⚡" if pct >= 40 else "⏳"
        lines.append(f"{status} *{brand}*")
        lines.append(f"   Target: *{target:,}€*")
        lines.append(f"   Today: *{actual:,.0f}€* ({pct}%)")
        lines.append(f"   `{bar}`")

    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
    await query.answer()  # Always answer first to stop loading spinner
    data = load()
    uid = str(query.from_user.id)

    if query.data.startswith("setteam_"):
        team = query.data.replace("setteam_", "")
        if uid in data["users"]:
            data["users"][uid]["team"] = team
            data["users"][uid]["teams"] = [team]
            if team in DAILY_ROUTINES:
                data["daily"][uid] = [{"text": r, "done_date": None} for r in DAILY_ROUTINES[team]]
            save(data)
            await query.edit_message_text(
                f"✅ Team set to *{team}*!\n\n📋 Daily routines loaded.\n\nType `/clockin` to start! 🚀",
                parse_mode="Markdown"
            )
        return

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
    
    # Find who hasn't clocked in
    not_clocked = []
    for uid, user in data["users"].items():
        if not user.get("clocked_in"):
            today_sessions = [s for s in data["sessions"].get(uid, []) if s["date"] == today()]
            if not today_sessions:
                not_clocked.append(user["name"])
                # Also send personal DM
                try:
                    await ctx.bot.send_message(
                        chat_id=int(uid),
                        text=f"⏰ Hey *{user['name']}*, you haven't clocked in yet!\n\nType `/clockin` to start. 💪",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"DM error: {e}")
    
    # Post in group with bot button
    if not_clocked:
        keyboard = [[InlineKeyboardButton("▶️ Start Working", url="https://t.me/teamflow_scale_bot")]]
        msg = (
            f"⏰ *Good morning, team!*\n\n"
            f"If you haven't clocked in yet — now is the time! 💪\n\n"
            f"👇 Tap below to open the bot and start your workday!"
        )
        for gid in data.get("groups", []):
            try:
                await ctx.bot.send_message(
                    chat_id=int(gid),
                    text=msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.warning(f"Group error: {e}")

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
    
    still_in = []
    for uid, user in data["users"].items():
        if user.get("clocked_in"):
            still_in.append(f"{user['name']} (since {user['clock_start']})")
            # Personal DM
            try:
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=f"🔔 *{user['name']}*, you're still clocked in!\n\n🕐 Since: {user['clock_start']}\n\nDon't forget to `/clockout`! 👋",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"DM error: {e}")
    
    # Post in group if anyone still clocked in
    if still_in:
        keyboard = [[InlineKeyboardButton("■ Clock Out Now", url="https://t.me/teamflow_scale_bot")]]
        msg = (
            f"🔔 *End of Day Reminder!*\n\n"
            f"If you're still working — don't forget to clock out! \n\n"
            f"👇 Tap below to open the bot and log your hours."
        )
        for gid in data.get("groups", []):
            try:
                await ctx.bot.send_message(
                    chat_id=int(gid),
                    text=msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.warning(f"Group error: {e}")

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
    app.add_handler(CommandHandler("announce", announce_cmd))
    app.add_handler(CommandHandler("targets", targets_cmd))

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

    from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

    # Default commands (for unregistered users)
    default_commands = [
        BotCommand("start", "👋 Welcome & open website"),
        BotCommand("register", "📝 Register your account"),
        BotCommand("manager", "🔐 Admin login"),
    ]

    # Member commands (general - all teams)
    member_commands = [
        BotCommand("start", "👋 Open TeamFlow"),
        BotCommand("clockin", "▶️ Clock in"),
        BotCommand("clockout", "■ Clock out"),
        BotCommand("status", "📊 My status"),
        BotCommand("tasks", "✅ My tasks"),
        BotCommand("addtask", "➕ Add task"),
        BotCommand("daily", "📋 Daily routines"),
        BotCommand("goals", "🎯 Set daily goals"),
        BotCommand("report", "📈 My weekly report"),
        BotCommand("meetings", "📅 Today's meetings"),
        BotCommand("targets", "🎯 ADS targets"),
    ]

    # Marketing Team extra commands
    marketing_commands = member_commands + [
        BotCommand("recap", "📢 Log marketing recap"),
        BotCommand("checklinks", "🌐 Check landing pages"),
        BotCommand("adddomain", "➕ Add domain"),
    ]

    # Safe Offers Team extra commands
    safe_offers_commands = member_commands + [
        BotCommand("newoffer", "🎯 New offer checklist"),
        BotCommand("checklinks", "🌐 Check landing pages"),
        BotCommand("adddomain", "➕ Add domain"),
    ]

    # ReSell Team extra commands
    resell_commands = member_commands + [
        BotCommand("resell", "🔄 Log ReSell stats"),
    ]

    # Sales Team extra commands
    sales_commands = member_commands + [
        BotCommand("orders", "💼 Log orders"),
        BotCommand("delivery", "🚚 Log delivery rate"),
    ]

    # Warehouse Team extra commands
    warehouse_commands = member_commands + [
        BotCommand("shipped", "📦 Log shipped orders"),
        BotCommand("stock", "📦 Update stock"),
    ]

    # Manager commands
    manager_commands = [
        BotCommand("start", "👋 Open TeamFlow"),
        BotCommand("teamstatus", "👥 Team live status"),
        BotCommand("teamreport", "📊 Weekly team report"),
        BotCommand("timelog", "⏱ Time log"),
        BotCommand("dailystats", "📈 Today's KPIs"),
        BotCommand("meeting", "📅 Add meeting"),
        BotCommand("meetings", "📅 Today's meetings"),
        BotCommand("announce", "📣 Announce to group"),
        BotCommand("listgroups", "🏢 Registered groups"),
        BotCommand("targets", "🎯 ADS targets"),
        BotCommand("clockin", "▶️ Clock in"),
        BotCommand("clockout", "■ Clock out"),
        BotCommand("status", "📊 My status"),
        BotCommand("report", "📈 My report"),
    ]

    print("✅ TeamFlow bot started with all scheduled jobs!")
    async with app:
        # Set default commands
        await app.bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())

        # Set per-user commands based on team
        data = load()
        for uid, user in data["users"].items():
            team = user.get("team", "")
            if team == "Marketing Team":
                cmds = marketing_commands
            elif team == "Safe Offers Team":
                cmds = safe_offers_commands
            elif team == "ReSell Team":
                cmds = resell_commands
            elif team == "Sales Team":
                cmds = sales_commands
            elif team == "Warehouse Team":
                cmds = warehouse_commands
            else:
                cmds = member_commands
            try:
                await app.bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=int(uid)))
            except Exception as e:
                logger.warning(f"Could not set commands for {uid}: {e}")

        # Set manager commands
        for mgr_uid in data.get("managers", []):
            try:
                await app.bot.set_my_commands(manager_commands, scope=BotCommandScopeChat(chat_id=int(mgr_uid)))
            except Exception as e:
                logger.warning(f"Could not set manager commands for {mgr_uid}: {e}")

        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    import requests
    # Delete any existing webhook and drop pending updates to avoid conflicts
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true")
    except:
        pass
    asyncio.run(run())
