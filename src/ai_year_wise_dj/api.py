"""FastAPI web server for AI Year-Wise DJ."""
import os
import pathlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from ai_year_wise_dj.spotify_service import SpotifyService

_INDEX_HTML_PATH = pathlib.Path(__file__).parent.parent.parent / "index.html"

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
    limit: int = Field(default=SpotifyService.SEARCH_PAGE_LIMIT, ge=1, le=SpotifyService.SEARCH_PAGE_LIMIT)

class TrackInfo(BaseModel):
    """Track information response."""
    id: str
    name: str
    artist: str
    year: int
    popularity: int = 0
    duration_ms: int = 0
    preview_url: str = None
    genres: list[str] = []
    mix_point_ms: int = 0

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


@app.get("/")
def serve_index():
    """Serve the frontend HTML."""
    if _INDEX_HTML_PATH.exists():
        return FileResponse(str(_INDEX_HTML_PATH), media_type="text/html")
    return {"message": "AI Year-Wise DJ API is running. Use /api/search to find transitions."}

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


def _compute_mix_point_ms(duration_ms: int) -> int:
    """Return an estimated mix-point in milliseconds.

    Uses a simple heuristic that places the transition point after the first
    chorus — typically around 35 % into the song — clamped so it is never
    earlier than 45 s or later than the midpoint of the track.  This avoids
    the restricted Spotify Audio-Analysis endpoint while still giving a
    musically sensible cue point.
    """
    if duration_ms <= 0:
        return 0
    after_first_chorus = int(duration_ms * 0.35)
    midpoint = duration_ms // 2
    return min(midpoint, max(45_000, after_first_chorus))


@app.post("/api/search", response_model=DJResponse)
def search_and_get_transitions(request: TrackSearchRequest):
    """
    Search for a track by artist + name, dynamically detect its genre, and
    return Spotify recommendations seeded with the track, its primary artist,
    and up to two of its genres.  Every returned track includes a ``mix_point_ms``
    cue placed after the first chorus (≈ 35 % of the track's duration, clamped
    between 45 s and the midpoint).
    """
    try:
        sp = get_spotify_client()

        # 1. Search for the starting track using reliable artist+track syntax.
        query = f"artist:{request.artist_name} track:{request.track_name}"
        results = sp.search(q=query, type="track", limit=1, market="US")

        if not results["tracks"]["items"]:
            raise HTTPException(
                status_code=404,
                detail=f"Track '{request.track_name}' by '{request.artist_name}' not found"
            )

        start_track = results["tracks"]["items"][0]
        track_id = start_track["id"]
        seed_year = int(start_track["album"]["release_date"][:4])

        # 2. Dynamically detect genres from the primary artist.
        seed_genres: list[str] = []
        artist_id: str | None = None
        if start_track.get("artists"):
            artist_id = start_track["artists"][0]["id"]
            artist_info = sp.artist(artist_id)
            seed_genres = artist_info.get("genres", [])

        # 3. Get recommendations seeded by track + artist + up to 2 genres.
        #    Total seeds must not exceed 5, so: 1 track + 1 artist + 2 genres = 4.
        artist_seeds = [artist_id] if artist_id else []
        rec_tracks = sp.recommendations(
            seed_tracks=[track_id],
            seed_artists=artist_seeds,
            seed_genres=seed_genres[:2],
            limit=request.limit,
            market="US",
        ).get("tracks", [])

        # 4. Build next-track list with mix-point cues.
        next_tracks = [
            TrackInfo(
                id=t["id"],
                name=t["name"],
                artist=t["artists"][0]["name"] if t.get("artists") else "Unknown",
                year=int(t["album"]["release_date"][:4]) if t.get("album", {}).get("release_date") else 0,
                popularity=t.get("popularity", 0),
                duration_ms=t.get("duration_ms", 0),
                preview_url=t.get("preview_url"),
                mix_point_ms=_compute_mix_point_ms(t.get("duration_ms", 0)),
            )
            for t in rec_tracks
            if t.get("id") and t["id"] != track_id
        ]

        return DJResponse(
            starting_track=TrackInfo(
                id=track_id,
                name=start_track["name"],
                artist=start_track["artists"][0]["name"] if start_track.get("artists") else "Unknown",
                year=seed_year,
                popularity=start_track.get("popularity", 0),
                duration_ms=start_track.get("duration_ms", 0),
                preview_url=start_track.get("preview_url"),
                genres=seed_genres,
                mix_point_ms=_compute_mix_point_ms(start_track.get("duration_ms", 0)),
            ),
            next_tracks=next_tracks,
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
