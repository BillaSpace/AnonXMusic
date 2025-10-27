# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import re
import asyncio

from pyrogram import enums, errors, types

from anony import app, config, db, yt, sp  # sp = Spotify instance exported from anony (project-wide)
# If your project exposes spotify instance under another name, adjust the import above.


def checkUB(play):
    """
    Decorator that validates user, chat, permissions, and bot presence
    before executing a playback command.

    - Supports URL detection for YouTube (via yt.url) and Spotify (open.spotify.com).
    - Reads play mode from DB and passes it to the wrapped `play` function.
    - Preserves existing permission logic (force/admin checks).
    - Ensures assistant/userbot joins the chat if required.
    """

    async def wrapper(_, m: types.Message):
        # -------------------------
        # 1) Basic user / chat checks
        # -------------------------
        if not m.from_user:
            return await m.reply_text(m.lang["play_user_invalid"])

        if m.chat.type != enums.ChatType.SUPERGROUP:
            await m.reply_text(m.lang["play_chat_invalid"])
            return await app.leave_chat(m.chat.id)

        # -------------------------
        # 2) Command / argument checks
        # -------------------------
        if not m.reply_to_message and (
            len(m.command) < 2 or (len(m.command) == 2 and m.command[1] == "-f")
        ):
            return await m.reply_text(m.lang["play_usage"])

        force = m.command[0].endswith("force") or (
            len(m.command) > 1 and "-f" in m.command[1]
        )
        video = m.command[0][0] == "v" and config.VIDEO_PLAY

        # -------------------------
        # 3) URL detection:
        #    - Prefer yt.url(m) (existing YouTube extractor)
        #    - Also scan message/caption for Spotify links
        # -------------------------
        url = None
        try:
            url = yt.url(m)  # existing helper that extracts URLs (mostly youtube in your code)
        except Exception:
            url = None

        # try to find spotify link in message/caption if present
        text = (m.text or "") + " " + (m.caption or "")
        spotify_match = re.search(
            r"(https?://open\.spotify\.com/(track|album|playlist)/[A-Za-z0-9]+)(\?.*)?",
            text,
            flags=re.IGNORECASE,
        )
        spotify_url = spotify_match.group(1) if spotify_match else None

        # If we found a spotify link, prefer it as the 'url' to pass along
        if spotify_url:
            url = spotify_url

        # validate url(s): if url exists and is a youtube url the yt.valid check helps
        if url:
            # if it's a spotify link, validate via sp.valid
            if "spotify" in url.lower():
                if not getattr(sp, "valid", lambda u: True)(url):
                    return await m.reply_text(m.lang["play_unsupported"])
            else:
                # fallback to youtube validation if possible
                if hasattr(yt, "valid") and not yt.valid(url):
                    return await m.reply_text(m.lang["play_unsupported"])

        # -------------------------
        # 4) Fetch play mode from DB
        #    Support both db.get_play_mode and db.get_mode (safe fallback)
        # -------------------------
        try:
            play_mode = await db.get_play_mode(m.chat.id)
        except AttributeError:
            # older/newer naming fallback
            try:
                play_mode = await db.get_mode(m.chat.id)
            except Exception:
                play_mode = None
        except Exception:
            play_mode = None

        # default to youtube if no mode set
        if not play_mode:
            play_mode = "youtube"

        # -------------------------
        # 5) Admin/authorized check for mode or force (preserves original behavior)
        # -------------------------
        if play_mode or force:
            adminlist = await db.get_admins(m.chat.id)
            if (
                m.from_user.id not in adminlist
                and not await db.is_auth(m.chat.id, m.from_user.id)
                and m.from_user.id not in app.sudoers
            ):
                return await m.reply_text(m.lang["play_admin"])

        # -------------------------
        # 6) Ensure assistant / client presence in chat (same logic as before)
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
                        await app.unban_chat_member(
                            chat_id=m.chat.id, user_id=client.id
                        )
                    except Exception:
                        return await m.reply_text(
                            m.lang["play_banned"].format(
                                app.name,
                                client.id,
                                client.mention,
                                f"@{client.username}" if client.username else None,
                            )
                        )
            except errors.ChatAdminRequired:
                return await m.reply_text(m.lang["admin_required"])
            except errors.UserNotParticipant:
                # try to resolve an invite / join
                if m.chat.username:
                    invite_link = m.chat.username
                    try:
                        await client.resolve_peer(invite_link)
                    except Exception:
                        pass
                else:
                    try:
                        invite_link = (await app.get_chat(m.chat.id)).invite_link
                        if not invite_link:
                            invite_link = await app.export_chat_invite_link(m.chat.id)
                    except errors.ChatAdminRequired:
                        return await m.reply_text(m.lang["admin_required"])
                    except Exception as ex:
                        return await m.reply_text(
                            m.lang["play_invite_error"].format(type(ex).__name__)
                        )

                umm = await m.reply_text(m.lang["play_invite"].format(app.name))
                await asyncio.sleep(2)
                try:
                    await client.join_chat(invite_link)
                except errors.UserAlreadyParticipant:
                    pass
                except errors.InviteRequestSent:
                    try:
                        await client.approve_chat_join_request(m.chat.id, client.id)
                    except Exception as ex:
                        return await umm.edit_text(
                            m.lang["play_invite_error"].format(type(ex).__name__)
                        )
                except Exception as ex:
                    return await umm.edit_text(
                        m.lang["play_invite_error"].format(type(ex).__name__)
                    )

                await umm.delete()
                await client.resolve_peer(m.chat.id)

        # -------------------------
        # 7) Try to delete the original trigger message (best-effort)
        # -------------------------
        try:
            await m.delete()
        except Exception:
            pass

        # -------------------------
        # 8) Call wrapped play function
        #    Pass url and play_mode so the play handler will choose Spotify/YouTube accordingly
        # -------------------------
        return await play(_, m, force, video, url, play_mode)

    return wrapper
