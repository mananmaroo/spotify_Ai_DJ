from __future__ import annotations

import os
from typing import Iterable

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class SpotifyService:
    def __init__(self) -> None:
        self._validate_credentials()
        self.client = spotipy.Spotify(auth_manager=SpotifyClientCredentials())

    @staticmethod
    def _validate_credentials() -> None:
        missing = [name for name in ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET") if not os.getenv(name)]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(
                f"Missing Spotify credentials: {missing_list}. "
                "Set them in environment variables or local .env file."
            )

    def search_tracks_by_year_window(self, year: int, window: int = 5, limit: int = 50) -> list[dict]:
        min_year = year - window
        max_year = year + window
        query = f"year:{min_year}-{max_year}"

        tracks: list[dict] = []
        offset = 0
        while len(tracks) < limit:
            page = self.client.search(q=query, type="track", limit=min(50, limit - len(tracks)), offset=offset)
            items = page.get("tracks", {}).get("items", [])
            if not items:
                break
            tracks.extend(items)
            offset += len(items)
        return tracks[:limit]

    def hydrate_track(self, track_id: str) -> tuple[dict, dict, dict]:
        track = self.client.track(track_id)
        features = self.client.audio_features([track_id])[0] or {}
        analysis = self.client.audio_analysis(track_id)
        return track, features, analysis

    def hydrate_tracks(self, track_ids: Iterable[str]) -> list[tuple[dict, dict, dict]]:
        hydrated: list[tuple[dict, dict, dict]] = []
        for tid in track_ids:
            hydrated.append(self.hydrate_track(tid))
        return hydrated
