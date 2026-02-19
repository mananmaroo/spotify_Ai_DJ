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


def build_track_fingerprint(track: dict, audio_features: dict, audio_analysis: dict) -> TrackFingerprint:
    sections = audio_analysis.get("sections", [])
    has_audio_features = bool(audio_features) or bool(sections)

    section_energies = [float(section.get("energy", audio_features.get("energy", 0.0))) for section in sections]
    section_tempos = [float(section.get("tempo", audio_features.get("tempo", 0.0))) for section in sections]
    section_loudness = [float(section.get("loudness", audio_features.get("loudness", -20.0))) for section in sections]

    if not sections:
        section_energies = [float(audio_features.get("energy", 0.0))]
        section_tempos = [float(audio_features.get("tempo", 0.0))]
        section_loudness = [float(audio_features.get("loudness", -20.0))]

    release_year = int(track["album"]["release_date"][:4])

    return TrackFingerprint(
        track_id=track["id"],
        track_name=track["name"],
        artist_names=[a["name"] for a in track.get("artists", [])],
        release_year=release_year,
        section_energies=_normalize(section_energies),
        section_tempos=_normalize(section_tempos),
        section_loudness=_normalize(section_loudness),
        popularity=int(track.get("popularity", 0)),
        duration_ms=int(track.get("duration_ms", 0)),
        has_audio_features=has_audio_features,
    )
