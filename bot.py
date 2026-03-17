"""
TeamFlow Telegram Bot v4.0
━━━━━━━━━━━━━━━━━━━━━━━━━━
Two AI Personas: Omni Sight (operations) + Stratex (research)
Full Notion integration — reads tasks, sends personalized DMs
Scheduled motivations, reminders, task briefings, EOD recaps
Smart error handling — unknown commands redirect to /help in DM
Professional friendly tone — we are a team, not a hierarchy
100% English
"""

import os
import logging
import asyncio
import json
import random
import hashlib
from datetime import datetime, timedelta, time as dtime
from typing import Optional, Dict, List

import pytz
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    PicklePersistence,
)
from telegram.constants import ParseMode
import aiohttp

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_TOKEN = os.getenv("BOT_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"

# Notion Page IDs
TELEGRAM_OUTBOX_PAGE_ID = os.getenv("TELEGRAM_OUTBOX_PAGE_ID", "32541c0c-6404-8162-971f-f78b9609f2aa")
AI_SUGGESTIONS_PAGE_ID = os.getenv("AI_SUGGESTIONS_PAGE_ID", "32441c0c-6404-81b5-bc39-d5b2711cbfe9")
TEAM_DIRECTORY_PAGE_ID = os.getenv("TEAM_DIRECTORY_PAGE_ID", "")

# Notion Task Database IDs (one per hub)
MARKETING_TASKS_DB_ID = os.getenv("MARKETING_TASKS_DB_ID", "")
SALES_TASKS_DB_ID = os.getenv("SALES_TASKS_DB_ID", "")
WAREHOUSE_TASKS_DB_ID = os.getenv("WAREHOUSE_TASKS_DB_ID", "")
SAFE_OFFERS_TASKS_DB_ID = os.getenv("SAFE_OFFERS_TASKS_DB_ID", "")
RESELL_TASKS_DB_ID = os.getenv("RESELL_TASKS_DB_ID", "")

HUB_DB_MAP = {
    "Marketing": MARKETING_TASKS_DB_ID,
    "Sales": SALES_TASKS_DB_ID,
    "Warehouse": WAREHOUSE_TASKS_DB_ID,
    "Safe Offers": SAFE_OFFERS_TASKS_DB_ID,
    "Resell": RESELL_TASKS_DB_ID,
}

# Telegram Group Chat IDs
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")
SAFE_OFFERS_GROUP_ID = os.getenv("SAFE_OFFERS_GROUP_ID")

# Timezone — Zurich
TZ = pytz.timezone(os.getenv("TIMEZONE", "Europe/Zurich"))

# Polling intervals
OUTBOX_POLL_INTERVAL = int(os.getenv("OUTBOX_POLL_INTERVAL", "60"))
DIRECTORY_REFRESH_INTERVAL = int(os.getenv("DIRECTORY_REFRESH_INTERVAL", "300"))

# Authorized admins
OWNER_USERNAMES = {"marcus_agent", "mate_marsic"}

# Google Sheets links (for reports — numbers shown there, not in Telegram)
SHEET_LINKS = {
    "Performance Dashboard": "https://docs.google.com/spreadsheets/d/1uJT1uzfzC-ASiqMpuqZDUL_BxmeJM2Gb6I345pHuQEg",
    "Profit Calculator": "https://docs.google.com/spreadsheets/d/1zvz5R216wSVhYe9nNsaCbEHG14dB-OnfZAKWOdDUbOQ",
    "Inventory Tracking": "https://docs.google.com/spreadsheets/d/1Vj_qmGznS2d1hGZiKSVH7OZnt4MLUIq2wyB_K-37ZA8",
    "Project Tracker": "https://docs.google.com/spreadsheets/d/18MCq8ez7nE3x9eRmEOZGjQ_QYdSCu9QssUodz_m2az4",
    "Daily P/L": "https://docs.google.com/spreadsheets/d/1lKfUVP4JlppVnV4imcStjm2N0JbfX7EUPt3kWw6_v08",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MOTIVATIONAL MESSAGES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MOTIVATION_GENERAL = [
    (
        "New day, new opportunities. Every task you complete "
        "today moves us closer to our goals.\n\nLet's make it count. 💪"
    ),
    (
        "Success isn't built in a day — it's built daily. "
        "Small wins today lead to big results this month.\n\nStay focused, stay sharp. 🎯"
    ),
    (
        "Consistency beats intensity. Show up, do the work, "
        "trust the process.\n\nWe've got this. 🔥"
    ),
    (
        "Every expert was once a beginner. Every pro was once "
        "an amateur. Keep learning, keep growing.\n\nLet's level up today. 📈"
    ),
    (
        "The best teams aren't the ones with the most talent — "
        "they're the ones that execute together.\n\nThat's us. Let's go. 🤝"
    ),
    (
        "Progress, not perfection. Done is better than perfect. "
        "Ship it, improve it, repeat.\n\nTime to execute. ⚡"
    ),
    (
        "Your future self will thank you for the work you put in today. "
        "No shortcuts, no excuses.\n\nLet's build something great. 🏗️"
    ),
    (
        "Focus on what you can control. Plan your priorities, "
        "knock them out one by one.\n\nSimple. Effective. Let's go. ✅"
    ),
]

MOTIVATION_MONDAY = [
    (
        "Monday sets the tone for the whole week. "
        "Plan smart, execute fast, support each other.\n\nLet's go! 🚀"
    ),
    (
        "New week, clean slate. Whatever happened last week stays there. "
        "This week is yours to own.\n\nMake it count. 💎"
    ),
]

MOTIVATION_WEDNESDAY = [
    (
        "We're halfway through the week — great momentum so far. "
        "Keep pushing, the finish line is closer than you think.\n\nYou've got this. ✨"
    ),
    (
        "Midweek check: are you on track with your top priorities? "
        "If not, now's the time to refocus.\n\nSecond half, let's go stronger. 💪"
    ),
]

MOTIVATION_FRIDAY = [
    (
        "Friday energy! Finish strong today and enjoy "
        "a well-deserved weekend knowing you gave 100%%.\n\nAlmost there. 🏁"
    ),
    (
        "End the week like you started it — with purpose. "
        "Wrap up loose ends, update your tasks, finish strong.\n\nWeekend is calling. 🎉"
    ),
]

MOTIVATION_SATURDAY = [
    (
        "Saturday grind. Not everyone shows up on weekends "
        "— that's what separates good from great.\n\nLet's wrap up strong. 💎"
    ),
    (
        "Weekend warriors! A few focused hours today "
        "can set us up for an amazing next week.\n\nLet's make it happen. 🔥"
    ),
]

EOD_MESSAGES = [
    "Great work everyone. Rest up — tomorrow we go again. 🌙",
    "Another day in the books. Recharge and come back strong. 🌙",
    "Well done today, team. Take a break, you've earned it. 🌙",
    "Good effort all around. See you tomorrow, refreshed and ready. 🌙",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEAM DIRECTORY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FALLBACK_TEAM_HANDLES = {
    "marcus_agent": {"name": "Marcus", "department": ["Marketing", "Administration"], "chat_id": None},
    "mate_marsic": {"name": "Mate", "department": ["Marketing", "Administration"], "chat_id": None},
    "nikonbelas": {"name": "Niko", "department": ["Marketing", "Safe Offers"], "chat_id": None},
    "ogiiiiz11": {"name": "Orhan", "department": ["Sales", "Resell"], "chat_id": None},
    "ognjen_89": {"name": "Ognjen", "department": ["Warehouse"], "chat_id": None},
    "lukawolk": {"name": "Luka", "department": ["Safe Offers", "Marketing"], "chat_id": None},
    "cb9999999999": {"name": "Dušan", "department": ["Safe Offers"], "chat_id": None},
    "jomlamladen": {"name": "Mladen", "department": ["Administration"], "chat_id": None},
}

TEAM_HANDLES = dict(FALLBACK_TEAM_HANDLES)

CHAT_IDS_FILE = "chat_ids.json"
PERSISTENCE_FILE = "teamflow_persistence.pkl"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGGING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TeamFlowBot")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHAT ID PERSISTENCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_chat_ids():
    global TEAM_HANDLES
    try:
        if os.path.exists(CHAT_IDS_FILE):
            with open(CHAT_IDS_FILE, "r") as f:
                saved = json.load(f)
                for handle, chat_id in saved.items():
                    if handle in TEAM_HANDLES:
                        TEAM_HANDLES[handle]["chat_id"] = chat_id
                logger.info(f"Loaded {len(saved)} chat IDs from file")
    except Exception as e:
        logger.error(f"Error loading chat IDs: {e}")


def save_chat_ids():
    try:
        data = {h: info["chat_id"] for h, info in TEAM_HANDLES.items() if info["chat_id"]}
        with open(CHAT_IDS_FILE, "w") as f:
            json.dump(data, f)
        logger.info(f"Saved {len(data)} chat IDs to file")
    except Exception as e:
        logger.error(f"Error saving chat IDs: {e}")


def get_chat_id_by_handle(handle: str) -> Optional[int]:
    handle = handle.lstrip("@")
    if handle in TEAM_HANDLES and TEAM_HANDLES[handle]["chat_id"]:
        return TEAM_HANDLES[handle]["chat_id"]
    return None


def get_name_by_handle(handle: str) -> str:
    handle = handle.lstrip("@")
    if handle in TEAM_HANDLES:
        return TEAM_HANDLES[handle]["name"]
    return handle


def get_departments_by_handle(handle: str) -> List[str]:
    handle = handle.lstrip("@")
    if handle in TEAM_HANDLES:
        return TEAM_HANDLES[handle].get("department", ["General"])
    return ["General"]


def is_safe_offers_related(message_text: str) -> bool:
    safe_keywords = [
        "safe offers", "safe offer", "clocking", "landing page",
        "offer structure", "money page", "safe page",
        "luka", "dušan", "dusan", "lukawolk", "cb9999999999",
        "project 2.0", "project 3.0", "project 4.0",
        "vs medic", "vitalix", "mellow mind",
        "creatives", "ads analytics", "media buy",
    ]
    text_lower = message_text.lower()
    return any(kw in text_lower for kw in safe_keywords)


def is_admin(username: str) -> bool:
    return username in OWNER_USERNAMES


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# USER SETTINGS (stored in context.user_data)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEFAULT_SETTINGS = {
    "morning_motivation": True,
    "daily_tasks": True,
    "eod_summary": True,
    "weekly_report": True,
}


def get_user_settings(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "settings" not in context.user_data:
        context.user_data["settings"] = dict(DEFAULT_SETTINGS)
    return context.user_data["settings"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NOTION API CLIENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class NotionClient:
    def __init__(self):
        self.api_key = NOTION_API_KEY
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def get_page_content(self, page_id: str) -> Optional[Dict]:
        url = f"{self.base_url}/blocks/{page_id}/children?page_size=100"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Notion API error {resp.status}: {await resp.text()}")
                    return None

    async def get_block_children(self, block_id: str) -> Optional[Dict]:
        url = f"{self.base_url}/blocks/{block_id}/children?page_size=100"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Notion block children error {resp.status}")
                    return None

    async def query_database(self, database_id: str, filter_obj: Optional[Dict] = None) -> Optional[List[Dict]]:
        """Query a Notion database with optional filter"""
        if not database_id:
            return None
        url = f"{self.base_url}/databases/{database_id}/query"
        payload = {}
        if filter_obj:
            payload["filter"] = filter_obj
        payload["page_size"] = 100

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("results", [])
                else:
                    logger.error(f"Notion DB query error {resp.status}: {await resp.text()}")
                    return None

    async def append_block(self, page_id: str, content: str) -> bool:
        url = f"{self.base_url}/blocks/{page_id}/children"
        payload = {
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"type": "text", "text": {"content": content[:2000]}}
                        ]
                    }
                }
            ]
        }
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=self.headers, json=payload) as resp:
                if resp.status == 200:
                    return True
                else:
                    logger.error(f"Notion append error {resp.status}: {await resp.text()}")
                    return False

    def extract_text_from_blocks(self, blocks: List[Dict]) -> str:
        texts = []
        for block in blocks:
            block_type = block.get("type", "")
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3",
                              "bulleted_list_item", "numbered_list_item"]:
                rich_text = block.get(block_type, {}).get("rich_text", [])
                for rt in rich_text:
                    texts.append(rt.get("plain_text", ""))
            elif block_type == "divider":
                texts.append("---")
            elif block_type == "to_do":
                checked = "✅" if block.get("to_do", {}).get("checked", False) else "⬜"
                rich_text = block.get("to_do", {}).get("rich_text", [])
                text = "".join(rt.get("plain_text", "") for rt in rich_text)
                texts.append(f"{checked} {text}")
        return "\n".join(texts)

    def extract_tasks_from_db_results(self, results: List[Dict]) -> List[Dict]:
        """Extract task info from Notion database query results"""
        tasks = []
        for page in results:
            props = page.get("properties", {})
            task = {}

            # Title (try common names)
            for title_key in ["Task", "Name", "Title", "Entry"]:
                if title_key in props and props[title_key].get("type") == "title":
                    title_arr = props[title_key].get("title", [])
                    task["title"] = "".join(t.get("plain_text", "") for t in title_arr)
                    break

            if not task.get("title"):
                for key, val in props.items():
                    if val.get("type") == "title":
                        title_arr = val.get("title", [])
                        task["title"] = "".join(t.get("plain_text", "") for t in title_arr)
                        break

            # Status
            for status_key in ["Status", "status"]:
                if status_key in props:
                    prop = props[status_key]
                    if prop.get("type") == "select" and prop.get("select"):
                        task["status"] = prop["select"].get("name", "Unknown")
                    elif prop.get("type") == "status" and prop.get("status"):
                        task["status"] = prop["status"].get("name", "Unknown")
                    break

            # Due Date
            for date_key in ["Due Date", "Due", "Date", "Deadline"]:
                if date_key in props and props[date_key].get("type") == "date":
                    date_val = props[date_key].get("date")
                    if date_val and date_val.get("start"):
                        task["due_date"] = date_val["start"]
                    break

            # Priority
            for prio_key in ["Priority", "priority"]:
                if prio_key in props:
                    prop = props[prio_key]
                    if prop.get("type") == "select" and prop.get("select"):
                        task["priority"] = prop["select"].get("name", "")
                    break

            # Assignee
            for assign_key in ["Assignee", "Assigned To", "Owner", "Person"]:
                if assign_key in props:
                    prop = props[assign_key]
                    if prop.get("type") == "people":
                        people = prop.get("people", [])
                        task["assignee"] = ", ".join(p.get("name", "") for p in people)
                    elif prop.get("type") == "rich_text":
                        texts = prop.get("rich_text", [])
                        task["assignee"] = "".join(t.get("plain_text", "") for t in texts)
                    break

            # Hub
            for hub_key in ["Hub", "Department"]:
                if hub_key in props:
                    prop = props[hub_key]
                    if prop.get("type") == "select" and prop.get("select"):
                        task["hub"] = prop["select"].get("name", "")
                    break

            if task.get("title"):
                tasks.append(task)

        return tasks


