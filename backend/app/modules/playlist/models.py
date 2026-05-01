"""
Playlist Module — Data Models
Pydantic models for songs, playlist state, and audio stream info.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class Song(BaseModel):
    """Represents a single song entry fetched from a YouTube playlist."""

    video_id: str = Field(..., description="YouTube video ID (e.g. 'dQw4w9WgXcQ')")
    title: str
    artist: str = Field(default="Unknown Artist")
    duration_sec: int = Field(default=0, description="Duration in seconds")
    thumbnail_url: Optional[str] = None

    # Playback tracking — used by the weighted shuffle algorithm
    play_count: int = Field(default=0, description="Total times played in this session")
    last_played_at: Optional[datetime] = Field(
        default=None, description="UTC timestamp of last playback"
    )

    # Runtime field — populated just before playback, not persisted
    audio_stream_url: Optional[str] = Field(
        default=None, description="Direct audio stream URL extracted by yt-dlp (temporary)"
    )

    @property
    def youtube_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def mark_played(self) -> None:
        """Update tracking fields when a song starts playing."""
        self.play_count += 1
        self.last_played_at = datetime.utcnow()


class PlaylistState(BaseModel):
    """
    Represents the full runtime state of a loaded playlist.
    Tracks the ordered queue and the current playback position.
    """

    playlist_url: str = Field(..., description="Original YouTube playlist URL")
    songs: list[Song] = Field(default_factory=list)
    current_index: int = Field(default=0)
    total_songs: int = Field(default=0)

    def current_song(self) -> Optional[Song]:
        if 0 <= self.current_index < len(self.songs):
            return self.songs[self.current_index]
        return None

    def is_finished(self) -> bool:
        return self.current_index >= len(self.songs)


class AudioStreamInfo(BaseModel):
    """Resolved audio stream details from yt-dlp."""

    video_id: str
    stream_url: str
    ext: str = Field(default="webm", description="Audio container format")
    abr: Optional[float] = Field(default=None, description="Average bitrate (kbps)")
    duration_sec: Optional[int] = None
    title: str = ""
    uploader: str = ""
    # Headers yt-dlp says must accompany this URL (User-Agent, etc.)
    # Without these the googlevideo.com server returns 403.
    http_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Request headers required to access stream_url (from yt-dlp)",
    )
