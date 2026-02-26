
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
Spotify DJ – FastAPI backend
- Fuzzy "song artist" search (no strict field syntax)
- 2 Spotify calls per recommendation: seed + one random pool
- Threading lock + 429 Retry-After + 10-min TTL cache
"""


REDIRECT_URI          = "https://spotify-ai-dj.onrender.com/callback"
SCOPES = (
    "streaming user-read-email user-read-private "
    "user-read-playback-state user-modify-playback-state"
)

app = FastAPI()

# ──────────────────────────────────────────────
#  STATE
# ──────────────────────────────────────────────
_blacklist:  set = set()
_view_count: int = 0

# ──────────────────────────────────────────────
#  CACHE
# ──────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL    = 600  # 10 min

def _cget(k):
    e = _cache.get(k)
    return e[0] if e and time.time() < e[1] else None

def _cset(k, v):
    _cache[k] = (v, time.time() + CACHE_TTL)

# ──────────────────────────────────────────────
#  RATE LIMIT
# ──────────────────────────────────────────────
_lock       = threading.Lock()
_hold_until = 0.0

# ──────────────────────────────────────────────
#  CLIENT CREDENTIALS TOKEN
# ──────────────────────────────────────────────
_cc = {"tok": None, "exp": 0}

def _token() -> str:
    if _cc["tok"] and time.time() < _cc["exp"] - 60:
        return _cc["tok"]
    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}"},
        data={"grant_type": "client_credentials"},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    _cc["tok"] = d["access_token"]
    _cc["exp"] = time.time() + d["expires_in"]
    return _cc["tok"]

# ──────────────────────────────────────────────
#  SPOTIFY GET — lock + cache + 429 backoff
# ──────────────────────────────────────────────
def sp_get(url: str, params: dict = None) -> dict:
    global _hold_until
    key = url + str(sorted((params or {}).items()))
    hit = _cget(key)
    if hit is not None:
        return hit

    with _lock:
        hit = _cget(key)
        if hit is not None:
            return hit

        for attempt in range(4):
            gap = _hold_until - time.time()
            if gap > 0:
                time.sleep(gap + 0.1)
            try:
                r = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {_token()}"},
                    params=params,
                    timeout=15,
                )
                if r.status_code == 429:
                    wait = min(int(r.headers.get("Retry-After", "10")), 60)
                    _hold_until = time.time() + wait
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                data = r.json()
                _cset(key, data)
                return data
            except requests.HTTPError as e:
                if attempt < 3:
                    time.sleep(1)
                    continue
                raise HTTPException(502, f"Spotify API error: {e}")
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise HTTPException(503, f"Cannot reach Spotify: {e}")

        raise HTTPException(429, "Rate limited — please try again in a moment.")

# ──────────────────────────────────────────────
#  PREVIEW URL SCRAPER
# ──────────────────────────────────────────────
_pcache: dict = {}

def get_preview(track_id: str) -> Optional[str]:
    if track_id in _pcache:
        return _pcache[track_id]
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
    _pcache[track_id] = url
    return url

# ──────────────────────────────────────────────
#  FILTERS
# ──────────────────────────────────────────────
_GOOD_TYPES = {"album", "single", "compilation"}

def _keep(t: dict) -> bool:
    if t.get("type") != "track":
        return False
    if t.get("album", {}).get("album_type", "").lower() not in _GOOD_TYPES:
        return False
    for a in t.get("artists", []):
        if a.get("name", "").lower() in _blacklist:
            return False
    return True

# ──────────────────────────────────────────────
#  OAUTH
# ──────────────────────────────────────────────
def _post_tok(data: dict) -> dict:
    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data, timeout=15,
    )
    r.raise_for_status()
    return r.json()

def exchange_code(code: str) -> dict:
    return _post_tok({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    })

def do_refresh(rt: str) -> dict:
    return _post_tok({
        "grant_type": "refresh_token",
        "refresh_token": rt,
    })

# ──────────────────────────────────────────────
#  SEARCH
# ──────────────────────────────────────────────
YEAR_TERMS = ["love", "night", "feel", "time", "new", "life", "back", "good"]

def find_seed(song: str, artist: str) -> Optional[dict]:
    """
    Plain text queries only — no Spotify field syntax.
    "Shape of You ed sheeran" works; "track:Shape of You artist:ed sheeran" often doesn't.
    """
    for q in [f"{song} {artist}", song]:
        try:
            d = sp_get("https://api.spotify.com/v1/search", {
                "q": q, "type": "track", "limit": 10, "market": "US",
            })
            items = d.get("tracks", {}).get("items", [])
            if not items:
                continue
            al = artist.lower()
            # 1. exact artist name
            for item in items:
                if any(a["name"].lower() == al for a in item.get("artists", [])):
                    return item
            # 2. partial artist name ("ed sheeran" ↔ "Ed Sheeran")
            for item in items:
                if any(al in a["name"].lower() or a["name"].lower() in al
                       for a in item.get("artists", [])):
                    return item
            # 3. song-only query: take first result
            if q == song:
                return items[0]
        except HTTPException:
            raise  # surface real errors (429, 503, etc.)
        except Exception:
            continue
    return None

def artist_pool(name: str, exclude: str) -> list:
    try:
        d = sp_get("https://api.spotify.com/v1/search", {
            "q": name, "type": "track", "limit": 10, "market": "US",
        })
        return [t for t in d.get("tracks", {}).get("items", [])
                if t["id"] != exclude and _keep(t)]
    except Exception:
        return []

def year_pool(year: int, exclude: str) -> list:
    try:
        d = sp_get("https://api.spotify.com/v1/search", {
            "q": f"{random.choice(YEAR_TERMS)} year:{year}",
            "type": "track", "limit": 10, "market": "US",
        })
        return [t for t in d.get("tracks", {}).get("items", [])
                if t["id"] != exclude and _keep(t)]
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
        "preview_url": get_preview(t["id"]),
        "spotify_url": t.get("external_urls", {}).get("spotify", ""),
        "image":       images[0]["url"] if images else "",
        "duration_ms": t.get("duration_ms", 0),
        "popularity":  t.get("popularity", 0),
    }

# ──────────────────────────────────────────────
#  MODELS
# ──────────────────────────────────────────────
class SearchReq(BaseModel):
    song:   str
    artist: str

class RefreshReq(BaseModel):
    refresh_token: str

class BLReq(BaseModel):
    artist: str

# ──────────────────────────────────────────────
#  ROUTES — auth
# ──────────────────────────────────────────────
@app.get("/login")
def login():
    return RedirectResponse(
        "https://accounts.spotify.com/authorize?" + urlencode({
            "response_type": "code",
            "client_id":     SPOTIFY_CLIENT_ID,
            "scope":         SCOPES,
            "redirect_uri":  REDIRECT_URI,
            "state":         secrets.token_urlsafe(16),
            "show_dialog":   "false",
        })
    )

@app.get("/callback")
def callback(code: str = Query(None), error: str = Query(None)):
    if error or not code:
        return RedirectResponse(f"/?auth_error={error or 'no_code'}")
    try:
        tok = exchange_code(code)
        return RedirectResponse(
            f"/#at={tok['access_token']}"
            f"&rt={tok.get('refresh_token', '')}"
            f"&exp={tok.get('expires_in', 3600)}"
        )
    except Exception:
        return RedirectResponse("/?auth_error=token_exchange_failed")

@app.post("/api/refresh")
def api_refresh(req: RefreshReq):
    try:
        d = do_refresh(req.refresh_token)
        return {
            "access_token":  d["access_token"],
            "expires_in":    d.get("expires_in", 3600),
            "refresh_token": d.get("refresh_token", req.refresh_token),
        }
    except Exception:
        raise HTTPException(401, "Token refresh failed.")

# ──────────────────────────────────────────────
#  ROUTES — blacklist
# ──────────────────────────────────────────────
@app.get("/api/blacklist")
def get_bl():
    return {"blacklist": sorted(_blacklist)}

@app.post("/api/blacklist")
def add_bl(req: BLReq):
    n = req.artist.strip()
    if not n:
        raise HTTPException(400, "Empty name.")
    _blacklist.add(n.lower())
    return {"blacklist": sorted(_blacklist)}

@app.delete("/api/blacklist")
def del_bl(artist: str = Query(...)):
    _blacklist.discard(artist.strip().lower())
    return {"blacklist": sorted(_blacklist)}

# ──────────────────────────────────────────────
#  ROUTES — views
# ──────────────────────────────────────────────
@app.get("/api/views")
def get_views():
    return {"views": _view_count}

@app.post("/api/views/increment")
def inc_views():
    global _view_count
    _view_count += 1
    return {"views": _view_count}

# ──────────────────────────────────────────────
#  ROUTES — recommend
#  Max 2 Spotify calls: seed lookup + one pool
# ──────────────────────────────────────────────
@app.post("/api/recommend")
def recommend(req: SearchReq):
    # 1. Find seed
    seed = find_seed(req.song.strip(), req.artist.strip())
    if not seed:
        raise HTTPException(
            404,
            f"Couldn't find '{req.song}' by '{req.artist}' on Spotify. "
            "Check spelling — use the song name exactly as it appears on Spotify."
        )

    seed_id   = seed["id"]
    seed_year = int(seed["album"]["release_date"][:4])
    artist_nm = seed["artists"][0]["name"]

    # 2. Pick bucket FIRST (no API call), then fetch only that one
    use_artist = random.random() < 0.6   # 60% same artist, 40% same year
    if use_artist:
        pool   = artist_pool(artist_nm, seed_id)
        reason = "Same Artist"
        if not pool:  # fallback
            pool   = year_pool(seed_year, seed_id)
            reason = "Same Year"
    else:
        pool   = year_pool(seed_year, seed_id)
        reason = "Same Year"
        if not pool:  # fallback
            pool   = artist_pool(artist_nm, seed_id)
            reason = "Same Artist"

    if not pool:
        raise HTTPException(404, "No recommendations found. Try a different song.")

    pick = random.choice(pool)
    return {
        "seed":           fmt(seed),
        "recommendation": {**fmt(pick), "match_reason": reason},
    }

# ──────────────────────────────────────────────
#  STATIC  — must come LAST
# ──────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("index.html")

@app.get("/{path:path}")
def static(path: str):
    # Only serve index for non-API paths
    if path.startswith("api/") or path in ("login", "callback"):
        raise HTTPException(404)
    return FileResponse("index.html")
