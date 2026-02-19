from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TrackFingerprint:
    track_id: str
    track_name: str
    artist_names: list[str]
    artist_ids: list[str]
    release_year: int
    section_energies: list[float]
    section_tempos: list[float]
    section_loudness: list[float]
    popularity: int = 0
    duration_ms: int = 0
    has_audio_features: bool = True


@dataclass(slots=True)
class TransitionCandidate:
    from_track_id: str
    to_track_id: str
    score: float
    reason: str
