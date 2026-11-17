"""
Playlist Module — FastAPI Router

Exposes REST endpoints used by the frontend and by other backend modules
to interact with the playlist / music engine.

Endpoints
---------
POST /playlist/load                  — load a YouTube playlist, return metadata + initial queue
GET  /playlist/next                  — pick next song (weighted random) and resolve its stream URL
GET  /playlist/stream/{video_id}     — resolve audio stream metadata for a video ID
GET  /playlist/audio/{video_id}      — PROXY: stream audio bytes through the server (fixes 403)
GET  /playlist/queue                 — inspect the current in-memory queue

Why the /audio proxy?
---------------------
YouTube's googlevideo.com stream URLs are IP-locked and require specific
headers (User-Agent, Origin, etc.) that yt-dlp sets when it resolves them.
If the client browser tries to open the raw URL directly it receives 403
Access Denied because:
  1. The client IP differs from the server IP that resolved the URL.
  2. The browser sends its own User-Agent, not the one YouTube expects.

Solution: the server fetches the audio bytes with the correct headers and
streams them back to the client.  The client's audio element points to
/playlist/audio/{video_id} instead of the raw googlevideo.com URL.

Latency strategy
----------------
* Resolved stream URLs are cached for 45 minutes (see ``fetcher``), so a
  repeat request for a track is served from memory.
* ``/playlist/load`` warms the cache for the first upcoming tracks in the
  background while the user is still looking at the playlist screen.
* ``/playlist/next`` warms the cache for the tracks after the one it just
  returned, so every transition starts with an already-resolved URL.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .fetcher import (
    BLOCKED_HINT,
    YouTubeBlockedError,
    cached_stream,
    fetch_playlist_songs,
    invalidate_stream,
    prefetch_audio_stream,
    probe_clients,
    resolve_audio_stream,
)
from .models import AudioStreamInfo, Song
from .shuffler import build_radio_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playlist", tags=["playlist"])

# ---------------------------------------------------------------------------
# In-memory session state (single-user MVP — replace with Redis for multi-user)
# ---------------------------------------------------------------------------

_session_songs: list[Song] = []
_session_queue: list[Song] = []
_queue_index: int = -1
_queue_size: int = 10
_last_played_id: str | None = None

# How many upcoming tracks to resolve in the background.
_PREFETCH_AHEAD = 2

# Chunk size for the streaming proxy (64 KB — fewer round trips, smoother audio)
_CHUNK_SIZE = 65_536

# MIME types for audio formats
_AUDIO_MIME: dict[str, str] = {
    "webm": "audio/webm",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/ogg; codecs=opus",
}

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class LoadPlaylistRequest(BaseModel):
    url: str
    queue_size: int = 10


class LoadPlaylistResponse(BaseModel):
    total_songs: int
    queue: list[Song]


class NextSongResponse(BaseModel):
    song: Song
    stream: AudioStreamInfo
    # The URL the frontend should use (the proxy, not the raw YouTube URL)
    playback_url: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _warm_cache(start_index: int, ahead: int = _PREFETCH_AHEAD) -> None:
    """Start resolving the next *ahead* tracks without blocking the response."""
    for song in _session_queue[start_index : start_index + ahead]:
        prefetch_audio_stream(song.video_id)


def _rebuild_queue() -> None:
    """Build a fresh weighted-random queue, never starting with the last song."""
    global _session_queue
    _session_queue = build_radio_queue(_session_songs, queue_size=_queue_size)
    if (
        _last_played_id
        and len(_session_queue) > 1
        and _session_queue[0].video_id == _last_played_id
    ):
        _session_queue.append(_session_queue.pop(0))


def _playback_url(request: Request, video_id: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/playlist/audio/{video_id}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/load", response_model=LoadPlaylistResponse)
async def load_playlist(body: LoadPlaylistRequest, request: Request) -> LoadPlaylistResponse:
    """
    Fetch all songs from a YouTube playlist URL and build the initial
    weighted-random queue.  Returns the queue so the frontend can display
    upcoming tracks.
    """
    global _session_songs, _session_queue, _queue_index, _queue_size, _last_played_id

    started = time.perf_counter()
    url = body.url.strip()
    logger.info("POST /playlist/load  url=%s  queue_size=%s", url, body.queue_size)

    try:
        songs = await fetch_playlist_songs(url)
    except Exception as exc:
        logger.exception("Failed to fetch playlist %s", url)
        raise HTTPException(
            status_code=400, detail=f"Could not read that playlist: {exc}"
        ) from exc

    if not songs:
        raise HTTPException(
            status_code=404,
            detail="No playable songs found. The playlist may be private or empty.",
        )

    _session_songs = songs
    _queue_size = max(1, min(body.queue_size or 10, 50))
    _session_queue = build_radio_queue(songs, queue_size=_queue_size)
    _queue_index = -1
    _last_played_id = None

    # Warm the first few tracks while the user reads the playlist summary.
    _warm_cache(0)

    logger.info(
        "Loaded %d songs / queue of %d in %.0f ms",
        len(songs),
        len(_session_queue),
        (time.perf_counter() - started) * 1000,
    )
    return LoadPlaylistResponse(total_songs=len(songs), queue=_session_queue)


@router.get("/next", response_model=NextSongResponse)
async def get_next_song(request: Request) -> NextSongResponse:
    """
    Pick the next song from the weighted-random queue and resolve its audio
    stream (from cache whenever possible).
    """
    global _queue_index, _last_played_id

    if not _session_songs:
        raise HTTPException(
            status_code=400,
            detail="No playlist loaded. Call POST /playlist/load first.",
        )

    started = time.perf_counter()
    last_error: Exception | None = None
    blocked = False

    # Try a handful of tracks so one unplayable video never stalls the station.
    for _ in range(4):
        if _queue_index + 1 >= len(_session_queue):
            logger.info("Queue exhausted — rebuilding with refreshed weights.")
            _rebuild_queue()
            _queue_index = 0
        else:
            _queue_index += 1

        song = _session_queue[_queue_index]
        try:
            stream = cached_stream(song.video_id) or await resolve_audio_stream(
                song.video_id
            )
        except YouTubeBlockedError as exc:
            # A refusal is per video and per client, not per host: the next
            # track usually still streams, so skip instead of going off air.
            blocked = True
            last_error = exc
            logger.warning("YouTube refused %s - trying another track", song.video_id)
            continue
        except Exception as exc:  # noqa: BLE001 - try the next track instead
            last_error = exc
            logger.warning("Skipping %s (%s)", song.video_id, exc)
            continue

        song.audio_stream_url = stream.stream_url
        song.mark_played()
        _last_played_id = song.video_id

        # Resolve what's coming up next while this track plays.
        _warm_cache(_queue_index + 1)

        logger.info(
            "Now playing '%s' (%s) in %.0f ms, ext=%s",
            song.title,
            song.video_id,
            (time.perf_counter() - started) * 1000,
            stream.ext,
        )
        return NextSongResponse(
            song=song,
            stream=stream,
            playback_url=_playback_url(request, song.video_id),
        )

    if blocked:
        raise HTTPException(status_code=503, detail=BLOCKED_HINT)

    raise HTTPException(
        status_code=502,
        detail=(
            "Could not find a playable track in this playlist. "
            f"Last error: {last_error}"
        ),
    )


@router.get("/stream/{video_id}", response_model=AudioStreamInfo)
async def get_stream_info(video_id: str) -> AudioStreamInfo:
    """
    Resolve audio stream *metadata* for any YouTube video ID.
    Returns the raw googlevideo.com URL + headers (for server-side use only).
    Use the ``/audio/{video_id}`` endpoint for client-facing playback.
    """
    try:
        return await resolve_audio_stream(video_id)
    except Exception as exc:
        logger.exception("Stream resolution failed for %s", video_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/audio/{video_id}")
async def proxy_audio_stream(video_id: str, request: Request) -> StreamingResponse:
    """
    **Streaming audio proxy** — resolves the YouTube audio stream server-side
    and pipes the bytes to the client with the correct headers.

    * Uses the cached stream URL whenever possible (no yt-dlp round trip).
    * Forwards ``Range`` and mirrors ``206`` / ``Content-Range`` so seeking and
      reconnects work in the native player.
    * If YouTube answers 403 (expired URL) the URL is re-resolved once.
    """
    range_header = request.headers.get("range")
    stream_info = await _stream_for_playback(video_id)

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, read=60.0), follow_redirects=True
    )
    try:
        upstream = await client.send(
            client.build_request(
                "GET",
                stream_info.stream_url,
                headers=_upstream_headers(stream_info, range_header),
            ),
            stream=True,
        )

        if upstream.status_code == 403:
            logger.info("Stream URL for %s expired - re-resolving once.", video_id)
            await upstream.aclose()
            invalidate_stream(video_id)
            stream_info = await resolve_audio_stream(video_id, force_refresh=True)
            upstream = await client.send(
                client.build_request(
                    "GET",
                    stream_info.stream_url,
                    headers=_upstream_headers(stream_info, range_header),
                ),
                stream=True,
            )

        if upstream.status_code not in (200, 206):
            status = upstream.status_code
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=502,
                detail=f"YouTube rejected the audio request ({status}).",
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface as a clean API error
        await client.aclose()
        logger.exception("Audio upstream error for %s", video_id)
        raise HTTPException(status_code=502, detail=f"Audio upstream error: {exc}") from exc

    response_headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
        "X-Video-Id": video_id,
    }
    for header in ("content-range", "content-length"):
        if header in upstream.headers:
            response_headers[header.title()] = upstream.headers[header]

    media_type = _audio_media_type(upstream.headers.get("content-type"), stream_info.ext)

    async def _byte_stream() -> AsyncIterator[bytes]:
        bytes_sent = 0
        try:
            async for chunk in upstream.aiter_raw(chunk_size=_CHUNK_SIZE):
                bytes_sent += len(chunk)
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()
            logger.info(
                "Audio stream closed for %s after %.2f MB", video_id, bytes_sent / 1e6
            )

    return StreamingResponse(
        _byte_stream(),
        status_code=upstream.status_code,
        media_type=media_type,
        headers=response_headers,
    )


@router.get("/diagnose/{video_id}")
async def diagnose_video(video_id: str) -> list[dict[str, Any]]:
    """
    Resolve *video_id* once per YouTube player client and report the outcome.

    Answers "which client still streams this video from this host?" without
    needing the host's logs.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, probe_clients, video_id)


