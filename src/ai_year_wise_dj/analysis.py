from __future__ import annotations

from ai_year_wise_dj.models import TrackFingerprint


def _normalize(values: list[float]) -> list[float]:
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
    audio_features: dict | None = None,
    audio_analysis: dict | None = None,
) -> TrackFingerprint:
    audio_features = audio_features or {}
    audio_analysis = audio_analysis or {}

    sections = audio_analysis.get("sections", [])

    # Only true when we actually have usable audio section data.
    has_audio_features = bool(sections)

    section_energies: list[float] = []
    section_tempos: list[float] = []
    section_loudness: list[float] = []

    for section in sections:
        section_energies.append(float(section.get("energy", 0.0)))
        section_tempos.append(float(section.get("tempo", 0.0)))
        section_loudness.append(float(section.get("loudness", -20.0)))

    release_year = int(track["album"]["release_date"][:4])

    return TrackFingerprint(
        track_id=track["id"],
        track_name=track["name"],
        artist_names=[a["name"] for a in track.get("artists", [])],
        artist_ids=[a["id"] for a in track.get("artists", [])],
        release_year=release_year,
        section_energies=_normalize(section_energies),
        section_tempos=_normalize(section_tempos),
        section_loudness=_normalize(section_loudness),
        popularity=int(track.get("popularity", 0)),
        duration_ms=int(track.get("duration_ms", 0)),
        has_audio_features=has_audio_features,
    )
