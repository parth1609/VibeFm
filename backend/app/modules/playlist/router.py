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
streams them back to the client using FastAPI's StreamingResponse.  The
client's <audio> tag points to /playlist/audio/{video_id} instead of the
raw googlevideo.com URL.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .fetcher import fetch_playlist_songs, resolve_audio_stream
from .models import AudioStreamInfo, PlaylistState, Song
from .shuffler import build_radio_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playlist", tags=["playlist"])

# ---------------------------------------------------------------------------
# In-memory session state (single-user MVP — replace with Redis for multi-user)
# ---------------------------------------------------------------------------

_session_songs: list[Song] = []
_session_queue: list[Song] = []
_queue_index: int = -1

# Chunk size for the streaming proxy (32 KB)
_CHUNK_SIZE = 32_768

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
    # The URL the frontend should use — calls the proxy instead of raw YT URL
    playback_url: str


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
    global _session_songs, _session_queue, _queue_index

    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"📥 POST /playlist/load - Client: {client_ip}, URL: {body.url}, Queue Size: {body.queue_size}")
    logger.debug(f"📥 Request headers: {dict(request.headers)}")
    try:
        logger.info(f"🔍 Starting playlist fetch for URL: {body.url}")
        songs = await fetch_playlist_songs(body.url)
        logger.info(f"✅ Successfully loaded {len(songs)} songs into session")
        logger.debug(f"📝 First 3 songs: {[song.title for song in songs[:3]]}")
    except Exception as exc:
        logger.error(f"❌ Failed to fetch playlist: {exc}")
        logger.exception(f"Full traceback for playlist fetch failure: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not songs:
        raise HTTPException(
            status_code=404,
            detail="No playable songs found. The playlist may be private or empty.",
        )

    _session_songs = songs
    logger.info(f"🎯 Building radio queue with {len(songs)} songs, target size: {body.queue_size}")
    _session_queue = build_radio_queue(songs, queue_size=body.queue_size)
    _queue_index = -1
    logger.info(f"🎲 Radio queue built with {len(_session_queue)} songs")
    logger.debug(f"📋 Queue preview: {[song.title for song in _session_queue[:5]]}")

    logger.info(f"🚀 POST /playlist/load completed - Total songs: {len(songs)}, Queue size: {len(_session_queue)}")
    return LoadPlaylistResponse(total_songs=len(songs), queue=_session_queue)


@router.get("/next", response_model=NextSongResponse)
async def get_next_song(request: Request) -> NextSongResponse:
    """
    Pick the next song from the weighted-random queue and resolve its audio
    stream.
    """
    global _session_songs, _session_queue, _queue_index
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"⏭️ GET /playlist/next - Client: {client_ip}, Queue index: {_queue_index}, Queue size: {len(_session_queue)}")

    if not _session_songs:
        logger.warning("⚠️ Cannot fetch next song: No playlist is currently loaded")
        raise HTTPException(
            status_code=400,
            detail="No playlist loaded. Call POST /playlist/load first.",
        )

    # Try up to 5 songs to find one that works
    max_attempts = 5
    attempts = 0
    
    while attempts < max_attempts:
        _queue_index += 1
        if _queue_index >= len(_session_queue):
            logger.info("🔄 Queue exhausted! Rebuilding with aggressively refreshed weights...")
            _session_queue = build_radio_queue(_session_songs, queue_size=10)
            _queue_index = 0
            logger.info(f"🔄 Queue rebuilt with {len(_session_queue)} songs")

        song = _session_queue[_queue_index]
        logger.info(f"🎵 Selected song: '{song.title}' (ID: {song.video_id}) at position {_queue_index}")

        try:
            logger.info(f"🔗 Resolving audio stream URL via yt-dlp for {song.video_id}...")
            stream = await resolve_audio_stream(song.video_id)
            logger.info(f"✅ Stream resolved successfully! Format: {stream.ext}, Size: {stream.filesize_bytes if hasattr(stream, 'filesize_bytes') else 'unknown'}")
            logger.debug(f"🎧 Stream URL: {stream.stream_url[:100]}...")
            break  # Success! Exit the retry loop
        except Exception as exc:
            logger.warning(f"⚠️ Failed to resolve stream for {song.video_id}: {exc}")
            attempts += 1
            if attempts >= max_attempts:
                logger.error(f"❌ Failed to resolve audio stream after {max_attempts} attempts")
                raise HTTPException(status_code=502, detail=f"Unable to find playable audio after {max_attempts} attempts. Last error: {exc}") from exc
            logger.info(f"🔄 Trying next song (attempt {attempts + 1}/{max_attempts})")
            continue

    song.audio_stream_url = stream.stream_url
    song.mark_played()
    logger.debug(f"📝 Song marked as played, play count: {getattr(song, 'play_count', 'unknown')}")

    # Build the proxy URL (works in both dev and prod)
    base = str(request.base_url).rstrip("/")
    playback_url = f"{base}/playlist/audio/{song.video_id}"
    logger.info(f"🔗 Playback URL generated: {playback_url}")

    logger.info(f"🚀 GET /playlist/next completed - Song: {song.title}, Duration: {getattr(song, 'duration', 'unknown')}")
    return NextSongResponse(song=song, stream=stream, playback_url=playback_url)


