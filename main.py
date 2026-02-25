
import random
import base64
import time
import secrets
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
from urllib.parse import urlencode

# -----------------------------
# Spotify Credentials (hardcoded for now)
# -----------------------------
SPOTIFY_CLIENT_ID = "1924460439a14115b48fc7d3d03e2e2a"
SPOTIFY_CLIENT_SECRET = "95a349e198c248448ed7e8ad1029410e"

"""
Spotify DJ – FastAPI backend
Only uses endpoints confirmed working for new apps (post Nov 2024 / Feb 2026):
  - GET  /search                         (search tracks/artists)
  - GET  /artists/{id}/albums            (artist's albums)
  - GET  /albums/{id}/tracks             (tracks inside an album)
  - GET  /tracks/{id}                    (single track detail)
  - POST /me/player/play                 (premium playback – user token)

Removed/deprecated endpoints we explicitly DO NOT call:
  - GET /artists/{id}/top-tracks         (removed Feb 2026)
  - GET /recommendations                 (removed Nov 2024)
  - GET /audio-features                  (removed Nov 2024)
  - GET /browse/new-releases             (removed Feb 2026)
"""



# ── Update this after first Render deploy ──────────────────────
# REDIRECT_URI = "https://your-app-name.onrender.com/callback"
REDIRECT_URI = "http://localhost:8000/callback"

SCOPES = (
    "streaming "
    "user-read-email "
    "user-read-private "
    "user-read-playback-state "
    "user-modify-playback-state"
)

app = FastAPI()

# ─────────────────────────────────────────────────────────────────
#  CLIENT-CREDENTIALS TOKEN  (for catalog/search calls only)
# ─────────────────────────────────────────────────────────────────
_cc: dict = {"value": None, "expires_at": 0}

def get_cc_token() -> str:
    if _cc["value"] and time.time() < _cc["expires_at"] - 60:
        return _cc["value"]
    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}"},
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()
    _cc["value"] = d["access_token"]
    _cc["expires_at"] = time.time() + d["expires_in"]
    return _cc["value"]

def sp_get(url: str, params: dict = None) -> dict:
    """Authenticated GET using client-credentials token."""
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {get_cc_token()}"},
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

# ─────────────────────────────────────────────────────────────────
#  OAUTH HELPERS  (user token for premium playback)
# ─────────────────────────────────────────────────────────────────
def exchange_code(code: str) -> dict:
    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

def do_refresh(refresh_token: str) -> dict:
    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

# ─────────────────────────────────────────────────────────────────
#  CATALOG HELPERS  (only using allowed endpoints)
# ─────────────────────────────────────────────────────────────────

def search_track(song: str, artist: str) -> Optional[dict]:
    """Search for a specific track. Uses /search – always allowed."""
    data = sp_get("https://api.spotify.com/v1/search", {
        "q": f"track:{song} artist:{artist}",
        "type": "track",
        "limit": 1,
    })
    items = data.get("tracks", {}).get("items", [])
    return items[0] if items else None

def search_tracks_by_year(year: int, exclude_id: str, limit: int = 50) -> list:
    """
    Search for popular tracks from a given year.
    Uses /search with year filter – allowed.
    """
    data = sp_get("https://api.spotify.com/v1/search", {
        "q": f"year:{year}",
        "type": "track",
        "limit": limit,
    })
    return [
        t for t in data.get("tracks", {}).get("items", [])
        if t["id"] != exclude_id
    ]

def get_artist_tracks_via_albums(artist_id: str, exclude_id: str, max_tracks: int = 40) -> list:
    """
    Get tracks by an artist by:
      1. GET /artists/{id}/albums  (allowed)
      2. GET /albums/{id}/tracks   (allowed)
    This replaces the removed /artists/{id}/top-tracks endpoint.
    """
    # Step 1: fetch up to 10 albums (singles + albums give best track variety)
    try:
        albums_data = sp_get(
            f"https://api.spotify.com/v1/artists/{artist_id}/albums",
            {
                "include_groups": "album,single",
                "limit": 10,
                "market": "US",
            },
        )
    except Exception:
        return []

    albums = albums_data.get("items", [])
    if not albums:
        return []

    # Step 2: for each album fetch its tracks (stop once we have enough)
    tracks = []
    for album in albums:
        if len(tracks) >= max_tracks:
            break
        album_id = album["id"]
        try:
            tracks_data = sp_get(
                f"https://api.spotify.com/v1/albums/{album_id}/tracks",
                {"limit": 10, "market": "US"},
            )
        except Exception:
            continue

        for t in tracks_data.get("items", []):
            if t["id"] == exclude_id:
                continue
            # Album tracks endpoint returns simplified track objects;
            # we need to add album info manually so fmt() works
            t["album"] = album
            tracks.append(t)
            if len(tracks) >= max_tracks:
                break

    return tracks

