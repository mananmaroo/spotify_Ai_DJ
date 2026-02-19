"""FastAPI web server for AI Year-Wise DJ."""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

app = FastAPI(title="AI Year-Wise DJ")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class TrackSearchRequest(BaseModel):
    """Request to search for a track by name and artist."""
    track_name: str
    artist_name: str
    year: int = 2018
    window: int = 2
    limit: int = 20

class TrackInfo(BaseModel):
    """Track information response."""
    id: str
    name: str
    artist: str
    year: int
    popularity: int = 0
    duration_ms: int = 0
    preview_url: str = None

class DJResponse(BaseModel):
    """Response with starting track and next recommendations."""
    starting_track: TrackInfo
    next_tracks: list[TrackInfo]

def get_spotify_client():
    """Initialize Spotify client."""
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set")

    credentials = SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret
    )
    return spotipy.Spotify(client_credentials_manager=credentials)


def _track_release_year(track: dict) -> int:
    release_date = track.get("album", {}).get("release_date") or track.get("release_date", "0")
    return int(release_date[:4])


def _score_candidate(seed: dict, candidate: dict, target_year: int, window: int) -> float:
    pop_diff = abs(seed.get("popularity", 0) - candidate.get("popularity", 0))
    pop_score = max(0.0, 1.0 - pop_diff / 100.0)

    dur_diff = abs(seed.get("duration_ms", 0) - candidate.get("duration_ms", 0))
    dur_score = max(0.0, 1.0 - dur_diff / 120_000.0)

    year_diff = abs(_track_release_year(candidate) - target_year)
    year_score = max(0.0, 1.0 - year_diff / max(window, 1))

    return 0.5 * pop_score + 0.2 * dur_score + 0.3 * year_score


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/api/search", response_model=DJResponse)
def search_and_get_transitions(request: TrackSearchRequest):
    """
    Search for a track by name and artist, then find transition matches via
    Spotify's Recommendations API scored by popularity, duration, and year.
    """
    try:
        sp = get_spotify_client()

        # Search for the starting track
        query = f"track:{request.track_name} artist:{request.artist_name}"
        results = sp.search(q=query, type="track", limit=1)

        if not results["tracks"]["items"]:
            raise HTTPException(
                status_code=404,
                detail=f"Track '{request.track_name}' by '{request.artist_name}' not found"
            )

        seed_track = results["tracks"]["items"][0]
        track_id = seed_track["id"]

        # Fetch recommendations seeded by the starting track (no restricted endpoints)
        rec_result = sp.recommendations(seed_tracks=[track_id], limit=request.limit)
        rec_tracks = rec_result.get("tracks", [])

        # Score and sort candidates by popularity, duration, and year proximity
        scored = []
        for track in rec_tracks:
            year_diff = abs(_track_release_year(track) - request.year)
            if year_diff > request.window:
                continue
            score = _score_candidate(seed_track, track, request.year, request.window)
            scored.append((score, track))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_tracks = [t for _, t in scored[:5]]

        return DJResponse(
            starting_track=TrackInfo(
                id=track_id,
                name=seed_track["name"],
                artist=seed_track["artists"][0]["name"] if seed_track["artists"] else "Unknown",
                year=_track_release_year(seed_track),
                popularity=seed_track.get("popularity", 0),
                duration_ms=seed_track.get("duration_ms", 0),
                preview_url=seed_track.get("preview_url"),
            ),
            next_tracks=[
                TrackInfo(
                    id=t["id"],
                    name=t["name"],
                    artist=t["artists"][0]["name"] if t["artists"] else "Unknown",
                    year=_track_release_year(t),
                    popularity=t.get("popularity", 0),
                    duration_ms=t.get("duration_ms", 0),
                    preview_url=t.get("preview_url"),
                )
                for t in top_tracks
            ]
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