notion = NotionClient()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NOTION TEAM DIRECTORY SYNC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def sync_team_directory():
    global TEAM_HANDLES

    if not TEAM_DIRECTORY_PAGE_ID:
        logger.info("TEAM_DIRECTORY_PAGE_ID not set — using fallback directory")
        return

    try:
        result = await notion.get_page_content(TEAM_DIRECTORY_PAGE_ID)
        if not result:
            logger.warning("Could not read Team Directory — keeping current")
            return

        blocks = result.get("results", [])
        raw_text = notion.extract_text_from_blocks(blocks)

        if not raw_text.strip():
            logger.warning("Team Directory empty — keeping current")
            return

        new_handles = {}
        lines = raw_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("#"):
                continue
            if line.startswith(("✅ ", "⬜ ")):
                line = line[2:].strip()

            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                handle = parts[0].lstrip("@").strip()
                name = parts[1].strip()
                departments = []
                if len(parts) >= 3:
                    departments = [d.strip() for d in parts[2].split(",") if d.strip()]

                if handle and name:
                    existing_chat_id = None
                    if handle in TEAM_HANDLES:
                        existing_chat_id = TEAM_HANDLES[handle].get("chat_id")

                    new_handles[handle] = {
                        "name": name,
                        "department": departments or ["General"],
                        "chat_id": existing_chat_id,
                    }

        if new_handles:
            old_count = len(TEAM_HANDLES)
            TEAM_HANDLES.clear()
            TEAM_HANDLES.update(new_handles)
            load_chat_ids()
            logger.info(f"Team Directory synced: {len(TEAM_HANDLES)} members (was {old_count})")
        else:
            logger.warning("No valid members parsed — keeping current")

    except Exception as e:
        logger.error(f"Error syncing Team Directory: {e}")


