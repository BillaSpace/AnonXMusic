# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

from anony import db


class PlayMode:
    """Manage default play platform (YouTube/Spotify)"""

    async def set_mode(self, chat_id: int, mode: str) -> str:
        mode = mode.lower()
        if mode not in ["youtube", "spotify"]:
            return "Invalid mode! Choose either 'youtube' or 'spotify'."
        await db.set_mode(chat_id, mode)
        return f"✅ Play mode set to **{mode.capitalize()}**"

    async def get_mode(self, chat_id: int) -> str:
        mode = await db.get_mode(chat_id)
        return mode or "youtube"  # default fallback
