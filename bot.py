"""
TeamFlow Telegram Bot v3.0
100% Notion-integrated — No website functionality
Reads from Notion Telegram Outbox, sends to Telegram groups and DMs
Reads Team Directory from Notion — add/remove members without code changes
Works with Omni Sight and Stratex AI agents
"""

import os
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List

import pytz
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
import aiohttp

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Telegram Bot Token (from @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Notion API
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"

# Notion Page IDs (from your workspace)
TELEGRAM_OUTBOX_PAGE_ID = os.getenv("TELEGRAM_OUTBOX_PAGE_ID", "32541c0c-6404-8162-971f-f78b9609f2aa")
AI_SUGGESTIONS_PAGE_ID = os.getenv("AI_SUGGESTIONS_PAGE_ID", "32441c0c-6404-81b5-bc39-d5b2711cbfe9")
TEAM_DIRECTORY_PAGE_ID = os.getenv("TEAM_DIRECTORY_PAGE_ID", "")

# Telegram Group Chat IDs (set via /setup command or env vars)
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")  # Team Leaders group — ALL hub leaders see business overview
SAFE_OFFERS_GROUP_ID = os.getenv("SAFE_OFFERS_GROUP_ID")  # Safe Offers team group

# Timezone
TZ = pytz.timezone(os.getenv("TIMEZONE", "Europe/Rome"))

# Polling interval for Notion Outbox (seconds)
OUTBOX_POLL_INTERVAL = int(os.getenv("OUTBOX_POLL_INTERVAL", "60"))

# Refresh team directory from Notion (seconds) — every 5 minutes
DIRECTORY_REFRESH_INTERVAL = int(os.getenv("DIRECTORY_REFRESH_INTERVAL", "300"))

# Authorized admin usernames (can use /setup, /force_brief, /outbox)
OWNER_USERNAMES = {"marcus_agent", "mate_marsic"}

# Morning brief time (hour, minute)
MORNING_BRIEF_HOUR = int(os.getenv("MORNING_BRIEF_HOUR", "9"))
MORNING_BRIEF_MINUTE = int(os.getenv("MORNING_BRIEF_MINUTE", "5"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEAM DIRECTORY (Telegram handles → chat IDs)
# Loaded from Notion Team Directory page, with hardcoded fallback
# Chat IDs are populated automatically when team members /start the bot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Fallback directory — used only if Notion Team Directory page is not set
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

# Active team directory — starts as fallback, updated from Notion
TEAM_HANDLES = dict(FALLBACK_TEAM_HANDLES)

# File to persist chat IDs between restarts
CHAT_IDS_FILE = "chat_ids.json"

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
    """Load saved chat IDs from file"""
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
    """Save current chat IDs to file"""
    try:
        data = {h: info["chat_id"] for h, info in TEAM_HANDLES.items() if info["chat_id"]}
        with open(CHAT_IDS_FILE, "w") as f:
            json.dump(data, f)
        logger.info(f"Saved {len(data)} chat IDs to file")
    except Exception as e:
        logger.error(f"Error saving chat IDs: {e}")


def get_chat_id_by_handle(handle: str) -> Optional[int]:
    """Get chat ID from Telegram handle (without @)"""
    handle = handle.lstrip("@")
    if handle in TEAM_HANDLES and TEAM_HANDLES[handle]["chat_id"]:
        return TEAM_HANDLES[handle]["chat_id"]
    return None


def get_name_by_handle(handle: str) -> str:
    """Get team member name from handle"""
    handle = handle.lstrip("@")
    if handle in TEAM_HANDLES:
        return TEAM_HANDLES[handle]["name"]
    return handle


def is_safe_offers_related(message_text: str) -> bool:
    """Check if a message is related to Safe Offers department"""
    safe_keywords = [
        "safe offers", "safe offer", "clocking", "landing page",
        "offer structure", "money page", "safe page",
        "luka", "dušan", "dusan", "lukawolk", "cb9999999999",
        "project 2.0", "project 3.0", "project 4.0",
        "vs medic", "vitalix", "mellow mind",
        "creatives", "ads analytics", "media buy"
    ]
    text_lower = message_text.lower()
    return any(kw in text_lower for kw in safe_keywords)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NOTION API CLIENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class NotionClient:
    """Handles all Notion API interactions"""

    def __init__(self):
        self.api_key = NOTION_API_KEY
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def get_page_content(self, page_id: str) -> Optional[Dict]:
        """Fetch all blocks from a Notion page"""
        url = f"{self.base_url}/blocks/{page_id}/children?page_size=100"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Notion API error {resp.status}: {await resp.text()}")
                    return None

    async def get_block_children(self, block_id: str) -> Optional[Dict]:
        """Fetch children of a specific block"""
        url = f"{self.base_url}/blocks/{block_id}/children?page_size=100"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Notion block children error {resp.status}")
                    return None

    async def append_block(self, page_id: str, content: str) -> bool:
        """Append a text block to a Notion page"""
        url = f"{self.base_url}/blocks/{page_id}/children"
        payload = {
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": content[:2000]}  # Notion limit
                            }
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

    async def update_block_text(self, block_id: str, new_text: str) -> bool:
        """Update an existing block's text"""
        url = f"{self.base_url}/blocks/{block_id}"
        payload = {
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": new_text[:2000]}
                    }
                ]
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=self.headers, json=payload) as resp:
                return resp.status == 200

    def extract_text_from_blocks(self, blocks: List[Dict]) -> str:
        """Extract plain text from Notion blocks"""
        texts = []
        for block in blocks:
            block_type = block.get("type", "")
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
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


notion = NotionClient()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NOTION TEAM DIRECTORY SYNC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def sync_team_directory():
    """
    Fetch team members from Notion Team Directory page.

    Expected format on Notion page (each line as a bullet or paragraph):
        @handle | Display Name | Department1, Department2

    Example:
        @marcus_agent | Marcus | Marketing, Administration
        @nikonbelas | Niko | Marketing, Safe Offers
        @lukawolk | Luka | Safe Offers, Marketing

    Members added in Notion automatically become available.
    Members removed from Notion keep working until bot restarts.
    """
    global TEAM_HANDLES

    if not TEAM_DIRECTORY_PAGE_ID:
        logger.info("TEAM_DIRECTORY_PAGE_ID not set — using fallback directory")
        return

    try:
        result = await notion.get_page_content(TEAM_DIRECTORY_PAGE_ID)
        if not result:
            logger.warning("Could not read Team Directory page — keeping current directory")
            return

        blocks = result.get("results", [])
        raw_text = notion.extract_text_from_blocks(blocks)

        if not raw_text.strip():
            logger.warning("Team Directory page is empty — keeping current directory")
            return

        # Parse members from page content
        new_handles = {}
        lines = raw_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("#"):
                continue

            # Strip checkbox prefixes if present
            if line.startswith(("✅ ", "⬜ ")):
                line = line[2:].strip()

            # Expected: @handle | Name | Dept1, Dept2
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                handle = parts[0].lstrip("@").strip()
                name = parts[1].strip()
                departments = []
                if len(parts) >= 3:
                    departments = [d.strip() for d in parts[2].split(",") if d.strip()]

                if handle and name:
                    # Preserve existing chat_id if member was already registered
                    existing_chat_id = None
                    if handle in TEAM_HANDLES:
                        existing_chat_id = TEAM_HANDLES[handle].get("chat_id")

                    new_handles[handle] = {
                        "name": name,
                        "department": departments or ["General"],
                        "chat_id": existing_chat_id,
                    }

        if new_handles:
            # Merge: keep chat_ids from current TEAM_HANDLES for existing members
            old_count = len(TEAM_HANDLES)
            TEAM_HANDLES.clear()
            TEAM_HANDLES.update(new_handles)

            # Re-apply saved chat IDs from file
            load_chat_ids()

            added = len(TEAM_HANDLES) - old_count
            logger.info(f"Team Directory synced: {len(TEAM_HANDLES)} members"
                       f" (was {old_count}, delta {added:+d})")
        else:
            logger.warning("No valid members parsed from Team Directory — keeping current directory")

    except Exception as e:
        logger.error(f"Error syncing Team Directory: {e}")


async def refresh_team_directory(context: ContextTypes.DEFAULT_TYPE):
    """Job: periodically refresh team directory from Notion"""
    await sync_team_directory()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OUTBOX PARSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_outbox_messages(raw_text: str) -> List[Dict]:
    """
    Parse structured messages from Telegram Outbox page.

    Expected format:
    ---
    TO: @handle (or GROUP or ADMIN)
    TYPE: PERSONAL | GROUP | ESCALATION | ADMIN
    FROM: Omni Sight | Stratex
    DATE: 2026-03-16
    ---
    Message content here
    ---

    Also supports simpler format without separators:
    TO: @handle
    Message content on next lines
    """
    messages = []
    blocks = raw_text.split("---")

    i = 0
    while i < len(blocks):
        block = blocks[i].strip()

        # Skip empty blocks and already-sent confirmations
        if not block or block.startswith("✅ SENT"):
            i += 1
            continue

        # Look for TO: header
        if block.upper().startswith("TO:") or "\nTO:" in block.upper():
            lines = block.split("\n")
            msg = {"to": None, "type": "PERSONAL", "from": "TeamFlow", "date": None, "content": "", "raw": block}
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
                    # Lines after headers are inline content
                    content_lines.append(line_stripped)

            # Check next block for message body (standard separator format)
            if i + 1 < len(blocks):
                next_block = blocks[i + 1].strip()
                # Only use next block as content if it's NOT a header block and NOT a sent confirmation
                if next_block and not next_block.upper().startswith("TO:") and not next_block.startswith("✅ SENT"):
                    msg["content"] = next_block
                    i += 1

            # If no content from next block, use inline content
            if not msg["content"] and content_lines:
                msg["content"] = "\n".join(content_lines)

            # Auto-detect type from TO field
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
                logger.debug(f"Parsed outbox message: TO={msg['to']} TYPE={msg['type']} FROM={msg['from']}")

        i += 1

    return messages


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGE SENDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_to_telegram(bot: Bot, message: Dict) -> bool:
    """Send a parsed outbox message to the correct Telegram destination"""
    try:
        to = message["to"]
        content = message["content"]
        msg_type = message.get("type", "PERSONAL")
        from_agent = message.get("from", "TeamFlow")

        # Add agent header
        header = f"🤖 *{from_agent}*\n{'━' * 20}\n"
        full_message = header + content

        # Determine destination
        if to.upper() == "GROUP":
            # Send to Team Leaders group (all hub leaders see everything)
            if ADMIN_GROUP_ID:
                await bot.send_message(
                    chat_id=int(ADMIN_GROUP_ID),
                    text=full_message,
                    parse_mode=ParseMode.MARKDOWN,
                )
                logger.info(f"Sent GROUP message to Team Leaders group")

            # Also send to Safe Offers group if relevant
            if SAFE_OFFERS_GROUP_ID and is_safe_offers_related(content):
                await bot.send_message(
                    chat_id=int(SAFE_OFFERS_GROUP_ID),
                    text=full_message,
                    parse_mode=ParseMode.MARKDOWN,
                )
                logger.info(f"Sent GROUP message to Safe Offers group")

            return True

        elif to.upper() == "ADMIN" or msg_type == "ESCALATION":
            # Escalation — send to Team Leaders group + DM Marcus
            escalation_msg = f"🚨 *ESCALATION*\n{'━' * 20}\n{content}"
            if ADMIN_GROUP_ID:
                await bot.send_message(
                    chat_id=int(ADMIN_GROUP_ID),
                    text=escalation_msg,
                    parse_mode=ParseMode.MARKDOWN,
                )
                logger.info(f"Sent ESCALATION to Team Leaders group")

            # Also DM Marcus directly for urgent visibility
            marcus_id = get_chat_id_by_handle("marcus_agent")
            if marcus_id:
                await bot.send_message(
                    chat_id=marcus_id,
                    text=escalation_msg,
                    parse_mode=ParseMode.MARKDOWN,
                )
            return True

        else:
            # Personal message — send DM to specific person
            handle = to.lstrip("@")
            chat_id = get_chat_id_by_handle(handle)

            if chat_id:
                await bot.send_message(
                    chat_id=chat_id,
                    text=full_message,
                    parse_mode=ParseMode.MARKDOWN,
                )
                logger.info(f"Sent PERSONAL message to {handle}")

                # Also forward to Team Leaders group for visibility
                if ADMIN_GROUP_ID:
                    admin_msg = f"📨 *DM sent to {get_name_by_handle(handle)}:*\n{content}"
                    await bot.send_message(
                        chat_id=int(ADMIN_GROUP_ID),
                        text=admin_msg,
                        parse_mode=ParseMode.MARKDOWN,
                    )

                return True
            else:
                logger.warning(f"No chat ID for handle: {handle}. User needs to /start the bot first.")
                return False

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OUTBOX POLLING JOB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Track which messages we've already sent (by content hash)
sent_messages = set()


async def poll_outbox(context: ContextTypes.DEFAULT_TYPE):
    """Poll Notion Telegram Outbox for new messages and send them"""
    try:
        result = await notion.get_page_content(TELEGRAM_OUTBOX_PAGE_ID)
        if not result:
            return

        blocks = result.get("results", [])
        raw_text = notion.extract_text_from_blocks(blocks)

        # Parse messages from outbox
        messages = parse_outbox_messages(raw_text)

        for msg in messages:
            # Create unique hash for this message to avoid duplicates
            msg_hash = hash(f"{msg['to']}:{msg['content'][:100]}:{msg.get('date', '')}")

            if msg_hash not in sent_messages:
                success = await send_to_telegram(context.bot, msg)
                if success:
                    sent_messages.add(msg_hash)
                    logger.info(f"Delivered message to {msg['to']}")

                    # Mark as sent in Notion (append confirmation)
                    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
                    await notion.append_block(
                        TELEGRAM_OUTBOX_PAGE_ID,
                        f"✅ SENT — {msg['to']} — {now}"
                    )

        # Keep sent_messages set from growing too large
        if len(sent_messages) > 1000:
            sent_messages.clear()

    except Exception as e:
        logger.error(f"Error polling outbox: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MORNING BRIEF JOB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def send_morning_brief(context: ContextTypes.DEFAULT_TYPE):
    """
    Read the latest morning brief from AI Suggestions and send to groups.
    Omni Sight writes the brief to AI Suggestions at 09:00,
    this bot picks it up at 09:05 and distributes.
    """
    try:
        result = await notion.get_page_content(AI_SUGGESTIONS_PAGE_ID)
        if not result:
            logger.warning("Could not read AI Suggestions page")
            return

        blocks = result.get("results", [])
        raw_text = notion.extract_text_from_blocks(blocks)

        # Find the latest morning brief
        today_str = datetime.now(TZ).strftime("%Y-%m-%d")
        brief_text = None

        # Look for today's brief marker
        if "MORNING BRIEF" in raw_text and today_str in raw_text:
            # Extract the brief section
            start = raw_text.find("MORNING BRIEF")
            # Find the end (next major section or end of content)
            end = raw_text.find("WEEKLY SUMMARY", start + 1)
            if end == -1:
                end = raw_text.find("SCRIPT IMPROVEMENT", start + 1)
            if end == -1:
                end = min(start + 2000, len(raw_text))

            brief_text = raw_text[start:end].strip()

        if brief_text:
            # Send brief to Team Leaders group (all hub leaders see business overview)
            leaders_msg = f"📋 *OMNI SIGHT — Daily Brief*\n{'━' * 25}\n{brief_text[:3500]}"
            if ADMIN_GROUP_ID:
                await context.bot.send_message(
                    chat_id=int(ADMIN_GROUP_ID),
                    text=leaders_msg,
                    parse_mode=ParseMode.MARKDOWN,
                )
                logger.info("Morning brief sent to Team Leaders group")

            # Send Safe Offers filtered version
            if SAFE_OFFERS_GROUP_ID:
                # Filter for Safe Offers relevant content
                so_lines = []
                for line in brief_text.split("\n"):
                    if any(kw in line.lower() for kw in ["safe offers", "luka", "dušan", "dusan", "all hubs", "overall", "completion", "overdue", "focus"]):
                        so_lines.append(line)

                if so_lines:
                    so_msg = f"📋 *Morning Brief — Safe Offers*\n{'━' * 25}\n" + "\n".join(so_lines)
                    await context.bot.send_message(
                        chat_id=int(SAFE_OFFERS_GROUP_ID),
                        text=so_msg[:3500],
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    logger.info("Morning brief (filtered) sent to Safe Offers group")
        else:
            logger.info("No morning brief found for today")

    except Exception as e:
        logger.error(f"Error sending morning brief: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TELEGRAM COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register user's chat ID for personal messages"""
    user = update.effective_user
    username = user.username

    # Try a fresh sync in case member was just added to Notion
    if username and username not in TEAM_HANDLES:
        await sync_team_directory()

    if username and username in TEAM_HANDLES:
        TEAM_HANDLES[username]["chat_id"] = update.effective_chat.id
        save_chat_ids()
        dept_str = ", ".join(TEAM_HANDLES[username]["department"])
        await update.message.reply_text(
            f"✅ Welcome {TEAM_HANDLES[username]['name']}!\n\n"
            f"You're registered for TeamFlow notifications.\n"
            f"Department: {dept_str}\n\n"
            f"Commands:\n"
            f"/status — Check your pending tasks\n"
            f"/brief — Get today's morning brief\n"
            f"/help — See all commands"
        )
        logger.info(f"Registered {username} with chat_id {update.effective_chat.id}")
    else:
        source = "Notion Team Directory" if TEAM_DIRECTORY_PAGE_ID else "the team directory"
        await update.message.reply_text(
            f"👋 Hi {user.first_name}!\n\n"
            f"Your Telegram username (@{username}) is not in {source}.\n"
            f"Ask an admin to add you and then try /start again."
        )


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setup command for Marcus to register group chat IDs"""
    user = update.effective_user
    if user.username not in OWNER_USERNAMES:
        await update.message.reply_text("⟔ Only authorized admins can use /setup")
        return

    chat = update.effective_chat

    if len(context.args) > 0:
        group_type = context.args[0].lower()

        if group_type == "admin":
            global ADMIN_GROUP_ID
            ADMIN_GROUP_ID = str(chat.id)
            await update.message.reply_text(
                f"✅ Team Leaders group registered!\n"
                f"Chat ID: {chat.id}\n"
                f"All hub leaders will see business updates here.\n"
                f"Set ADMIN_GROUP_ID={chat.id} in your Render env vars."
            )
        elif group_type == "safeoffers":
            global SAFE_OFFERS_GROUP_ID
            SAFE_OFFERS_GROUP_ID = str(chat.id)
            await update.message.reply_text(
                f"✅ Safe Offers group registered!\n"
                f"Chat ID: {chat.id}\n"
                f"Set SAFE_OFFERS_GROUP_ID={chat.id} in your Render env vars."
            )
        else:
            await update.message.reply_text(
                "Usage:\n"
                "/setup admin — Register this chat as Team Leaders group\n"
                "/setup safeoffers — Register this chat as Safe Offers group"
            )
    else:
        await update.message.reply_text(
            "Usage:\n"
            "/setup admin — Register this chat as Admin group\n"
            "/setup safeoffers — Register this chat as Safe Offers group"
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's current task status from Notion"""
    user = update.effective_user
    username = user.username
    name = get_name_by_handle(username) if username else "Unknown"

    await update.message.reply_text(
        f"📊 *Status for {name}*\n\n"
        f"Omni Sight monitors your tasks automatically.\n"
        f"Check your hub's Fix Tasks in Notion for details.\n\n"
        f"Mention @OmniSight in Notion for a personalized update.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get today's morning brief on demand"""
    await update.message.reply_text("📋 Fetching today's brief from Notion...")

    # Reuse the morning brief function but send to requesting user
    try:
        result = await notion.get_page_content(AI_SUGGESTIONS_PAGE_ID)
        if not result:
            await update.message.reply_text("❌ Could not read AI Suggestions page")
            return

        blocks = result.get("results", [])
        raw_text = notion.extract_text_from_blocks(blocks)

        today_str = datetime.now(TZ).strftime("%Y-%m-%d")

        if "MORNING BRIEF" in raw_text:
            start = raw_text.rfind("MORNING BRIEF")
            end = min(start + 2000, len(raw_text))
            brief = raw_text[start:end].strip()

            await update.message.reply_text(
                f"📋 *Latest Brief*\n{'━' * 25}\n{brief[:3500]}",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("No morning brief found. Omni Sight may not have run yet today.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available commands"""
    await update.message.reply_text(
        "🤖 *TeamFlow Bot Commands*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "/start — Register for notifications\n"
        "/status — Check your task status\n"
        "/brief — Get today's morning brief\n"
        "/help — Show this message\n\n"
        "*Admin only:*\n"
        "/setup admin — Set this chat as Team Leaders group\n"
        "/setup safeoffers — Set this chat as Safe Offers group\n"
        "/force\\_brief — Force send morning brief now\n"
        "/outbox — Check Outbox for pending messages\n",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_force_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force send morning brief (admin only)"""
    user = update.effective_user
    if user.username not in OWNER_USERNAMES:
        await update.message.reply_text("⟔ Only authorized admins can use /force_brief")
        return

    await update.message.reply_text("📋 Forcing morning brief delivery...")
    await send_morning_brief(context)
    await update.message.reply_text("✅ Morning brief sent to all groups")


async def cmd_outbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Outbox status (admin only)"""
    user = update.effective_user
    if user.username not in OWNER_USERNAMES:
        await update.message.reply_text("⛔ Only authorized admins can use /outbox")
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
                f"Already sent: {len(sent_messages)}\n\n"
                f"Outbox is polled every {OUTBOX_POLL_INTERVAL} seconds.",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text("❌ Could not read Outbox page")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in group chats (for future reply-to-bot feature)"""
    # For now, just log group messages that mention the bot
    if update.message and update.message.text:
        text = update.message.text
        bot_username = context.bot.username

        if f"@{bot_username}" in text:
            await update.message.reply_text(
                "👋 I'm TeamFlow Bot! I deliver notifications from Omni Sight and Stratex.\n"
                "Use /help to see available commands."
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEALTH CHECK (for Render)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def health_check():
    """Simple HTTP server for Render health checks"""
    from aiohttp import web

    async def handle(request):
        return web.Response(text="TeamFlow Bot is running ✅")

    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/health", handle)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server running on port {port}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def post_init(application: Application):
    """Run after application initialization — sync team directory from Notion"""
    await sync_team_directory()
    logger.info(f"Team directory loaded: {len(TEAM_HANDLES)} members")


def main():
    """Start the bot"""
    # Validate config
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Set it in environment variables.")
        return
    if not NOTION_API_KEY:
        logger.error("NOTION_API_KEY not set! Set it in environment variables.")
        return

    # Load saved chat IDs (fallback directory gets chat IDs immediately)
    load_chat_ids()

    # Build application with post_init hook for async Notion sync
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("setup", cmd_setup))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("force_brief", cmd_force_brief))
    app.add_handler(CommandHandler("outbox", cmd_outbox))

    # Group message handler
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        handle_group_message
    ))

    # Schedule jobs
    job_queue = app.job_queue

    # Poll Notion Outbox every 60 seconds
    job_queue.run_repeating(
        poll_outbox,
        interval=OUTBOX_POLL_INTERVAL,
        first=10,
        name="outbox_poll"
    )

    # Refresh team directory from Notion every 5 minutes
    job_queue.run_repeating(
        refresh_team_directory,
        interval=DIRECTORY_REFRESH_INTERVAL,
        first=60,
        name="directory_refresh"
    )

    # Morning brief at 09:05 (5 min after Omni Sight runs at 09:00)
    brief_time = datetime.now(TZ).replace(
        hour=MORNING_BRIEF_HOUR,
        minute=MORNING_BRIEF_MINUTE,
        second=0,
        microsecond=0,
    ).timetz()

    job_queue.run_daily(
        send_morning_brief,
        time=brief_time,
        name="morning_brief"
    )

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("🤖 TeamFlow Bot v3.0 Starting")
    logger.info(f"📬 Outbox polling: every {OUTBOX_POLL_INTERVAL}s")
    logger.info(f"📋 Morning brief: {MORNING_BRIEF_HOUR}:{MORNING_BRIEF_MINUTE:02d}")
    logger.info(f"🌍 Timezone: {TZ}")
    logger.info(f"👥 Team Leaders Group: {'SET' if ADMIN_GROUP_ID else 'NOT SET'}")
    logger.info(f"🔒 Safe Offers Group: {'SET' if SAFE_OFFERS_GROUP_ID else 'NOT SET'}")
    logger.info(f"📇 Team Directory: {'NOTION' if TEAM_DIRECTORY_PAGE_ID else 'FALLBACK'}")
    logger.info(f"👤 Team Members: {len(TEAM_HANDLES)}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Start health check server in background
    loop = asyncio.get_event_loop()
    loop.create_task(health_check())

    # Start polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
