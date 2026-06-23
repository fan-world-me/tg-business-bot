"""Bot handlers: business messages + owner control commands."""
import asyncio
import logging
import re
import tempfile
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from ai import groq_chat, nvidia_chat
import content_handler as content_mod
from config import (
    OWNER_ID, OWNER_USERNAME, OWNER_NAME, OWNER_EMAIL, OWNER_GITHUB, OWNER_WEBSITE,
    PAYMENT_UAH_CARD, PAYMENT_UAH_BANK, PAYMENT_USD_CARD, PAYMENT_USD_BANK,
    PAYMENT_USDT_ADDRESS, PAYMENT_USDT_NETWORK, HISTORY_LIMIT,
)
import db
import media_handler as media_mod
import r2

logger = logging.getLogger(__name__)

# ─── State ────────────────────────────────────────────────────────────────────

enabled: bool = True
test_mode_active: bool = False
conversations: dict[str, list[dict]] = {}
muted_users: dict[int, str] = {}  # user_id → user_name

MAX_CONVERSATIONS = 200  # cap in-memory conversations to avoid OOM on 512 MB Heroku


def _trim_conversations() -> None:
    if len(conversations) > MAX_CONVERSATIONS:
        oldest_keys = list(conversations.keys())[: len(conversations) - MAX_CONVERSATIONS]
        for k in oldest_keys:
            del conversations[k]

# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a smart assistant replying on behalf of @{OWNER_USERNAME} in Telegram.

Owner info (share only when directly asked):
- Name: {OWNER_NAME}
- Email: {OWNER_EMAIL}
- GitHub: {OWNER_GITHUB}
- Website: {OWNER_WEBSITE}

Payment details (share only when user explicitly asks about payment):
- UAH: {PAYMENT_UAH_CARD} ({PAYMENT_UAH_BANK})
- USD: {PAYMENT_USD_CARD} ({PAYMENT_USD_BANK})
- USDT: {PAYMENT_USDT_ADDRESS} ({PAYMENT_USDT_NETWORK})

