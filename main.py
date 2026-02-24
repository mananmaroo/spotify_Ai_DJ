import base64
import random
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# -----------------------------
# APP SETUP
# -----------------------------
app = FastAPI(title="AI DJ Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# SPOTIFY CREDENTIALS
# -----------------------------
SPOTIFY_CLIENT_ID = "1924460439a14115b48fc7d3d03e2e2a"
SPOTIFY_CLIENT_SECRET = "95a349e198c248448ed7e8ad1029410e"

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
# SPOTIFY HELPERS
# -----------------------------
def get_spotify_token() -> str:
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_header}"}
    data = {"grant_type": "client_credentials"}
    response = requests.post("https://accounts.spotify.com/api/token", headers=headers, data=data)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Spotify token error: {response.text}")
    return response.json()["access_token"]

def search_track(name: str, artist: str) -> dict:
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    query = f"track:{name} artist:{artist}"
    response = requests.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params={"q": query, "type": "track", "limit": 5}
    )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Spotify search error: {response.text}")
    items = response.json().get("tracks", {}).get("items", [])
    if not items:
        raise HTTPException(status_code=404, detail="Track not found on Spotify")
    return items[0]

def get_next_track(seed_track_id: str, limit: int = 3) -> dict:
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        "https://api.spotify.com/v1/recommendations",
        headers=headers,
        params={"seed_tracks": seed_track_id, "limit": limit}
    )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Spotify recommendations error: {response.text}")
    items = response.json().get("tracks", [])
    if not items:
        raise HTTPException(status_code=404, detail="No recommendations found")
    return random.choice(items)

# -----------------------------
# ROUTES
# -----------------------------
@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/api/health")
def health_check():
    return {"status": "AI DJ backend running"}

@app.post("/api/search", response_model=TrackResponse)
def api_search(req: TrackRequest):
    seed = search_track(req.track_name, req.artist_name)
    artists = [a["name"] for a in seed.get("artists", [])] if seed.get("artists") else []
    return TrackResponse(
        name=seed["name"],
        artists=artists,
        release_date=seed["album"]["release_date"],
        id=seed["id"],
        uri=seed["uri"]
    )

@app.post("/api/next-track", response_model=TrackResponse)
def api_next(req: TrackRequest):
    seed = search_track(req.track_name, req.artist_name)
    next_track = get_next_track(seed["id"])
    artists = [a["name"] for a in next_track.get("artists", [])] if next_track.get("artists") else []
    return TrackResponse(
        name=next_track["name"],
        artists=artists,
        release_date=next_track["album"]["release_date"],
        id=next_track["id"],
        uri=next_track["uri"]
    )
