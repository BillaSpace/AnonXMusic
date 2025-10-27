# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


from pyrogram import filters, types

from anony import anon, app, config, db, lang, queue, tg, yt, sp
from anony.helpers import buttons, utils
from anony.helpers._play import checkUB


@app.on_message(
    filters.command(["play", "playforce", "vplay", "vplayforce"])
    & filters.group
    & ~app.bl_users
)
@lang.language()
@checkUB
async def play_hndlr(
    _,
    m: types.Message,
    force: bool = False,
    video: bool = False,
    url: str = None,
    play_mode: str = "youtube",  # <-- new param from decorator
) -> None:
    """
    Handles /play and /vplay commands.
    Auto-detects URL type or uses DB-configured play mode (YouTube/Spotify).
    """

    sent = await m.reply_text(m.lang["play_searching"])

    # ---------------------------------------------------------
    # 1️⃣ Queue limit check
    # ---------------------------------------------------------
    if len(queue.get_queue(m.chat.id)) >= 20:
        return await sent.edit_text(m.lang["queue_full"])

    # ---------------------------------------------------------
    # 2️⃣ Check for replied media
    # ---------------------------------------------------------
    media = tg.get_media(m.reply_to_message) if m.reply_to_message else None

    file = None

    # ---------------------------------------------------------
    # 3️⃣ Detect URL or query based on mode
    # ---------------------------------------------------------
    if url:
        # --- Spotify URL ---
        if "spotify" in url and sp.valid(url):
            file = await sp.fetch_info(url, sent.id)
            if not file:
                return await sent.edit_text(m.lang["play_not_found"].format(config.SUPPORT_CHAT))

        # --- YouTube URL ---
        elif yt.valid(url):
            file = await yt.fetch_info(url, sent.id, video=video)
            if not file:
                return await sent.edit_text(m.lang["play_not_found"].format(config.SUPPORT_CHAT))

        else:
            return await sent.edit_text(m.lang["play_unsupported"])

    elif len(m.command) >= 2:
        query = " ".join(m.command[1:])

        # --- Determine based on play mode stored in DB ---
        if play_mode == "spotify" or "spotify" in query.lower():
            file = await sp.search(query, sent.id)
            if not file:
                return await sent.edit_text(m.lang["play_not_found"].format(config.SUPPORT_CHAT))
        else:
            file = await yt.search(query, sent.id, video=video)
            if not file:
                return await sent.edit_text(m.lang["play_not_found"].format(config.SUPPORT_CHAT))

    elif media:
        setattr(sent, "lang", m.lang)
        file = await tg.download(m.reply_to_message, sent)

    # ---------------------------------------------------------
    # 4️⃣ Duration restriction
    # ---------------------------------------------------------
    if not file:
        return await sent.edit_text(m.lang["play_not_found"].format(config.SUPPORT_CHAT))

    if file.duration_sec > 3600:
        return await sent.edit_text(m.lang["play_duration_limit"])

    # ---------------------------------------------------------
    # 5️⃣ Log play (if enabled)
    # ---------------------------------------------------------
    if await db.is_logger():
        await utils.play_log(m, file.title, file.duration)

    # ---------------------------------------------------------
    # 6️⃣ Add to queue
    # ---------------------------------------------------------
    file.user = m.from_user.mention
    if force:
        queue.force_add(m.chat.id, file)
    else:
        position = queue.add(m.chat.id, file)
        if await db.get_call(m.chat.id):
            return await sent.edit_text(
                m.lang["play_queued"].format(
                    position,
                    file.url,
                    file.title,
                    file.duration,
                    m.from_user.mention,
                ),
                reply_markup=buttons.play_queued(
                    m.chat.id, file.id, m.lang["play_now"]
                ),
            )

    # ---------------------------------------------------------
    # 7️⃣ Download from correct source
    # ---------------------------------------------------------
    if not file.file_path:
        try:
            if play_mode == "spotify" or "spotify" in (file.url or "").lower():
                file.file_path = await sp.download(file.url)
            else:
                file.file_path = await yt.download(file.id, video=video)

        except Exception:
            await anon.stop(m.chat.id)
            return await sent.edit_text(
                m.lang["error_no_file"].format(config.SUPPORT_CHAT)
            )

    # ---------------------------------------------------------
    # 8️⃣ Play in VC
    # ---------------------------------------------------------
    await anon.play_media(chat_id=m.chat.id, message=sent, media=file)
