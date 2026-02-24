import spotipy


class SpotifyService:
    def __init__(self, token: str):
        self.client = spotipy.Spotify(auth=token)

    def hydrate_track(self, track_id: str):
        return self.client.track(track_id)

    def get_recommendations(self, seed_track_id: str, limit: int = 20):
        result = self.client.recommendations(
            seed_tracks=[seed_track_id],
            limit=limit,
        )
        return result.get("tracks", [])

    def get_audio_analysis(self, track_id: str):
        try:
            return self.client.audio_analysis(track_id)
        except:
            return {}
