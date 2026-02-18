from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TrackFingerprint:
    track_id: str
    track_name: str
    artist_names: list[str]
    release_year: int
    section_energies: list[float]
    section_tempos: list[float]
    section_loudness: list[float]


@dataclass(slots=True)
class TransitionCandidate:
    from_track_id: str
    to_track_id: str
    from_section_index: int
    to_section_index: int
    score: float
    reason: str
