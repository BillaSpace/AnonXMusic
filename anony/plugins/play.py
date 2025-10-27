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
    play_mode: str = None,
) -> None:
    """
    Handles /play and /vplay commands.
    - Detects platform automatically for URLs (YouTube / Spotify)
    - Uses DB-configured platform for text queries
    """

    sent = await m.reply_text(m.lang["play_searching"])

    # 1️⃣ Queue limit check
    if len(queue.get_queue(m.chat.id)) >= 20:
        return await sent.edit_text(m.lang["queue_full"])

    # 2️⃣ Replied media check
    media = tg.get_media(m.reply_to_message) if m.reply_to_message else None
    file = None
    platform = play_mode or "youtube"  # fallback default

    # 3️⃣ Detect platform from URL
    if url:
        if "spotify.com" in url and sp.valid(url):
            platform = "spotify"
            file = await sp.fetch_info(url, sent.id)
        elif yt.valid(url):
            platform = "youtube"
            file = await yt.fetch_info(url, sent.id, video=video)
        else:
            return await sent.edit_text(m.lang["play_unsupported"])

    # 4️⃣ Handle text query (based on DB mode only)
    elif len(m.command) >= 2:
        query = " ".join(m.command[1:])
        if platform == "spotify":
            file = await sp.search(query, sent.id)
        else:
            file = await yt.search(query, sent.id, video=video)

    # 5️⃣ Handle replied media
    elif media:
        setattr(sent, "lang", m.lang)
        file = await tg.download(m.reply_to_message, sent)
        platform = "telegram"

    # 6️⃣ Validation
    if not file:
        return await sent.edit_text(m.lang["play_not_found"].format(config.SUPPORT_CHAT))

    if file.duration_sec > 3600:
        return await sent.edit_text(m.lang["play_duration_limit"])

    # 7️⃣ Optional: show platform info
    await sent.edit_text(
        f"🎵 <b>Detected platform:</b> <code>{platform.title()}</code>\n\n🔍 <b>Processing...</b>"
    )

    # 8️⃣ Play log
    if await db.is_logger():
        await utils.play_log(m, file.title, file.duration)

    # 9️⃣ Queue handling
    file.user = m.from_user.mention
    if force:
        queue.force_add(m.chat.id, file)
    else:
        pos = queue.add(m.chat.id, file)
        if await db.get_call(m.chat.id):
            return await sent.edit_text(
                m.lang["play_queued"].format(
                    pos,
                    file.url,
                    file.title,
                    file.duration,
                    m.from_user.mention,
                ),
                reply_markup=buttons.play_queued(
                    m.chat.id, file.id, m.lang["play_now"]
                ),
            )

    # 🔟 Download based on platform
    if not getattr(file, "file_path", None):
        try:
            if platform == "spotify":
                file.file_path = await sp.download(file.url)
            elif platform == "youtube":
                file.file_path = await yt.download(file.id, video=video)
            else:
                raise Exception("Unsupported platform for download")
        except Exception:
            await anon.stop(m.chat.id)
            return await sent.edit_text(
                m.lang["error_no_file"].format(config.SUPPORT_CHAT)
            )

    # 1️⃣1️⃣ Final playback
    await sent.edit_text(f"🎶 <b>Playing via:</b> <code>{platform.title()}</code>")
    await anon.play_media(chat_id=m.chat.id, message=sent, media=file)
