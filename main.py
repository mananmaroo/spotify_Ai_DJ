
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
Spotify DJ – FastAPI backend (Feb 2026 compliant)

Only uses endpoints/fields confirmed working for Development Mode apps
after the February 2026 Spotify API changes:

  ALLOWED (and used here):
  ✅ POST /api/token                      – client credentials + OAuth
  ✅ GET  /search?q=...&type=track&limit≤10  – search (max 10 per request now)
  ✅ GET  /artists/{id}/albums            – artist's albums list
  ✅ GET  /albums/{id}/tracks             – tracks inside an album
  ✅ GET  /me/player/play                 – premium playback (user token)

  NOT USED (removed or restricted):
  ❌ GET /artists/{id}/top-tracks         – removed Feb 2026
  ❌ GET /recommendations                 – removed Nov 2024
  ❌ GET /audio-features                  – removed Nov 2024
  ❌ GET /browse/new-releases             – removed Feb 2026
  ❌ search with limit > 10              – now 400s in Dev Mode
  ❌ year: as sole query term             – 400s, must include a keyword too

  REMOVED FIELDS we no longer read:
  ❌ popularity, available_markets, external_ids, label, album_group
"""

# ── Update this to your Render URL before deploying ──────────────
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
#  CLIENT-CREDENTIALS TOKEN  (search & catalog only)
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
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {get_cc_token()}"},
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()

# ─────────────────────────────────────────────────────────────────
#  OAUTH  (user token for Web Playback SDK)
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
#  CATALOG HELPERS
# ─────────────────────────────────────────────────────────────────

def search_track(song: str, artist: str) -> Optional[dict]:
    """Find a specific track. /search with limit=1 — always works."""
    data = sp_get("https://api.spotify.com/v1/search", {
        "q":     f"track:{song} artist:{artist}",
        "type":  "track",
        "limit": 1,
    })
    items = data.get("tracks", {}).get("items", [])
    return items[0] if items else None


# Feb 2026: search limit is now max 10 per request in Dev Mode.
# "year:" alone as the query term causes 400 Bad Request.
# Fix: use the ARTIST NAME as the keyword + year: as filter,
# then try a few different common search terms to get variety.
YEAR_SEED_TERMS = [
    "the", "love", "night", "feel", "time",
    "new", "life", "way", "good", "day", "rock", "hiphop", "rap",
]

def search_tracks_by_year(year: int, exclude_id: str) -> list:
    """
    Search for tracks from a given year.
    Uses a keyword + year: filter (bare year: alone = 400 in Dev Mode).
    Runs multiple searches with different seed words to build a pool.
    Limit capped at 10 per request (Feb 2026 restriction).
    """
    results = []
    seen_ids = {exclude_id}
    terms = random.sample(YEAR_SEED_TERMS, min(4, len(YEAR_SEED_TERMS)))
    for term in terms:
        try:
            data = sp_get("https://api.spotify.com/v1/search", {
                "q":     f"{term} year:{year}",
                "type":  "track",
                "limit": 10,   # max allowed in Dev Mode
            })
            for t in data.get("tracks", {}).get("items", []):
                if t["id"] not in seen_ids:
                    seen_ids.add(t["id"])
                    results.append(t)
        except requests.HTTPError:
            continue  # skip if this particular combo fails
    return results


def get_artist_tracks_via_albums(
    artist_id: str,
    artist_name: str,
    exclude_id: str,
    max_tracks: int = 30,
) -> list:
    """
    Fetch tracks by an artist using the still-available endpoints:
      GET /artists/{id}/albums  → GET /albums/{id}/tracks
    Replaces the removed GET /artists/{id}/top-tracks.

    Strategy: search for 'artist:{name}' across multiple pages to get
    a diverse track list, supplemented by album track crawling.
    """
    tracks = []
    seen_ids = {exclude_id}

    # --- Strategy A: search "artist:{name}" (fast, good variety) ---
    for offset in [0, 10]:
        if len(tracks) >= max_tracks:
            break
        try:
            data = sp_get("https://api.spotify.com/v1/search", {
                "q":      f"artist:{artist_name}",
                "type":   "track",
                "limit":  10,
                "offset": offset,
            })
            for t in data.get("tracks", {}).get("items", []):
                if t["id"] not in seen_ids:
                    seen_ids.add(t["id"])
                    tracks.append(t)
        except requests.HTTPError:
            break

    if len(tracks) >= max_tracks:
        return tracks[:max_tracks]

    # --- Strategy B: albums → tracks (deeper crawl as fallback) ---
    try:
        albums_data = sp_get(
            f"https://api.spotify.com/v1/artists/{artist_id}/albums",
            {
                "include_groups": "album,single",
                "limit":          10,
                "market":         "US",
            },
        )
    except requests.HTTPError:
        return tracks[:max_tracks]

    for album in albums_data.get("items", []):
        if len(tracks) >= max_tracks:
            break
        try:
            album_tracks = sp_get(
                f"https://api.spotify.com/v1/albums/{album['id']}/tracks",
                {"limit": 10, "market": "US"},
            )
        except requests.HTTPError:
            continue
        for t in album_tracks.get("items", []):
            if t["id"] not in seen_ids:
                seen_ids.add(t["id"])
                t["album"] = album   # inject album info (simplified tracks lack it)
                tracks.append(t)
            if len(tracks) >= max_tracks:
                break

    return tracks[:max_tracks]


def fmt(t: dict) -> dict:
    """Normalise any track object for the frontend."""
    album  = t.get("album", {})
    images = album.get("images", [])
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
#  ROUTES
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
    # 1. Find seed track
    seed = search_track(req.song.strip(), req.artist.strip())
    if not seed:
        raise HTTPException(
            404,
            f"Could not find '{req.song}' by '{req.artist}' on Spotify.",
        )

    seed_year        = int(seed["album"]["release_date"][:4])
    seed_artist_id   = seed["artists"][0]["id"]
    seed_artist_name = seed["artists"][0]["name"]
    seed_id          = seed["id"]

    # 2. Build pools — all using Feb-2026-safe endpoints
    # Pool 1: Same artist  (search + album crawl)
    pool1 = get_artist_tracks_via_albums(
        seed_artist_id, seed_artist_name, seed_id
    )

    # Pool 2: Same year  (keyword + year: filter, multiple queries)
    pool2 = search_tracks_by_year(seed_year, seed_id)

    # Pool 3: ±1 year
    pool3 = (
        search_tracks_by_year(seed_year - 1, seed_id)
        + search_tracks_by_year(seed_year + 1, seed_id)
    )

    groups    = [(pool1, "Same Artist"), (pool2, "Same Year"), (pool3, "±1 Year")]
    non_empty = [(p, lbl) for p, lbl in groups if p]

    if not non_empty:
        raise HTTPException(
            404, "No recommendations found. Try a different song."
        )

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
#  SERVE FRONTEND
# ─────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("index.html")

# Catch-all: serve index.html for all non-API routes (SPA behaviour)
@app.get("/{full_path:path}")
def catch_all(full_path: str):
    if full_path.startswith(("api/", "login", "callback")):
        raise HTTPException(404)
    return FileResponse("index.html")
