# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

from pyrogram import filters
from pyrogram.types import Message

from anony import app, db


class PlayMode:
    """Manage default play platform (YouTube/Spotify)"""

    async def set_mode(self, chat_id: int, mode: str) -> str:
        mode = mode.lower()
        if mode not in ["youtube", "spotify"]:
            return "❌ Invalid mode! Choose either 'youtube' or 'spotify'."
        await db.set_mode(chat_id, mode)
        return f"✅ Play mode set to {mode.capitalize()}."

    async def get_mode(self, chat_id: int) -> str:
        mode = await db.get_mode(chat_id)
        return mode or "youtube"  # default fallback


mode = PlayMode()

@app.on_message(filters.command("mode") & filters.group & ~app.bl_users)
async def change_mode(_, m: Message):
    """
    Handles /mode command:
    - /mode → shows current mode
    - /mode youtube → sets mode to YouTube
    - /mode spotify → sets mode to Spotify
    """

    if len(m.command) == 1:
        current = await mode.get_mode(m.chat.id)
        return await m.reply_text(
            f"🎶 Current play mode: {current.capitalize()}\n\n"
            "Use `/mode youtube` or `/mode spotify` to change it.",
            disable_web_page_preview=True,
        )

    new_mode = m.command[1].lower()
    msg = await mode.set_mode(m.chat.id, new_mode)
    await m.reply_text(msg)