async def refresh_team_directory(context: ContextTypes.DEFAULT_TYPE):
    await sync_team_directory()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TASK FETCHING FROM NOTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def get_tasks_for_member(handle: str) -> List[Dict]:
    """Get all active tasks across all hubs for a team member"""
    all_tasks = []
    name = get_name_by_handle(handle)
    departments = get_departments_by_handle(handle)

    for dept in departments:
        db_id = HUB_DB_MAP.get(dept, "")
        if not db_id:
            continue

        filter_obj = {
            "and": [
                {
                    "property": "Status",
                    "select": {"does_not_equal": "Done"}
                }
            ]
        }

        results = await notion.query_database(db_id, filter_obj)
        if results:
            tasks = notion.extract_tasks_from_db_results(results)
            for t in tasks:
                assignee = t.get("assignee", "").lower()
                if name.lower() in assignee or handle.lower() in assignee:
                    t["hub"] = t.get("hub", dept)
                    all_tasks.append(t)

    return all_tasks


async def get_hub_task_summary(hub_name: str) -> Dict:
    """Get task count summary for a hub"""
    db_id = HUB_DB_MAP.get(hub_name, "")
    if not db_id:
        return {"total": 0, "completed": 0, "in_progress": 0, "overdue": 0, "not_started": 0}

    results = await notion.query_database(db_id)
    if not results:
        return {"total": 0, "completed": 0, "in_progress": 0, "overdue": 0, "not_started": 0}

    tasks = notion.extract_tasks_from_db_results(results)
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    summary = {"total": len(tasks), "completed": 0, "in_progress": 0, "overdue": 0, "not_started": 0}
    for t in tasks:
        status = t.get("status", "").lower()
        if status in ["done", "completed", "complete"]:
            summary["completed"] += 1
        elif status in ["in progress", "in_progress", "doing"]:
            summary["in_progress"] += 1
        else:
            summary["not_started"] += 1

        due = t.get("due_date", "")
        if due and due < today and status not in ["done", "completed", "complete"]:
            summary["overdue"] += 1

    return summary


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MOTIVATION HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_motivation_message() -> str:
    now = datetime.now(TZ)
    weekday = now.weekday()

    if weekday == 0:
        pool = MOTIVATION_MONDAY
    elif weekday == 2:
        pool = MOTIVATION_WEDNESDAY
    elif weekday == 4:
        pool = MOTIVATION_FRIDAY
    elif weekday == 5:
        pool = MOTIVATION_SATURDAY
    else:
        pool = MOTIVATION_GENERAL

    day_seed = now.strftime("%Y-%m-%d")
    random.seed(day_seed)
    msg = random.choice(pool)
    random.seed()
    return msg


def get_eod_message() -> str:
    now = datetime.now(TZ)
    random.seed(now.strftime("%Y-%m-%d-eod"))
    msg = random.choice(EOD_MESSAGES)
    random.seed()
    return msg


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OUTBOX PARSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_outbox_messages(raw_text: str) -> List[Dict]:
    messages = []
    blocks = raw_text.split("---")

    i = 0
    while i < len(blocks):
        block = blocks[i].strip()

        if not block or block.startswith("✅ SENT"):
            i += 1
            continue

        if block.upper().startswith("TO:") or "\nTO:" in block.upper():
            lines = block.split("\n")
            msg = {"to": None, "type": "PERSONAL", "from": "Omni Sight", "date": None, "content": "", "raw": block}
            content_lines = []
            header_done = False

            for line in lines:
                line_stripped = line.strip()
                line_upper = line_stripped.upper()

                if line_upper.startswith("TO:"):
                    msg["to"] = line_stripped[3:].strip()
                elif line_upper.startswith("TYPE:"):
                    msg["type"] = line_stripped[5:].strip().upper()
                elif line_upper.startswith("FROM:"):
                    msg["from"] = line_stripped[5:].strip()
                elif line_upper.startswith("DATE:"):
                    msg["date"] = line_stripped[5:].strip()
                    header_done = True
                elif header_done and line_stripped:
                    content_lines.append(line_stripped)

            if i + 1 < len(blocks):
                next_block = blocks[i + 1].strip()
                if next_block and not next_block.upper().startswith("TO:") and not next_block.startswith("✅ SENT"):
                    msg["content"] = next_block
                    i += 1

            if not msg["content"] and content_lines:
                msg["content"] = "\n".join(content_lines)

            if msg["to"]:
                to_upper = msg["to"].upper()
                if to_upper == "GROUP":
                    msg["type"] = "GROUP"
                elif to_upper == "ADMIN":
                    msg["type"] = "ADMIN"
                elif to_upper == "ESCALATION":
                    msg["type"] = "ESCALATION"

            if msg["to"] and msg["content"]:
                messages.append(msg)

        i += 1

    return messages


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGE SENDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def format_agent_header(agent_name: str) -> str:
    if "stratex" in agent_name.lower():
        return f"🧠 *Stratex*\n{'━' * 20}\n"
    else:
        return f"🔍 *Omni Sight*\n{'━' * 20}\n"


