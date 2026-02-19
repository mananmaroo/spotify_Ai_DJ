from __future__ import annotations

from ai_year_wise_dj.models import TrackFingerprint


def build_track_fingerprint(track: dict) -> TrackFingerprint:
    release_year = int(track["album"]["release_date"][:4])

    return TrackFingerprint(
        track_id=track["id"],
        track_name=track["name"],
        artist_names=[a["name"] for a in track.get("artists", [])],
        artist_ids=[a["id"] for a in track.get("artists", [])],
        release_year=release_year,
        popularity=int(track.get("popularity", 0)),
        duration_ms=int(track.get("duration_ms", 0)),
    )
