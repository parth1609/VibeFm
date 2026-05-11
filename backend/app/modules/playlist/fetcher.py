"""
Playlist Fetcher — yt-dlp Integration
Fetches playlist metadata and resolves direct audio stream URLs
from YouTube using yt-dlp without any video rendering.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import yt_dlp

from .models import AudioStreamInfo, Song

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# yt-dlp option presets
# ---------------------------------------------------------------------------

# Used when fetching playlist metadata only (no stream URLs needed)
_METADATA_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",   # fast: only fetch top-level info, no video page
    "skip_download": True,
    "ignoreerrors": True,             # skip geo-blocked / deleted videos gracefully
}

# Used when resolving a single video's best audio stream URL
_STREAM_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "format": (
        # Prefer: m4a (better browser support), then webm, then fallback
        "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
    ),
    "ignoreerrors": True,
    # Add comprehensive browser-like headers to bypass YouTube bot detection
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    },
    "noplaylist": True,  # Prevent playlist extraction to avoid bot detection
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
        }
    },
}

# Invidious instances for fallback when YouTube direct extraction fails
_INVIDIOUS_INSTANCES = [
    "https://yewtu.be",
    "https://invidious.snopyta.org", 
    "https://yewtu.be",
    "https://vid.puffyan.us",
]

# Fallback options for Invidious instances
_INVIDIOUS_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "format": "bestaudio/best",
    "ignoreerrors": True,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_playlist_songs(playlist_url: str) -> list[Song]:
    """
    Fetch all songs from a YouTube playlist URL.

    Runs yt-dlp in a thread-pool executor so it does not block the event loop.
    Returns a list of :class:`Song` objects with metadata populated.
    Deleted / private / geo-blocked videos are silently skipped.

    Args:
        playlist_url: Full YouTube playlist URL
                      (e.g. ``https://www.youtube.com/playlist?list=PLxxx``)

    Returns:
        List of :class:`Song` objects (may be empty if the playlist is private).

    Raises:
        ValueError: If the URL is not recognised as a YouTube playlist by yt-dlp.
    """
    loop = asyncio.get_running_loop()
    songs: list[Song] = await loop.run_in_executor(
        None, _sync_fetch_playlist, playlist_url
    )
    logger.info("Fetched %d songs from %s", len(songs), playlist_url)
    return songs


async def resolve_audio_stream(video_id: str) -> AudioStreamInfo:
    """
    Resolve the best audio-only stream URL for a YouTube video.

    The returned URL is a direct media URL (expires after a few hours).
    Call this just-in-time, right before the song needs to play.

    Args:
        video_id: YouTube video ID (e.g. ``"dQw4w9WgXcQ"``)

    Returns:
        :class:`AudioStreamInfo` with a ready-to-stream URL.

    Raises:
        RuntimeError: If yt-dlp cannot extract stream info.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, _sync_resolve_stream, url)
    logger.info("Resolved audio stream for %s → ext=%s abr=%s", video_id, info.ext, info.abr)
    return info


# ---------------------------------------------------------------------------
# Sync helpers (run inside executor)
# ---------------------------------------------------------------------------


def _sync_fetch_playlist(playlist_url: str) -> list[Song]:
    """Blocking yt-dlp call — must be run in an executor."""
    with yt_dlp.YoutubeDL(_METADATA_OPTS) as ydl:
        info = ydl.extract_info(playlist_url, download=False)

    if info is None:
        raise ValueError(f"yt-dlp returned no info for URL: {playlist_url}")

    # For a playlist, entries are under the "entries" key
    entries = info.get("entries") or []
    songs: list[Song] = []

    for entry in entries:
        if entry is None:
            continue  # deleted / private video placeholder

        video_id = entry.get("id") or entry.get("url", "").split("v=")[-1]
        if not video_id:
            continue

        title = entry.get("title") or "Unknown Title"
        # yt-dlp puts the uploader/channel as the closest thing to "artist"
        artist = (
            entry.get("uploader")
            or entry.get("channel")
            or entry.get("creator")
            or "Unknown Artist"
        )
        duration = entry.get("duration") or 0
        thumbnail = _best_thumbnail(entry.get("thumbnails") or [])

        songs.append(
            Song(
                video_id=video_id,
                title=title,
                artist=artist,
                duration_sec=int(duration),
                thumbnail_url=thumbnail,
            )
        )

    return songs


def _sync_resolve_stream(url: str) -> AudioStreamInfo:
    """Blocking yt-dlp call — must be run in an executor."""
    # Try YouTube first
    try:
        with yt_dlp.YoutubeDL(_STREAM_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
        
        if info and info.get("url"):
            return _create_stream_info(info)
    except Exception as e:
        logger.warning(f"YouTube direct extraction failed: {e}")
    
    # Fallback to Invidious instances
    video_id = url.split("v=")[-1].split("&")[0]
    for instance in _INVIDIOUS_INSTANCES:
        try:
            invidious_url = f"{instance}/watch?v={video_id}"
            with yt_dlp.YoutubeDL(_INVIDIOUS_OPTS) as ydl:
                info = ydl.extract_info(invidious_url, download=False)
            
            if info and info.get("url"):
                logger.info(f"Successfully used Invidious fallback: {instance}")
                return _create_stream_info(info)
        except Exception as e:
            logger.debug(f"Invidious instance {instance} failed: {e}")
            continue
    
    raise RuntimeError(f"Could not extract audio stream URL for: {url} (tried YouTube + Invidious fallbacks)")


def _create_stream_info(info: dict) -> AudioStreamInfo:
    """Create AudioStreamInfo from yt-dlp info dict."""
    # When format selection produces a single format, the stream URL is in
    # info["url"]; for merged formats it would be in info["requested_formats"].
    stream_url = info.get("url")
    if not stream_url:
        # Fallback: grab from the first requested format
        requested = info.get("requested_formats") or []
        for fmt in requested:
            if fmt.get("url"):
                stream_url = fmt["url"]
                break

    if not stream_url:
        raise RuntimeError(f"Could not extract audio stream URL from info: {info.get('id', 'unknown')}")

    return AudioStreamInfo(
        video_id=info.get("id", ""),
        stream_url=stream_url,
        ext=info.get("ext", "webm"),
        abr=info.get("abr"),
        duration_sec=info.get("duration"),
        title=info.get("title", ""),
        uploader=info.get("uploader") or info.get("channel", ""),
        # yt-dlp always populates http_headers with what YouTube requires.
        # Fall back to checking the selected format dict if top-level is empty.
        http_headers=info.get("http_headers") or _extract_headers_from_formats(info),
    )


def _best_thumbnail(thumbnails: list[dict]) -> str | None:
    """Return the highest-resolution thumbnail URL from yt-dlp's list."""
    if not thumbnails:
        return None
    # yt-dlp thumbnails may have a 'preference' or 'width' field
    sorted_thumbs = sorted(
        thumbnails,
        key=lambda t: (t.get("preference", 0), t.get("width", 0)),
        reverse=True,
    )
    return sorted_thumbs[0].get("url")


def _extract_headers_from_formats(info: dict) -> dict[str, str]:
    """
    Fallback: pull http_headers from the first requested_formats entry.
    yt-dlp sometimes nests headers inside per-format dicts rather than
    at the top level, especially for merged (audio+video) formats.
    """
    for fmt in info.get("requested_formats") or []:
        headers = fmt.get("http_headers")
        if headers:
            return dict(headers)
    return {}

