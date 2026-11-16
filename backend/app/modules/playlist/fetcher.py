"""
Playlist Fetcher — yt-dlp Integration
Fetches playlist metadata and resolves direct audio stream URLs
from YouTube using yt-dlp without any video rendering.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
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
    # Surface real errors instead of silently returning an empty result.
    "ignoreerrors": False,
    # NOTE: do not override http_headers here. yt-dlp negotiates its own request
    # headers per YouTube API call and reports the ones playback needs in
    # info["http_headers"]; injecting browser navigation headers makes YouTube
    # answer with an unusable player response ("no stream URL").
    "noplaylist": True,  # Prevent playlist extraction to avoid bot detection
    # Fail fast instead of hanging for a minute on a dead URL
    "socket_timeout": 15,
    "retries": 1,
    "extractor_retries": 1,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
        }
    },
}

# Invidious instances for fallback when YouTube direct extraction fails
_INVIDIOUS_INSTANCES = [
    "https://yewtu.be",
    "https://inv.nadeko.net",
]

# Fallback options for Invidious instances
# ---------------------------------------------------------------------------
# Stream URL cache
#
# A resolved googlevideo.com URL stays valid for hours while yt-dlp extraction
# costs seconds. Caching it turns every repeat play / seek / reconnect into a
# memory lookup, which is the single biggest latency win in the radio loop.
# ---------------------------------------------------------------------------

_STREAM_CACHE_TTL_S = 45 * 60  # refresh long before YouTube expires the URL
_STREAM_CACHE_MAX = 512

_stream_cache: dict[str, tuple[float, AudioStreamInfo]] = {}
_resolve_inflight: dict[str, "asyncio.Task[AudioStreamInfo]"] = {}
_prefetch_tasks: set["asyncio.Task[None]"] = set()

# yt-dlp talks to YouTube, which rate-limits bursts. Prefetching a few tracks in
# parallel is fine, a stampede is not: it provokes "Failed to extract any player
# response", which is the very failure that made tracks unplayable.
_EXTRACT_LIMITER = asyncio.Semaphore(2)

# Fallback options for Invidious instances
_INVIDIOUS_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "format": "bestaudio/best",
    "ignoreerrors": False,
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


async def resolve_audio_stream(
    video_id: str, *, force_refresh: bool = False
) -> AudioStreamInfo:
    """
    Resolve the best audio-only stream URL for a YouTube video.

    Results are cached in-process for :data:`_STREAM_CACHE_TTL_S` seconds, and
    concurrent requests for the same video share a single yt-dlp extraction.
    This is what makes pressing play feel instant: extraction costs 1-4 s of
    network work, a cache hit costs microseconds.

    Args:
        video_id: YouTube video ID (e.g. ``"dQw4w9WgXcQ"``).
        force_refresh: Ignore any cached entry (used when YouTube returns 403).

    Returns:
        :class:`AudioStreamInfo` with a ready-to-stream URL.

    Raises:
        RuntimeError: If yt-dlp cannot extract stream info.
    """
    if not force_refresh:
        hit = cached_stream(video_id)
        if hit is not None:
            return hit

    task = _resolve_inflight.get(video_id)
    if task is None:
        task = asyncio.create_task(_resolve_and_store(video_id))
        _resolve_inflight[video_id] = task
        task.add_done_callback(
            lambda _t, vid=video_id: _resolve_inflight.pop(vid, None)
        )

    # shield(): if this particular request is cancelled (client navigated away)
    # the shared extraction keeps running for everyone else.
    return await asyncio.shield(task)


def cached_stream(video_id: str) -> AudioStreamInfo | None:
    """Return a still-valid cached stream for *video_id*, if there is one."""
    entry = _stream_cache.get(video_id)
    if entry is None:
        return None
    expires_at, info = entry
    if expires_at <= time.monotonic():
        _stream_cache.pop(video_id, None)
        return None
    return info


def invalidate_stream(video_id: str) -> None:
    """Drop a cached stream URL (e.g. after YouTube answers 403)."""
    _stream_cache.pop(video_id, None)


def prefetch_audio_stream(video_id: str) -> None:
    """
    Fire-and-forget stream resolution used to warm the cache ahead of playback.

    Safe to call from any running event loop; never raises, and never starts a
    second extraction for a video that is already cached or in flight.
    """
    if video_id in _stream_cache or video_id in _resolve_inflight:
        return
    try:
        task = asyncio.create_task(_safe_prefetch(video_id))
    except RuntimeError:  # no running loop — nothing to schedule on
        return
    _prefetch_tasks.add(task)
    task.add_done_callback(_prefetch_tasks.discard)


async def _safe_prefetch(video_id: str) -> None:
    try:
        await asyncio.wait_for(resolve_audio_stream(video_id), timeout=45)
        logger.debug("Prefetched audio stream for %s", video_id)
    except Exception as exc:  # noqa: BLE001 - best effort only
        logger.debug("Prefetch failed for %s: %s", video_id, exc)


async def _resolve_and_store(video_id: str) -> AudioStreamInfo:
    url = f"https://www.youtube.com/watch?v={video_id}"
    loop = asyncio.get_running_loop()
    async with _EXTRACT_LIMITER:
        info = await loop.run_in_executor(None, _sync_resolve_stream, url)
    _self = video_id or info.video_id
    if len(_stream_cache) >= _STREAM_CACHE_MAX:
        # Evict the entry that expires soonest; URL validity is time-ordered.
        oldest = min(_stream_cache, key=lambda k: _stream_cache[k][0])
        _stream_cache.pop(oldest, None)
    _stream_cache[_self] = (time.monotonic() + _STREAM_CACHE_TTL_S, info)
    logger.info(
        "Resolved audio stream for %s (ext=%s abr=%s)", video_id, info.ext, info.abr
    )
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
        # Flat playlist extraction usually has no channel info, so fall back to
        # the "Artist - Song" convention most YouTube uploads follow.
        artist = _guess_artist(
            title,
            entry.get("uploader"),
            entry.get("channel"),
            entry.get("creator"),
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
    # Try YouTube first. Extraction is occasionally flaky ("Failed to extract any
    # player response"), so give it one retry before using the slower fallback.
    for attempt in range(2):
        try:
            with yt_dlp.YoutubeDL(_STREAM_OPTS) as ydl:
                info = ydl.extract_info(url, download=False)
            if info and info.get("url"):
                return _create_stream_info(info)
            logger.warning("YouTube returned no stream URL (attempt %d)", attempt + 1)
        except Exception as e:
            logger.warning("YouTube direct extraction failed (attempt %d): %s", attempt + 1, e)
        if attempt == 0:
            time.sleep(0.8)

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


_ARTIST_SEPARATOR = re.compile(r"\s+[-–—]\s+")


def _guess_artist(title: str, *candidates: str | None) -> str:
    """Best-effort artist name: channel info first, then the title prefix."""
    for candidate in candidates:
        if candidate and candidate.strip():
            return candidate.strip()

    parts = _ARTIST_SEPARATOR.split(title, maxsplit=1)
    if len(parts) == 2:
        head = parts[0].strip()
        # Only trust short prefixes; long ones are usually the song title.
        if 0 < len(head) <= 60:
            return head
    return "Unknown Artist"


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

