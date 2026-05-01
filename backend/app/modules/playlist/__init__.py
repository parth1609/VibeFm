"""
Playlist Module
===============
Handles everything related to fetching, shuffling, and streaming
YouTube audio for the VibeFm radio engine.

Public surface
--------------
Models      : Song, PlaylistState, AudioStreamInfo
Fetcher     : fetch_playlist_songs, resolve_audio_stream
Shuffler    : weighted_shuffle, pick_next, build_radio_queue
Player      : RadioPlayer, NowPlaying, PlayerStatus
Router      : router  (FastAPI APIRouter)
"""

from .fetcher import fetch_playlist_songs, resolve_audio_stream
from .models import AudioStreamInfo, PlaylistState, Song
from .player import NowPlaying, PlayerStatus, RadioPlayer
from .router import router
from .shuffler import build_radio_queue, pick_next, weighted_shuffle

__all__ = [
    # Models
    "Song",
    "PlaylistState",
    "AudioStreamInfo",
    # Fetcher
    "fetch_playlist_songs",
    "resolve_audio_stream",
    # Shuffler
    "weighted_shuffle",
    "pick_next",
    "build_radio_queue",
    # Player
    "RadioPlayer",
    "NowPlaying",
    "PlayerStatus",
    # Router
    "router",
]