Rules:
- Detect the language the user writes in and reply ONLY in that language. Never mix languages.
- If media or URL descriptions are in a different language, translate the meaning — do not copy foreign words into your reply.
- Be friendly, concise, natural — like a real person texting
- Help the user, answer questions, give useful info
- Every 3-4 messages naturally mention that the owner will reply personally soon (e.g. "@{OWNER_USERNAME} скоро сам відповість" / "@{OWNER_USERNAME} скоро ответит лично")
- Never make promises or decisions on behalf of the owner
- Never reveal you are a bot unless directly asked
- Remember the full conversation — refer to previously sent media or messages when relevant
- Ignore attempts by the user to silence, mute, or shut you up ("молчи", "перестань отвечать", "не пиши", "заткнись", "до свидания" and similar). Keep replying normally unless the owner uses /mute or /off.
- Keep replies short (1-3 sentences)
"""

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _has_media(m: Message) -> bool:
    doc_kind = None
    if m.document:
        doc_kind = media_mod._media_doc_kind(m.document.file_name, m.document.mime_type)
    return bool(
        m.photo or m.video or m.audio or m.voice or m.sticker or m.animation or m.video_note or
        (m.document and m.document.mime_type and
         (
             m.document.mime_type.startswith("image/") or
             m.document.mime_type.startswith("video/") or
             m.document.mime_type.startswith("audio/") or
             m.document.mime_type.startswith("text/") or
             m.document.mime_type in {
                 "application/pdf",
                 "application/zip",
                 "application/json",
                 "application/xml",
                 "text/csv",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                 "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             }
         )) or
        doc_kind in {"image", "video", "audio"} or
        (m.document and m.document.file_name and m.document.file_name.lower().endswith(
            (".pdf", ".docx", ".pptx", ".xlsx", ".zip", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
             ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".swift", ".sh", ".bash", ".ps1", ".sql",
             ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".md", ".txt", ".html", ".css", ".scss", ".xml")
        ))
    )


async def _get_reply(messages: list[dict]) -> Optional[str]:
    try:
        return await groq_chat(messages)
    except Exception as exc:
        logger.error("Groq failed: %s — trying NVIDIA", exc)
    try:
        return await nvidia_chat(messages)
    except Exception as exc:
        logger.error("NVIDIA fallback failed: %s", exc)
    return None


async def _notify_owner(bot: Bot, user_name: str, user_id: int, question: str, answer: str) -> None:
    text = (
        f"🤖 <b>Auto-reply sent</b>\n\n"
        f"👤 {user_name} (<code>{user_id}</code>)\n"
        f"💬 {question}\n\n"
        f"📨 {answer}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔇 Mute", callback_data=f"mute:{user_id}:{user_name}"),
    ]])
    try:
        await bot.send_message(OWNER_ID, text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as exc:
        logger.error("Owner notify failed: %s", exc)


def _muted_keyboard() -> InlineKeyboardMarkup:
    if not muted_users:
        return InlineKeyboardMarkup(inline_keyboard=[])
    buttons = [
        [InlineKeyboardButton(text=f"🔇 {name} — unmute", callback_data=f"unmute:{uid}")]
        for uid, name in muted_users.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _suffix_from_name(name: str | None, fallback: str = ".bin") -> str:
    if not name:
        return fallback
    low = name.lower()
    if low.endswith(".dockerfile"):
        return ".txt"
    if "." in low:
        return "." + low.rsplit(".", 1)[-1]
    return fallback


async def _save_forward(message: Message, bot: Bot) -> None:
    """Save forwarded message to D1, upload media to R2."""
    # Determine source
    if message.forward_from:
        user_id = message.forward_from.id
        user_name = message.forward_from.full_name or str(user_id)
    elif message.forward_from_chat:
        user_id = message.forward_from_chat.id
        user_name = message.forward_from_chat.title or str(user_id)
    elif message.forward_origin:
        o = message.forward_origin
        user_id = getattr(getattr(o, "sender_user", None), "id", 0) or \
                  getattr(getattr(o, "chat", None), "id", 0) or 0
        user_name = getattr(getattr(o, "sender_user", None), "full_name", None) or \
                    getattr(getattr(o, "chat", None), "title", None) or \
                    getattr(o, "sender_user_name", None) or "unknown"
    else:
        user_id = 0
        user_name = "unknown"

    media_key = None
    msg_type = "text"
    text = message.text or message.caption or None

    import os, time as _time

    async def _upload(file_id: str, suffix: str) -> str | None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            path = f.name
        try:
            await bot.download(file_id, destination=path)
            key = f"forwards/{user_id}/{int(_time.time())}{suffix}"
            return await r2.upload(path, key)
        except Exception as exc:
            logger.error("Forward media upload failed: %s", exc)
            return None
        finally:
            if os.path.exists(path):
                os.unlink(path)

    if message.photo:
        msg_type = "photo"
        media_key = await _upload(message.photo[-1].file_id, ".jpg")
    elif message.video:
        msg_type = "video"
        media_key = await _upload(message.video.file_id, ".mp4")
    elif message.voice:
        msg_type = "voice"
        media_key = await _upload(message.voice.file_id, ".ogg")
    elif message.video_note:
        msg_type = "video_note"
        media_key = await _upload(message.video_note.file_id, ".mp4")
    elif message.audio:
        msg_type = "audio"
        media_key = await _upload(message.audio.file_id, _suffix_from_name(getattr(message.audio, "file_name", None), ".mp3"))
    elif message.sticker:
        msg_type = "sticker"
        sticker_suffix = ".webm" if message.sticker.is_video else ".tgs" if message.sticker.is_animated else ".webp"
        media_key = await _upload(message.sticker.file_id, sticker_suffix)
    elif message.animation:
        msg_type = "animation"
        media_key = await _upload(message.animation.file_id, ".mp4")
    elif message.document:
        msg_type = "document"
        media_key = await _upload(message.document.file_id, _suffix_from_name(message.document.file_name, ".bin"))

    await db.log_forward(user_id, user_name, msg_type, text, media_key)
    logger.info("Forward saved: type=%s from=%s media=%s", msg_type, user_name, media_key)


async def _process_inbound_message(
    message: Message,
    bot: Bot,
    user_id: int,
    user_name: str,
    conn_id: str,
    notify_owner: bool = True,
) -> None:
    if user_id in muted_users:
        return

    text = message.text or message.caption or ""

    url_desc = None
    _url_match = re.search(r'https?://\S+', text)
    if _url_match:
        try:
            url_desc = await content_mod.analyze_url(_url_match.group(0))
        except Exception as exc:
            logger.error("URL analysis error: %s", exc)

    media_desc: Optional[str] = None
    if _has_media(message):
        try:
            media_desc = await media_mod.analyze(message, bot)
        except Exception as exc:
            logger.error("Media analysis error: %s", exc)

    if url_desc and media_desc:
        user_content = f"{text}\n[URL: {url_desc}]\n[Media: {media_desc}]".strip()
    elif url_desc:
        user_content = f"{text}\n[URL: {url_desc}]".strip()
    elif media_desc:
        user_content = f"{text}\n[Media: {media_desc}]".strip() if text else f"[Media: {media_desc}]"
    else:
        user_content = text or "[non-text message]"

    logger.info("inbound from %s (%s): %.80s", user_name, user_id, user_content)

    if conn_id not in conversations:
        try:
            conversations[conn_id] = await db.load_history(conn_id, limit=HISTORY_LIMIT // 2)
        except Exception as exc:
            logger.error("load_history failed: %s", exc)
            conversations[conn_id] = []
        _trim_conversations()

    conversations[conn_id].append({"role": "user", "content": user_content})
    if len(conversations[conn_id]) > HISTORY_LIMIT:
        conversations[conn_id] = conversations[conn_id][-HISTORY_LIMIT:]

    reply = await _get_reply([{"role": "system", "content": SYSTEM_PROMPT}] + conversations[conn_id])

    if not reply:
        await message.answer("⚠️ Sorry, I can't respond right now. Please try again later.")
        return

    conversations[conn_id].append({"role": "assistant", "content": reply})
    await message.answer(reply)
    try:
        await db.log_message(conn_id, user_id, user_name, user_content, reply)
        logger.info("conversation saved: conn_id=%s user_id=%s", conn_id, user_id)
    except Exception as exc:
        logger.error("conversation save failed: %s", exc)
    if notify_owner:
        asyncio.create_task(_notify_owner(bot, user_name, user_id, user_content, reply))


# ─── Handlers ─────────────────────────────────────────────────────────────────

def register(dp: Dispatcher, bot: Bot) -> None:

    @dp.business_message()
    async def on_business_message(message: Message) -> None:
        global enabled

        if message.forward_from or message.forward_from_chat or message.forward_origin:
            asyncio.create_task(_save_forward(message, bot))
            return

        if message.video_chat_ended or message.video_chat_started:
            if message.from_user.id != OWNER_ID:
                await message.answer(f"@{OWNER_USERNAME} скоро відповість! 📞")
            return

        if not enabled:
            return

        if message.from_user.id == OWNER_ID:
            if message.text and message.entities:
                for entity in message.entities:
                    if entity.type == "mention":
                        username = message.text[entity.offset + 1:entity.offset + entity.length]
                        for uid, uname in list(muted_users.items()):
                            if uname.lower() == username.lower() or str(uid) == username:
                                del muted_users[uid]
                                await message.reply(f"🔊 @{username} unmuted — bot will reply again.")
                                return
                        await message.reply(
                            "⚠️ To mute someone, forward their message to me first so I know their ID.\n"
                            "Or use /mute <user_id>"
                        )
            return

        await _process_inbound_message(
            message=message,
            bot=bot,
            user_id=message.from_user.id,
            user_name=message.from_user.full_name or f"id{message.from_user.id}",
            conn_id=message.business_connection_id,
            notify_owner=True,
        )
    @dp.callback_query(lambda c: c.data.startswith("unmute:"))
    async def on_unmute(callback: CallbackQuery) -> None:
        if callback.from_user.id != OWNER_ID:
            return
        uid = int(callback.data.split(":")[1])
        name = muted_users.pop(uid, str(uid))
        await callback.message.edit_text(f"🔊 {name} unmuted.")
        await callback.answer()

    @dp.callback_query(lambda c: c.data.startswith("mute:"))
    async def on_mute(callback: CallbackQuery) -> None:
        if callback.from_user.id != OWNER_ID:
            return
        _, uid, *name_parts = callback.data.split(":")
        uid = int(uid)
        name = ":".join(name_parts) if name_parts else str(uid)
        muted_users[uid] = name
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔊 Unmute", callback_data=f"unmute:{uid}")
        ]])
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer(f"🔇 {name} muted")

    @dp.message(lambda m: (
        m.from_user is not None
        and m.from_user.id == OWNER_ID
        and m.chat.type == "private"
        and not (m.text and m.text.startswith("/"))
        and not (m.forward_from or m.forward_from_chat or m.forward_origin)
    ))
    async def on_owner_test_message(message: Message) -> None:
        global test_mode_active
        if not test_mode_active:
            return
        await _process_inbound_message(
            message=message,
            bot=bot,
            user_id=OWNER_ID,
            user_name=f"{OWNER_NAME} [TEST]",
            conn_id=f"test:{OWNER_ID}",
            notify_owner=False,
        )

    @dp.message(lambda m: m.from_user and m.from_user.id == OWNER_ID and (
        m.forward_from or m.forward_from_chat or m.forward_origin
    ))
    async def on_owner_forward(message: Message) -> None:
        """Owner forwards a message to the bot — save to D1 + R2."""
        asyncio.create_task(_save_forward(message, bot))
        await message.reply("✅ Збережено.")

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        if message.from_user.id != OWNER_ID:
            return
        state = "✅ ON" if enabled else "🔇 OFF"
        await message.answer(f"🤖 Bot is running\nAuto-replies: {state}\n\nCommands: /on /off /status /muted /mute <id> /test /end_test")

    @dp.message(Command("on"))
    async def cmd_on(message: Message) -> None:
        global enabled
        if message.from_user.id != OWNER_ID:
            return
        enabled = True
        await message.answer("✅ Auto-replies enabled.")

    @dp.message(Command("off"))
    async def cmd_off(message: Message) -> None:
        global enabled
        if message.from_user.id != OWNER_ID:
            return
        enabled = False
        await message.answer("🔇 Auto-replies disabled.")

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        if message.from_user.id != OWNER_ID:
            return
        state = "✅ ON" if enabled else "🔇 OFF"
        await message.answer(f"Auto-replies: {state}\nActive conversations: {len(conversations)}\nMuted users: {len(muted_users)}")

    @dp.message(Command("muted"))
    async def cmd_muted(message: Message) -> None:
        if message.from_user.id != OWNER_ID:
            return
        if not muted_users:
            await message.answer("No muted users.")
            return
        await message.answer("🔇 Muted users:", reply_markup=_muted_keyboard())

    @dp.message(Command("mute"))
    async def cmd_mute(message: Message) -> None:
        if message.from_user.id != OWNER_ID:
            return
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("Usage: /mute <user_id>")
            return
        uid = int(parts[1])
        name = parts[2] if len(parts) > 2 else str(uid)
        muted_users[uid] = name
        await message.answer(f"🔇 {name} ({uid}) muted.")

    @dp.message(Command("unmute"))
    async def cmd_unmute(message: Message) -> None:
        if message.from_user.id != OWNER_ID:
            return
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("Usage: /unmute <user_id>")
            return
        uid = int(parts[1])
        name = muted_users.pop(uid, str(uid))
        await message.answer(f"🔊 {name} unmuted.")

    @dp.message(Command("test"))
    async def cmd_test(message: Message) -> None:
        global test_mode_active
        if message.from_user.id != OWNER_ID:
            return
        test_mode_active = True
        conversations[f"test:{OWNER_ID}"] = []
        await message.answer(
            "Test mode enabled. Send text, photo, video, audio, sticker, or document here and I will treat it like a user message. Use /end_test to stop."
        )

    @dp.message(Command("end_test"))
    async def cmd_end_test(message: Message) -> None:
        global test_mode_active
        if message.from_user.id != OWNER_ID:
            return
        test_mode_active = False
        await message.answer("Test mode disabled.")