@router.get("/queue", response_model=list[Song])
async def get_queue() -> list[Song]:
    """Return the current in-memory playback queue (for UI display)."""
    return _session_queue


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _upstream_headers(
    stream_info: AudioStreamInfo, range_header: str | None
) -> dict[str, str]:
    """
    Build the upstream request headers.

    Always sends a Range header: some googlevideo URLs (notably the ones handed
    out by Invidious) answer 403 to a full-file GET but 206 to a ranged one, and
    it keeps the proxy streaming instead of buffering the whole track.
    """
    headers = dict(stream_info.http_headers)
    headers["Range"] = range_header or "bytes=0-"
    return headers


def _audio_media_type(content_type: str | None, ext: str) -> str:
    """
    Report an *audio* MIME type even though the container may be labelled
    ``video/mp4``. A ``bestaudio`` DASH stream is audio-only; telling the player
    it is video would send it down the video pipeline.
    """
    codecs = ""
    if content_type and ";" in content_type:
        codecs = ";" + content_type.split(";", 1)[1].strip()

    base = (content_type or "").split(";")[0].strip().lower()
    if base in {"video/mp4", "audio/mp4", "application/mp4", "video/x-m4a"}:
        return "audio/mp4" + codecs
    if base in {"video/webm", "audio/webm"}:
        return "audio/webm" + codecs
    if base.startswith("audio/"):
        return base + codecs
    return _AUDIO_MIME.get(ext, "audio/mp4")


async def _stream_for_playback(video_id: str) -> AudioStreamInfo:
    try:
        return await resolve_audio_stream(video_id)
    except YouTubeBlockedError as exc:
        raise HTTPException(status_code=503, detail=BLOCKED_HINT) from exc
    except Exception as exc:  # noqa: BLE001 - map to a clean API error
        logger.exception("Cannot resolve audio stream for %s", video_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
