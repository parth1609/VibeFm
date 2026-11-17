"""
Playlist Fetcher — yt-dlp Integration
Fetches playlist metadata and resolves direct audio stream URLs
from YouTube using yt-dlp without any video rendering.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import tempfile
import time
from functools import lru_cache
from typing import Any

import httpx
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

# Used when resolving a single video's best audio stream URL.
# The player client list is injected per attempt (see _CLIENT_STRATEGIES).
_STREAM_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    # Prefer true audio-only streams: AAC/m4a first (widest device support),
    # then any bestaudio, and only fall back to a muxed stream if none exist.
    "format": "bestaudio[acodec^=mp4a]/bestaudio/best",
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
}

# YouTube decides what it will hand out based on the client identity *and* the
# requesting IP. Cloud hosts (Render, Fly, ...) are handled far more strictly
# than a home connection, so try progressively simpler clients until one returns
# a URL that really serves bytes.
#
# Order matters: `tv` and `web_embedded` are the clients YouTube still serves
# without a PO token, so they are the ones that survive a datacenter IP. The
# browser/mobile clients (`web`, `mweb`, `ios`) now need a PO token for the
# video server request and answer 403 to the byte reads from cloud hosts.
_CLIENT_STRATEGIES: tuple[tuple[str, ...], ...] = (
    # Measured best: these two hand back a real audio-only (m4a) stream that
    # answers 206 to the byte probe.
    ("android_vr", "tv_samsung"),
    # No PO token needed, so they survive cloud IPs, but they often advertise
    # formats that then 403 on playback -- the probe below catches that.
    ("tv", "web_embedded"),
    ("web_safari", "mweb", "ios"),
    # Last resort: the old browser set, usually PO-token gated now.
    ("android", "web"),
)

# Give up on one video after this long so a dead track cannot stall the station.
_RESOLVE_BUDGET_S = 20.0
_PROBE_TIMEOUT_S = 12.0

# YouTube answers datacenter IPs with "Sign in to confirm you're not a bot".
# Every following request from the same host gets the same answer, so remember
# it briefly and fail fast instead of re-probing every track.
_BLOCKED_TTL_S = 15 * 60
_blocked_until: float = 0.0

_BLOCKED_MARKERS = (
    "sign in to confirm",
    "confirm you're not a bot",
    "confirm you’re not a bot",
    "please sign in",
)

BLOCKED_HINT = (
    "YouTube is refusing to stream to this server's IP (datacenter block). "
    "Set the YTDLP_COOKIES environment variable on the backend host with a "
    "YouTube cookie file (raw or base64), or run the backend on a home "
    "connection. Playlists still load; audio needs this step."
)


class YouTubeBlockedError(RuntimeError):
    """YouTube will not hand out streams to this host without credentials."""


def youtube_blocked() -> bool:
    """True while this host is known to be blocked by YouTube."""
    return time.monotonic() < _blocked_until


def _mark_blocked() -> None:
    global _blocked_until
    _blocked_until = time.monotonic() + _BLOCKED_TTL_S


def _looks_blocked(message: object) -> bool:
    text = str(message).lower()
    return any(marker in text for marker in _BLOCKED_MARKERS)

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

    # Known-blocked host without cookies: don't burn 10s per track to re-learn it.
    if youtube_blocked() and _cookie_file() is None:
        raise YouTubeBlockedError(BLOCKED_HINT)

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


def _stream_opts(clients: tuple[str, ...]) -> dict[str, Any]:
    """Build yt-dlp options for one extraction attempt."""
    opts = dict(_STREAM_OPTS)
    opts["extractor_args"] = {"youtube": {"player_client": list(clients)}}

    cookie_file = _cookie_file()
    if cookie_file:
        # A logged-in cookie sidesteps YouTube's datacenter bot check entirely.
        opts["cookiefile"] = cookie_file
    proxy = os.environ.get("YTDLP_PROXY")
    if proxy:
        opts["proxy"] = proxy
    return opts


@lru_cache(maxsize=1)
def _cookie_file() -> str | None:
    """
    Optional YouTube cookies for hosts YouTube treats as suspicious.

    Render env vars: ``YTDLP_COOKIES_FILE`` (path) or ``YTDLP_COOKIES`` (the
    netscape cookie file itself, raw or base64). Never committed to the repo.
    """
    explicit = os.environ.get("YTDLP_COOKIES_FILE")
    if explicit and os.path.isfile(explicit):
        return explicit

    blob = os.environ.get("YTDLP_COOKIES")
    if not blob:
        return None

    data = blob.encode("utf-8")
    try:
        data = base64.b64decode(blob, validate=True)
    except Exception:  # noqa: BLE001 - not base64, keep the raw text
        pass

    path = os.path.join(tempfile.gettempdir(), "vibefm_yt_cookies.txt")
    try:
        with open(path, "wb") as handle:
            handle.write(data)
        return path
    except OSError as exc:
        logger.warning("Could not write cookie file: %s", exc)
        return None


def _sync_resolve_stream(url: str) -> AudioStreamInfo:
    """
    Blocking — must be run in an executor.

    Tries each client strategy and only accepts a URL that actually serves
    bytes. Accepting the first URL yt-dlp returns is not enough: YouTube happily
    hands back URLs that answer 403 to the request that follows when it does not
    like the client or the IP it came from.
    """
    video_id = url.split("v=")[-1].split("&")[0]
    deadline = time.monotonic() + _RESOLVE_BUDGET_S
    last_error: object = "no client returned a playable URL"

    if youtube_blocked() and _cookie_file() is None:
        raise YouTubeBlockedError(BLOCKED_HINT)

    for clients in _CLIENT_STRATEGIES:
        if time.monotonic() >= deadline:
            logger.warning("Resolution budget exhausted for %s", video_id)
            break

        try:
            with yt_dlp.YoutubeDL(_stream_opts(clients)) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                last_error = "null player response"
                continue
            candidate = _create_stream_info(info)
        except Exception as exc:  # noqa: BLE001 - try the next client
            last_error = exc
            logger.warning(
                "Extraction failed for %s with clients %s: %s",
                video_id,
                ",".join(clients),
                exc,
            )
            # A bot check on one client says nothing about the next one: `web`
            # refuses cloud IPs while `tv` / `web_embedded` still stream them.
            # Keep walking the strategies and only fail once all of them refuse.
            continue

        if _is_playable(candidate):
            logger.info(
                "Resolved %s via %s (ext=%s)",
                video_id,
                ",".join(clients),
                candidate.ext,
            )
            return candidate

        last_error = "URL answered 403 to playback"
        logger.warning(
            "Clients %s gave an unplayable URL for %s", ",".join(clients), video_id
        )

    if _looks_blocked(last_error) and _cookie_file() is None:
        _mark_blocked()
        raise YouTubeBlockedError(BLOCKED_HINT)

    raise RuntimeError(
        f"Could not extract a playable audio stream for {video_id} "
        f"(last error: {last_error})"
    )


def _is_playable(info: AudioStreamInfo) -> bool:
    """Cheaply confirm the resolved URL really streams (first KB only)."""
    headers = dict(info.http_headers)
    headers["Range"] = "bytes=0-1023"
    try:
        with httpx.Client(
            timeout=httpx.Timeout(_PROBE_TIMEOUT_S, read=_PROBE_TIMEOUT_S),
            follow_redirects=True,
        ) as client:
            with client.stream(
                "GET", info.stream_url, headers=headers
            ) as response:
                if response.status_code not in (200, 206):
                    logger.debug(
                        "Probe rejected %s: HTTP %s", info.video_id, response.status_code
                    )
                    return False
                next(response.iter_bytes(1024), None)
                return True
    except Exception as exc:  # noqa: BLE001 - treat as unusable
        logger.debug("Probe failed for %s: %s", info.video_id, exc)
        return False



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

