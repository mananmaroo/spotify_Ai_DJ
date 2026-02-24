import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

class SpotifyService:
    def __init__(self, token: str):
        self.token = token
        self.client = spotipy.Spotify(auth_manager=SpotifyClientCredentials())

    def hydrate_track(self, track_id: str) -> dict:
        return self.client.track(track_id, market="US")

    def get_audio_analysis(self, track_id: str) -> dict:
        try:
            return self.client.audio_analysis(track_id)
        except Exception:
            return {}

    def get_recommendations(self, seed_track_ids: list[str], limit: int = 20) -> list[dict]:
        try:
            result = self.client.recommendations(seed_tracks=seed_track_ids[:5], limit=limit)
            return result.get("tracks", [])
        except Exception:
            return []
