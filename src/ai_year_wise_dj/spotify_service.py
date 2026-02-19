from __future__ import annotations

import os
import warnings
from typing import Iterable

import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyClientCredentials
from requests.exceptions import HTTPError


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

    # Spotify's search endpoint enforces a maximum of 20 results per page for
    # restricted app credentials.  Using a higher value returns HTTP 400
    # "Invalid limit", so we cap every page request at this safe maximum.
    _SEARCH_PAGE_LIMIT = 20

    def search_tracks_by_year_window(self, year: int, window: int = 5, limit: int = 50) -> list[dict]:
        min_year = year - window
        max_year = year + window
        query = f"year:{min_year}-{max_year}"

        tracks: list[dict] = []
        offset = 0
        while len(tracks) < limit:
            page_size = min(self._SEARCH_PAGE_LIMIT, limit - len(tracks))
            try:
                page = self.client.search(q=query, type="track", limit=page_size, offset=offset, market="US")
            except (HTTPError, SpotifyException) as exc:
                status = exc.response.status_code if isinstance(exc, HTTPError) else exc.http_status
                if status == 400:
                    warnings.warn(
                        f"Spotify search returned 400 Bad Request (limit={page_size}, offset={offset}). "
                        "Returning tracks collected so far.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    break
                raise
            items = page.get("tracks", {}).get("items", [])
            if not items:
                break
            tracks.extend(items)
            offset += len(items)
        return tracks[:limit]

    def find_starting_track(self, query_text: str, year: int, window: int = 5) -> dict | None:
        min_year = year - window
        max_year = year + window
        query = f"track:{query_text} year:{min_year}-{max_year}"
        page = self.client.search(q=query, type="track", limit=1, offset=0, market="US")
        items = page.get("tracks", {}).get("items", [])
        return items[0] if items else None

    def hydrate_track(self, track_id: str) -> tuple[dict, dict, dict]:
        track = self.client.track(track_id, market="US")
        features = self._safe_audio_features(track_id)
        analysis = self._safe_audio_analysis(track_id)
        return track, features, analysis

    def _safe_audio_features(self, track_id: str) -> dict:
        try:
            result = self.client.audio_features([track_id])[0]
            return result or {}
        except (HTTPError, SpotifyException) as exc:
            status = exc.response.status_code if isinstance(exc, HTTPError) else exc.http_status
            if status == 403:
                warnings.warn(
                    "Spotify audio-features endpoint returned 403 Forbidden. "
                    "This endpoint may be restricted for your app credentials. "
                    "Falling back to empty features.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return {}
            raise

    def _safe_audio_analysis(self, track_id: str) -> dict:
        try:
            return self.client.audio_analysis(track_id)
        except (HTTPError, SpotifyException) as exc:
            status = exc.response.status_code if isinstance(exc, HTTPError) else exc.http_status
            if status == 403:
                warnings.warn(
                    "Spotify audio-analysis endpoint returned 403 Forbidden. "
                    "This endpoint may be restricted for your app credentials. "
                    "Falling back to empty analysis.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return {}
            raise

    def hydrate_tracks(self, track_ids: Iterable[str]) -> list[tuple[dict, dict, dict]]:
        hydrated: list[tuple[dict, dict, dict]] = []
        for tid in track_ids:
            hydrated.append(self.hydrate_track(tid))
        return hydrated
