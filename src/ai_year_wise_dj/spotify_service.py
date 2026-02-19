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
        start_year = year - window
        end_year = year + window
        num_years = end_year - start_year + 1
        per_year_limit = max(1, limit // num_years)

        tracks: list[dict] = []
        for y in range(start_year, end_year + 1):
            try:
                page = self.client.search(
                    q=f"year:{y}",
                    type="track",
                    limit=min(self._SEARCH_PAGE_LIMIT, per_year_limit),
                    offset=0,
                    market="US",
                )
            except (HTTPError, SpotifyException) as exc:
                status = exc.response.status_code if isinstance(exc, HTTPError) else exc.http_status
                if status == 400:
                    warnings.warn(
                        f"Spotify search returned 400 Bad Request for year {y}. "
                        "Skipping this year.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    continue
                raise
            items = page.get("tracks", {}).get("items", [])
            tracks.extend(items)
            if len(tracks) >= limit:
                break
        return tracks[:limit]

    def find_starting_track(self, query_text: str, year: int, window: int = 5) -> dict | None:
        for y in range(year - window, year + window + 1):
            try:
                query = f"track:{query_text} year:{y}"
                page = self.client.search(q=query, type="track", limit=1, offset=0, market="US")
                items = page.get("tracks", {}).get("items", [])
                if items:
                    return items[0]
            except (HTTPError, SpotifyException):
                continue
        return None

    def hydrate_track(self, track_id: str) -> dict:
        return self.client.track(track_id, market="US")

    def hydrate_tracks(self, track_ids: Iterable[str]) -> list[dict]:
        return [self.hydrate_track(tid) for tid in track_ids]

    def get_recommendations(self, seed_track_ids: list[str], limit: int = 20) -> list[dict]:
        try:
            result = self.client.recommendations(seed_tracks=seed_track_ids[:5], limit=limit)
            return result.get("tracks", [])
        except (HTTPError, SpotifyException):
            return []
