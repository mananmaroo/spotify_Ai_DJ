
import os
import random
import base64
import time
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

# -----------------------------
# Spotify Credentials (hardcoded for now)
# -----------------------------
SPOTIFY_CLIENT_ID = "1924460439a14115b48fc7d3d03e2e2a"
SPOTIFY_CLIENT_SECRET = "95a349e198c248448ed7e8ad1029410e"


app = FastAPI()

# ─────────────────────────────────────────────
#  TOKEN CACHE
# ─────────────────────────────────────────────
_token: dict = {"value": None, "expires_at": 0}

def get_token() -> str:
    if _token["value"] and time.time() < _token["expires_at"] - 60:
        return _token["value"]
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}"},
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()
    _token["value"] = d["access_token"]
    _token["expires_at"] = time.time() + d["expires_in"]
    return _token["value"]

def sp(url: str, params: dict = None) -> dict:
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {get_token()}"},
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def search_seed_track(song: str, artist: str) -> Optional[dict]:
    data = sp("https://api.spotify.com/v1/search", {
        "q": f"track:{song} artist:{artist}",
        "type": "track",
        "limit": 1,
    })
    items = data.get("tracks", {}).get("items", [])
    return items[0] if items else None

def artist_other_tracks(artist_id: str, exclude_id: str) -> list:
    data = sp(f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks", {"market": "US"})
    return [t for t in data.get("tracks", []) if t["id"] != exclude_id]

def year_tracks(year: int, exclude_id: str, limit: int = 50) -> list:
    data = sp("https://api.spotify.com/v1/search", {
        "q": f"year:{year}",
        "type": "track",
        "limit": limit,
    })
    return [t for t in data.get("tracks", {}).get("items", []) if t["id"] != exclude_id]

def fmt(t: dict) -> dict:
    album = t.get("album", {})
    images = album.get("images", [])
    return {
        "id":          t["id"],
        "name":        t["name"],
        "artist":      ", ".join(a["name"] for a in t["artists"]),
        "album":       album.get("name", ""),
        "year":        album.get("release_date", "")[:4],
        "preview_url": t.get("preview_url"),
        "spotify_url": t.get("external_urls", {}).get("spotify", ""),
        "image":       images[0]["url"] if images else "",
        "duration_ms": t.get("duration_ms", 0),
    }

# ─────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────
class SearchRequest(BaseModel):
    song: str
    artist: str

# ─────────────────────────────────────────────
#  API ROUTES
# ─────────────────────────────────────────────
@app.post("/api/recommend")
def recommend(req: SearchRequest):
    seed = search_seed_track(req.song.strip(), req.artist.strip())
    if not seed:
        raise HTTPException(404, f"Could not find '{req.song}' by '{req.artist}' on Spotify.")

    seed_year  = int(seed["album"]["release_date"][:4])
    seed_aid   = seed["artists"][0]["id"]
    seed_id    = seed["id"]

    # --- pool 1: same artist ---
    pool1 = artist_other_tracks(seed_aid, seed_id)

    # --- pool 2: same year ---
    pool2 = year_tracks(seed_year, seed_id)

    # --- pool 3: ±1 year ---
    pool3 = year_tracks(seed_year - 1, seed_id) + year_tracks(seed_year + 1, seed_id)

    # weighted random group pick
    groups = [(pool1, "Same Artist"), (pool2, "Same Year"), (pool3, "±1 Year")]
    non_empty = [(p, label) for p, label in groups if p]
    if not non_empty:
        raise HTTPException(404, "No recommendations found. Try a different song.")

    pool, match_reason = random.choice(non_empty)
    pick = random.choice(pool)

    return {
        "seed":        fmt(seed),
        "recommendation": {**fmt(pick), "match_reason": match_reason},
    }

@app.get("/api/token")
def get_client_token():
    """Return a fresh client-credentials token for Web Playback SDK."""
    return {"access_token": get_token()}

# ─────────────────────────────────────────────
#  STATIC FILES  (frontend served from root)
# ─────────────────────────────────────────────
app.mount("/", StaticFiles(directory=".", html=True), name="static")

@app.get("/")
def index():
    return FileResponse("index.html")
