
import random
import base64
import time
import secrets
import requests
import threading
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
Spotify DJ – FastAPI backend (lean version)

Flow per /api/recommend:
  1. Find seed track — plain fuzzy query "song artist", fallback to song-only
  2. Pick one bucket type at random (artist OR year)
  3. Fire exactly that ONE search call
  4. Return result

Total Spotify API calls per request: 2 maximum (seed + 1 pool)
With 10-min cache: 0-2 depending on history

Rate limiting: threading.Lock serialises all calls + 429 Retry-After respected
"""


REDIRECT_URI          = "https://spotify-ai-dj.onrender.com/callback"
SCOPES = "streaming user-read-email user-read-private user-read-playback-state user-modify-playback-state"

app = FastAPI()

# ─────────────────────────────────────────────────────────────────
#  IN-MEMORY STATE
# ─────────────────────────────────────────────────────────────────
_blacklist:  set = set()
_view_count: int = 0

# ─────────────────────────────────────────────────────────────────
#  RATE LIMIT & CACHE
# ─────────────────────────────────────────────────────────────────
_api_lock         = threading.Lock()
_rate_limit_until = 0.0
_cache: dict      = {}
CACHE_TTL         = 600   # 10 min

def _cache_get(key):
    e = _cache.get(key)
    return e[0] if e and time.time() < e[1] else None

def _cache_set(key, val):
    _cache[key] = (val, time.time() + CACHE_TTL)

# ─────────────────────────────────────────────────────────────────
#  CLIENT CREDENTIALS TOKEN
# ─────────────────────────────────────────────────────────────────
_cc = {"value": None, "expires_at": 0}

def _get_token() -> str:
    if _cc["value"] and time.time() < _cc["expires_at"] - 60:
        return _cc["value"]
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}"},
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    _cc["value"] = d["access_token"]
    _cc["expires_at"] = time.time() + d["expires_in"]
    return _cc["value"]

# ─────────────────────────────────────────────────────────────────
#  CORE GET — serialised, cached, 429-aware
# ─────────────────────────────────────────────────────────────────
def sp_get(url: str, params: dict = None) -> dict:
    global _rate_limit_until
    key = url + str(sorted((params or {}).items()))

    hit = _cache_get(key)
    if hit is not None:
        return hit

    with _api_lock:
        hit = _cache_get(key)
        if hit is not None:
            return hit

        for attempt in range(4):
            # honour global rate-limit cooldown
            gap = _rate_limit_until - time.time()
            if gap > 0:
                time.sleep(gap + 0.05)

            try:
                r = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {_get_token()}"},
                    params=params,
                    timeout=15,
                )

                if r.status_code == 429:
                    wait = min(int(r.headers.get("Retry-After", "10")), 60)
                    _rate_limit_until = time.time() + wait
                    time.sleep(wait)
                    continue

                r.raise_for_status()
                data = r.json()
                _cache_set(key, data)
                return data

            except requests.HTTPError as e:
                if attempt < 3:
                    time.sleep(1)
                    continue
                raise HTTPException(502, f"Spotify error: {e}")
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise HTTPException(503, f"Cannot reach Spotify: {e}")

        raise HTTPException(429, "Rate limited — please try again shortly.")

# ─────────────────────────────────────────────────────────────────
#  PREVIEW URL SCRAPER
# ─────────────────────────────────────────────────────────────────
_preview_cache: dict = {}

def get_preview_url(track_id: str) -> Optional[str]:
    if track_id in _preview_cache:
        return _preview_cache[track_id]
    try:
        r = requests.get(
            f"https://open.spotify.com/embed/track/{track_id}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=8,
        )
        m = re.search(r'"audioPreview"\s*:\s*\{"url"\s*:\s*"(https://[^"]+)"', r.text)
        if not m:
            m = re.search(r'"preview_url"\s*:\s*"(https://[^"]+)"', r.text)
        url = m.group(1) if m else None
    except Exception:
        url = None
    _preview_cache[track_id] = url
    return url

# ─────────────────────────────────────────────────────────────────
#  FILTERS
# ─────────────────────────────────────────────────────────────────
MUSIC_ALBUM_TYPES = {"album", "single", "compilation"}

def _is_music(t: dict) -> bool:
    if t.get("type", "track") != "track":
        return False
    return t.get("album", {}).get("album_type", "album").lower() in MUSIC_ALBUM_TYPES

def _is_blacklisted(t: dict) -> bool:
    return any(a.get("name", "").lower() in _blacklist for a in t.get("artists", []))

def clean(tracks: list) -> list:
    return [t for t in tracks if _is_music(t) and not _is_blacklisted(t)]

# ─────────────────────────────────────────────────────────────────
#  OAUTH
# ─────────────────────────────────────────────────────────────────
def _post_token(data: dict) -> dict:
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
        data=data, timeout=15,
    )
    r.raise_for_status()
    return r.json()

def exchange_code(code):  return _post_token({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI})
def do_refresh(rt):       return _post_token({"grant_type": "refresh_token", "refresh_token": rt})

# ─────────────────────────────────────────────────────────────────
#  SEARCH HELPERS
# ─────────────────────────────────────────────────────────────────
YEAR_TERMS = ["love", "night", "feel", "time", "new", "life", "way", "good", "back", "like"]

def find_seed(song: str, artist: str) -> Optional[dict]:
    """
    Try queries from most to least permissive.
    Plain 'song artist' works for virtually everything on Spotify.
    """
    for q in [f"{song} {artist}", song]:
        try:
            d = sp_get("https://api.spotify.com/v1/search",
                       {"q": q, "type": "track", "limit": 5})
            items = d.get("tracks", {}).get("items", [])
            if not items:
                continue
            # Prefer item whose artist name matches
            al = artist.lower()
            for item in items:
                if any(al in a["name"].lower() or a["name"].lower() in al
                       for a in item.get("artists", [])):
                    return item
            return items[0]
        except Exception:
            continue
    return None

def artist_pool(artist_name: str, exclude_id: str) -> list:
    try:
        d = sp_get("https://api.spotify.com/v1/search",
                   {"q": artist_name, "type": "track", "limit": 10})
        return clean([t for t in d.get("tracks", {}).get("items", []) if t["id"] != exclude_id])
    except Exception:
        return []

def year_pool(year: int, exclude_id: str) -> list:
    term = random.choice(YEAR_TERMS)
    try:
        d = sp_get("https://api.spotify.com/v1/search",
                   {"q": f"{term} year:{year}", "type": "track", "limit": 10})
        return clean([t for t in d.get("tracks", {}).get("items", []) if t["id"] != exclude_id])
    except Exception:
        return []

def fmt(t: dict) -> dict:
    album   = t.get("album", {})
    images  = album.get("images", [])
    release = album.get("release_date", "")
    return {
        "id":          t["id"],
        "uri":         t.get("uri") or f"spotify:track:{t['id']}",
        "name":        t["name"],
        "artist":      ", ".join(a["name"] for a in t.get("artists", [])),
        "album":       album.get("name", ""),
        "year":        release[:4] if release else "?",
        "preview_url": get_preview_url(t["id"]),
        "spotify_url": t.get("external_urls", {}).get("spotify", ""),
        "image":       images[0]["url"] if images else "",
        "duration_ms": t.get("duration_ms", 0),
        "popularity":  t.get("popularity", 0),
    }

# ─────────────────────────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────────────────────────
def popularity_filter(tracks: list, mode: str) -> list:
    """No extra API calls — popularity is already in the track objects."""
    if mode == "popular":
        hi = [t for t in tracks if t.get("popularity", 0) >= 60]
        return hi or tracks          # fallback to full pool if none qualify
    if mode == "underground":
        lo = [t for t in tracks if t.get("popularity", 0) < 40]
        return lo or tracks
    # balanced (default) — prefer 30-70, fall back to all
    mid = [t for t in tracks if 30 <= t.get("popularity", 50) <= 70]
    return mid or tracks

class SearchRequest(BaseModel):
    song:       str
    artist:     str
    popularity: str = "balanced"   # popular | balanced | underground

class RefreshRequest(BaseModel):
    refresh_token: str

class BlacklistAddRequest(BaseModel):
    artist: str

# ─────────────────────────────────────────────────────────────────
#  AUTH ROUTES
# ─────────────────────────────────────────────────────────────────
@app.get("/login")
def login():
    return RedirectResponse("https://accounts.spotify.com/authorize?" + urlencode({
        "response_type": "code", "client_id": SPOTIFY_CLIENT_ID,
        "scope": SCOPES, "redirect_uri": REDIRECT_URI,
        "state": secrets.token_urlsafe(16), "show_dialog": "false",
    }))

@app.get("/callback")
def callback(code: str = Query(None), error: str = Query(None)):
    if error or not code:
        return RedirectResponse(f"/?auth_error={error or 'no_code'}")
    try:
        tok = exchange_code(code)
        return RedirectResponse(f"/#at={tok['access_token']}&rt={tok.get('refresh_token','')}&exp={tok.get('expires_in',3600)}")
    except Exception:
        return RedirectResponse("/?auth_error=token_exchange_failed")

@app.post("/api/refresh")
def api_refresh(req: RefreshRequest):
    try:
        d = do_refresh(req.refresh_token)
        return {"access_token": d["access_token"], "expires_in": d.get("expires_in", 3600),
                "refresh_token": d.get("refresh_token", req.refresh_token)}
    except Exception:
        raise HTTPException(401, "Token refresh failed.")

# ─────────────────────────────────────────────────────────────────
#  BLACKLIST ROUTES
# ─────────────────────────────────────────────────────────────────
@app.get("/api/blacklist")
def get_blacklist():   return {"blacklist": sorted(_blacklist)}

@app.post("/api/blacklist")
def add_blacklist(req: BlacklistAddRequest):
    n = req.artist.strip()
    if not n: raise HTTPException(400, "Empty name.")
    _blacklist.add(n.lower())
    return {"blacklist": sorted(_blacklist), "added": n}

@app.delete("/api/blacklist")
def del_blacklist(artist: str = Query(...)):
    _blacklist.discard(artist.strip().lower())
    return {"blacklist": sorted(_blacklist)}

# ─────────────────────────────────────────────────────────────────
#  VIEWS
# ─────────────────────────────────────────────────────────────────
@app.get("/api/views")
def get_views():  return {"views": _view_count}

@app.post("/api/views/increment")
def inc_views():
    global _view_count; _view_count += 1; return {"views": _view_count}

# ─────────────────────────────────────────────────────────────────
#  RECOMMEND  — 2 Spotify calls max, bucket chosen before any call
# ─────────────────────────────────────────────────────────────────
@app.post("/api/recommend")
def recommend(req: SearchRequest):
    # 1. Find seed (1 call, cached after first time)
    seed = find_seed(req.song.strip(), req.artist.strip())
    if not seed:
        raise HTTPException(404,
            f"Couldn't find '{req.song}' by '{req.artist}'. Check the spelling and try again.")

    seed_id   = seed["id"]
    seed_year = int(seed["album"]["release_date"][:4])
    artist_nm = seed["artists"][0]["name"]

    # 2. Choose bucket type randomly — NO API calls yet
    bucket = random.choice(["artist", "artist", "year"])  # artist weighted 2:1

    # 3. Fetch ONLY that bucket (1 call, cached)
    if bucket == "artist":
        pool   = artist_pool(artist_nm, seed_id)
        reason = "Same Artist"
    else:
        pool   = year_pool(seed_year, seed_id)
        reason = "Same Year"

    # 4. Fallback: if chosen bucket empty, try the other
    if not pool:
        if bucket == "artist":
            pool = year_pool(seed_year, seed_id); reason = "Same Year"
        else:
            pool = artist_pool(artist_nm, seed_id); reason = "Same Artist"

    if not pool:
        raise HTTPException(404, "No recommendations found. Try a different song.")

    pick = random.choice(popularity_filter(pool, req.popularity))
    return {
        "seed":           fmt(seed),
        "recommendation": {**fmt(pick), "match_reason": reason},
    }

# ─────────────────────────────────────────────────────────────────
#  STATIC
# ─────────────────────────────────────────────────────────────────
@app.get("/")
def index():  return FileResponse("index.html")

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    if full_path.startswith(("api/", "login", "callback")): raise HTTPException(404)
    return FileResponse("index.html")
