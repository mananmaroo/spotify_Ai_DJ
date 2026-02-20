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
    """Request to search for a track by song, artist, genre, and year."""
    track_name: str
    artist_name: str
    genre: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
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


def _seed_genres(sp: spotipy.Spotify, track: dict, fallback_genre: str | None) -> list[str]:
    artist_id = (track.get("artists") or [{}])[0].get("id")
    if artist_id:
        artist = sp.artist(artist_id)
        artist_genres = artist.get("genres") or []
        if artist_genres:
            return artist_genres
    return [fallback_genre] if fallback_genre else []


def _score_candidate(seed: dict, candidate: dict, target_year: int, window: int) -> float:
    pop_diff = abs(seed.get("popularity", 0) - candidate.get("popularity", 0))
    pop_score = max(0.0, 1.0 - pop_diff / 100.0)

    dur_diff = abs(seed.get("duration_ms", 0) - candidate.get("duration_ms", 0))
    dur_score = max(0.0, 1.0 - dur_diff / 120_000.0)

    year_diff = abs(_track_release_year(candidate) - target_year)
    year_score = max(0.0, 1.0 - year_diff / max(window, 1))

    return 0.5 * pop_score + 0.2 * dur_score + 0.3 * year_score


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

_POPULARITY_WEIGHT = 0.5
_DURATION_WEIGHT = 0.3


@app.post("/api/search", response_model=DJResponse)
def search_and_get_transitions(request: TrackSearchRequest):
    """Search by song, artist, genre, and exact year, then find transitions."""
    try:
        sp = get_spotify_client()

        # Search for the starting track
        query_parts = [f"track:{request.track_name}", f"artist:{request.artist_name}"]
        if request.genre:
            query_parts.append(f'genre:"{request.genre}"')
        if request.year:
            query_parts.append(f"year:{request.year}")
        query = " ".join(query_parts)
        results = sp.search(q=query, type="track", limit=1)

        if not results["tracks"]["items"]:
            raise HTTPException(
                status_code=404,
                detail=f"Track '{request.track_name}' by '{request.artist_name}' not found"
            )

        start_track = results["tracks"]["items"][0]
        track_id = start_track["id"]
        seed_popularity = start_track.get("popularity", 50)
        seed_duration_ms = start_track.get("duration_ms", 0)
        year = _track_release_year(start_track)
        genres = _seed_genres(sp, start_track, request.genre)

        search_query_parts = [f"year:{year}"]
        if genres:
            search_query_parts.insert(0, f'genre:"{genres[0]}"')
        search_query = " ".join(search_query_parts)

        safe_limit = min(request.limit, SpotifyService.SEARCH_PAGE_LIMIT)
        candidates_result = sp.search(q=search_query, type="track", limit=safe_limit, market="US")
        candidate_items = candidates_result["tracks"]["items"]

        # If the genre-filtered search returned nothing, fall back to exact year-only
        if not candidate_items:
            fallback_result = sp.search(q=f"year:{year}", type="track", limit=safe_limit, market="US")
            candidate_items = fallback_result["tracks"]["items"]

        # Rank candidates using metadata (popularity gradient + duration proximity).
        # This avoids the restricted /v1/audio-features endpoint.
        next_tracks = []
        for track in candidate_items:
            if track["id"] == track_id:
                continue
            track_popularity = track.get("popularity", 50)
            track_duration_ms = track.get("duration_ms", 0)
            release_date = track["album"].get("release_date", "0000")
            track_year = int(release_date[:4]) if release_date else 0
            popularity_penalty = abs(seed_popularity - track_popularity) / 100.0
            duration_penalty = min(1.0, abs(seed_duration_ms - track_duration_ms) / 60_000.0)
            score = max(0.0, 1.0 - _POPULARITY_WEIGHT * popularity_penalty - _DURATION_WEIGHT * duration_penalty)
            next_tracks.append({
                "id": track["id"],
                "name": track["name"],
                "artist": track["artists"][0]["name"] if track["artists"] else "Unknown",
                "year": track_year,
                "preview_url": track.get("preview_url"),
                "score": score,
            })

        # Sort by descending score (higher = better match)
        next_tracks.sort(key=lambda x: x["score"], reverse=True)
        next_tracks = next_tracks[:5]  # Keep top 5

        return DJResponse(
            starting_track=TrackInfo(
                id=track_id,
                name=start_track["name"],
                artist=start_track["artists"][0]["name"] if start_track["artists"] else "Unknown",
                year=year,
                popularity=start_track.get("popularity", 0),
                duration_ms=start_track.get("duration_ms", 0),
                preview_url=start_track.get("preview_url"),
                genres=genres,
            ),
            next_tracks=[
                TrackInfo(
                    id=t["id"],
                    name=t["name"],
                    artist=t["artist"],
                    year=t["year"],
                    preview_url=t.get("preview_url"),
                )
                for t in next_tracks
            ]
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
