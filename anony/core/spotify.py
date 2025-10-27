# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

import os
import re
import aiohttp
import asyncio
from anony.helpers import Track, utils
from urllib.parse import quote, urlparse


class Spotify:
    def __init__(self):
        self.regex = r"(https?://open\.spotify\.com/(track|album|playlist)/[A-Za-z0-9]+)(\?.*)?"
        self.spotify_api_base = "https://api.spotify.com/v1"
        self.download_api_base = os.getenv(
            "SPI_URL",
            "https://downloader.space/spotify/dl"
        )
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.access_token = None

    # ---------------------------------------------------------------------
    async def get_access_token(self):
        """Obtain Spotify API access token using Client Credentials flow."""
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in environment variables."
            )

        auth_url = "https://accounts.spotify.com/api/token"
        auth_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(auth_url, data=auth_data) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to authenticate with Spotify API: {resp.status}")
                data = await resp.json()
                self.access_token = data.get("access_token")
                return self.access_token

    # ---------------------------------------------------------------------
    def valid(self, url: str) -> bool:
        """Validate Spotify URL."""
        return bool(re.match(self.regex, url))

    # ---------------------------------------------------------------------
    async def fetch_info(self, url: str, m_id: int) -> Track | None:
        """Fetch metadata from Spotify Web API for a given Spotify URL."""
        if not self.valid(url):
            return None

        match = re.match(self.regex, url)
        if not match:
            return None
        resource_type, resource_id = match.group(2), match.group(1).split("/")[-1]

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
                        async with session.get(endpoint, headers=headers) as retry_resp:
                            if retry_resp.status != 200:
                                return None
                            data = await retry_resp.json()
                    else:
                        return None
                else:
                    data = await resp.json()

        # Parse data for track/album/playlist
        if resource_type == "track":
            return self._parse_track_data(data, url, m_id)
        elif resource_type in ["album", "playlist"]:
            items = data.get("tracks", {}).get("items", [])
            if not items:
                return None
            first = items[0].get("track") if resource_type == "playlist" else items[0]
            return self._parse_track_data(first, url, m_id)
        return None

    # ---------------------------------------------------------------------
    def _parse_track_data(self, data: dict, url: str, m_id: int) -> Track:
        """Helper: convert Spotify JSON data into a Track object."""
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

    # ---------------------------------------------------------------------
    async def search(self, query: str, m_id: int) -> Track | None:
        """Search for a Spotify track by query and return a Track object."""
        if not self.access_token:
            await self.get_access_token()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"q": query, "type": "track", "limit": 1}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.spotify_api_base}/search", headers=headers, params=params
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        items = data.get("tracks", {}).get("items", [])
        if not items:
            return None

        track = items[0]
        track_url = f"https://open.spotify.com/track/{track['id']}"
        return self._parse_track_data(track, track_url, m_id)

    # ---------------------------------------------------------------------
    async def download(self, url: str) -> str | None:
        """Download Spotify audio via external API. Returns local file path or None."""
        params = {"url": url}
        async with aiohttp.ClientSession() as session:
            async with session.get(self.download_api_base, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        if (
            not data.get("success")
            or not data.get("data")
            or not data["data"].get("downloadLinks")
        ):
            return None

        download_links = data["data"]["downloadLinks"]
        dl_url, ext = None, "mp3"
        for link in download_links:
            if link.get("type") == "audio":
                dl_url = link.get("url")
                ext = link.get("extension", "mp3")
                break

        if not dl_url:
            return None

        os.makedirs("downloads", exist_ok=True)
        filename = f"downloads/{utils.sanitize_filename(data['data']['title'])}.{ext}"

        async with aiohttp.ClientSession() as session:
            async with session.get(dl_url) as dl_resp:
                if dl_resp.status != 200:
                    return None
                content = await dl_resp.read()

        with open(filename, "wb") as f:
            f.write(content)

        return filename
