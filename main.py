
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

Features:
- Preview URL scraped from embed (API returns null for new apps)
- Blacklist: in-memory list, resets on server restart, user-managed via API
- Lyrics filter: only return tracks where track_number > 0 and
  album_type is 'album' or 'single' (filters out podcasts/audiobooks)
- Only uses Feb-2026-safe Spotify API endpoints
"""


# Must match exactly what's in Spotify Dashboard → App Settings → Redirect URIs
REDIRECT_URI = "https://spotify-ai-dj.onrender.com/callback"

SCOPES = (
    "streaming "
    "user-read-email "
    "user-read-private "
    "user-read-playback-state "
    "user-modify-playback-state"
)

app = FastAPI()

# ─────────────────────────────────────────────────────────────────
#  IN-MEMORY BLACKLIST  (resets on every server restart)
# ─────────────────────────────────────────────────────────────────
# Stored as lowercase for case-insensitive matching
_blacklist: set = set()

# ─────────────────────────────────────────────────────────────────
#  CLIENT-CREDENTIALS TOKEN
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
#  PREVIEW URL SCRAPER
#  Spotify removed preview_url from API responses for new apps (Nov 2024).
#  Scrape from public embed HTML instead — no auth needed.
# ─────────────────────────────────────────────────────────────────
_preview_cache: dict = {}

def get_preview_url(track_id: str) -> Optional[str]:
    if track_id in _preview_cache:
        return _preview_cache[track_id]
    try:
        r = requests.get(
            f"https://open.spotify.com/embed/track/{track_id}",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
            timeout=8,
        )
        # Try new JSON structure first
        match = re.search(r'"audioPreview"\s*:\s*\{"url"\s*:\s*"(https://[^"]+)"', r.text)
        if not match:
            match = re.search(r'"preview_url"\s*:\s*"(https://[^"]+)"', r.text)
        url = match.group(1) if match else None
        _preview_cache[track_id] = url
        return url
    except Exception:
        _preview_cache[track_id] = None
        return None

# ─────────────────────────────────────────────────────────────────
#  LYRICS / MUSIC FILTER
#  Spotify's 'type' field on album: 'album', 'single', 'compilation'
#  Podcasts/audiobooks have album type 'podcast' or come via episode objects.
#  We also check the track object type == 'track' (not 'episode').
# ─────────────────────────────────────────────────────────────────
MUSIC_ALBUM_TYPES = {"album", "single", "compilation"}

def is_music_track(t: dict) -> bool:
    """Return True only if this is a real music track (not podcast/audiobook)."""
    # Track-level type check
    if t.get("type", "track") != "track":
        return False
    # Album-level type check
    album_type = t.get("album", {}).get("album_type", "album").lower()
    if album_type not in MUSIC_ALBUM_TYPES:
        return False
    return True

# ─────────────────────────────────────────────────────────────────
#  BLACKLIST FILTER
# ─────────────────────────────────────────────────────────────────
def is_blacklisted(t: dict) -> bool:
    """Return True if any artist on the track is in the blacklist."""
    for artist in t.get("artists", []):
        if artist.get("name", "").lower() in _blacklist:
            return True
    return False

def filter_tracks(tracks: list) -> list:
    """Apply music filter + blacklist filter to a pool of tracks."""
    return [t for t in tracks if is_music_track(t) and not is_blacklisted(t)]

# ─────────────────────────────────────────────────────────────────
#  OAUTH
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
YEAR_SEED_TERMS = [
    "the", "love", "night", "feel", "time",
    "new", "life", "way", "good", "day",
]

def search_track(song: str, artist: str) -> Optional[dict]:
    data = sp_get("https://api.spotify.com/v1/search", {
        "q":     f"track:{song} artist:{artist}",
        "type":  "track",
        "limit": 1,
    })
    items = data.get("tracks", {}).get("items", [])
    return items[0] if items else None

def search_tracks_by_year(year: int, exclude_id: str) -> list:
    results, seen = [], {exclude_id}
    for term in random.sample(YEAR_SEED_TERMS, 4):
        try:
            data = sp_get("https://api.spotify.com/v1/search", {
                "q":     f"{term} year:{year}",
                "type":  "track",
                "limit": 10,
            })
            for t in data.get("tracks", {}).get("items", []):
                if t["id"] not in seen:
                    seen.add(t["id"])
                    results.append(t)
        except requests.HTTPError:
            continue
    return results

def get_artist_tracks(artist_id: str, artist_name: str, exclude_id: str) -> list:
    tracks, seen = [], {exclude_id}
    for offset in [0, 10]:
        if len(tracks) >= 30:
            break
        try:
            data = sp_get("https://api.spotify.com/v1/search", {
                "q":      f"artist:{artist_name}",
                "type":   "track",
                "limit":  10,
                "offset": offset,
            })
            for t in data.get("tracks", {}).get("items", []):
                if t["id"] not in seen:
                    seen.add(t["id"])
                    tracks.append(t)
        except requests.HTTPError:
            break
    if len(tracks) < 30:
        try:
            albums = sp_get(
                f"https://api.spotify.com/v1/artists/{artist_id}/albums",
                {"include_groups": "album,single", "limit": 10, "market": "US"},
            ).get("items", [])
            for album in albums:
                if len(tracks) >= 30:
                    break
                try:
                    for t in sp_get(
                        f"https://api.spotify.com/v1/albums/{album['id']}/tracks",
                        {"limit": 10, "market": "US"},
                    ).get("items", []):
                        if t["id"] not in seen:
                            seen.add(t["id"])
                            t["album"] = album
                            tracks.append(t)
                except requests.HTTPError:
                    continue
        except requests.HTTPError:
            pass
    return tracks

def fmt(t: dict) -> dict:
    album   = t.get("album", {})
    images  = album.get("images", [])
    release = album.get("release_date", "")
    preview = get_preview_url(t["id"])
    return {
        "id":          t["id"],
        "uri":         t.get("uri") or f"spotify:track:{t['id']}",
        "name":        t["name"],
        "artist":      ", ".join(a["name"] for a in t.get("artists", [])),
        "album":       album.get("name", ""),
        "year":        release[:4] if release else "?",
        "preview_url": preview,
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

class BlacklistAddRequest(BaseModel):
    artist: str

# ─────────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────────

# ── Auth ──────────────────────────────────────────────────────────
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

# ── Blacklist ─────────────────────────────────────────────────────
@app.get("/api/blacklist")
def get_blacklist():
    """Return current blacklist (sorted, original casing not preserved)."""
    return {"blacklist": sorted(_blacklist)}

@app.post("/api/blacklist")
def add_to_blacklist(req: BlacklistAddRequest):
    """Add an artist to the in-memory blacklist."""
    name = req.artist.strip()
    if not name:
        raise HTTPException(400, "Artist name cannot be empty.")
    _blacklist.add(name.lower())
    return {"blacklist": sorted(_blacklist), "added": name}

@app.delete("/api/blacklist")
def remove_from_blacklist(artist: str = Query(...)):
    """Remove an artist from the blacklist."""
    key = artist.strip().lower()
    _blacklist.discard(key)
    return {"blacklist": sorted(_blacklist), "removed": artist}

# ── Recommendations ───────────────────────────────────────────────
@app.post("/api/recommend")
def recommend(req: SearchRequest):
    seed = search_track(req.song.strip(), req.artist.strip())
    if not seed:
        raise HTTPException(404, f"Could not find '{req.song}' by '{req.artist}' on Spotify.")

    seed_year        = int(seed["album"]["release_date"][:4])
    seed_artist_id   = seed["artists"][0]["id"]
    seed_artist_name = seed["artists"][0]["name"]
    seed_id          = seed["id"]

    # Build pools and apply music + blacklist filter
    pool1 = filter_tracks(get_artist_tracks(seed_artist_id, seed_artist_name, seed_id))
    pool2 = filter_tracks(search_tracks_by_year(seed_year, seed_id))
    pool3 = filter_tracks(
        search_tracks_by_year(seed_year - 1, seed_id)
        + search_tracks_by_year(seed_year + 1, seed_id)
    )

    groups    = [(pool1, "Same Artist"), (pool2, "Same Year"), (pool3, "±1 Year")]
    non_empty = [(p, lbl) for p, lbl in groups if p]
    if not non_empty:
        raise HTTPException(404, "No recommendations found. Try a different song or adjust the blacklist.")

    pool, reason = random.choice(non_empty)
    pick = random.choice(pool)

    return {
        "seed":           fmt(seed),
        "recommendation": {**fmt(pick), "match_reason": reason},
    }

@app.get("/api/client-id")
def client_id_route():
    return {"client_id": SPOTIFY_CLIENT_ID}

# ── Static ────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("index.html")

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    if full_path.startswith(("api/", "login", "callback")):
        raise HTTPException(404)
    return FileResponse("index.html")
