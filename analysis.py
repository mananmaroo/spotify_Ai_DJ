# analysis.py
from __future__ import annotations
from typing import List, Optional
from models import TrackFingerprint

def _normalize(values: List[float]) -> List[float]:
    """Normalize a list of numbers to [0,1]."""
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [0.5 for _ in values]
    span = max_v - min_v
    return [(v - min_v) / span for v in values]

def build_track_fingerprint(
    track: dict,
    audio_features: Optional[dict] = None,
    audio_analysis: Optional[dict] = None,
) -> TrackFingerprint:
    """
    Build a track fingerprint from Spotify track and analysis.
    
    :param track: Spotify track object
    :param audio_features: Optional features from Spotify
    :param audio_analysis: Optional detailed analysis from Spotify
    :return: TrackFingerprint object
    """
    audio_analysis = audio_analysis or {}
    sections = audio_analysis.get("sections", [])

    # Only true if Spotify returned usable audio sections
    has_audio_features = bool(sections)

    section_energies: List[float] = []
    section_tempos: List[float] = []
    section_loudness: List[float] = []

    for section in sections:
        section_energies.append(float(section.get("energy", 0.0)))
        section_tempos.append(float(section.get("tempo", 0.0)))
        section_loudness.append(float(section.get("loudness", -20.0)))

    # Extract release year from album
    release_date = track.get("album", {}).get("release_date", "0")
    release_year = int(release_date[:4]) if release_date else 0

    return TrackFingerprint(
        track_id=track.get("id", ""),
        track_name=track.get("name", ""),
        artist_names=[a.get("name", "") for a in track.get("artists", [])],
        artist_ids=[a.get("id", "") for a in track.get("artists", [])],
        release_year=release_year,
        section_energies=_normalize(section_energies),
        section_tempos=_normalize(section_tempos),
        section_loudness=_normalize(section_loudness),
        popularity=int(track.get("popularity", 0)),
        duration_ms=int(track.get("duration_ms", 0)),
        has_audio_features=has_audio_features,
    )
