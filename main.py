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

# ---------------------------
# App Setup
# ---------------------------
app = FastAPI(title="AI DJ")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Serve frontend directly from root
app.mount("/", StaticFiles(directory=".", html=True), name="frontend")

# ---------------------------
# Data Models
# ---------------------------
class TrackRequest(BaseModel):
    track_name: str
    artist_name: str

class TrackResponse(BaseModel):
    name: str
    artists: list[str]
    release_date: str
    id: str
    uri: str

# ---------------------------
# Spotify Helpers
# ---------------------------
def get_spotify_token():
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_header}"}
    data = {"grant_type": "client_credentials"}
    for i in range(3):  # retry token 3 times
        r = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
        if r.status_code == 200:
            return r.json()["access_token"]
        time.sleep(1)
    raise HTTPException(status_code=500, detail="Spotify token error")

def safe_track(track: dict):
    return {
        "name": track.get("name", "Unknown"),
        "artists": [a.get("name", "Unknown") for a in track.get("artists", [])] if track else ["Unknown"],
        "release_date": track.get("album", {}).get("release_date", "Unknown") if track else "Unknown",
        "id": track.get("id", ""),
        "uri": track.get("uri", "")
    }

def search_track(name: str, artist: str, retries: int = 10):
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    query = f"track:{name} artist:{artist}"
    for _ in range(retries):
        r = requests.get("https://api.spotify.com/v1/search",
                         headers=headers,
                         params={"q": query, "type": "track", "limit": 5})
        if r.status_code == 200:
            items = r.json().get("tracks", {}).get("items", [])
            if items:
                return random.choice(items)  # random choice if multiple results
        time.sleep(0.5)
    return {}  # fallback empty dict

def get_next_track(seed: dict, year_window: int = 2, retries: int = 10):
    if not seed:
        return {}
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    seed_year = seed.get("album", {}).get("release_date", "0")[:4]
    try:
        seed_year = int(seed_year)
    except:
        seed_year = 0

    for _ in range(retries):
        # randomly pick either same artist or year window
        choice = random.choice(["artist", "year"])
        if choice == "artist":
            artist = seed.get("artists", [{}])[0].get("name", "")
            query = f"artist:{artist}" if artist else ""
        else:
            offset = random.randint(-year_window, year_window)
            query = f"year:{seed_year+offset}" if seed_year else ""
        if not query:
            continue
        r = requests.get("https://api.spotify.com/v1/search",
                         headers=headers,
                         params={"q": query, "type": "track", "limit": 5})
        if r.status_code == 200:
            items = r.json().get("tracks", {}).get("items", [])
            candidates = [t for t in items if t.get("id") != seed.get("id")]
            if candidates:
                return random.choice(candidates)
        time.sleep(0.5)
    return seed  # fallback to seed

# ---------------------------
# API Routes
# ---------------------------
@app.get("/api/health")
def health_check():
    return {"status": "AI DJ backend running"}

@app.post("/api/search", response_model=TrackResponse)
def api_search(req: TrackRequest):
    track = search_track(req.track_name, req.artist_name)
    return safe_track(track)

@app.post("/api/next-track", response_model=TrackResponse)
def api_next(req: TrackRequest):
    seed = search_track(req.track_name, req.artist_name)
    next_track = get_next_track(seed, year_window=2)
    return safe_track(next_track)
