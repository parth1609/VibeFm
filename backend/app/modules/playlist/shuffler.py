"""
Playlist Shuffler — Weighted Randomness Engine

Implements the "Discovery within Familiarity" algorithm described in the PRD:

    weight(song) = recency_factor × frequency_factor

    recency_factor  = 1 + hours_since_last_played   (more time = higher weight)
    frequency_factor = 1 / (1 + play_count)          (fewer plays = higher weight)

Songs that haven't been played recently AND have a low play count get the
highest probability of being picked next.  This mimics the feel of a good
radio station: familiar but never predictable.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from .models import Song


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def weighted_shuffle(songs: list[Song]) -> list[Song]:
    """
    Return a new ordering of *songs* using weighted random sampling **without
    replacement** (reservoir / cumulative-weight technique).

    The order reflects probability from highest-to-lowest weight, so the
    first element is the most likely "next song" and the last is least likely.

    Args:
        songs: The pool of available songs.

    Returns:
        A new list with the same songs in weighted-random order.
    """
    if not songs:
        return []

    weights = [_compute_weight(s) for s in songs]
    # random.choices supports weights but allows repeats — use the manual
    # weighted-sampling-without-replacement approach instead.
    return _weighted_sample_without_replacement(songs, weights)


def pick_next(songs: list[Song], exclude_index: int | None = None) -> tuple[int, Song]:
    """
    Pick the next song to play using weighted randomness.

    Args:
        songs: Full list of songs.
        exclude_index: Index to exclude (e.g. currently playing song) to
                       avoid immediate repeat.

    Returns:
        ``(index, song)`` tuple of the chosen song.
    """
    if not songs:
        raise ValueError("Cannot pick from an empty song list.")

    pool = [(i, s) for i, s in enumerate(songs) if i != exclude_index]
    if not pool:
        # Only one song — must repeat
        pool = list(enumerate(songs))

    weights = [_compute_weight(s) for _, s in pool]
    chosen_pos = random.choices(range(len(pool)), weights=weights, k=1)[0]
    idx, song = pool[chosen_pos]
    return idx, song


def build_radio_queue(songs: list[Song], queue_size: int = 10) -> list[Song]:
    """
    Build a ready-to-play ordered queue of *queue_size* songs using weighted
    shuffle.  Useful for pre-computing the next N songs so the AI RJ engine
    can be given context about upcoming tracks.

    Args:
        songs: Full song pool.
        queue_size: How many songs to include in the queue.

    Returns:
        Ordered list of up to *queue_size* songs.
    """
    shuffled = weighted_shuffle(songs)
    return shuffled[:queue_size]


# ---------------------------------------------------------------------------
# Weight calculation
# ---------------------------------------------------------------------------


def _compute_weight(song: Song) -> float:
    """
    Compute a non-negative float weight for *song*.

    Higher weight → higher probability of being selected next.

        recency_factor  = clamped hours since last play (0 if never played → max boost)
        frequency_factor = 1 / (1 + play_count)

    The recency component is capped at 168 hours (1 week) to avoid infinite
    weight accumulation for songs that haven't been heard in a very long time.
    """
    # --- Recency factor ---
    max_hours = 168.0  # cap at 1 week
    if song.last_played_at is None:
        # Never played → give maximum recency bonus
        hours_since = max_hours
    else:
        now = datetime.now(tz=timezone.utc)
        last = song.last_played_at
        # Make last_played_at timezone-aware if it isn't
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta_hours = (now - last).total_seconds() / 3600.0
        hours_since = min(delta_hours, max_hours)

    recency_factor = 1.0 + hours_since  # range: [1, 169]

    # --- Frequency factor ---
    frequency_factor = 1.0 / (1.0 + song.play_count)  # range: (0, 1]

    weight = recency_factor * frequency_factor
    # Use a small epsilon floor so every song always has a nonzero chance
    return max(weight, 1e-6)


# ---------------------------------------------------------------------------
# Weighted sampling without replacement (Fisher-Yates variant)
# ---------------------------------------------------------------------------


def _weighted_sample_without_replacement(
    items: list[Song], weights: list[float]
) -> list[Song]:
    """
    Sample all items without replacement according to *weights*.

    Uses an O(n log n) approach based on the key  ``key = u^(1/w)``
    (Efraimidis & Spirakis A-Res algorithm).
    """
    if len(items) != len(weights):
        raise ValueError("items and weights must have the same length")

    # Assign a random key to each item: key = U^(1/weight)
    keyed = []
    for item, w in zip(items, weights):
        u = random.random()
        if u == 0.0:
            u = 1e-300  # avoid log(0)
        key = u ** (1.0 / w)
        keyed.append((key, item))

    # Sort descending by key — highest key = picked first
    keyed.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in keyed]
