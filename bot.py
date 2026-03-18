"""
TeamFlow Telegram Bot v5.1 - AI-Powered Task & Team Management
============================================================

A sophisticated Telegram bot integrating Notion databases and Claude AI for intelligent
task management, team coordination, and automated insights across multiple hubs.

FEATURES (v5.1):
- Unified central database for all hubs with Hub column filtering
- Task management with status tracking (Not Started, In Progress, Done)
- AI-powered insights: briefings, recaps, analysis, planning, motivation
- Team member tracking with Notion directory sync
- Automated scheduled jobs (morning/EOD motivation, briefings, reports)
- Smart error handling and rate limiting
- Multi-hub support (Marketing, Sales, Warehouse, Safe Offers, Resell)

COMMANDS:
/start, /help, /status, /mytasks, /hub, /week, /brief, /settings
/ask, /plan, /analyze, /kudos, /standup
/setup, /force_brief, /report, /outbox, /broadcast, /teamstatus

Bot Token: env var BOT_TOKEN (required)
Notion API Key: env var NOTION_API_KEY (required)
Notion Database ID: env var CENTRAL_TASKS_DB_ID (or default provided)
Claude API Key: env var ANTHROPIC_API_KEY (required for AI features)

Author: TeamFlow Development
License: MIT
"""

import os
import json
import logging
import asyncio
import re
from datetime import datetime, timedelta, time as dtime
from typing import List, Dict, Optional, Callable
from functools import wraps

import pytz
import aiohttp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

# ============================================================================
# CONFIGURATION
# ============================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NOTION_VERSION = "2022-06-28"

# Page IDs
TELEGRAM_OUTBOX_PAGE_ID = os.getenv("TELEGRAM_OUTBOX_PAGE_ID", "32541c0c-6404-8162-971f-f78b9609f2aa")
AI_SUGGESTIONS_PAGE_ID = os.getenv("AI_SUGGESTIONS_PAGE_ID", "32441c0c-6404-81b5-bc39-d5b2711cbfe9")
TEAM_DIRECTORY_PAGE_ID = os.getenv("TEAM_DIRECTORY_PAGE_ID", "")

# Central Fix Tasks Database (ONE database for all hubs)
CENTRAL_TASKS_DB_ID = os.getenv("CENTRAL_TASKS_DB_ID", "1a048562b95c4d29aabec5d4e5140c78")

# Legacy env vars — all point to central DB now
MARKETING_TASKS_DB_ID = os.getenv("MARKETING_TASKS_DB_ID", CENTRAL_TASKS_DB_ID)
SALES_TASKS_DB_ID = os.getenv("SALES_TASKS_DB_ID", CENTRAL_TASKS_DB_ID)
WAREHOUSE_TASKS_DB_ID = os.getenv("WAREHOUSE_TASKS_DB_ID", CENTRAL_TASKS_DB_ID)
SAFE_OFFERS_TASKS_DB_ID = os.getenv("SAFE_OFFERS_TASKS_DB_ID", CENTRAL_TASKS_DB_ID)
RESELL_TASKS_DB_ID = os.getenv("RESELL_TASKS_DB_ID", CENTRAL_TASKS_DB_ID)

HUB_DB_MAP = {
    "Marketing": CENTRAL_TASKS_DB_ID,
    "Sales": CENTRAL_TASKS_DB_ID,
    "Warehouse": CENTRAL_TASKS_DB_ID,
    "Safe Offers": CENTRAL_TASKS_DB_ID,
    "Resell": CENTRAL_TASKS_DB_ID,
}

# Telegram Group Chat IDs
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")
SAFE_OFFERS_GROUP_ID = os.getenv("SAFE_OFFERS_GROUP_ID")

# Timezone — Zurich
TZ = pytz.timezone(os.getenv("TIMEZONE", "Europe/Zurich"))

# Polling intervals
OUTBOX_POLL_INTERVAL = int(os.getenv("OUTBOX_POLL_INTERVAL", "60"))
DIRECTORY_REFRESH_INTERVAL = int(os.getenv("DIRECTORY_REFRESH_INTERVAL", "300"))

# Owner access for admin commands
OWNER_USERNAMES = {"marcus_agent", "mate_marsic"}

# Help links
SHEET_LINKS = {
    "Performance Dashboard": "https://docs.google.com/spreadsheets/d/1uJT1uzfzC-ASiqMpuqZDUL_BxmeJM2Gb6I345pHuQEg",
    "Profit Calculator": "https://docs.google.com/spreadsheets/d/1zvz5R216wSVhYe9nNsaCbEHG14dB-OnfZAKWOdDUbOQ",
    "Inventory Tracking": "https://docs.google.com/spreadsheets/d/1Vj_qmGznS2d1hGZiKSVH7OZnt4MLUIq2wyB_K-37ZA8",
    "Project Tracker": "https://docs.google.com/spreadsheets/d/18MCq8ez7nE3x9eRmEOZGjQ_QYdSCu9QssUodz_m2az4",
    "Daily P/L": "https://docs.google.com/spreadsheets/d/1lKfUVP4JlppVnV4imcStjm2N0JbfX7EUPt3kWw6_v08",
}

# ============================================================================
# MOTIVATIONAL MESSAGES
# ============================================================================

MOTIVATION_GENERAL = [
    "🚀 Let's build something great today!",
    "💪 You've got this! One task at a time.",
    "🎯 Stay focused, stay fierce!",
    "✨ Your effort today = Success tomorrow.",
    "🔥 Let's crush these goals!",
]

MONDAY = [
    "🚀 Monday Momentum! Let's kick off the week strong!",
    "💪 Fresh week, fresh energy! You've got this!",
    "🎯 Monday = Reset button. Let's make it count!",
]

WEDNESDAY = [
    "⚡ Midweek surge! You're halfway there!",
    "💯 Wednesday power! Keep that momentum!",
    "🎢 Over the hump—let's finish strong!",
]

FRIDAY = [
    "🎉 Friday feels! You earned this!",
    "🏁 Finish line in sight! Final push!",
    "🌟 End the week like a champion!",
]

SATURDAY = [
    "☀️ Weekend vibes! Time to recharge!",
    "🏖️ You've earned your weekend! Enjoy!",
    "✨ Relax, refresh, come back stronger!",
]

EOD_MESSAGES = [
    "Great work today! Rest well.",
    "You crushed it! See you tomorrow.",
    "Epic day! Time to wind down.",
    "Mission accomplished! Sleep tight.",
    "Outstanding effort! Enjoy your evening.",
]

# ============================================================================
# TEAM DIRECTORY
# ============================================================================

