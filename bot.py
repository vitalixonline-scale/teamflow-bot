"""
TeamFlow Telegram Bot v2.0
100% Notion-integrated — No website functionality
Reads from Notion Telegram Outbox, sends to Telegram groups and DMs
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

# Telegram Group Chat IDs (set via /setup command or env vars)
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")  # Team Leaders group — ALL hub leaders see business overview
SAFE_OFFERS_GROUP_ID = os.getenv("SAFE_OFFERS_GROUP_ID")  # Safe Offers team group

# Timezone
TZ = pytz.timezone(os.getenv("TIMEZONE", "Europe/Rome"))

# Polling interval for Notion Outbox (seconds)
OUTBOX_POLL_INTERVAL = int(os.getenv("OUTBOX_POLL_INTERVAL", "60"))

# Morning brief time (hour, minute)
MORNING_BRIEF_HOUR = int(os.getenv("MORNING_BRIEF_HOUR", "9"))
MORNING_BRIEF_MINUTE = int(os.getenv("MORNING_BRIEF_MINUTE", "5"))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEAM DIRECTORY (Telegram handles → chat IDs)
# Chat IDs are populated automatically when team members /start the bot
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEAM_HANDLES = {
    "marcus_agent": {"name": "Marcus", "department": ["Marketing", "Administration"], "chat_id": None},
    "nikonbelas": {"name": "Niko", "department": ["Marketing", "Safe Offers"], "chat_id": None},
    "ogiiiiz11": {"name": "Orhan", "department": ["Sales", "Resell"], "chat_id": None},
    "ognjen_89": {"name": "Ognjen", "department": ["Warehouse"], "chat_id": None},
    "lukawolk": {"name": "Luka", "department": ["Safe Offers", "Marketing"], "chat_id": None},
    "cb9999999999": {"name": "Dušan", "department": ["Safe Offers"], "chat_id": None},
    "jomlamladen": {"name": "Mladen", "department": ["Administration"], "chat_id": None},
}

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
# OUTBOX PARSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_outbox_messages(raw_text: str) -> List[Dict]:
    """
    Parse structured messages from Telegram Outbox page.

    Expected format:
    ---
    TO: @handle (or GROUP)
    TYPE: PERSONAL | GROUP | ESCALATION
    FROM: Omni Sight
    DATE: 2026-03-16
    ---
    Message content here
    ---
    """
    messages = []
    blocks = raw_text.split("---")

    i = 0
    while i < len(blocks):
        block = blocks[i].strip()

        # Look for TO: header
        if block.startswith("TO:") or "\nTO:" in block:
            lines = block.split("\n")
            msg = {"to": None, "type": "PERSONAL", "from": None, "date": None, "content": "", "raw": block}

            for line in lines:
                line = line.strip()
                if line.startswith("TO:"):
                    msg["to"] = line.replace("TO:", "").strip()
                elif line.startswith("TYPE:"):
                    msg["type"] = line.replace("TYPE:", "").strip()
                elif line.startswith("FROM:"):
                    msg["from"] = line.replace("FROM:", "").strip()
                elif line.startswith("DATE:"):
                    msg["date"] = line.replace("DATE:", "").strip()

            # Next block is the message content
            if i + 1 < len(blocks):
                msg["content"] = blocks[i + 1].strip()
                i += 1

            if msg["to"] and msg["content"]:
                messages.append(msg)

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

    if username and username in TEAM_HANDLES:
        TEAM_HANDLES[username]["chat_id"] = update.effective_chat.id
        save_chat_ids()
        await update.message.reply_text(
            f"✅ Welcome {TEAM_HANDLES[username]['name']}!\n\n"
            f"You're registered for TeamFlow notifications.\n"
            f"Department: {', '.join(TEAM_HANDLES[username]['department'])}\n\n"
            f"Commands:\n"
            f"/status — Check your pending tasks\n"
            f"/brief — Get today's morning brief\n"
            f"/help — See all commands"
        )
        logger.info(f"Registered {username} with chat_id {update.effective_chat.id}")
    else:
        await update.message.reply_text(
            f"👋 Hi {user.first_name}!\n\n"
            f"Your Telegram username (@{username}) is not in the TeamFlow directory.\n"
            f"Contact Marcus to be added."
        )


async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Setup command for Marcus to register group chat IDs"""
    user = update.effective_user
    if user.username != "marcus_agent":
        await update.message.reply_text("⛔ Only Marcus can use /setup")
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
    if user.username != "marcus_agent":
        await update.message.reply_text("⛔ Only Marcus can use /force_brief")
        return

    await update.message.reply_text("📋 Forcing morning brief delivery...")
    await send_morning_brief(context)
    await update.message.reply_text("✅ Morning brief sent to all groups")


async def cmd_outbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Outbox status (admin only)"""
    user = update.effective_user
    if user.username != "marcus_agent":
        await update.message.reply_text("⛔ Only Marcus can use /outbox")
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

def main():
    """Start the bot"""
    # Validate config
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Set it in environment variables.")
        return
    if not NOTION_API_KEY:
        logger.error("NOTION_API_KEY not set! Set it in environment variables.")
        return

    # Load saved chat IDs
    load_chat_ids()

    # Build application
    app = Application.builder().token(BOT_TOKEN).build()

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
    logger.info("🤖 TeamFlow Bot v2.0 Starting")
    logger.info(f"📬 Outbox polling: every {OUTBOX_POLL_INTERVAL}s")
    logger.info(f"📋 Morning brief: {MORNING_BRIEF_HOUR}:{MORNING_BRIEF_MINUTE:02d}")
    logger.info(f"🌍 Timezone: {TZ}")
    logger.info(f"👥 Team Leaders Group: {'SET' if ADMIN_GROUP_ID else 'NOT SET'}")
    logger.info(f"🔒 Safe Offers Group: {'SET' if SAFE_OFFERS_GROUP_ID else 'NOT SET'}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Start health check server in background
    loop = asyncio.get_event_loop()
    loop.create_task(health_check())

    # Start polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