async def send_to_telegram(bot: Bot, message: Dict) -> bool:
    try:
        to = message["to"]
        content = message["content"]
        from_agent = message.get("from", "Omni Sight")

        header = format_agent_header(from_agent)
        full_message = header + content

        if to.upper() == "GROUP":
            if ADMIN_GROUP_ID:
                await bot.send_message(
                    chat_id=int(ADMIN_GROUP_ID),
                    text=full_message,
                    parse_mode=ParseMode.MARKDOWN,
                )

            if SAFE_OFFERS_GROUP_ID and is_safe_offers_related(content):
                await bot.send_message(
                    chat_id=int(SAFE_OFFERS_GROUP_ID),
                    text=full_message,
                    parse_mode=ParseMode.MARKDOWN,
                )
            return True

        elif to.upper() == "ADMIN" or message.get("type") == "ESCALATION":
            escalation_msg = f"🚨 *ESCALATION*\n{'━' * 20}\n{content}"
            if ADMIN_GROUP_ID:
                await bot.send_message(
                    chat_id=int(ADMIN_GROUP_ID),
                    text=escalation_msg,
                    parse_mode=ParseMode.MARKDOWN,
                )
            marcus_id = get_chat_id_by_handle("marcus_agent")
            if marcus_id:
                await bot.send_message(
                    chat_id=marcus_id,
                    text=escalation_msg,
                    parse_mode=ParseMode.MARKDOWN,
                )
            return True

        else:
            handle = to.lstrip("@")
            chat_id = get_chat_id_by_handle(handle)

            if chat_id:
                await bot.send_message(
                    chat_id=chat_id,
                    text=full_message,
                    parse_mode=ParseMode.MARKDOWN,
                )

                if ADMIN_GROUP_ID:
                    admin_msg = f"📨 *DM sent to {get_name_by_handle(handle)}:*\n{content[:500]}"
                    await bot.send_message(
                        chat_id=int(ADMIN_GROUP_ID),
                        text=admin_msg,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                return True
            else:
                logger.warning(f"No chat ID for {handle}. User needs to /start first.")
                return False

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEDULED JOBS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

sent_messages = set()


async def poll_outbox(context: ContextTypes.DEFAULT_TYPE):
    try:
        result = await notion.get_page_content(TELEGRAM_OUTBOX_PAGE_ID)
        if not result:
            return

        blocks = result.get("results", [])
        raw_text = notion.extract_text_from_blocks(blocks)
        messages = parse_outbox_messages(raw_text)

        for msg in messages:
            msg_hash = hash(f"{msg['to']}:{msg['content'][:100]}:{msg.get('date', '')}")

            if msg_hash not in sent_messages:
                success = await send_to_telegram(context.bot, msg)
                if success:
                    sent_messages.add(msg_hash)
                    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
                    await notion.append_block(
                        TELEGRAM_OUTBOX_PAGE_ID,
                        f"✅ SENT — {msg['to']} — {now}"
                    )

        if len(sent_messages) > 1000:
            sent_messages.clear()

    except Exception as e:
        logger.error(f"Error polling outbox: {e}")


async def job_morning_motivation(context: ContextTypes.DEFAULT_TYPE):
    """09:00 — Morning motivation to groups"""
    try:
        motivation = get_motivation_message()
        msg = f"🌅 *Good morning, team!*\n\n{motivation}"

        if ADMIN_GROUP_ID:
            await context.bot.send_message(
                chat_id=int(ADMIN_GROUP_ID), text=msg, parse_mode=ParseMode.MARKDOWN,
            )

        if SAFE_OFFERS_GROUP_ID:
            await context.bot.send_message(
                chat_id=int(SAFE_OFFERS_GROUP_ID), text=msg, parse_mode=ParseMode.MARKDOWN,
            )

        logger.info("Morning motivation sent to groups")
    except Exception as e:
        logger.error(f"Error sending morning motivation: {e}")


async def job_work_start_reminder(context: ContextTypes.DEFAULT_TYPE):
    """09:45 — Work starts in 15 minutes"""
    try:
        msg = (
            "⏰ *Heads up — work starts in 15 minutes!*\n\n"
            "Quick checklist before 10:00:\n"
            "• Check your Notion hub for today's tasks\n"
            "• Review any overnight updates\n"
            "• Set your top 3 priorities for today\n\n"
            "See you at 10:00. Let's go. 🟢"
        )

        if ADMIN_GROUP_ID:
            await context.bot.send_message(
                chat_id=int(ADMIN_GROUP_ID), text=msg, parse_mode=ParseMode.MARKDOWN,
            )

        if SAFE_OFFERS_GROUP_ID:
            await context.bot.send_message(
                chat_id=int(SAFE_OFFERS_GROUP_ID), text=msg, parse_mode=ParseMode.MARKDOWN,
            )

        logger.info("Work start reminder sent")
    except Exception as e:
        logger.error(f"Error sending work start reminder: {e}")


async def job_personal_task_briefing(context: ContextTypes.DEFAULT_TYPE):
    """10:00 — Personal task briefing DM to each member"""
    try:
        today = datetime.now(TZ).strftime("%Y-%m-%d")

        for handle, info in TEAM_HANDLES.items():
            chat_id = info.get("chat_id")
            if not chat_id:
                continue

            name = info["name"]
            departments = info.get("department", ["General"])

            tasks = await get_tasks_for_member(handle)

            if tasks:
                task_lines = []
                overdue_count = 0
                for t in tasks[:10]:
                    title = t.get("title", "Untitled")
                    due = t.get("due_date", "")
                    status = t.get("status", "")

                    line = f"• {title}"
                    if due:
                        line += f" — Due: {due}"
                        if due < today:
                            line += " ⚠️ Overdue"
                            overdue_count += 1
                    if status:
                        line += f" [{status}]"
                    task_lines.append(line)

                tasks_text = "\n".join(task_lines)
                hub_text = ", ".join(departments)

                msg = (
                    f"📋 *Good morning, {name}!*\n\n"
                    f"Here's your focus for today:\n\n"
                    f"*Your Tasks ({hub_text}):*\n"
                    f"{tasks_text}\n"
                )

                if overdue_count > 0:
                    msg += f"\n⚠️ *{overdue_count} overdue task(s)* — please prioritize these.\n"

                msg += "\nIf you need help with anything, just message me here. Have a productive day! 🎯"

            else:
                msg = (
                    f"📋 *Good morning, {name}!*\n\n"
                    f"No specific tasks assigned to you right now.\n"
                    f"Check your hub in Notion for updates, or ask "
                    f"your team if there's anything you can help with.\n\n"
                    f"Have a great day! 🎯"
                )

            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.error(f"Error sending task briefing to {handle}: {e}")

            await asyncio.sleep(0.5)

        logger.info("Personal task briefings sent")
    except Exception as e:
        logger.error(f"Error in personal task briefing job: {e}")


async def job_morning_brief(context: ContextTypes.DEFAULT_TYPE):
    """09:05 — Morning brief from AI Suggestions"""
    try:
        result = await notion.get_page_content(AI_SUGGESTIONS_PAGE_ID)
        if not result:
            return

        blocks = result.get("results", [])
        raw_text = notion.extract_text_from_blocks(blocks)

        today_str = datetime.now(TZ).strftime("%Y-%m-%d")
        brief_text = None

        if "MORNING BRIEF" in raw_text and today_str in raw_text:
            start = raw_text.find("MORNING BRIEF")
            end = raw_text.find("WEEKLY SUMMARY", start + 1)
            if end == -1:
                end = raw_text.find("SCRIPT IMPROVEMENT", start + 1)
            if end == -1:
                end = min(start + 2000, len(raw_text))
            brief_text = raw_text[start:end].strip()

        if brief_text:
            header = format_agent_header("Omni Sight")
            leaders_msg = f"{header}📋 *Daily Brief*\n{'━' * 25}\n{brief_text[:3500]}"

            if ADMIN_GROUP_ID:
                await context.bot.send_message(
                    chat_id=int(ADMIN_GROUP_ID), text=leaders_msg, parse_mode=ParseMode.MARKDOWN,
                )

            if SAFE_OFFERS_GROUP_ID:
                so_lines = []
                for line in brief_text.split("\n"):
                    if any(kw in line.lower() for kw in [
                        "safe offers", "luka", "dušan", "dusan",
                        "all hubs", "overall", "completion", "overdue", "focus"
                    ]):
                        so_lines.append(line)

                if so_lines:
                    so_msg = f"{header}📋 *Daily Brief — Safe Offers*\n{'━' * 25}\n" + "\n".join(so_lines)
                    await context.bot.send_message(
                        chat_id=int(SAFE_OFFERS_GROUP_ID), text=so_msg[:3500], parse_mode=ParseMode.MARKDOWN,
                    )

            logger.info("Morning brief sent")
        else:
            logger.info("No morning brief found for today")

    except Exception as e:
        logger.error(f"Error sending morning brief: {e}")


async def job_eod_group(context: ContextTypes.DEFAULT_TYPE):
    """18:00 — End of day wrap-up to groups"""
    try:
        eod = get_eod_message()
        msg = (
            f"🌆 *That's a wrap for today!*\n\n"
            f"Great work everyone. Before you sign off:\n"
            f"• Update your task status in Notion\n"
            f"• Note anything blocked or pending\n"
            f"• Quick win? Share it with the team!\n\n"
            f"{eod}"
        )

        if ADMIN_GROUP_ID:
            await context.bot.send_message(
                chat_id=int(ADMIN_GROUP_ID), text=msg, parse_mode=ParseMode.MARKDOWN,
            )

        if SAFE_OFFERS_GROUP_ID:
            await context.bot.send_message(
                chat_id=int(SAFE_OFFERS_GROUP_ID), text=msg, parse_mode=ParseMode.MARKDOWN,
            )

        logger.info("EOD group message sent")
    except Exception as e:
        logger.error(f"Error sending EOD group message: {e}")


async def job_eod_personal(context: ContextTypes.DEFAULT_TYPE):
    """18:15 — Personal end-of-day check DM"""
    try:
        for handle, info in TEAM_HANDLES.items():
            chat_id = info.get("chat_id")
            if not chat_id:
                continue

            name = info["name"]
            tasks = await get_tasks_for_member(handle)

            today = datetime.now(TZ).strftime("%Y-%m-%d")
            completed = sum(1 for t in tasks if t.get("status", "").lower() in ["done", "completed"])
            in_progress = sum(1 for t in tasks if t.get("status", "").lower() in ["in progress", "in_progress", "doing"])
            overdue = sum(1 for t in tasks if t.get("due_date", "") and t["due_date"] < today
                         and t.get("status", "").lower() not in ["done", "completed"])

            if completed > 0 and in_progress == 0 and overdue == 0:
                msg = (
                    f"🌆 *End of day, {name}.*\n\n"
                    f"Amazing work today — all tasks done! 🎉\n\n"
                    f"Enjoy your evening, you've earned it. See you tomorrow! 🌙"
                )
            else:
                msg = (
                    f"🌆 *End of day, {name}.*\n\n"
                    f"Quick check on your tasks:\n\n"
                    f"*Completed:* {completed}\n"
                    f"*Still in progress:* {in_progress}\n"
                )
                if overdue > 0:
                    msg += f"*Overdue:* {overdue} ⚠️\n"

                msg += (
                    f"\nDon't forget to update your task statuses in Notion "
                    f"before signing off.\n\nSee you tomorrow! 🌙"
                )

            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.error(f"Error sending EOD to {handle}: {e}")

            await asyncio.sleep(0.5)

        logger.info("Personal EOD messages sent")
    except Exception as e:
        logger.error(f"Error in personal EOD job: {e}")


async def job_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Monday 10:30 — Weekly report to Admin group"""
    try:
        now = datetime.now(TZ)
        week_num = now.isocalendar()[1]

        hub_lines = []
        for hub_name in ["Marketing", "Sales", "Warehouse", "Safe Offers", "Resell"]:
            summary = await get_hub_task_summary(hub_name)
            if summary["overdue"] > 0:
                status_icon = "🟡" if summary["overdue"] < 3 else "🔴"
            else:
                status_icon = "🟢"

            hub_lines.append(
                f"{status_icon} *{hub_name}* — "
                f"{summary['completed']} completed, "
                f"{summary['in_progress']} in progress"
                + (f", {summary['overdue']} overdue ⚠️" if summary['overdue'] > 0 else "")
            )

        hub_text = "\n".join(hub_lines)

        sheet_lines = []
        for name, url in SHEET_LINKS.items():
            sheet_lines.append(f"📈 [{name}]({url})")
        sheets_text = "\n".join(sheet_lines)

        header = format_agent_header("Omni Sight")
        msg = (
            f"{header}"
            f"📊 *Weekly Report — Week {week_num}*\n"
            f"{'━' * 25}\n\n"
            f"*Hub Overview:*\n{hub_text}\n\n"
            f"*Numbers & Sheets:*\n{sheets_text}\n\n"
            f"Let's make this week count! 🚀"
        )

        if ADMIN_GROUP_ID:
            await context.bot.send_message(
                chat_id=int(ADMIN_GROUP_ID), text=msg[:4000],
                parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True,
            )

        logger.info(f"Weekly report sent (Week {week_num})")
    except Exception as e:
        logger.error(f"Error sending weekly report: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username

    if username and username not in TEAM_HANDLES:
        await sync_team_directory()

    if username and username in TEAM_HANDLES:
        TEAM_HANDLES[username]["chat_id"] = update.effective_chat.id
        save_chat_ids()

        name = TEAM_HANDLES[username]["name"]
        dept_str = ", ".join(TEAM_HANDLES[username]["department"])

        await update.message.reply_text(
            f"👋 *Welcome to TeamFlow, {name}!*\n\n"
            f"I'm your team assistant — I help you stay on top of "
            f"tasks, deadlines, and team updates.\n\n"
            f"*You're registered as:*\n"
            f"📍 Hub: {dept_str}\n"
            f"🔔 Notifications: ON\n\n"
            f"*What I do:*\n"
            f"• 🌅 Start your day with team motivation at 9:00\n"
            f"• 📋 Send you daily task briefings at 10:00\n"
            f"• ⏰ Remind you of deadlines and priorities\n"
            f"• 🌆 Wrap up your day with a summary at 18:00\n"
            f"• 📊 Weekly reports every Monday\n\n"
            f"*Quick start:*\n"
            f"/status — See your current tasks\n"
            f"/help — All available commands\n"
            f"/settings — Customize notifications\n\n"
            f"Let's build something great together! 🚀",
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info(f"Registered {username} with chat_id {update.effective_chat.id}")
    else:
        source = "Notion Team Directory" if TEAM_DIRECTORY_PAGE_ID else "the team directory"
        await update.message.reply_text(
            f"👋 Hi {user.first_name}!\n\n"
            f"Your Telegram username (@{username}) is not in {source}.\n"
            f"Ask an admin to add you and then try /start again.",
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or ""
    is_private = update.effective_chat.type == "private"

    if not is_private:
        bot_username = (await context.bot.get_me()).username
        await update.message.reply_text(
            f"👋 For the full command list, message me privately!\n"
            f"Tap → @{bot_username}",
        )
        return

    msg = (
        "🤖 *TeamFlow — Your Commands*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📋 *Tasks & Status*\n"
        "/status — Your task overview\n"
        "/mytasks — Detailed task list from Notion\n"
        "/week — Weekly summary\n\n"
        "📊 *Information*\n"
        "/brief — Today's briefing\n"
        "/hub — Hub status check\n"
        "  _(marketing, sales, warehouse, safeoffers, resell)_\n\n"
        "⚙️ *Settings*\n"
        "/settings — Notification preferences\n"
        "/help — This message\n\n"
        "💡 *Tip:* Message me anytime — I'm here to help!"
    )

    if is_admin(username):
        msg += (
            "\n\n🔐 *Admin Commands*\n"
            "/setup admin — Set this chat as Admin group\n"
            "/setup safeoffers — Set Safe Offers group\n"
            "/force\\_brief — Force morning brief now\n"
            "/report — Force weekly report now\n"
            "/outbox — Check Outbox status\n"
            "/broadcast — Send message to all members\n"
            "/teamstatus — Team registration overview"
        )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or ""
    name = get_name_by_handle(username)

    await update.message.reply_text("📊 Checking your tasks...")

    tasks = await get_tasks_for_member(username)

    if tasks:
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        total = len(tasks)
        overdue = sum(1 for t in tasks if t.get("due_date", "") and t["due_date"] < today)
        in_progress = sum(1 for t in tasks if t.get("status", "").lower() in ["in progress", "in_progress", "doing"])

        top_tasks = tasks[:5]
        task_lines = []
        for t in top_tasks:
            title = t.get("title", "Untitled")
            due = t.get("due_date", "")
            line = f"• {title}"
            if due:
                line += f" — {due}"
                if due < today:
                    line += " ⚠️"
            task_lines.append(line)

        tasks_text = "\n".join(task_lines)

        msg = (
            f"📊 *Status for {name}*\n\n"
            f"*Active tasks:* {total}\n"
            f"*In progress:* {in_progress}\n"
        )
        if overdue > 0:
            msg += f"*Overdue:* {overdue} ⚠️\n"

        msg += f"\n*Top tasks:*\n{tasks_text}"

        if total > 5:
            msg += f"\n\n_...and {total - 5} more. Use /mytasks for the full list._"
    else:
        msg = (
            f"📊 *Status for {name}*\n\n"
            f"No active tasks found in Notion right now.\n"
            f"Check your hub for updates or ask @Omni\\_Sight for a personalized update."
        )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_mytasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or ""
    name = get_name_by_handle(username)

    await update.message.reply_text("📝 Fetching your full task list...")

    tasks = await get_tasks_for_member(username)

    if tasks:
        today = datetime.now(TZ).strftime("%Y-%m-%d")

        by_hub = {}
        for t in tasks:
            hub = t.get("hub", "General")
            if hub not in by_hub:
                by_hub[hub] = []
            by_hub[hub].append(t)

        msg = f"📝 *All Tasks — {name}*\n{'━' * 25}\n"

        for hub, hub_tasks in by_hub.items():
            msg += f"\n*{hub}:*\n"
            for t in hub_tasks:
                title = t.get("title", "Untitled")
                due = t.get("due_date", "")
                status = t.get("status", "")
                priority = t.get("priority", "")

                line = f"• {title}"
                if priority:
                    line += f" [{priority}]"
                if due:
                    line += f" — Due: {due}"
                    if due < today:
                        line += " ⚠️ OVERDUE"
                if status:
                    line += f" ({status})"
                msg += line + "\n"

        msg += f"\n_Total: {len(tasks)} active tasks_"
    else:
        msg = (
            f"📝 *All Tasks — {name}*\n\n"
            f"No active tasks found.\n"
            f"Check your Notion hub or ask your team lead for updates."
        )

    if len(msg) > 4000:
        await update.message.reply_text(msg[:4000], parse_mode=ParseMode.MARKDOWN)
        if len(msg) > 4000:
            await update.message.reply_text(msg[4000:], parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        hub_input = " ".join(context.args).strip().lower()
        hub_map = {
            "marketing": "Marketing",
            "sales": "Sales",
            "warehouse": "Warehouse",
            "safeoffers": "Safe Offers",
            "safe offers": "Safe Offers",
            "safe_offers": "Safe Offers",
            "resell": "Resell",
        }
        hub_name = hub_map.get(hub_input)
    else:
        msg = "🏢 *Hub Status Overview*\n━━━━━━━━━━━━━━━━━━\n\n"
        for hub_name in ["Marketing", "Sales", "Warehouse", "Safe Offers", "Resell"]:
            summary = await get_hub_task_summary(hub_name)
            if summary["overdue"] > 0:
                icon = "🟡" if summary["overdue"] < 3 else "🔴"
            else:
                icon = "🟢"
            msg += (
                f"{icon} *{hub_name}*\n"
                f"   {summary['completed']} done · {summary['in_progress']} active · "
                f"{summary['overdue']} overdue\n\n"
            )
        msg += "_Use /hub [name] for details (e.g. /hub marketing)_"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return

    if not hub_name:
        await update.message.reply_text(
            "🏢 Available hubs: marketing, sales, warehouse, safeoffers, resell\n\n"
            "Usage: /hub marketing"
        )
        return

    summary = await get_hub_task_summary(hub_name)
    if summary["overdue"] > 0:
        icon = "🟡" if summary["overdue"] < 3 else "🔴"
    else:
        icon = "🟢"

    msg = (
        f"{icon} *{hub_name} Hub Status*\n"
        f"{'━' * 25}\n\n"
        f"*Total tasks:* {summary['total']}\n"
        f"*Completed:* {summary['completed']}\n"
        f"*In progress:* {summary['in_progress']}\n"
        f"*Not started:* {summary['not_started']}\n"
    )
    if summary["overdue"] > 0:
        msg += f"*Overdue:* {summary['overdue']} ⚠️\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or ""
    name = get_name_by_handle(username)

    tasks = await get_tasks_for_member(username)
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    total = len(tasks)
    completed = sum(1 for t in tasks if t.get("status", "").lower() in ["done", "completed"])
    in_progress = sum(1 for t in tasks if t.get("status", "").lower() in ["in progress", "in_progress"])
    overdue = sum(1 for t in tasks if t.get("due_date", "") and t["due_date"] < today
                  and t.get("status", "").lower() not in ["done", "completed"])

    msg = (
        f"📅 *Weekly Summary — {name}*\n"
        f"{'━' * 25}\n\n"
        f"*Total tasks:* {total}\n"
        f"*Completed:* {completed} ✅\n"
        f"*In progress:* {in_progress}\n"
    )
    if overdue > 0:
        msg += f"*Overdue:* {overdue} ⚠️\n"

    if total > 0:
        completion_rate = int((completed / total) * 100)
        msg += f"\n*Completion rate:* {completion_rate}%"
        if completion_rate >= 80:
            msg += " 🔥 Great work!"
        elif completion_rate >= 50:
            msg += " 👍 Keep going!"
        else:
            msg += " 💪 Let's push harder!"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Fetching today's brief...")

    try:
        result = await notion.get_page_content(AI_SUGGESTIONS_PAGE_ID)
        if not result:
            await update.message.reply_text("❌ Could not read AI Suggestions page")
            return

        blocks = result.get("results", [])
        raw_text = notion.extract_text_from_blocks(blocks)

        if "MORNING BRIEF" in raw_text:
            start = raw_text.rfind("MORNING BRIEF")
            end = min(start + 2000, len(raw_text))
            brief = raw_text[start:end].strip()

            header = format_agent_header("Omni Sight")
            await update.message.reply_text(
                f"{header}📋 *Latest Brief*\n{'━' * 25}\n{brief[:3500]}",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(
                "No morning brief found yet. Omni Sight may not have run today.\n"
                "Try again later or ask an admin to use /force\\_brief.",
                parse_mode=ParseMode.MARKDOWN,
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("⚙️ Settings are only available in private chat. Message me directly!")
        return

    settings = get_user_settings(context)

    keyboard = [
        [
            InlineKeyboardButton(
                f"{'🔔' if settings['morning_motivation'] else '🔕'} Morning",
                callback_data="toggle_morning_motivation",
            ),
            InlineKeyboardButton(
                f"{'🔔' if settings['daily_tasks'] else '🔕'} Tasks",
                callback_data="toggle_daily_tasks",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{'🔔' if settings['eod_summary'] else '🔕'} Evening",
                callback_data="toggle_eod_summary",
            ),
            InlineKeyboardButton(
                f"{'🔔' if settings['weekly_report'] else '🔕'} Weekly",
                callback_data="toggle_weekly_report",
            ),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ *Your Notification Settings*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Tap a button to toggle notifications on/off:\n\n"
        f"🌅 Morning motivation: {'ON ✅' if settings['morning_motivation'] else 'OFF ❌'}\n"
        f"📋 Daily task briefing: {'ON ✅' if settings['daily_tasks'] else 'OFF ❌'}\n"
        f"🌆 End-of-day summary: {'ON ✅' if settings['eod_summary'] else 'OFF ❌'}\n"
        f"📊 Weekly reports: {'ON ✅' if settings['weekly_report'] else 'OFF ❌'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    settings = get_user_settings(context)
    key = query.data.replace("toggle_", "")

    if key in settings:
        settings[key] = not settings[key]
        context.user_data["settings"] = settings

    keyboard = [
        [
            InlineKeyboardButton(
                f"{'🔔' if settings['morning_motivation'] else '🔕'} Morning",
                callback_data="toggle_morning_motivation",
            ),
            InlineKeyboardButton(
                f"{'🔔' if settings['daily_tasks'] else '🔕'} Tasks",
                callback_data="toggle_daily_tasks",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{'🔔' if settings['eod_summary'] else '🔕'} Evening",
                callback_data="toggle_eod_summary",
            ),
            InlineKeyboardButton(
                f"{'🔔' if settings['weekly_report'] else '🔕'} Weekly",
                callback_data="toggle_weekly_report",
            ),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "⚙️ *Your Notification Settings*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Tap a button to toggle notifications on/off:\n\n"
        f"🌅 Morning motivation: {'ON ✅' if settings['morning_motivation'] else 'OFF ❌'}\n"
        f"📋 Daily task briefing: {'ON ✅' if settings['daily_tasks'] else 'OFF ❌'}\n"
        f"🌆 End-of-day summary: {'ON ✅' if settings['eod_summary'] else 'OFF ❌'}\n"
        f"📊 Weekly reports: {'ON ✅' if settings['weekly_report'] else 'OFF ❌'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ADMIN COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("⛔ Only authorized admins can use /setup")
        return

    chat = update.effective_chat

    if context.args:
        group_type = context.args[0].lower()

        if group_type == "admin":
            global ADMIN_GROUP_ID
            ADMIN_GROUP_ID = str(chat.id)
            await update.message.reply_text(
                f"✅ *Admin group registered!*\n\n"
                f"Chat ID: `{chat.id}`\n"
                f"All hub leaders will see business updates here.\n\n"
                f"Set in Render:\n`ADMIN_GROUP_ID={chat.id}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        elif group_type == "safeoffers":
            global SAFE_OFFERS_GROUP_ID
            SAFE_OFFERS_GROUP_ID = str(chat.id)
            await update.message.reply_text(
                f"✅ *Safe Offers group registered!*\n\n"
                f"Chat ID: `{chat.id}`\n\n"
                f"Set in Render:\n`SAFE_OFFERS_GROUP_ID={chat.id}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(
                "Usage:\n/setup admin — Register Admin group\n/setup safeoffers — Register Safe Offers group"
            )
    else:
        await update.message.reply_text(
            "Usage:\n/setup admin — Register Admin group\n/setup safeoffers — Register Safe Offers group"
        )


async def cmd_force_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("⛔ Admin only")
        return

    await update.message.reply_text("📋 Forcing morning brief...")
    await job_morning_brief(context)
    await update.message.reply_text("✅ Morning brief sent to all groups")


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("⛔ Admin only")
        return

    await update.message.reply_text("📊 Generating weekly report...")
    await job_weekly_report(context)
    await update.message.reply_text("✅ Weekly report sent")


async def cmd_outbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("⛔ Admin only")
        return

    try:
        result = await notion.get_page_content(TELEGRAM_OUTBOX_PAGE_ID)
        if result:
            blocks = result.get("results", [])
            raw_text = notion.extract_text_from_blocks(blocks)
            messages = parse_outbox_messages(raw_text)

            pending = [m for m in messages if hash(f"{m['to']}:{m['content'][:100]}:{m.get('date', '')}") not in sent_messages]

            await update.message.reply_text(
                f"📬 *Telegram Outbox Status*\n\n"
                f"Total messages parsed: {len(messages)}\n"
                f"Pending delivery: {len(pending)}\n"
                f"Already sent this session: {len(sent_messages)}\n\n"
                f"Polling every {OUTBOX_POLL_INTERVAL}s",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("❌ Could not read Outbox page")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("⛔ Admin only")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    message_text = " ".join(context.args)
    sent_count = 0

    for handle, info in TEAM_HANDLES.items():
        chat_id = info.get("chat_id")
        if chat_id:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📢 *Team Broadcast*\n{'━' * 20}\n\n{message_text}",
                    parse_mode=ParseMode.MARKDOWN,
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Broadcast to {handle} failed: {e}")
            await asyncio.sleep(0.3)

    await update.message.reply_text(f"✅ Broadcast sent to {sent_count} team members")


async def cmd_teamstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("⛔ Admin only")
        return

    lines = []
    registered = 0
    for handle, info in TEAM_HANDLES.items():
        status = "✅" if info.get("chat_id") else "❌"
        if info.get("chat_id"):
            registered += 1
        dept = ", ".join(info.get("department", []))
        lines.append(f"{status} @{handle} ({info['name']}) — {dept}")

    members_text = "\n".join(lines)

    await update.message.reply_text(
        f"👥 *Team Registration Status*\n"
        f"{'━' * 25}\n\n"
        f"{members_text}\n\n"
        f"*Registered:* {registered}/{len(TEAM_HANDLES)}\n"
        f"*Source:* {'Notion' if TEAM_DIRECTORY_PAGE_ID else 'Fallback'}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SMART ERROR HANDLING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = get_name_by_handle(user.username) if user.username else user.first_name
    is_private = update.effective_chat.type == "private"
    command = update.message.text.split()[0] if update.message.text else ""

    if is_private:
        await update.message.reply_text(
            f"🤔 I don't recognize \"{command}\"\n\n"
            f"Here's what I can help you with:\n\n"
            f"📋 /status — Your task overview\n"
            f"📝 /mytasks — All your active tasks\n"
            f"📊 /brief — Today's briefing\n"
            f"🏢 /hub — Hub status check\n"
            f"📅 /week — Weekly summary\n"
            f"⚙️ /settings — Notification preferences\n"
            f"❓ /help — Full command list\n\n"
            f"Just pick one or type what you need!",
        )
    else:
        bot_username = (await context.bot.get_me()).username
        msg = await update.message.reply_text(
            f"👋 Hey {name}, I didn't recognize that command.\n\n"
            f"For a full list, message me privately → @{bot_username}",
        )
        try:
            await asyncio.sleep(30)
            await msg.delete()
        except Exception:
            pass


async def handle_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = get_name_by_handle(user.username) if user.username else user.first_name

    await update.message.reply_text(
        f"👋 Hey {name}! I work best with commands.\n\n"
        f"Try /help to see everything I can do,\n"
        f"or /status for a quick task check.\n\n"
        f"Need something specific? I'm here to help! 💬",
    )


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    bot_me = await context.bot.get_me()
    bot_username = bot_me.username

    if f"@{bot_username}" in text:
        await update.message.reply_text(
            "👋 I'm TeamFlow Bot! I deliver notifications from Omni Sight and Stratex.\n\n"
            f"For commands, message me privately → @{bot_username}",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def health_check():
    from aiohttp import web

    async def handle(request):
        now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        return web.Response(
            text=f"TeamFlow Bot v4.0 is running ✅\nTime: {now}\nMembers: {len(TEAM_HANDLES)}"
        )

    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/health", handle)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check running on port {port}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def post_init(application: Application):
    await sync_team_directory()
    logger.info(f"Team directory loaded: {len(TEAM_HANDLES)} members")


def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    if not NOTION_API_KEY:
        logger.error("NOTION_API_KEY not set!")
        return

    load_chat_ids()

    persistence = PicklePersistence(filepath=PERSISTENCE_FILE)
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .post_init(post_init)
        .build()
    )

    # ── Command Handlers ──
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("mytasks", cmd_mytasks))
    app.add_handler(CommandHandler("hub", cmd_hub))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("setup", cmd_setup))
    app.add_handler(CommandHandler("force_brief", cmd_force_brief))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("outbox", cmd_outbox))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("teamstatus", cmd_teamstatus))

    # ── Settings inline buttons ──
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^toggle_"))

    # ── Smart error handling ──
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.COMMAND, handle_unknown_command,
    ))
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.COMMAND, handle_unknown_command,
    ))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_private_text,
    ))
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, handle_group_message,
    ))

    # ── Scheduled Jobs ──
    jq = app.job_queue

    jq.run_repeating(poll_outbox, interval=OUTBOX_POLL_INTERVAL, first=10, name="outbox_poll")
    jq.run_repeating(refresh_team_directory, interval=DIRECTORY_REFRESH_INTERVAL, first=60, name="dir_refresh")

    jq.run_daily(
        job_morning_motivation,
        time=dtime(hour=9, minute=0, second=0, tzinfo=TZ),
        days=(0, 1, 2, 3, 4, 5), name="morning_motivation",
    )
    jq.run_daily(
        job_morning_brief,
        time=dtime(hour=9, minute=5, second=0, tzinfo=TZ),
        days=(0, 1, 2, 3, 4, 5), name="morning_brief",
    )
    jq.run_daily(
        job_work_start_reminder,
        time=dtime(hour=9, minute=45, second=0, tzinfo=TZ),
        days=(0, 1, 2, 3, 4, 5), name="work_start_reminder",
    )
    jq.run_daily(
        job_personal_task_briefing,
        time=dtime(hour=10, minute=0, second=0, tzinfo=TZ),
        days=(0, 1, 2, 3, 4, 5), name="task_briefing",
    )
    jq.run_daily(
        job_eod_group,
        time=dtime(hour=18, minute=0, second=0, tzinfo=TZ),
        days=(0, 1, 2, 3, 4, 5), name="eod_group",
    )
    jq.run_daily(
        job_eod_personal,
        time=dtime(hour=18, minute=15, second=0, tzinfo=TZ),
        days=(0, 1, 2, 3, 4, 5), name="eod_personal",
    )
    jq.run_daily(
        job_weekly_report,
        time=dtime(hour=10, minute=30, second=0, tzinfo=TZ),
        days=(0,), name="weekly_report",
    )

    # ── Startup log ──
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("🤖 TeamFlow Bot v4.0 Starting")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"📬 Outbox polling: every {OUTBOX_POLL_INTERVAL}s")
    logger.info(f"🌍 Timezone: {TZ}")
    logger.info(f"👥 Admin Group: {'SET' if ADMIN_GROUP_ID else 'NOT SET'}")
    logger.info(f"🔒 Safe Offers Group: {'SET' if SAFE_OFFERS_GROUP_ID else 'NOT SET'}")
    logger.info(f"📇 Team Directory: {'NOTION' if TEAM_DIRECTORY_PAGE_ID else 'FALLBACK'}")
    logger.info(f"👤 Members: {len(TEAM_HANDLES)}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("Scheduled: 09:00 motivation | 09:05 brief | 09:45 start reminder")
    logger.info("Scheduled: 10:00 task DMs | 18:00 EOD group | 18:15 EOD DMs")
    logger.info("Scheduled: Mon 10:30 weekly report")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    loop = asyncio.get_event_loop()
    loop.create_task(health_check())

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
