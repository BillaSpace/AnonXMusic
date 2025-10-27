# Copyright (c) 2025 BillaSpace
# Licensed under the MIT License.
# This file is part of AnonXMusic

import os
import re
import aiohttp
import asyncio
from urllib.parse import quote, urlparse
from anony.helpers import Track, utils


class Spotify:
    def __init__(self):
        # Regex for Spotify URLs
        self.regex = r"(https?://open\.spotify\.com/(track|album|playlist)/[A-Za-z0-9]+)(\?.*)?"
        self.spotify_api_base = "https://api.spotify.com/v1"
        self.api_base = os.getenv("SPI_URL", "https://downloader.space")
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
        """
        Fetch metadata using the external API for a given Spotify URL.
        This replaces direct Spotify Web API calls for simplicity.
        """
        if not self.valid(url):
            return None

        api_url = f"{self.api_base}/get_track?url={quote(url)}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        # Expect schema with `results` list
        results = data.get("results", [])
        if not results:
            return None

        item = results[0]
        return self._parse_track_result(item, m_id)

    # ---------------------------------------------------------------------
    async def search(self, query: str, m_id: int) -> Track | None:
        """
        Search for a Spotify track by query using the external API.
        """
        api_url = f"{self.api_base}/search?query={quote(query)}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        results = data.get("results", [])
        if not results:
            return None

        item = results[0]
        return self._parse_track_result(item, m_id)

    # ---------------------------------------------------------------------
    def _parse_track_result(self, item: dict, m_id: int) -> Track:
        """Convert external API result JSON into Track object."""
        duration_sec = int(item.get("duration", 0))
        duration = utils.format_duration(duration_sec)

        return Track(
            id=item.get("id"),
            title=item.get("name")[:25],
            duration=duration,
            duration_sec=duration_sec,
            url=item.get("spotify_url"),
            thumbnail=item.get("cover"),
            channel_name=item.get("artist"),
            message_id=m_id,
            video=False,
        )

    # ---------------------------------------------------------------------
    async def download(self, url: str) -> str | None:
        """
        Download Spotify audio via external API.
        from the new API schema.
        """
        api_url = f"{self.api_base}/get_track?url={quote(url)}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        results = data.get("results", [])
        if not results:
            return None

        item = results[0]
        dl_url = item.get("download_url")
        title = item.get("name", "spotify_track")

        if not dl_url:
            return None

        os.makedirs("downloads", exist_ok=True)
        filename = f"downloads/{utils.sanitize_filename(title)}.mp3"

        async with aiohttp.ClientSession() as session:
            async with session.get(dl_url) as dl_resp:
                if dl_resp.status != 200:
                    return None
                content = await dl_resp.read()

        with open(filename, "wb") as f:
            f.write(content)

        return filename
