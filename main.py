from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import base64

# -----------------------------
# Spotify Credentials (hardcoded for now)
# -----------------------------
SPOTIFY_CLIENT_ID = "1924460439a14115b48fc7d3d03e2e2a"
SPOTIFY_CLIENT_SECRET = "95a349e198c248448ed7e8ad1029410e"

# -----------------------------
# App setup
# -----------------------------
app = FastAPI(title="AI Year-Wise DJ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend directly from root
app.mount("/", StaticFiles(directory=".", html=True), name="frontend")

# -----------------------------
# Data models
# -----------------------------
class TrackRequest(BaseModel):
    track_name: str
    artist_name: str

class TrackResponse(BaseModel):
    name: str
    artists: list[str]
    release_date: str
    id: str
    uri: str

# -----------------------------
# Helper functions
# -----------------------------
def get_spotify_token() -> str:
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_header}"}
    data = {"grant_type": "client_credentials"}
    response = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Spotify token error: {response.text}")
    return response.json().get("access_token", "")

def search_track(name: str, artist: str) -> dict:
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    query = f"track:{name} artist:{artist}"
    response = requests.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params={"q": query, "type": "track", "limit": 1}
    )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Spotify search error: {response.text}")
    items = response.json().get("tracks", {}).get("items", [])
    if not items:
        raise HTTPException(status_code=404, detail="Track not found on Spotify")
    return items[0]

def get_next_track(seed_track: dict, year_window: int = 5) -> dict:
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    seed_year = seed_track.get("album", {}).get("release_date", "0")[:4]
    try:
        seed_year = int(seed_year)
    except ValueError:
        seed_year = 2020  # fallback

    # Simple year-based search
    for delta in range(year_window + 1):
        years_to_try = [seed_year - delta, seed_year + delta]
        for y in years_to_try:
            query = f"year:{y}"
            response = requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params={"q": query, "type": "track", "limit": 5}
            )
            items = response.json().get("tracks", {}).get("items", [])
            for t in items:
                if t.get("id") != seed_track.get("id"):
                    return t
    return seed_track  # fallback

# -----------------------------
# API routes
# -----------------------------
@app.get("/api/health")
def health_check():
    return {"status": "AI DJ backend running"}

@app.post("/api/search", response_model=TrackResponse)
def api_search(req: TrackRequest):
    seed = search_track(req.track_name, req.artist_name)
    artists = [a.get("name", "Unknown") for a in seed.get("artists", [])] if seed.get("artists") else []
    release_date = seed.get("album", {}).get("release_date", "Unknown")
    return TrackResponse(
        name=seed.get("name", "Unknown"),
        artists=artists,
        release_date=release_date,
        id=seed.get("id", ""),
        uri=seed.get("uri", "")
    )

@app.post("/api/next-track", response_model=TrackResponse)
def api_next(req: TrackRequest):
    seed = search_track(req.track_name, req.artist_name)
    next_track = get_next_track(seed, year_window=5)
    artists = [a.get("name", "Unknown") for a in next_track.get("artists", [])] if next_track.get("artists") else []
    release_date = next_track.get("album", {}).get("release_date", "Unknown")
    return TrackResponse(
        name=next_track.get("name", "Unknown"),
        artists=artists,
        release_date=release_date,
        id=next_track.get("id", ""),
        uri=next_track.get("uri", "")
    )
