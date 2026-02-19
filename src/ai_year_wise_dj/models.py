from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TrackFingerprint:
    track_id: str
    track_name: str
    artist_names: list[str]
    artist_ids: list[str]
    release_year: int
    popularity: int
    duration_ms: int


@dataclass(slots=True)
class TransitionCandidate:
    from_track_id: str
    to_track_id: str
    score: float
    reason: str