FALLBACK_TEAM_HANDLES = {
    "marcus_agent": {"name": "Marcus", "departments": ["Marketing", "Administration"]},
    "mate_marsic": {"name": "Mate", "departments": ["Marketing", "Administration"]},
    "nikonbelas": {"name": "Niko", "departments": ["Marketing", "Safe Offers"]},
    "ogiiiiz11": {"name": "Orhan", "departments": ["Sales", "Resell"]},
    "ognjen_89": {"name": "Ognjen", "departments": ["Warehouse"]},
    "lukawolk": {"name": "Luka", "departments": ["Safe Offers", "Marketing"]},
    "cb9999999999": {"name": "Dušan", "departments": ["Safe Offers"]},
    "jomlamladen": {"name": "Mladen", "departments": ["Administration"]},
}

TEAM_HANDLES = {}

TEAM_HANDLES_FILE = "/tmp/team_handles.json"
CHAT_IDS_FILE = "/tmp/chat_ids.json"

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================================
# CHAT ID PERSISTENCE
# ============================================================================

def load_chat_ids() -> Dict:
    """Load chat IDs from persistent storage."""
    if os.path.exists(CHAT_IDS_FILE):
        try:
            with open(CHAT_IDS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading chat IDs: {e}")
    return {}

def save_chat_ids(chat_ids: Dict):
    """Save chat IDs to persistent storage."""
    try:
        with open(CHAT_IDS_FILE, "w") as f:
            json.dump(chat_ids, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving chat IDs: {e}")

def get_chat_id_by_handle(handle: str) -> Optional[int]:
    """Retrieve chat ID for a user by handle."""
    chat_ids = load_chat_ids()
    return chat_ids.get(handle.lower())

def get_name_by_handle(handle: str) -> str:
    """Get user's full name from directory."""
    handle_lower = handle.lower()
    if handle_lower in TEAM_HANDLES:
        return TEAM_HANDLES[handle_lower].get("name", handle)
    if handle_lower in FALLBACK_TEAM_HANDLES:
        return FALLBACK_TEAM_HANDLES[handle_lower]["name"]
    return handle

def get_departments_by_handle(handle: str) -> List[str]:
    """Get user's departments."""
    handle_lower = handle.lower()
    if handle_lower in TEAM_HANDLES:
        return TEAM_HANDLES[handle_lower].get("departments", [])
    if handle_lower in FALLBACK_TEAM_HANDLES:
        return FALLBACK_TEAM_HANDLES[handle_lower]["departments"]
    return []

def is_safe_offers_related(handle: str) -> bool:
    """Check if user is in Safe Offers."""
    deps = get_departments_by_handle(handle)
    return "Safe Offers" in deps

def is_admin(user_id: int, username: str = "") -> bool:
    """Check if user is an admin."""
    return username.lower() in OWNER_USERNAMES

# ============================================================================
# USER SETTINGS
# ============================================================================

USER_SETTINGS_FILE = "/tmp/user_settings.json"

def load_user_settings() -> Dict:
    """Load user settings from persistent storage."""
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading user settings: {e}")
    return {}

def save_user_settings(settings: Dict):
    """Save user settings to persistent storage."""
    try:
        with open(USER_SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving user settings: {e}")

# ============================================================================
# NOTION API CLIENT
# ============================================================================

class NotionClient:
    """Handles all Notion API interactions."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def query_database(self, db_id: str, filter_obj: Optional[Dict] = None, sorts: Optional[List] = None) -> Optional[Dict]:
        """Query a Notion database with optional filtering and sorting."""
        import aiohttp
        url = f"{self.base_url}/databases/{db_id}/query"
        payload = {}
        if filter_obj:
            payload["filter"] = filter_obj
        if sorts:
            payload["sorts"] = sorts
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Notion query_database error: {resp.status} - {await resp.text()}")
                        return None
        except Exception as e:
            logger.error(f"Exception in query_database: {e}")
            return None

    async def get_page(self, page_id: str) -> Optional[Dict]:
        """Retrieve a Notion page."""
        import aiohttp
        url = f"{self.base_url}/pages/{page_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Notion get_page error: {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"Exception in get_page: {e}")
            return None

    async def get_page_content(self, page_id: str) -> Optional[Dict]:
        """Retrieve page blocks/content."""
        import aiohttp
        url = f"{self.base_url}/blocks/{page_id}/children"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Notion get_page_content error: {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"Exception in get_page_content: {e}")
            return None

    async def update_page_properties(self, page_id: str, properties: Dict) -> bool:
        """Update page properties."""
        import aiohttp
        url = f"{self.base_url}/pages/{page_id}"
        payload = {"properties": properties}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(url, headers=self.headers, json=payload) as resp:
                    if resp.status in [200, 204]:
                        return True
                    else:
                        logger.error(f"Notion update_page_properties error: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Exception in update_page_properties: {e}")
            return False

    async def create_page(self, parent_id: str, title: str, properties: Dict = None) -> Optional[str]:
        """Create a new Notion page."""
        import aiohttp
        url = f"{self.base_url}/pages"
        payload = {
            "parent": {"page_id": parent_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": title}}]
                }
            }
        }
        if properties:
            payload["properties"].update(properties)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("id")
                    else:
                        logger.error(f"Notion create_page error: {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"Exception in create_page: {e}")
            return None

    def extract_tasks_from_db_results(self, results: Dict) -> List[Dict]:
        """Extract task data from Notion database query results."""
        tasks = []
        pages = results.get("results", [])
        for page in pages:
            props = page.get("properties", {})
            task = {
                "id": page.get("id"),
                "title": self._get_prop_title(props),
                "status": self._get_prop_select(props, "Status"),
                "assignee": self._get_prop_people(props, "Assignee"),
                "due_date": self._get_prop_date(props, "Due Date"),
                "priority": self._get_prop_select(props, "Priority"),
                "hub": self._get_prop_select(props, "Hub"),
            }
            if task["title"]:
                tasks.append(task)
        return tasks

    def _get_prop_title(self, props: Dict) -> str:
        """Extract title from any title-type property (Task, Name, Title, Entry)."""
        for key in ["Task", "Name", "Title", "Entry"]:
            prop = props.get(key, {})
            if prop.get("type") == "title":
                texts = prop.get("title", [])
                return "".join([t.get("text", {}).get("content", "") for t in texts]).strip()
        # Fallback: find any title property
        for key, prop in props.items():
            if prop.get("type") == "title":
                texts = prop.get("title", [])
                return "".join([t.get("text", {}).get("content", "") for t in texts]).strip()
        return ""

    def _get_prop_people(self, props: Dict, key: str) -> str:
        """Extract people names from a People property."""
        prop = props.get(key, {})
        if prop.get("type") == "people":
            people = prop.get("people", [])
            return ", ".join([p.get("name", "") for p in people if p.get("name")]).strip()
        # Fallback to rich_text (some DBs use text for assignee)
        if prop.get("type") == "rich_text":
            texts = prop.get("rich_text", [])
            return "".join([t.get("text", {}).get("content", "") for t in texts]).strip()
        return ""

    def _get_prop_text(self, props: Dict, key: str) -> str:
        """Extract text from property."""
        prop = props.get(key, {})
        if prop.get("type") == "title":
            texts = prop.get("title", [])
            return "".join([t.get("text", {}).get("content", "") for t in texts]).strip()
        elif prop.get("type") == "rich_text":
            texts = prop.get("rich_text", [])
            return "".join([t.get("text", {}).get("content", "") for t in texts]).strip()
        return ""

    def _get_prop_select(self, props: Dict, key: str) -> str:
        """Extract select value from property."""
        prop = props.get(key, {})
        if prop.get("type") == "select":
            select = prop.get("select")
            if select:
                return select.get("name", "")
        elif prop.get("type") == "multi_select":
            options = prop.get("multi_select", [])
            return ", ".join([o.get("name", "") for o in options]).strip()
        return ""

    def _get_prop_date(self, props: Dict, key: str) -> str:
        """Extract date from property."""
        prop = props.get(key, {})
        if prop.get("type") == "date":
            date_obj = prop.get("date")
            if date_obj:
                return date_obj.get("start", "")
        return ""

    def extract_text_from_blocks(self, blocks: List[Dict]) -> str:
        """Extract plain text from page blocks."""
        text_parts = []
        for block in blocks:
            block_type = block.get("type")
            if block_type == "paragraph":
                para = block.get("paragraph", {})
                texts = para.get("rich_text", [])
                text_parts.append("".join([t.get("text", {}).get("content", "") for t in texts]))
            elif block_type == "heading_1":
                heading = block.get("heading_1", {})
                texts = heading.get("rich_text", [])
                text_parts.append("".join([t.get("text", {}).get("content", "") for t in texts]))
            elif block_type == "heading_2":
                heading = block.get("heading_2", {})
                texts = heading.get("rich_text", [])
                text_parts.append("".join([t.get("text", {}).get("content", "") for t in texts]))
            elif block_type == "heading_3":
                heading = block.get("heading_3", {})
                texts = heading.get("rich_text", [])
                text_parts.append("".join([t.get("text", {}).get("content", "") for t in texts]))
            elif block_type == "bulleted_list_item":
                item = block.get("bulleted_list_item", {})
                texts = item.get("rich_text", [])
                text_parts.append("- " + "".join([t.get("text", {}).get("content", "") for t in texts]))
            elif block_type == "numbered_list_item":
                item = block.get("numbered_list_item", {})
                texts = item.get("rich_text", [])
                text_parts.append("• " + "".join([t.get("text", {}).get("content", "") for t in texts]))
        return "\n".join(text_parts).strip()

# ============================================================================
# NOTION TEAM DIRECTORY SYNC
# ============================================================================

notion = NotionClient(NOTION_API_KEY)

async def sync_team_directory():
    """Sync team member data from Notion directory page."""
    global TEAM_HANDLES
    try:
        page_data = await notion.get_page_content(TEAM_DIRECTORY_PAGE_ID)
        if not page_data:
            logger.warning("Could not sync team directory from Notion")
            return

        blocks = page_data.get("results", [])
        new_handles = {}

        for block in blocks:
            if block.get("type") == "paragraph":
                text = notion.extract_text_from_blocks([block])
                if "@" in text:
                    parts = text.split("|")
                    if len(parts) >= 3:
                        handle = parts[0].strip().replace("@", "").lower()
                        name = parts[1].strip()
                        depts = [d.strip() for d in parts[2].split(",")]
                        new_handles[handle] = {
                            "name": name,
                            "departments": depts,
                        }

        if new_handles:
            TEAM_HANDLES = new_handles
            logger.info(f"Synced {len(new_handles)} team members from Notion")

    except Exception as e:
        logger.error(f"Error syncing team directory: {e}")

# ============================================================================
# TASK FETCHING FROM NOTION
# ============================================================================

async def get_tasks_for_member(handle: str) -> List[Dict]:
    """Get all active tasks for a team member from the central database."""
    all_tasks = []
    name = get_name_by_handle(handle)
    departments = get_departments_by_handle(handle)
    db_id = CENTRAL_TASKS_DB_ID
    if not db_id:
        return []

    filter_obj = {
        "and": [
            {
                "property": "Status",
                "select": {"does_not_equal": "Done"}
            }
        ]
    }

    results = await notion.query_database(db_id, filter_obj)
    if not results:
        return []

    tasks = notion.extract_tasks_from_db_results(results)

    for t in tasks:
        assignee = t.get("assignee", "").lower()
        task_hub = t.get("hub", "").strip()
        if name.lower() in assignee or handle.lower() in assignee:
            if task_hub:
                t["hub"] = task_hub
            elif departments:
                t["hub"] = departments[0]
            all_tasks.append(t)

    return all_tasks

async def get_hub_task_summary(hub_name: str) -> Dict:
    """Get task count summary for a hub using the Hub column filter."""
    db_id = CENTRAL_TASKS_DB_ID
    if not db_id:
        return {"total": 0, "completed": 0, "in_progress": 0, "overdue": 0, "not_started": 0}

    filter_obj = {
        "property": "Hub",
        "select": {"equals": hub_name}
    }

    results = await notion.query_database(db_id, filter_obj)
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

# ============================================================================
# MOTIVATION HELPERS
# ============================================================================

def get_daily_motivation() -> str:
    """Get appropriate motivation message based on day of week."""
    day = datetime.now(TZ).weekday()
    if day == 0:
        return MONDAY[hash(str(datetime.now(TZ).date())) % len(MONDAY)]
    elif day == 2:
        return WEDNESDAY[hash(str(datetime.now(TZ).date())) % len(WEDNESDAY)]
    elif day == 4:
        return FRIDAY[hash(str(datetime.now(TZ).date())) % len(FRIDAY)]
    elif day == 5:
        return SATURDAY[hash(str(datetime.now(TZ).date())) % len(SATURDAY)]
    else:
        return MOTIVATION_GENERAL[hash(str(datetime.now(TZ).date())) % len(MOTIVATION_GENERAL)]

def get_eod_message() -> str:
    """Get a random EOD message."""
    return EOD_MESSAGES[hash(str(datetime.now(TZ).date())) % len(EOD_MESSAGES)]

def format_agent_header(agent_name: str) -> str:
    """Format a header for AI agent responses."""
    if "stratex" in agent_name.lower():
        return f"🧠 *Stratex*\n{'━' * 20}\n"
    else:
        return f"🔍 *Omni Sight*\n{'━' * 20}\n"

# ============================================================================
# CLAUDE AI ENGINE
# ============================================================================

OMNI_SIGHT_SYSTEM = """You are Omni Sight — an AI operations monitoring agent for TeamFlow.
Your role: analyze task data, identify bottlenecks, flag overdue items, spot patterns in team velocity.
Tone: professional, direct, data-driven. Use clear metrics and actionable observations.
Keep responses concise (max 800 chars for Telegram). Use bullet points sparingly.
Never use emojis excessively — max 2-3 per message. Always end with one clear action item.
Language: English only."""

STRATEX_SYSTEM = """You are Stratex — an AI strategy and optimization agent for TeamFlow.
Your role: analyze workload distribution, suggest priority rebalancing, recommend process improvements, deliver strategic insights.
Tone: visionary but practical, motivational but grounded in data. Think like a COO.
Keep responses concise (max 800 chars for Telegram). Focus on the big picture.
Never use emojis excessively — max 2-3 per message. Always end with a strategic recommendation.
Language: English only."""

async def ask_claude(persona: str, prompt: str, context_data: str = "") -> Optional[str]:
    """Call Claude API with the specified persona via aiohttp. Returns AI response or None."""
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI generation")
        return None

    system_prompt = OMNI_SIGHT_SYSTEM if persona == "omni_sight" else STRATEX_SYSTEM

    user_message = prompt
    if context_data:
        user_message = f"{prompt}\n\nHere is the current data:\n{context_data}"

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 500,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("content", [{}])[0].get("text", "")
                    return text.strip() if text else None
                else:
                    error = await resp.text()
                    logger.error(f"Claude API error {resp.status}: {error[:200]}")
                    return None
    except Exception as e:
        logger.error(f"Claude API request failed: {e}")
        return None

async def ai_morning_briefing(hub_name: str) -> Optional[str]:
    """Generate morning briefing for a hub."""
    db_id = CENTRAL_TASKS_DB_ID
    if not db_id:
        return None

    filter_obj = {
        "property": "Hub",
        "select": {"equals": hub_name}
    }

    results = await notion.query_database(db_id, filter_obj)
    if not results:
        return None

    tasks = notion.extract_tasks_from_db_results(results)
    today = datetime.now(TZ).strftime("%Y-%m-%d")

    task_lines = []
    for t in tasks[:20]:
        title = t.get("title", "Untitled")
        status = t.get("status", "N/A")
        due = t.get("due_date", "N/A")
        assignee = t.get("assignee", "Unassigned")
        priority = t.get("priority", "")
        task_lines.append(f"- {title} | {status} | Due: {due} | {assignee} | {priority}")

    context_data = f"{hub_name} Hub Tasks:\n" + "\n".join(task_lines[:15])

    prompt = f"""Generate a brief, energetic morning briefing for the {hub_name} hub.
    Cover:
    1. Total active tasks and status breakdown
    2. Top 3 priorities for today
    3. Any critical deadlines
    4. One motivational sentence
    Keep it under 500 characters."""

    return await ask_claude("omni_sight", prompt, context_data)

async def ai_eod_recap(hub_name: str) -> Optional[str]:
    """Generate EOD recap for a hub."""
    db_id = CENTRAL_TASKS_DB_ID
    if not db_id:
        return None

    filter_obj = {
        "property": "Hub",
        "select": {"equals": hub_name}
    }

    results = await notion.query_database(db_id, filter_obj)
    if not results:
        return None

    tasks = notion.extract_tasks_from_db_results(results)

    task_lines = []
    for t in tasks[:20]:
        title = t.get("title", "Untitled")
        status = t.get("status", "N/A")
        task_lines.append(f"- {title} | {status}")

    context_data = f"{hub_name} Hub Tasks:\n" + "\n".join(task_lines[:15])

    prompt = f"""Generate a brief EOD recap for the {hub_name} hub.
    Highlight:
    1. What was completed today
    2. What remains for tomorrow
    3. Any blockers or concerns
    4. Closing motivational note
    Keep it under 400 characters."""

    return await ask_claude("stratex", prompt, context_data)

async def ai_motivation(name: str) -> Optional[str]:
    """Generate personalized motivation for a team member."""
    prompt = f"""Write a brief, personalized motivational message for {name}.
    Be warm, specific to work/productivity, and encouraging.
    Keep it under 150 characters."""

    return await ask_claude("stratex", prompt)

async def ai_personal_insight(handle: str) -> Optional[str]:
    """Generate personal work insight for a team member."""
    name = get_name_by_handle(handle)
    tasks = await get_tasks_for_member(handle)

    task_lines = []
    for t in tasks[:10]:
        title = t.get("title", "Untitled")
        status = t.get("status", "N/A")
        due = t.get("due_date", "N/A")
        task_lines.append(f"- {title} | {status} | Due: {due}")

    context_data = f"Tasks for {name}:\n" + "\n".join(task_lines) if task_lines else "No active tasks."

    prompt = f"""Generate a brief personal work insight for {name}.
    Based on their task list, suggest:
    1. Top priority for today
    2. One suggestion for staying organized
    3. Encouraging observation
    Keep it under 400 characters."""

    return await ask_claude("omni_sight", prompt, context_data)

async def ai_weekly_analysis() -> Optional[str]:
    """Generate weekly performance analysis."""
    db_id = CENTRAL_TASKS_DB_ID
    if not db_id:
        return None

    results = await notion.query_database(db_id)
    if not results:
        return None

    tasks = notion.extract_tasks_from_db_results(results)

    by_hub = {}
    for t in tasks:
        hub = t.get("hub", "Unassigned")
        if hub not in by_hub:
            by_hub[hub] = {"total": 0, "done": 0}
        by_hub[hub]["total"] += 1
        if t.get("status", "").lower() in ["done", "completed"]:
            by_hub[hub]["done"] += 1

    hub_lines = []
    for hub, stats in by_hub.items():
        pct = (stats["done"] / stats["total"] * 100) if stats["total"] > 0 else 0
        hub_lines.append(f"- {hub}: {stats['done']}/{stats['total']} done ({pct:.0f}%)")

    context_data = "Hub Performance:\n" + "\n".join(hub_lines)

    prompt = """Generate a weekly team performance summary.
    Cover:
    1. Overall completion rate
    2. Top performing hub
    3. Areas needing attention
    4. One strategic recommendation
    Keep it under 600 characters."""

    return await ask_claude("stratex", prompt, context_data)

# ============================================================================
# OUTBOX PARSER
# ============================================================================

async def parse_outbox_page() -> List[Dict]:
    """Parse messages from AI suggestions outbox page."""
    messages = []
    try:
        content = await notion.get_page_content(AI_SUGGESTIONS_PAGE_ID)
        if not content:
            return messages

        blocks = content.get("results", [])
        for block in blocks:
            if block.get("type") == "paragraph":
                text = notion.extract_text_from_blocks([block])
                if text.strip().startswith("[") and "|" in text:
                    parts = text.split("|", 3)
                    if len(parts) >= 4:
                        recipient = parts[0].strip().strip("[]").lower()
                        message_type = parts[1].strip()
                        message_text = parts[2].strip()
                        timestamp = parts[3].strip()

                        messages.append({
                            "recipient": recipient,
                            "type": message_type,
                            "text": message_text,
                            "timestamp": timestamp,
                            "block_id": block.get("id"),
                        })
    except Exception as e:
        logger.error(f"Error parsing outbox: {e}")

    return messages

# ============================================================================
# MESSAGE SENDER
# ============================================================================

async def send_direct_message(bot, handle: str, message_text: str) -> bool:
    """Send a direct message to a team member."""
    chat_id = get_chat_id_by_handle(handle)
    if not chat_id:
        logger.warning(f"No chat ID found for {handle}")
        return False

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    except TelegramError as e:
        logger.error(f"Error sending message to {handle}: {e}")
        return False

async def send_group_message(bot, group_id: int, message_text: str) -> bool:
    """Send a message to a group."""
    try:
        await bot.send_message(
            chat_id=group_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    except TelegramError as e:
        logger.error(f"Error sending message to group {group_id}: {e}")
        return False

# ============================================================================
# SCHEDULED JOBS
# ============================================================================

sent_messages = set()

async def poll_outbox(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check outbox and send pending messages."""
    global sent_messages
    try:
        messages = await parse_outbox_page()
        for msg in messages:
            msg_key = f"{msg['recipient']}_{msg['timestamp']}"
            if msg_key not in sent_messages:
                success = await send_direct_message(context.bot, msg['recipient'], msg['text'])
                if success:
                    sent_messages.add(msg_key)
                    logger.info(f"Sent outbox message to {msg['recipient']}")
    except Exception as e:
        logger.error(f"Error in poll_outbox: {e}")

async def job_morning_motivation(context: ContextTypes.DEFAULT_TYPE):
    """Send morning motivation to all registered users."""
    try:
        chat_ids = load_chat_ids()
        motivation = get_daily_motivation()
        for handle, chat_id in chat_ids.items():
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🌅 Good morning! {motivation}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.warning(f"Could not send motivation to {handle}: {e}")
    except Exception as e:
        logger.error(f"Error in job_morning_motivation: {e}")

async def job_work_start_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send work start reminder to team members."""
    try:
        chat_ids = load_chat_ids()
        for handle, chat_id in chat_ids.items():
            name = get_name_by_handle(handle)
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"📌 {name}, check your tasks for the day with /mytasks!",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.warning(f"Could not send reminder to {handle}: {e}")
    except Exception as e:
        logger.error(f"Error in job_work_start_reminder: {e}")

async def job_personal_task_briefing(context: ContextTypes.DEFAULT_TYPE):
    """Send personalized task briefing to each team member."""
    try:
        chat_ids = load_chat_ids()
        for handle, chat_id in chat_ids.items():
            name = get_name_by_handle(handle)
            tasks = await get_tasks_for_member(handle)

            if not tasks:
                msg = f"✅ {name}, you have no active tasks. Great job!"
            else:
                msg = f"📋 *{name}'s Tasks Today ({len(tasks)} active):*\n\n"
                for i, t in enumerate(tasks[:5], 1):
                    title = t.get("title", "Untitled")
                    status = t.get("status", "N/A")
                    due = t.get("due_date", "Today" if not t.get("due_date") else t.get("due_date"))
                    msg += f"{i}. {title}\n   Status: {status} | Due: {due}\n"
                if len(tasks) > 5:
                    msg += f"\n+{len(tasks) - 5} more tasks. Use /mytasks to see all."

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.warning(f"Could not send briefing to {handle}: {e}")
    except Exception as e:
        logger.error(f"Error in job_personal_task_briefing: {e}")

async def job_morning_brief(context: ContextTypes.DEFAULT_TYPE):
    """Send morning briefing to admin group."""
    try:
        if not ADMIN_GROUP_ID:
            return
        all_summaries = []
        for hub_name in ["Marketing", "Sales", "Warehouse", "Safe Offers", "Resell"]:
            summary = await get_hub_task_summary(hub_name)
            all_summaries.append(f"*{hub_name}:* {summary['completed']}/{summary['total']} done, {summary['overdue']} overdue")
        msg = f"📋 *Morning Brief*\n{'━' * 25}\n\n" + "\n".join(all_summaries)
        await send_group_message(context.bot, int(ADMIN_GROUP_ID), msg)
    except Exception as e:
        logger.error(f"Error in job_morning_brief: {e}")

async def job_eod_group(context: ContextTypes.DEFAULT_TYPE):
    """Send EOD recap to admin group."""
    try:
        if not ADMIN_GROUP_ID:
            return
        eod_msg = get_eod_message()
        header = format_agent_header("Stratex")
        msg = f"{header}🌆 *End of Day*\n\n{eod_msg}"
        await send_group_message(context.bot, int(ADMIN_GROUP_ID), msg)
    except Exception as e:
        logger.error(f"Error in job_eod_group: {e}")

async def job_eod_personal(context: ContextTypes.DEFAULT_TYPE):
    """Send EOD message to all team members."""
    try:
        chat_ids = load_chat_ids()
        eod_msg = get_eod_message()
        for handle, chat_id in chat_ids.items():
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🌙 {eod_msg}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.warning(f"Could not send EOD to {handle}: {e}")
    except Exception as e:
        logger.error(f"Error in job_eod_personal: {e}")

async def job_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    """Send weekly performance report to admin group."""
    try:
        if not ADMIN_GROUP_ID:
            return
        analysis = await ai_weekly_analysis()
        if not analysis:
            return
        header = format_agent_header("Omni Sight")
        msg = f"{header}📊 *Weekly Report*\n{'━' * 25}\n\n{analysis}"
        await send_group_message(context.bot, int(ADMIN_GROUP_ID), msg)
    except Exception as e:
        logger.error(f"Error in job_weekly_report: {e}")

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — Initialize the bot and save chat ID."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    username = user.username or ""

    chat_ids = load_chat_ids()
    chat_ids[username.lower()] = chat_id
    save_chat_ids(chat_ids)

    name = get_name_by_handle(username)

    await update.message.reply_text(
        f"👋 *Welcome, {name}!*\n\n"
        f"I'm TeamFlow, your AI-powered task & team management bot.\n\n"
        f"*Quick Start:*\n"
        f"• /mytasks — See your active tasks\n"
        f"• /hub <name> — Hub status & insights\n"
        f"• /brief — Personal briefing\n"
        f"• /ask — Ask AI questions about tasks\n"
        f"• /help — Full command list\n\n"
        f"Let's get productive! 🚀",
        parse_mode=ParseMode.MARKDOWN
    )

    await sync_team_directory()

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help — Show all available commands."""
    help_text = """*TeamFlow Bot — Complete Command List*

*📋 Task Management:*
/status — Overall team task status
/mytasks — Your active tasks
/hub <name> — Hub status (Marketing, Sales, Warehouse, Safe Offers, Resell)
/week — Weekly task summary

*📊 Insights & Analytics:*
/brief — Personal work briefing
/ask <question> — Ask AI about tasks
/analyze — Hub performance analysis
/plan — AI-powered task planning

*🤖 AI Features:*
/kudos <name> — Send recognition
/standup — Generate daily standup

*⚙️ Settings:*
/settings — Customize preferences

*👨‍💼 Admin Commands (Owner Only):*
/setup — Initialize bot
/force_brief — Trigger morning brief
/report — Generate weekly report
/outbox — View pending messages
/broadcast — Send team announcement
/teamstatus — Full team status

*Need Help?*
Use /help <command> for command-specific details.
Contact @mate_marsic for support.

*Version:* v5.1 - Unified Central Database
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — Show overall team task status."""
    await update.message.reply_text("📊 *Team Status Summary*\n\nQuerying databases...", parse_mode=ParseMode.MARKDOWN)

    hubs_info = []
    for hub_name in ["Marketing", "Sales", "Warehouse", "Safe Offers", "Resell"]:
        summary = await get_hub_task_summary(hub_name)
        completed_pct = (summary["completed"] / summary["total"] * 100) if summary["total"] > 0 else 0
        hubs_info.append(f"*{hub_name}:* {summary['completed']}/{summary['total']} done ({completed_pct:.0f}%) | Overdue: {summary['overdue']}")

    status_msg = "🟢 *All Hubs Status:*\n\n" + "\n".join(hubs_info)

    await update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_mytasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mytasks — Show your active tasks."""
    user = update.effective_user
    username = user.username or ""
    name = get_name_by_handle(username)

    tasks = await get_tasks_for_member(username)

    if not tasks:
        await update.message.reply_text(f"✅ {name}, you have no active tasks! Great work!")
        return

    msg = f"📋 *Your Active Tasks ({len(tasks)}):*\n\n"
    for i, t in enumerate(tasks[:15], 1):
        title = t.get("title", "Untitled")
        status = t.get("status", "Not Started")
        due = t.get("due_date", "No due date")
        priority = t.get("priority", "")
        hub = t.get("hub", "")

        priority_str = f" | Priority: {priority}" if priority else ""
        hub_str = f" | Hub: {hub}" if hub else ""

        msg += f"{i}. *{title}*\n   Status: {status} | Due: {due}{priority_str}{hub_str}\n\n"

    if len(tasks) > 15:
        msg += f"\n... and {len(tasks) - 15} more tasks."

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/hub <name> — Get hub status and insights."""
    if not context.args:
        hubs = ", ".join(HUB_DB_MAP.keys())
        await update.message.reply_text(
            f"🏢 *Available Hubs:*\n{hubs}\n\n"
            f"Usage: /hub <hub_name>",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    hub_name = " ".join(context.args).strip()
    if hub_name not in HUB_DB_MAP:
        await update.message.reply_text(f"❌ Hub '{hub_name}' not found. Use /hub to see available hubs.")
        return

    await update.message.reply_text(f"🔍 Fetching {hub_name} hub data...", parse_mode=ParseMode.MARKDOWN)

    summary = await get_hub_task_summary(hub_name)
    msg = f"📊 *{hub_name} Hub Status:*\n\n"
    msg += f"Total Tasks: {summary['total']}\n"
    msg += f"Completed: {summary['completed']}\n"
    msg += f"In Progress: {summary['in_progress']}\n"
    msg += f"Not Started: {summary['not_started']}\n"
    msg += f"🚨 Overdue: {summary['overdue']}\n"

    if summary["total"] > 0:
        completion_pct = (summary["completed"] / summary["total"]) * 100
        msg += f"\n✅ Completion Rate: {completion_pct:.1f}%"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/week — Show weekly summary."""
    await update.message.reply_text("📅 *Weekly Summary*\n\nGenerating analysis...", parse_mode=ParseMode.MARKDOWN)

    analysis = await ai_weekly_analysis()
    if analysis:
        header = format_agent_header("Omni Sight")
        await update.message.reply_text(
            f"{header}{analysis}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("❌ Could not generate weekly summary.")

async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/brief — Get your personal briefing."""
    user = update.effective_user
    username = user.username or ""

    await update.message.reply_text("📋 Generating your briefing...", parse_mode=ParseMode.MARKDOWN)

    insight = await ai_personal_insight(username)
    if insight:
        name = get_name_by_handle(username)
        header = format_agent_header("Stratex")
        await update.message.reply_text(
            f"{header}*Briefing for {name}:*\n\n{insight}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("❌ Could not generate briefing.")

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/settings — Manage your preferences."""
    user = update.effective_user
    username = user.username or ""

    settings = load_user_settings()
    user_settings = settings.get(username, {})

    keyboard = [
        [
            InlineKeyboardButton("🔔 Notifications", callback_data="settings_notifications"),
            InlineKeyboardButton("🎯 Preferences", callback_data="settings_preferences"),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="settings_close"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ *Your Settings:*\n\nChoose an option to customize:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle settings callbacks."""
    query = update.callback_query
    user = query.from_user
    username = user.username or ""

    if query.data == "settings_close":
        await query.edit_message_text("✅ Settings closed.")
    else:
        await query.answer("Feature coming soon!", show_alert=True)

# ============================================================================
# ADMIN COMMANDS
# ============================================================================

async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setup — Initialize bot (admin only)."""
    user = update.effective_user
    if not is_admin(user.id, user.username):
        await update.message.reply_text("❌ Admin access required.")
        return

    await update.message.reply_text("🔧 *Setting up TeamFlow Bot...*\n\nSyncing team directory...", parse_mode=ParseMode.MARKDOWN)

    await sync_team_directory()

    await update.message.reply_text(
        "✅ *Setup Complete!*\n\n"
        f"Synced {len(TEAM_HANDLES or FALLBACK_TEAM_HANDLES)} team members\n"
        f"Central Tasks DB: {CENTRAL_TASKS_DB_ID}\n"
        f"Ready to go! 🚀",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_force_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/force_brief — Trigger morning briefing immediately (admin only)."""
    user = update.effective_user
    if not is_admin(user.id, user.username):
        await update.message.reply_text("❌ Admin access required.")
        return

    await update.message.reply_text("📋 *Sending morning briefs to all hubs...*", parse_mode=ParseMode.MARKDOWN)

    await job_morning_brief(context)

    await update.message.reply_text("✅ Morning briefs sent!")

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/report — Generate weekly report (admin only)."""
    user = update.effective_user
    if not is_admin(user.id, user.username):
        await update.message.reply_text("❌ Admin access required.")
        return

    await update.message.reply_text("📊 *Generating weekly report...*", parse_mode=ParseMode.MARKDOWN)

    await job_weekly_report(context)

    await update.message.reply_text("✅ Weekly report sent!")

async def cmd_outbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/outbox — View pending messages (admin only)."""
    user = update.effective_user
    if not is_admin(user.id, user.username):
        await update.message.reply_text("❌ Admin access required.")
        return

    messages = await parse_outbox_page()

    if not messages:
        await update.message.reply_text("📪 Outbox is empty.")
        return

    msg = "📬 *Outbox Messages:*\n\n"
    for i, m in enumerate(messages, 1):
        msg += f"{i}. To: {m['recipient']}\n"
        msg += f"   Type: {m['type']}\n"
        msg += f"   Text: {m['text'][:100]}...\n"
        msg += f"   Time: {m['timestamp']}\n\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/broadcast <message> — Send announcement to all hubs (admin only)."""
    user = update.effective_user
    if not is_admin(user.id, user.username):
        await update.message.reply_text("❌ Admin access required.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message = " ".join(context.args)

    await update.message.reply_text("📢 *Broadcasting to all hubs...*", parse_mode=ParseMode.MARKDOWN)

    msg = f"📢 *Team Announcement:*\n\n{message}"
    chat_ids = load_chat_ids()
    for handle, chat_id in chat_ids.items():
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Could not broadcast to {handle}: {e}")

    await update.message.reply_text("✅ Broadcast sent to all hubs!")

async def cmd_teamstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/teamstatus — Show full team status (admin only)."""
    user = update.effective_user
    if not is_admin(user.id, user.username):
        await update.message.reply_text("❌ Admin access required.")
        return

    await update.message.reply_text("📊 *Team Status Report*\n\nGathering data...", parse_mode=ParseMode.MARKDOWN)

    msg = "👥 *Full Team Status:*\n\n"

    for hub_name in ["Marketing", "Sales", "Warehouse", "Safe Offers", "Resell"]:
        summary = await get_hub_task_summary(hub_name)
        completion = (summary["completed"] / summary["total"] * 100) if summary["total"] > 0 else 0
        msg += f"*{hub_name}:*\n"
        msg += f"  Total: {summary['total']} | Done: {summary['completed']} ({completion:.0f}%) | In Progress: {summary['in_progress']} | Overdue: {summary['overdue']}\n\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ============================================================================
# AI-POWERED COMMANDS
# ============================================================================

async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ask [question] — Ask Omni Sight anything about tasks. Pulls Notion data + Claude AI."""
    user = update.effective_user
    username = user.username or ""
    name = get_name_by_handle(username)

    if not context.args:
        await update.message.reply_text(
            "❓ *Usage:* /ask your question here\n\n"
            "*Examples:*\n"
            "• /ask which tasks are overdue in Sales hub?\n"
            "• /ask what should Niko focus on today?\n"
            "• /ask how is Marketing performing this week?\n"
            "• /ask what are the top priorities across all hubs?",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    question = " ".join(context.args)
    await update.message.reply_text("🔍 *Omni Sight is analyzing...*", parse_mode=ParseMode.MARKDOWN)

    all_context_lines = []
    db_id = CENTRAL_TASKS_DB_ID
    if db_id:
        try:
            results = await notion.query_database(db_id)
            if results:
                tasks = notion.extract_tasks_from_db_results(results)
                today = datetime.now(TZ).strftime("%Y-%m-%d")
                by_hub = {}
                for t in tasks:
                    hub = t.get("hub", "Unassigned")
                    if hub not in by_hub:
                        by_hub[hub] = []
                    by_hub[hub].append(t)

                for hub_name, hub_tasks in by_hub.items():
                    hub_lines = [f"\n== {hub_name} Hub ({len(hub_tasks)} tasks) =="]
                    for t in hub_tasks[:15]:
                        title = t.get("title", "Untitled")
                        status = t.get("status", "N/A")
                        due = t.get("due_date", "N/A")
                        assignee = t.get("assignee", "Unassigned")
                        priority = t.get("priority", "")
                        overdue_flag = " [OVERDUE]" if due != "N/A" and due < today and status.lower() not in ["done", "completed"] else ""
                        hub_lines.append(f"- {title} | Status: {status} | Due: {due}{overdue_flag} | Assignee: {assignee} | Priority: {priority}")
                    all_context_lines.extend(hub_lines)
        except Exception as e:
            logger.error(f"Error querying central DB in /ask: {e}")

    try:
        ai_result = await notion.get_page_content(AI_SUGGESTIONS_PAGE_ID)
        if ai_result:
            blocks = ai_result.get("results", [])
            ai_text = notion.extract_text_from_blocks(blocks)
            if ai_text:
                all_context_lines.append(f"\n== AI Suggestions Page (latest) ==\n{ai_text[:1500]}")
    except Exception:
        pass

    context_data = "\n".join(all_context_lines) if all_context_lines else "No task data available from Notion."

    prompt = (
        f"Team member {name} (@{username}) is asking: \"{question}\"\n\n"
        f"Answer their question based on the Notion task data provided below. "
        f"Be specific — reference actual task names, assignees, dates when relevant. "
        f"If the data doesn't contain enough info to fully answer, say what you can and note what's missing. "
        f"Keep response under 800 characters for Telegram."
    )

    response = await ask_claude("omni_sight", prompt, context_data)
    if response:
        header = format_agent_header("Omni Sight")
        await update.message.reply_text(
            f"{header}💬 *Answer for {name}:*\n\n{response}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            "❌ Couldn't generate an answer right now. AI might be unavailable.\n"
            "Try /status or /hub for manual data checks."
        )

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/plan — Get AI task planning assistance."""
    user = update.effective_user
    username = user.username or ""
    name = get_name_by_handle(username)

    tasks = await get_tasks_for_member(username)

    task_lines = []
    for t in tasks[:10]:
        title = t.get("title", "Untitled")
        priority = t.get("priority", "Medium")
        due = t.get("due_date", "No due date")
        task_lines.append(f"- {title} ({priority} priority, due {due})")

    context_data = f"Tasks for {name}:\n" + "\n".join(task_lines) if task_lines else "No active tasks."

    prompt = f"""Help {name} plan their work. Based on their task list:
    1. Suggest a priority order for today
    2. Estimate time for each high-priority task
    3. Recommend breaks or focus sessions
    Keep response under 600 characters."""

    await update.message.reply_text("📋 *Task Planner is analyzing...*", parse_mode=ParseMode.MARKDOWN)

    response = await ask_claude("stratex", prompt, context_data)
    if response:
        header = format_agent_header("Stratex")
        await update.message.reply_text(
            f"{header}*Planning for {name}:*\n\n{response}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("❌ Could not generate plan.")

async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/analyze [hub] — Analyze hub performance with Data Analyst."""
    hub_name = " ".join(context.args).strip() if context.args else "Marketing"

    if hub_name not in HUB_DB_MAP:
        await update.message.reply_text(f"❌ Hub '{hub_name}' not found.")
        return

    await update.message.reply_text(f"📊 *Analyzing {hub_name} hub...*", parse_mode=ParseMode.MARKDOWN)

    filter_obj = {
        "property": "Hub",
        "select": {"equals": hub_name}
    }
    results = await notion.query_database(CENTRAL_TASKS_DB_ID, filter_obj)

    if not results:
        await update.message.reply_text(f"❌ No tasks found for {hub_name}.")
        return

    tasks = notion.extract_tasks_from_db_results(results)

    task_lines = []
    for t in tasks[:15]:
        title = t.get("title", "Untitled")
        status = t.get("status", "N/A")
        assignee = t.get("assignee", "Unassigned")
        task_lines.append(f"- {title} ({status}) - {assignee}")

    context_data = f"{hub_name} Hub Tasks:\n" + "\n".join(task_lines)

    prompt = f"""Analyze {hub_name} hub performance. Consider:
    1. Overall completion rate and pace
    2. Task distribution among team members
    3. Potential bottlenecks or delays
    4. One actionable recommendation
    Keep response under 600 characters."""

    response = await ask_claude("omni_sight", prompt, context_data)
    if response:
        header = format_agent_header("Omni Sight")
        await update.message.reply_text(
            f"{header}*Analysis for {hub_name} Hub:*\n\n{response}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("❌ Could not generate analysis.")

async def cmd_kudos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/kudos <name> — Send recognition to a team member."""
    if not context.args:
        await update.message.reply_text("Usage: /kudos <team_member_name>")
        return

    recipient_name = " ".join(context.args).strip()

    await update.message.reply_text("🏆 *Kudos Bot is preparing recognition...*", parse_mode=ParseMode.MARKDOWN)

    prompt = f"""Write a warm, genuine recognition message for {recipient_name} who has been doing great work.
    Mention their dedication, teamwork, or impact.
    Keep it under 300 characters and make it personal."""

    response = await ask_claude("stratex", prompt)
    if response:
        header = format_agent_header("Stratex")
        await update.message.reply_text(
            f"{header}*Recognition for {recipient_name}:*\n\n{response}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("❌ Could not generate recognition.")

async def cmd_standup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/standup — Generate your daily standup."""
    user = update.effective_user
    username = user.username or ""
    name = get_name_by_handle(username)

    tasks = await get_tasks_for_member(username)

    if not tasks:
        done_text = "No completed tasks today."
        doing_text = "No tasks in progress."
        blocking_text = "No blockers."
    else:
        done_list = [t["title"] for t in tasks if t.get("status", "").lower() in ["done", "completed"]]
        doing_list = [t["title"] for t in tasks if t.get("status", "").lower() in ["in progress", "in_progress", "doing"]]
        blocking_list = []

        done_text = ", ".join(done_list) if done_list else "No completed tasks today."
        doing_text = ", ".join(doing_list) if doing_list else "No tasks in progress."
        blocking_text = ", ".join(blocking_list) if blocking_list else "No blockers."

    context_data = f"For {name}:\nDone: {done_text}\nDoing: {doing_text}\nBlockers: {blocking_text}"

    prompt = f"""Generate a brief, professional standup for {name}. Format:
    ✅ Yesterday: [what was completed]
    🔄 Today: [what they're working on]
    🚧 Blockers: [any obstacles]
    Keep it under 400 characters and actionable."""

    await update.message.reply_text("🎤 *Standup Generator is preparing...*", parse_mode=ParseMode.MARKDOWN)

    response = await ask_claude("omni_sight", prompt, context_data)
    if response:
        header = format_agent_header("Omni Sight")
        await update.message.reply_text(
            f"{header}*Daily Standup for {name}:*\n\n{response}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("❌ Could not generate standup.")

# ============================================================================
# SMART ERROR HANDLING
# ============================================================================

async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands gracefully."""
    if update.message and update.message.text:
        cmd = update.message.text.split()[0]
        await update.message.reply_text(
            f"❓ Command '{cmd}' not recognized.\n\n"
            f"Use /help to see available commands.",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct messages that aren't commands."""
    user = update.effective_user
    username = user.username or ""

    if update.message and update.message.text:
        text = update.message.text.strip()

        if text.lower().startswith("hello") or text.lower().startswith("hi"):
            name = get_name_by_handle(username)
            await update.message.reply_text(f"👋 Hi {name}! Need help? Try /help")
        elif text.lower() in ["thanks", "thank you", "thx"]:
            await update.message.reply_text("🙏 You're welcome!")
        else:
            await update.message.reply_text(
                "💬 I'm a task & team bot. Send /help to see what I can do!"
            )

async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle group chat messages."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    if text.startswith("/"):
        return

    if "task" in text.lower() or "help" in text.lower():
        await update.message.reply_text(
            "📋 For task help, DM me or use /mytasks!",
            reply_to_message_id=update.message.message_id
        )

# ============================================================================
# HEALTH CHECK (HTTP server for Render)
# ============================================================================

async def health_check():
    """Start aiohttp web server so Render keeps the service alive."""
    from aiohttp import web
    async def handle(request):
        now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
        return web.Response(
            text=f"TeamFlow Bot v5.1 is running ✅\nTime: {now}\nMembers: {len(TEAM_HANDLES or FALLBACK_TEAM_HANDLES)}"
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

# ============================================================================
# MAIN
# ============================================================================

async def post_init(application: Application):
    """Run after bot initialization."""
    await sync_team_directory()
    logger.info(f"Team directory loaded: {len(TEAM_HANDLES or FALLBACK_TEAM_HANDLES)} members")

def main():
    """Initialize and run the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    if not NOTION_API_KEY:
        logger.error("NOTION_API_KEY not set!")
        return

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("🤖 TeamFlow Bot v5.1 Starting")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"🌍 Timezone: {TZ}")
    logger.info(f"📬 Outbox polling: every {OUTBOX_POLL_INTERVAL}s")
    logger.info(f"👥 Admin Group: {'SET' if ADMIN_GROUP_ID else 'NOT SET'}")
    logger.info(f"🔒 Safe Offers Group: {'SET' if SAFE_OFFERS_GROUP_ID else 'NOT SET'}")
    logger.info(f"📇 Central Tasks DB: {CENTRAL_TASKS_DB_ID}")
    logger.info("AI Commands: /ask /plan /analyze /kudos /standup")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
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

    # ── Admin Commands ──
    app.add_handler(CommandHandler("setup", cmd_setup))
    app.add_handler(CommandHandler("force_brief", cmd_force_brief))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("outbox", cmd_outbox))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("teamstatus", cmd_teamstatus))

    # ── AI-Powered Commands (v5.0) ──
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("kudos", cmd_kudos))
    app.add_handler(CommandHandler("standup", cmd_standup))

    # ── Settings inline buttons ──
    app.add_handler(CallbackQueryHandler(settings_callback))

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
    jq.run_repeating(lambda ctx: sync_team_directory(), interval=DIRECTORY_REFRESH_INTERVAL, first=60, name="dir_refresh")

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

    logger.info("Scheduled: 09:00 motivation | 09:05 brief | 09:45 start reminder")
    logger.info("Scheduled: 10:00 task DMs | 18:00 EOD group | 18:15 EOD DMs")
    logger.info("Scheduled: Mon 10:30 weekly report")

    loop = asyncio.get_event_loop()
    loop.create_task(health_check())

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
