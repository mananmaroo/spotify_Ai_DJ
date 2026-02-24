from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
import base64
import random

# -----------------------------
# Spotify Credentials (hardcoded for now)
# -----------------------------
SPOTIFY_CLIENT_ID = "1924460439a14115b48fc7d3d03e2e2a"
SPOTIFY_CLIENT_SECRET = "95a349e198c248448ed7e8ad1029410e"

# -----------------------------
# APP SETUP
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
# DATA MODELS
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
# HELPER FUNCTIONS
# -----------------------------
def get_spotify_token() -> str:
    auth_header = base64.b64encode(f"{spotify_client_id}:{spotify_client_secret}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_header}"}
    data = {"grant_type": "client_credentials"}
    response = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Spotify token error")
    return response.json()["access_token"]

def search_track(name: str, artist: str) -> dict:
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    query = f"track:{name} artist:{artist}"
    response = requests.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params={"q": query, "type": "track", "limit": 1}
    )
    items = response.json().get("tracks", {}).get("items", [])
    if not items:
        return {}
    return items[0]

def get_next_track(seed_track: dict, year_window: int = 2) -> dict:
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    seed_year = int(seed_track.get("album", {}).get("release_date", "0")[:4] or 0)
    choices = []

    # 50/50: same artist or year +/- window
    if "artists" in seed_track:
        # 1. Same artist, different song
        artist_id = seed_track["artists"][0]["id"]
        r = requests.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params={"q": f"artist:{artist_id}", "type": "track", "limit": 10}
        )
        choices.extend([t for t in r.json().get("tracks", {}).get("items", []) if t["id"] != seed_track.get("id")])

    # 2. Year window
    for delta in range(-year_window, year_window+1):
        y = seed_year + delta
        r = requests.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params={"q": f"year:{y}", "type": "track", "limit": 5}
        )
        choices.extend([t for t in r.json().get("tracks", {}).get("items", []) if t["id"] != seed_track.get("id")])

    if not choices:
        return seed_track  # fallback

    return random.choice(choices)

# -----------------------------
# SAFETY HELPERS
# -----------------------------
def safe_str(val):
    return val if val else "Unknown"

def safe_artists(track: dict):
    if not track or "artists" not in track:
        return ["Unknown"]
    return [a.get("name", "Unknown") for a in track.get("artists", [])]

# -----------------------------
# ROUTES
# -----------------------------
@app.get("/api/health")
def health_check():
    return {"status": "AI DJ backend running"}

@app.api_route("/api/search", methods=["POST"], response_model=TrackResponse)
def api_search(req: TrackRequest):
    seed = search_track(req.track_name, req.artist_name)
    return TrackResponse(
        name=safe_str(seed.get("name")),
        artists=safe_artists(seed),
        release_date=safe_str(seed.get("album", {}).get("release_date")),
        id=safe_str(seed.get("id")),
        uri=safe_str(seed.get("uri"))
    )

@app.api_route("/api/next-track", methods=["POST"], response_model=TrackResponse)
def api_next(req: TrackRequest):
    seed = search_track(req.track_name, req.artist_name)
    next_track = get_next_track(seed, year_window=2)
    return TrackResponse(
        name=safe_str(next_track.get("name")),
        artists=safe_artists(next_track),
        release_date=safe_str(next_track.get("album", {}).get("release_date")),
        id=safe_str(next_track.get("id")),
        uri=safe_str(next_track.get("uri"))
    )
