"""
Playlist Player — Async Radio Playback Engine

Orchestrates the full radio loop:
  1. Load a YouTube playlist via yt-dlp (fetcher.py)
  2. Build a weighted-random queue (shuffler.py)
  3. Resolve each song's audio stream URL just-in-time (fetcher.py)
  4. Pre-fetch the *next* song's stream URL in the background while the
     current song is "playing" (zero-gap buffer strategy from the PRD)
  5. Emit lifecycle events so the RJ engine and any consumers can hook in

NOTE: This module handles the *orchestration* layer only.  Actual audio
      byte-streaming to the browser is handled at the transport layer
      (FastAPI StreamingResponse or WebSocket).  Here we manage state and
      URL resolution.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Coroutine, Optional

from .fetcher import fetch_playlist_songs, resolve_audio_stream
from .models import AudioStreamInfo, PlaylistState, Song
from .shuffler import build_radio_queue, pick_next

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Player State
# ---------------------------------------------------------------------------


class PlayerStatus(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"        # reserved for future use
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class NowPlaying:
    """Snapshot of what's currently playing + what's pre-fetched next."""

    song: Song
    stream: AudioStreamInfo
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    next_song: Optional[Song] = None
    next_stream: Optional[AudioStreamInfo] = None


# ---------------------------------------------------------------------------
# Lifecycle hooks type aliases
# ---------------------------------------------------------------------------

OnSongStart = Callable[[NowPlaying], Coroutine]   # async callback


# ---------------------------------------------------------------------------
# RadioPlayer
# ---------------------------------------------------------------------------


class RadioPlayer:
    """
    Async radio player that maintains a weighted-random queue and
    pre-fetches the next audio stream while the current track plays.

    Usage::

        player = RadioPlayer("https://youtube.com/playlist?list=PLxxx")
        await player.load()

        async for now_playing in player.play():
            print(f"▶ {now_playing.song.title} — stream: {now_playing.stream.stream_url}")
            # Hand stream_url to the transport layer to actually push audio bytes.
            await asyncio.sleep(now_playing.song.duration_sec)  # simulate playback
    """

    def __init__(
        self,
        playlist_url: str,
        *,
        queue_size: int = 10,
        prefetch: bool = True,
        on_song_start: Optional[OnSongStart] = None,
    ) -> None:
        self.playlist_url = playlist_url
        self.queue_size = queue_size
        self.prefetch = prefetch
        self.on_song_start = on_song_start

        self._state: PlaylistState | None = None
        self._queue: list[Song] = []
        self._status: PlayerStatus = PlayerStatus.IDLE
        self._current_index: int = -1
        self._now_playing: NowPlaying | None = None
        self._prefetch_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def status(self) -> PlayerStatus:
        return self._status

    @property
    def now_playing(self) -> NowPlaying | None:
        return self._now_playing

    @property
    def queue(self) -> list[Song]:
        """The current ordered playback queue."""
        return list(self._queue)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    async def load(self) -> PlaylistState:
        """
        Fetch playlist metadata from YouTube and build the initial
        weighted-random queue.

        Must be called before :meth:`play`.
        """
        self._status = PlayerStatus.LOADING
        logger.info("Loading playlist: %s", self.playlist_url)

        songs = await fetch_playlist_songs(self.playlist_url)
        if not songs:
            self._status = PlayerStatus.ERROR
            raise RuntimeError(
                f"No playable songs found in playlist: {self.playlist_url}"
            )

        self._state = PlaylistState(
            playlist_url=self.playlist_url,
            songs=songs,
            total_songs=len(songs),
        )
        self._queue = build_radio_queue(songs, queue_size=self.queue_size)
        self._current_index = -1
        self._status = PlayerStatus.IDLE

        logger.info(
            "Playlist loaded: %d songs, queue of %d built.",
            len(songs),
            len(self._queue),
        )
        return self._state

    # ------------------------------------------------------------------
    # Play loop (async generator)
    # ------------------------------------------------------------------

    async def play(self) -> AsyncIterator[NowPlaying]:
        """
        Async generator that yields a :class:`NowPlaying` for each song.

        The caller is responsible for actual audio delivery (streaming the
        ``stream.stream_url`` to the client) and for calling ``await
        asyncio.sleep(duration)`` to advance to the next song.

        The generator loops endlessly through the weighted-shuffled queue;
        when the queue is exhausted it rebuilds with fresh weights so recently-
        played songs are now deprioritised.
        """
        if self._state is None:
            raise RuntimeError("Call await player.load() before play().")

        self._status = PlayerStatus.PLAYING
        _prefetched_stream: AudioStreamInfo | None = None
        _prefetched_song: Song | None = None

        while True:  # radio plays forever
            # --- Advance queue ---
            self._current_index += 1

            # Rebuild the queue when we exhaust it
            if self._current_index >= len(self._queue):
                logger.info("Queue exhausted — rebuilding with updated weights.")
                # Update weights are reflected automatically via play_count /
                # last_played_at on each Song object (mutated in-place above).
                self._queue = build_radio_queue(
                    self._state.songs, queue_size=self.queue_size
                )
                self._current_index = 0
                _prefetched_stream = None
                _prefetched_song = None

            song = self._queue[self._current_index]

            # --- Resolve current song stream ---
            if _prefetched_stream and _prefetched_song and _prefetched_song.video_id == song.video_id:
                # Use pre-fetched stream — zero gap!
                stream = _prefetched_stream
                logger.debug("Using pre-fetched stream for '%s'", song.title)
            else:
                logger.info("Resolving audio stream for '%s' …", song.title)
                stream = await resolve_audio_stream(song.video_id)

            song.audio_stream_url = stream.stream_url
            song.mark_played()

            # --- Build NowPlaying snapshot ---
            now_playing = NowPlaying(song=song, stream=stream)
            self._now_playing = now_playing

            # --- Fire lifecycle hook ---
            if self.on_song_start:
                try:
                    await self.on_song_start(now_playing)
                except Exception:
                    logger.exception("on_song_start hook raised an error")

            # --- Pre-fetch next song in background ---
            _prefetched_stream = None
            _prefetched_song = None
            if self.prefetch:
                next_idx = self._current_index + 1
                if next_idx < len(self._queue):
                    next_song = self._queue[next_idx]
                    _prefetched_song = next_song
                    logger.debug(
                        "Pre-fetching stream for next song: '%s'", next_song.title
                    )
                    try:
                        _prefetched_stream = await asyncio.shield(
                            asyncio.create_task(
                                resolve_audio_stream(next_song.video_id)
                            )
                        )
                        now_playing.next_song = next_song
                        now_playing.next_stream = _prefetched_stream
                    except Exception:
                        logger.warning(
                            "Pre-fetch failed for '%s', will resolve on demand.",
                            next_song.title,
                        )
                        _prefetched_stream = None
                        _prefetched_song = None

            yield now_playing


# ---------------------------------------------------------------------------
# Convenience: run a quick demo / smoke-test from CLI
# ---------------------------------------------------------------------------


async def _demo(playlist_url: str, num_songs: int = 3) -> None:
    """Play the first *num_songs* songs from the CLI (prints stream URLs)."""

    async def _on_start(np: NowPlaying) -> None:
        headers_note = (
            f"{len(np.stream.http_headers)} headers captured [OK]"
            if np.stream.http_headers
            else "[WARN] no headers captured"
        )
        print(
            f"\n{'-' * 60}\n"
            f">>  {np.song.title}\n"
            f"   Artist  : {np.song.artist}\n"
            f"   Duration: {np.song.duration_sec}s\n"
            f"   Format  : {np.stream.ext}  {np.stream.abr or '?'} kbps\n"
            f"   Headers : {headers_note}\n"
            f"   Proxy   : /playlist/audio/{np.song.video_id}  <- use this in <audio src=>\n"
        )
        if np.next_song:
            print(f"   Up next : {np.next_song.title}")

    player = RadioPlayer(playlist_url, on_song_start=_on_start)

    print(f"Loading playlist: {playlist_url}")
    state = await player.load()
    print(f"[OK] {state.total_songs} songs loaded.\n")

    count = 0
    async for now_playing in player.play():
        count += 1
        if count >= num_songs:
            break
        # Simulate 5-second playback window per song in demo mode
        await asyncio.sleep(5)

    print("\nDemo finished.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m backend.app.modules.playlist.player <playlist_url> [num_songs]")
        sys.exit(1)

    url = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    asyncio.run(_demo(url, n))