@router.get("/stream/{video_id}", response_model=AudioStreamInfo)
async def get_stream_info(video_id: str, request: Request) -> AudioStreamInfo:
    """
    Resolve audio stream *metadata* for any YouTube video ID.
    Returns the raw googlevideo.com URL + headers (for server-side use only).
    Use the ``/audio/{video_id}`` endpoint for client-facing playback.
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"🔍 GET /playlist/stream/{video_id} - Client: {client_ip}")
    
    try:
        logger.info(f"🔗 Resolving stream metadata for video ID: {video_id}")
        stream_info = await resolve_audio_stream(video_id)
        logger.info(f"✅ Stream metadata resolved - Format: {stream_info.ext}, Duration: {getattr(stream_info, 'duration', 'unknown')}")
        return stream_info
    except Exception as exc:
        logger.error(f"❌ Stream resolution failed for {video_id}: {exc}")
        logger.exception(f"Full traceback for stream resolution failure: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/audio/{video_id}")
async def proxy_audio_stream(video_id: str, request: Request) -> StreamingResponse:
    """
    **Streaming audio proxy** — resolves the YouTube audio stream server-side
    and pipes the bytes to the client with correct headers.

    This fixes the 403 Access Denied problem that occurs when the browser
    tries to open a googlevideo.com URL directly:

    - The server resolves the URL (IP lock is to the server's IP ✓)
    - The server sends yt-dlp's required headers to YouTube ✓
    - The client gets clean audio bytes with no authentication issues ✓

    Supports the ``Range`` header so the browser can seek within the track.
    """
    client_ip = request.client.host if request.client else "unknown"
    range_header = request.headers.get("Range", "none")
    logger.info(f"🎧 GET /playlist/audio/{video_id} - Client: {client_ip}, Range: {range_header}")
    
    # 1. Resolve stream URL + required headers from yt-dlp
    try:
        logger.info(f"🔗 Resolving audio stream for proxy: {video_id}")
        stream_info = await resolve_audio_stream(video_id)
        logger.info(f"✅ Stream resolved for proxy - Format: {stream_info.ext}, Content-Type: {_AUDIO_MIME.get(stream_info.ext, 'audio/webm')}")
    except Exception as exc:
        logger.error(f"❌ Cannot resolve proxy stream for {video_id}: {exc}")
        logger.exception(f"Proxy stream resolution failure: {exc}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 2. Build the upstream request headers
    upstream_headers: dict[str, str] = dict(stream_info.http_headers)
    logger.debug(f"📤 Upstream headers prepared: {len(upstream_headers)} headers")

    # Forward Range header if the browser sent one (enables seeking)
    if range_header := request.headers.get("Range"):
        upstream_headers["Range"] = range_header
        logger.info(f"🎯 Range header forwarded: {range_header}")

    # 3. Determine response MIME type
    content_type = _AUDIO_MIME.get(stream_info.ext, "audio/webm")

    # 4. Stream bytes from YouTube → client
    async def _byte_stream() -> AsyncIterator[bytes]:
        logger.info(f"🌊 Starting byte stream from YouTube for {video_id}")
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream(
                "GET", stream_info.stream_url, headers=upstream_headers
            ) as yt_resp:
                logger.info(f"📡 YouTube response status: {yt_resp.status_code} for {video_id}")
                if yt_resp.status_code not in (200, 206):
                    logger.error(
                        "❌ YouTube upstream returned %d for %s",
                        yt_resp.status_code,
                        video_id,
                    )
                    # Nothing we can yield at this point; let the client handle EOF
                    return
                
                bytes_transferred = 0
                chunk_count = 0
                async for chunk in yt_resp.aiter_bytes(chunk_size=_CHUNK_SIZE):
                    bytes_transferred += len(chunk)
                    chunk_count += 1
                    if chunk_count % 100 == 0:  # Log every 100 chunks to avoid spam
                        logger.debug(f"📊 Transferred {bytes_transferred / (1024*1024):.2f} MB in {chunk_count} chunks")
                    yield chunk
                
                logger.info(f"✅ Streaming completed for {video_id} - Total: {bytes_transferred / (1024*1024):.2f} MB, Chunks: {chunk_count}")

    # 5. Determine response status (206 Partial Content if Range was requested)
    status_code = 206 if "Range" in request.headers else 200

    response_headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
        "X-Video-Id": video_id,
    }

    return StreamingResponse(
        _byte_stream(),
        status_code=status_code,
        media_type=content_type,
        headers=response_headers,
    )


@router.get("/queue", response_model=list[Song])
async def get_queue(request: Request) -> list[Song]:
    """Return the current in-memory playback queue (for UI display)."""
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"📋 GET /playlist/queue - Client: {client_ip}")
    
    if not _session_queue:
        logger.warning("⚠️ Queue requested but no queue is built yet")
        raise HTTPException(status_code=404, detail="No queue built yet.")
    
    logger.info(f"📊 Returning queue with {len(_session_queue)} songs, current index: {_queue_index}")
    logger.debug(f"📝 Queue preview: {[song.title for song in _session_queue[:3]]}...")
    return _session_queue
