# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

import re
import asyncio
from pyrogram import enums, errors, types
from anony import app, config, db, yt, sp  # sp = Spotify instance


def checkUB(play):
    """
    Decorator that:
    - Verifies user/chat validity
    - Detects YouTube and Spotify URLs
    - Fetches play mode from DB
    - Ensures assistant/client presence
    - Passes `force`, `video`, `url`, and `play_mode` to the play handler
    """

    async def wrapper(_, m: types.Message):
        # -------------------------
        # 1️⃣ User and chat validity
        # -------------------------
        if not m.from_user:
            return await m.reply_text(m.lang["play_user_invalid"])

        if m.chat.type != enums.ChatType.SUPERGROUP:
            await m.reply_text(m.lang["play_chat_invalid"])
            try:
                await app.leave_chat(m.chat.id)
            except Exception:
                pass
            return

        # -------------------------
        # 2️⃣ Command parsing
        # -------------------------
        if not m.reply_to_message and (
            len(m.command) < 2 or (len(m.command) == 2 and m.command[1] == "-f")
        ):
            return await m.reply_text(m.lang["play_usage"])

        force = m.command[0].endswith("force") or (
            len(m.command) > 1 and "-f" in m.command[1]
        )
        video = m.command[0].startswith("v") and config.VIDEO_PLAY

        # -------------------------
        # 3️⃣ URL detection (YouTube + Spotify)
        # -------------------------
        url = None
        try:
            url = yt.url(m)  # Extract YouTube URL (if present)
        except Exception:
            url = None

        # Detect Spotify URLs
        text = (m.text or "") + " " + (m.caption or "")
        spotify_match = re.search(
            r"(https?://open\.spotify\.com/(track|album|playlist)/[A-Za-z0-9]+)(\?.*)?",
            text,
            flags=re.IGNORECASE,
        )
        spotify_url = spotify_match.group(1) if spotify_match else None

        if spotify_url:
            url = spotify_url

        # Validate URLs
        if url:
            if "spotify" in url.lower():
                if not getattr(sp, "valid", lambda _: True)(url):
                    return await m.reply_text(m.lang["play_unsupported"])
            else:
                if hasattr(yt, "valid") and not yt.valid(url):
                    return await m.reply_text(m.lang["play_unsupported"])

        # -------------------------
        # 4️⃣ Fetch play mode from DB (Unified)
        # -------------------------
        try:
            play_mode = await db.get_mode(m.chat.id)
        except Exception:
            play_mode = "youtube"

        if play_mode not in ["youtube", "spotify"]:
            play_mode = "youtube"

        # Debug (optional)
        # print(f"[DEBUG] Mode for {m.chat.id}: {play_mode}")

        # -------------------------
        # 5️⃣ Admin/authorization checks
        # -------------------------
        if force:
            adminlist = await db.get_admins(m.chat.id)
            if (
                m.from_user.id not in adminlist
                and not await db.is_auth(m.chat.id, m.from_user.id)
                and m.from_user.id not in app.sudoers
            ):
                return await m.reply_text(m.lang["play_admin"])

        # -------------------------
        # 6️⃣ Ensure assistant/client is in chat
        # -------------------------
        if m.chat.id not in db.active_calls:
            client = await db.get_client(m.chat.id)
            try:
                member = await app.get_chat_member(m.chat.id, client.id)
                if member.status in [
                    enums.ChatMemberStatus.BANNED,
                    enums.ChatMemberStatus.RESTRICTED,
                ]:
                    try:
                        await app.unban_chat_member(m.chat.id, client.id)
                    except Exception:
                        return await m.reply_text(
                            m.lang["play_banned"].format(
                                app.name,
                                client.id,
                                client.mention,
                                f"@{client.username}" if client.username else "",
                            )
                        )
            except errors.ChatAdminRequired:
                return await m.reply_text(m.lang["admin_required"])
            except errors.UserNotParticipant:
                # Attempt to join the chat
                invite_link = None
                try:
                    chat = await app.get_chat(m.chat.id)
                    invite_link = chat.invite_link or await app.export_chat_invite_link(
                        m.chat.id
                    )
                except errors.ChatAdminRequired:
                    return await m.reply_text(m.lang["admin_required"])
                except Exception as ex:
                    return await m.reply_text(
                        m.lang["play_invite_error"].format(type(ex).__name__)
                    )

                joining = await m.reply_text(m.lang["play_invite"].format(app.name))
                await asyncio.sleep(2)
                try:
                    await client.join_chat(invite_link)
                except errors.UserAlreadyParticipant:
                    pass
                except errors.InviteRequestSent:
                    try:
                        await client.approve_chat_join_request(m.chat.id, client.id)
                    except Exception as ex:
                        return await joining.edit_text(
                            m.lang["play_invite_error"].format(type(ex).__name__)
                        )
                except Exception as ex:
                    return await joining.edit_text(
                        m.lang["play_invite_error"].format(type(ex).__name__)
                    )

                await joining.delete()
                await client.resolve_peer(m.chat.id)

        # -------------------------
        # 7️⃣ Try deleting the trigger message (best-effort)
        # -------------------------
        try:
            await m.delete()
        except Exception:
            pass

        # -------------------------
        # 8️⃣ Call wrapped play() with args
        # -------------------------
        return await play(_, m, force, video, url, play_mode)

    return wrapper
