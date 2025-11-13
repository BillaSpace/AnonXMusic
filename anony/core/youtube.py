import os
import re
import random
import asyncio
from pathlib import Path
from typing import Optional, Union

import yt_dlp
from py_yt import VideosSearch
from pyrogram import enums, types
import aiohttp
import aiofiles

from anony import config, logger
from anony.helpers import Track, utils


class YouTube:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.warned = False
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.id_regex = re.compile(r"(?:v=|youtu\.be/|/watch\?v=|/embed/|/v/)([A-Za-z0-9_-]{11})")

    def get_cookies(self):
        if not self.checked:
            path = Path("anony/cookies")
            if path.exists() and path.is_dir():
                for file in path.iterdir():
                    if file.suffix == ".txt":
                        self.cookies.append(file.name)
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return str(Path("anony/cookies") / random.choice(self.cookies))

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def extract_id(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = self.id_regex.search(text)
        if m:
            return m.group(1)
        m2 = re.search(r"([A-Za-z0-9_-]{11})", text)
        if m2:
            return m2.group(1)
        return None

    def url(self, message_1: types.Message) -> Union[str, None]:
        messages = [message_1]
        link = None
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            text = message.text or message.caption or ""

            if message.entities:
                for entity in message.entities:
                    if entity.type == enums.MessageEntityType.URL:
                        link = text[entity.offset : entity.offset + entity.length]
                        break

            if message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == enums.MessageEntityType.TEXT_LINK:
                        link = entity.url
                        break

        if link:
            return link.split("&si")[0].split("?si")[0]
        return None

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        _search = VideosSearch(query, limit=1)
        results = await _search.next()
        if results and results.get("result"):
            data = results["result"][0]
            return Track(
                id=data.get("id"),
                channel_name=data.get("channel", {}).get("name"),
                duration=data.get("duration"),
                duration_sec=utils.to_seconds(data.get("duration")),
                message_id=m_id,
                title=(data.get("title") or "")[:25],
                thumbnail=(data.get("thumbnails", [{}])[-1].get("url") or "").split("?")[0],
                url=data.get("link"),
                view_count=data.get("viewCount", {}).get("short") if data.get("viewCount") else None,
                video=video,
            )
        return None

    async def playlist(self, *args) -> list[str]:
        limit = None
        url = None
        for a in args:
            if isinstance(a, int):
                limit = a
            elif isinstance(a, str):
                if a.startswith("http") or re.search(self.regex, a):
                    url = a.split("&si")[0].split("?si")[0]
                else:
                    try:
                        limit = int(a)
                    except Exception:
                        pass
            else:
                try:
                    maybe = self.url(a)
                    if maybe:
                        url = maybe
                except Exception:
                    pass
        if limit is None:
            limit = 50
        if not url:
            return []
        vids = []
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "ignoreerrors": True,
            "geo_bypass": True,
            "skip_download": True,
            "playlistend": limit,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False) or {}
                for entry in info.get("entries", []):
                    if not entry:
                        continue
                    vid = entry.get("id") or entry.get("url")
                    if not vid and isinstance(entry, str):
                        vid = entry
                    if vid:
                        vids.append(vid)
        except Exception:
            pass
        return vids

    async def _fetch_json(self, session, url, retries=2, timeout_s=30):
        for attempt in range(retries + 1):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    logger.warning("YT API returned %s for %s", resp.status, url)
            except (asyncio.TimeoutError, aiohttp.ClientError, asyncio.CancelledError):
                if attempt < retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
            break
        return None

    async def _stream_to_file(self, session, url, path, timeout_s=60):
        tmp = path.with_suffix(".part")
        for attempt in range(3):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_s)) as dl:
                    if dl.status != 200:
                        logger.warning("Download stream error: %s (%s)", dl.status, url)
                        return False
                    async with aiofiles.open(tmp, "wb") as f:
                        async for chunk in dl.content.iter_chunked(65536):
                            if not chunk:
                                break
                            await f.write(chunk)
                    tmp.replace(path)
                    return True
            except (asyncio.TimeoutError, aiohttp.ClientError, asyncio.CancelledError):
                if attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
            break
        return False

    async def download(self, video_id: str, video: bool = False) -> Optional[str]:
        downloads_dir = Path("downloads")
        downloads_dir.mkdir(parents=True, exist_ok=True)
        provided = video_id or ""
        extracted_id = self.extract_id(provided)
        filename_id = extracted_id if extracted_id else re.sub(r"[^\w\-\.]", "_", provided)[:64]
        ext = "mp4" if video else "mp3"
        filename = downloads_dir / f"{filename_id}.{ext}"
        if filename.exists():
            return str(filename)
        api_base = getattr(config, "API_URL", None)
        if not api_base:
            logger.error("API_URL not found in config.")
            return None
        api_base = api_base.rstrip("/")
        if video:
            api_url = f"{api_base}/download?id={extracted_id or provided}&format=1080"
        else:
            api_url = f"{api_base}/mp3?id={extracted_id or provided}"
        connector = aiohttp.TCPConnector(limit=5, force_close=True, enable_cleanup_closed=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            data = await self._fetch_json(session, api_url)
            download_url = data.get("downloadUrl") if isinstance(data, dict) else None
            if download_url:
                ok = await self._stream_to_file(session, download_url, filename)
                if ok:
                    return str(filename)
        try:
            cookie = self.get_cookies()
            base_opts = {
                "outtmpl": str(downloads_dir / "%(id)s.%(ext)s"),
                "quiet": True,
                "noplaylist": True,
                "geo_bypass": True,
                "no_warnings": True,
                "overwrites": False,
                "nocheckcertificate": True,
                "cookiefile": cookie,
            }
            if video:
                ydl_opts = {
                    **base_opts,
                    "format": "(bestvideo[height<=?720][ext=mp4])+(bestaudio)",
                    "merge_output_format": "mp4",
                }
            else:
                ydl_opts = {**base_opts, "format": "bestaudio[ext=webm][acodec=opus]"}
            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        url = provided if provided.startswith("http") else self.base + (extracted_id or provided)
                        ydl.download([url])
                    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
                        if cookie and Path(cookie).name in self.cookies:
                            self.cookies.remove(Path(cookie).name)
                        return None
                for ext_try in ("mp4", "webm", "m4a", "mp3"):
                    p = downloads_dir / f"{filename_id}.{ext_try}"
                    if p.exists():
                        return str(p)
                if extracted_id:
                    for ext_try in ("mp4", "webm", "m4a", "mp3"):
                        p2 = downloads_dir / f"{extracted_id}.{ext_try}"
                        if p2.exists():
                            return str(p2)
                return None
            return await asyncio.to_thread(_download)
        except Exception:
            return None
