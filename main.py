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

def safe_str(val, default="Unknown"):
    return str(val) if val else default

def safe_artists(track):
    return [a.get("name", "Unknown") for a in track.get("artists", [])] if track.get("artists") else ["Unknown"]

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

def fetch_tracks(query: str, limit: int = 10) -> list:
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params={"q": query, "type": "track", "limit": limit}
    )
    if response.status_code != 200:
        return []
    return response.json().get("tracks", {}).get("items", [])

def get_next_track(seed_track: dict, year_window: int = 2) -> dict:
    release_date = seed_track.get("album", {}).get("release_date", "")
    try:
        seed_year = int(release_date[:4])
    except Exception:
        seed_year = 2020
    artist_ids = [a.get("id") for a in seed_track.get("artists", []) if a.get("id")]

    candidates = []

    # 1️⃣ Same year
    same_year_tracks = fetch_tracks(f"year:{seed_year}", limit=5)
    same_year_tracks = [t for t in same_year_tracks if t.get("id") != seed_track.get("id")]
    if same_year_tracks:
        candidates.append(same_year_tracks)

    # 2️⃣ Same artist
    if artist_ids:
        for aid in artist_ids:
            artist_tracks = fetch_tracks(f"artist:{aid}", limit=5)
            artist_tracks = [t for t in artist_tracks if t.get("id") != seed_track.get("id")]
            if artist_tracks:
                candidates.append(artist_tracks)

    # 3️⃣ ±2 years
    year_range_tracks = []
    for delta in range(1, year_window + 1):
        for y in [seed_year - delta, seed_year + delta]:
            tracks = fetch_tracks(f"year:{y}", limit=5)
            tracks = [t for t in tracks if t.get("id") != seed_track.get("id")]
            year_range_tracks.extend(tracks)
    if year_range_tracks:
        candidates.append(year_range_tracks)

    # Randomly pick one group, then one track from that group
    if candidates:
        group = random.choice(candidates)
        return random.choice(group)

    return seed_track
