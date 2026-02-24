# models.py
from dataclasses import dataclass
from typing import List

@dataclass
class TrackFingerprint:
    track_id: str
    track_name: str
    artist_names: List[str]
    artist_ids: List[str]
    release_year: int
    section_energies: List[float]
    section_tempos: List[float]
    section_loudness: List[float]
    popularity: int
    duration_ms: int
    has_audio_features: bool

@dataclass
class TransitionCandidate:
    from_track_id: str
    to_track_id: str
    score: float
    reason: str
