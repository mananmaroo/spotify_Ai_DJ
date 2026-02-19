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
    window: int = 5
    limit: int = 25

class TrackInfo(BaseModel):
    """Track information response."""
    id: str
    name: str
    artist: str
    year: int
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

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/api/search", response_model=DJResponse)
def search_and_get_transitions(request: TrackSearchRequest):
    """
    Search for a track by name and artist, then find transition matches.
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
        
        start_track = results["tracks"]["items"][0]
        track_id = start_track["id"]
        
        # Get audio features for the starting track
        audio_features = sp.audio_features(track_id)[0]
        
        # Search for tracks from the target year within the window
        year_range = f"{request.year - request.window}-{request.year + request.window}"
        search_query = f"year:{year_range}"
        
        candidates = sp.search(q=search_query, type="track", limit=request.limit)
        
        # Extract track info and sort by similarity to starting track
        next_tracks = []
        for track in candidates["tracks"]["items"]:
            try:
                track_audio_features = sp.audio_features(track["id"])"[0]
                if track_audio_features:
                    next_tracks.append({
                        "id": track["id"],
                        "name": track["name"],
                        "artist": track["artists"][0]["name"] if track["artists"] else "Unknown",
                        "year": track["release_date"].split("-")[0] if track.get("release_date") else "Unknown",
                        "preview_url": track.get("preview_url"),
                        "energy_diff": abs(audio_features["energy"] - track_audio_features["energy"]),
                        "tempo_diff": abs(audio_features["tempo"] - track_audio_features["tempo"]),
                    })
            except Exception as e:
                print(f"Error processing track {track['id']}: {e}")
                continue
        
        # Sort by similarity (lower difference = better match)
        next_tracks.sort(key=lambda x: x["energy_diff"] + (x["tempo_diff"] / 100))
        next_tracks = next_tracks[:5]  # Keep top 5
        
        return DJResponse(
            starting_track=TrackInfo(
                id=track_id,
                name=start_track["name"],
                artist=start_track["artists"][0]["name"] if start_track["artists"] else "Unknown",
                year=start_track["release_date"].split("-")[0] if start_track.get("release_date") else "Unknown",
                preview_url=start_track.get("preview_url"),
            ),
            next_tracks=[
                TrackInfo(
                    id=t["id"],
                    name=t["name"],
                    artist=t["artist"],
                    year=t["year"],
                    preview_url=t["preview_url"],
                )
                for t in next_tracks
            ]
        )
        
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
