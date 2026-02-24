# analysis.py
from models import TrackFingerprint

def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    min_v, max_v = min(values), max(values)
    if max_v == min_v:
        return [0.5 for _ in values]
    span = max_v - min_v
    return [(v - min_v) / span for v in values]

def build_track_fingerprint(track: dict, audio_analysis: dict | None = None) -> TrackFingerprint:
    audio_analysis = audio_analysis or {}
    sections = audio_analysis.get("sections", [])
    section_energies, section_tempos, section_loudness = [], [], []

    for sec in sections:
        section_energies.append(float(sec.get("energy", 0.0)))
        section_tempos.append(float(sec.get("tempo", 0.0)))
        section_loudness.append(float(sec.get("loudness", -20.0)))

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
        has_audio_features=bool(sections),
    )
