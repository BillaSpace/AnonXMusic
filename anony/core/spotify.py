# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

import os
import re
import aiohttp
import asyncio
from anony.helpers import Track, utils
from urllib.parse import urlparse

class Spotify:
    def __init__(self):
        self.regex = r"(https?://open\.spotify\.com/(track|album|playlist)/[A-Za-z0-9]+)(\?.*)?"
        self.spotify_api_base = "https://api.spotify.com/v1"
        self.download_api_base = os.getenv("SPI_URL", "https://downloader.app")
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.access_token = None

    async def get_access_token(self):
        """Obtain Spotify API access token using Client Credentials flow."""
        if not self.client_id or not self.client_secret:
            raise ValueError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in environment variables.")

        auth_url = "https://accounts.spotify.com/api/token"
        auth_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(auth_url, data=auth_data) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to authenticate with Spotify API: {resp.status}")
                data = await resp.json()
                self.access_token = data.get("access_token")
                return self.access_token

    def valid(self, url: str) -> bool:
        """Validate Spotify URL."""
        return bool(re.match(self.regex, url))

    async def fetch_info(self, url: str, m_id: int) -> Track | None:
        """Fetch metadata from Spotify Web API for a given Spotify URL."""
        if not self.valid(url):
            return None

        # Parse URL to determine type (track, album, playlist)
        match = re.match(self.regex, url)
        if not match:
            return None
        resource_type, resource_id = match.group(2), match.group(1).split('/')[-1]

        # Ensure access token is available
        if not self.access_token:
            await self.get_access_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        endpoint = f"{self.spotify_api_base}/{resource_type}s/{resource_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, headers=headers) as resp:
                if resp.status != 200:
                    if resp.status == 401:  # Token expired
                        await self.get_access_token()
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        async with session.get(endpoint, headers=headers) as resp:
                            if resp.status != 200:
                                return None
                            data = await resp.json()
                    else:
                        return None
                    data = await resp.json()

        if resource_type == "track":
            duration_ms = data.get("duration_ms", 0)
            duration_sec = duration_ms // 1000
            duration = utils.format_duration(duration_sec)
            return Track(
                id=data.get("id"),
                title=data.get("name")[:25],
                duration=duration,
                duration_sec=duration_sec,
                url=url,
                thumbnail=data.get("album", {}).get("images", [{}])[0].get("url"),
                channel_name=data.get("artists", [{}])[0].get("name"),
                message_id=m_id,
                video=False,
            )
        # For albums or playlists, return the first track as an example
        elif resource_type in ["album", "playlist"]:
            tracks = data.get("tracks", {}).get("items", [])
            if not tracks:
                return None
            track = tracks[0].get("track") if resource_type == "playlist" else tracks[0]
            duration_ms = track.get("duration_ms", 0)
            duration_sec = duration_ms // 1000
            duration = utils.format_duration(duration_sec)
            return Track(
                id=track.get("id"),
                title=track.get("name")[:25],
                duration=duration,
                duration_sec=duration_sec,
                url=url,
                thumbnail=track.get("album", {}).get("images", [{}])[0].get("url"),
                channel_name=track.get("artists", [{}])[0].get("name"),
                message_id=m_id,
                video=False,
            )
        return None

    async def download(self, url: str) -> str | None:
        """Download audio via api Returns local file path or None."""
        params = {"url": url}
        async with aiohttp.ClientSession() as session:
            async with session.get(self.download_api_base, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        if not data.get("success") or not data.get("data") or not data["data"].get("downloadLinks"):
            return None

        download_links = data["data"]["downloadLinks"]
        for link in download_links:
            if link.get("type") == "audio":
                dl_url = link.get("url")
                ext = link.get("extension", "mp3")
                break
        else:
            return None

        local_filename = f"downloads/{utils.sanitize_filename(data['data']['title'])}.{ext}"
        async with aiohttp.ClientSession() as session:
            async with session.get(dl_url) as dl_resp:
                if dl_resp.status != 200:
                    return None
                content = await dl_resp.read()

        os.makedirs("downloads", exist_ok=True)
        with open(local_filename, "wb") as f:
            f.write(content)

        return local_filename