def fmt(t: dict) -> dict:
    """Normalise a track object into a consistent dict for the frontend."""
    album  = t.get("album", {})
    images = album.get("images", [])
    # release_date can be "2021", "2021-03", or "2021-03-19"
    release = album.get("release_date", "")
    year = release[:4] if release else "?"
    return {
        "id":          t["id"],
        "uri":         t.get("uri") or f"spotify:track:{t['id']}",
        "name":        t["name"],
        "artist":      ", ".join(a["name"] for a in t.get("artists", [])),
        "album":       album.get("name", ""),
        "year":        year,
        "preview_url": t.get("preview_url"),
        "spotify_url": t.get("external_urls", {}).get("spotify", ""),
        "image":       images[0]["url"] if images else "",
        "duration_ms": t.get("duration_ms", 0),
    }

# ─────────────────────────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    song: str
    artist: str

class RefreshRequest(BaseModel):
    refresh_token: str

# ─────────────────────────────────────────────────────────────────
#  API ROUTES
# ─────────────────────────────────────────────────────────────────

@app.get("/login")
def login():
    params = {
        "response_type": "code",
        "client_id":     SPOTIFY_CLIENT_ID,
        "scope":         SCOPES,
        "redirect_uri":  REDIRECT_URI,
        "state":         secrets.token_urlsafe(16),
        "show_dialog":   "false",
    }
    return RedirectResponse(
        "https://accounts.spotify.com/authorize?" + urlencode(params)
    )

@app.get("/callback")
def callback(code: str = Query(None), error: str = Query(None)):
    if error or not code:
        return RedirectResponse(f"/?auth_error={error or 'no_code'}")
    try:
        tokens = exchange_code(code)
        at  = tokens["access_token"]
        rt  = tokens.get("refresh_token", "")
        exp = tokens.get("expires_in", 3600)
        # Pass tokens in URL fragment — never logged by server
        return RedirectResponse(f"/#at={at}&rt={rt}&exp={exp}")
    except Exception:
        return RedirectResponse("/?auth_error=token_exchange_failed")

@app.post("/api/refresh")
def api_refresh(req: RefreshRequest):
    try:
        data = do_refresh(req.refresh_token)
        return {
            "access_token":  data["access_token"],
            "expires_in":    data.get("expires_in", 3600),
            "refresh_token": data.get("refresh_token", req.refresh_token),
        }
    except Exception:
        raise HTTPException(401, "Token refresh failed. Please log in again.")

@app.post("/api/recommend")
def recommend(req: SearchRequest):
    # 1. Find the seed track
    seed = search_track(req.song.strip(), req.artist.strip())
    if not seed:
        raise HTTPException(
            404, f"Could not find '{req.song}' by '{req.artist}' on Spotify."
        )

    seed_year = int(seed["album"]["release_date"][:4])
    seed_aid  = seed["artists"][0]["id"]
    seed_id   = seed["id"]

    # 2. Build pools using ONLY allowed endpoints
    # Pool 1: Same artist  → via albums → tracks  (replaces removed top-tracks)
    pool1 = get_artist_tracks_via_albums(seed_aid, seed_id)

    # Pool 2: Same year    → search with year filter
    pool2 = search_tracks_by_year(seed_year, seed_id)

    # Pool 3: ±1 year      → search year-1 + year+1
    pool3 = (
        search_tracks_by_year(seed_year - 1, seed_id)
        + search_tracks_by_year(seed_year + 1, seed_id)
    )

    groups    = [(pool1, "Same Artist"), (pool2, "Same Year"), (pool3, "±1 Year")]
    non_empty = [(p, lbl) for p, lbl in groups if p]

    if not non_empty:
        raise HTTPException(404, "No recommendations found. Try a different song.")

    pool, reason = random.choice(non_empty)
    pick = random.choice(pool)

    return {
        "seed":           fmt(seed),
        "recommendation": {**fmt(pick), "match_reason": reason},
    }

@app.get("/api/client-id")
def client_id_route():
    return {"client_id": SPOTIFY_CLIENT_ID}

# ─────────────────────────────────────────────────────────────────
#  SERVE FRONTEND  (index.html at root)
# ─────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("index.html")

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    # Don't intercept API routes
    if full_path.startswith("api/") or full_path in ("login", "callback"):
        raise HTTPException(404)
    return FileResponse("index.html")
