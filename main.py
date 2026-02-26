
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

Rate-limit strategy:
  - threading.Lock serialises ALL Spotify API calls (one request at a time)
  - 429 → honour Retry-After header (capped at 30s) then retry once
  - TTL cache (10 min) keyed by URL+params — repeated calls are free
  - Max 3-4 Spotify calls per /api/recommend (down from 7+)
  - 1 term per year pool (was 2-4)

Other features:
  - Preview URL scraped from Spotify embed (removed from API Nov 2024)
  - Artist blacklist (in-memory, resets on restart)
  - Popularity filter: popular / balanced / underground
  - Genre-switch toggle
  - View counter (in-memory)
"""


REDIRECT_URI          = "https://spotify-ai-dj.onrender.com/callback"

SCOPES = (
    "streaming user-read-email user-read-private "
    "user-read-playback-state user-modify-playback-state"
)

app = FastAPI()

# ──────────────────────────────────────────────────────────────────
#  IN-MEMORY STATE
# ──────────────────────────────────────────────────────────────────
_blacklist:  set = set()
_view_count: int = 0

# ──────────────────────────────────────────────────────────────────
#  RATE-LIMIT MACHINERY
# ──────────────────────────────────────────────────────────────────
_api_lock = threading.Lock()            # one Spotify call at a time
_cache: dict = {}                       # url+params → (data, expiry)
CACHE_TTL = 600                         # 10 minutes


def _cache_get(key: str):
    e = _cache.get(key)
    return e[0] if e and time.time() < e[1] else None


def _cache_set(key: str, val):
    _cache[key] = (val, time.time() + CACHE_TTL)


# ──────────────────────────────────────────────────────────────────
#  CLIENT-CREDENTIALS TOKEN
# ──────────────────────────────────────────────────────────────────
_cc: dict = {"value": None, "expires_at": 0}


def _get_token() -> str:
    if _cc["value"] and time.time() < _cc["expires_at"] - 60:
        return _cc["value"]
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
    _cc["value"] = d["access_token"]
    _cc["expires_at"] = time.time() + d["expires_in"]
    return _cc["value"]


# ──────────────────────────────────────────────────────────────────
#  CORE HTTP HELPER — lock + cache + 429 back-off
#
#  _rate_limit_until: if we received a 429, all requests sleep until
#  this epoch passes. Shared across threads so one 429 cools everyone.
# ──────────────────────────────────────────────────────────────────
_rate_limit_until: float = 0.0


def sp_get(url: str, params: dict = None, max_retries: int = 4) -> dict:
    """
    Spotify GET with:
      - Pre-request wait if a 429 was recently received
      - Cache check (before and after acquiring lock)
      - Up to max_retries attempts; 429 → Retry-After sleep then retry;
        connection errors → short back-off then retry
    """
    global _rate_limit_until

    key = url + str(sorted((params or {}).items()))

    # Fast path: cache hit without taking the lock
    hit = _cache_get(key)
    if hit is not None:
        return hit

    with _api_lock:
        # Re-check inside lock
        hit = _cache_get(key)
        if hit is not None:
            return hit

        for attempt in range(max_retries):
            # Honour any global rate-limit cooldown
            wait_until = _rate_limit_until
            now = time.time()
            if wait_until > now:
                time.sleep(wait_until - now + 0.1)

            try:
                r = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {_get_token()}"},
                    params=params,
                    timeout=15,
                )

                if r.status_code == 429:
                    # Honour Retry-After; cap at 60s
                    retry_after = int(r.headers.get("Retry-After", "10"))
                    wait = min(retry_after, 60)
                    _rate_limit_until = time.time() + wait
                    time.sleep(wait)
                    continue  # retry same attempt counter slot

                r.raise_for_status()
                data = r.json()
                _cache_set(key, data)
                return data

            except requests.HTTPError as e:
                # Non-429 HTTP error (4xx/5xx) — retry once with small back-off
                if attempt < max_retries - 1:
                    time.sleep(1.0)
                    continue
                raise HTTPException(502, f"Spotify API error: {e}") from e

            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise HTTPException(503, f"Could not reach Spotify: {e}") from e

        raise HTTPException(429, "Spotify rate limit — please try again in a moment.")


# ──────────────────────────────────────────────────────────────────
#  PREVIEW URL SCRAPER
# ──────────────────────────────────────────────────────────────────
_preview_cache: dict = {}


def get_preview_url(track_id: str) -> Optional[str]:
    if track_id in _preview_cache:
        return _preview_cache[track_id]
    try:
        r = requests.get(
            f"https://open.spotify.com/embed/track/{track_id}",
            headers={"User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
            )},
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


# ──────────────────────────────────────────────────────────────────
#  FILTERS
# ──────────────────────────────────────────────────────────────────
MUSIC_ALBUM_TYPES = {"album", "single", "compilation"}


def _is_music(t: dict) -> bool:
    if t.get("type", "track") != "track":
        return False
    return t.get("album", {}).get("album_type", "album").lower() in MUSIC_ALBUM_TYPES


def _is_blacklisted(t: dict) -> bool:
    return any(a.get("name", "").lower() in _blacklist for a in t.get("artists", []))


def filter_tracks(tracks: list) -> list:
    return [t for t in tracks if _is_music(t) and not _is_blacklisted(t)]


def popularity_filter(tracks: list, mode: str) -> list:
    if mode == "popular":
        hi = [t for t in tracks if t.get("popularity", 0) >= 60]
        return hi or tracks
    if mode == "underground":
        lo = [t for t in tracks if t.get("popularity", 0) < 40]
        return lo or tracks
    mid = [t for t in tracks if 30 <= t.get("popularity", 50) <= 70]
    return mid or tracks


# ──────────────────────────────────────────────────────────────────
#  OAUTH
# ──────────────────────────────────────────────────────────────────
def _post_token(data: dict) -> dict:
    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data=data, timeout=15,
    )
    r.raise_for_status()
    return r.json()


def exchange_code(code: str) -> dict:
    return _post_token({"grant_type": "authorization_code",
                        "code": code, "redirect_uri": REDIRECT_URI})


def do_refresh(rt: str) -> dict:
    return _post_token({"grant_type": "refresh_token", "refresh_token": rt})


# ──────────────────────────────────────────────────────────────────
#  CATALOG HELPERS — max 3 Spotify calls per recommend request
# ──────────────────────────────────────────────────────────────────
YEAR_TERMS = ["the", "love", "night", "feel", "time", "new", "life", "way"]


def search_track(song: str, artist: str) -> Optional[dict]:
    """
    Find seed track. Tries progressively looser queries so real songs
    like 'The Hills' by 'The Weeknd' are always found.
    """
    queries = [
        f"{song} {artist}",                   # plain: most permissive, works best
        f"track:{song} artist:{artist}",       # strict field syntax fallback
        song,                                  # song name only if artist spelling is off
    ]
    for q in queries:
        try:
            d = sp_get("https://api.spotify.com/v1/search", {
                "q": q, "type": "track", "limit": 5,
            })
            items = d.get("tracks", {}).get("items", [])
            if not items:
                continue
            # Pick best match: prefer exact artist name match, else first result
            artist_lower = artist.lower()
            for item in items:
                names = [a["name"].lower() for a in item.get("artists", [])]
                if any(artist_lower in n or n in artist_lower for n in names):
                    return item
            return items[0]   # fallback: return first result
        except Exception:
            continue
    return None


def _artist_pool(artist_name: str, exclude_id: str) -> list:
    """1 API call — get artist's tracks via search."""
    try:
        d = sp_get("https://api.spotify.com/v1/search", {
            "q": f"artist:{artist_name}", "type": "track", "limit": 10,
        })
        return [t for t in d.get("tracks", {}).get("items", [])
                if t["id"] != exclude_id]
    except Exception:
        return []


def _year_pool(year: int, exclude_id: str) -> list:
    """1 API call — random term in given year."""
    term = random.choice(YEAR_TERMS)
    try:
        d = sp_get("https://api.spotify.com/v1/search", {
            "q": f"{term} year:{year}", "type": "track", "limit": 10,
        })
        return [t for t in d.get("tracks", {}).get("items", [])
                if t["id"] != exclude_id]
    except Exception:
        return []


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
        "popularity":  t.get("popularity", 0),
    }


# ──────────────────────────────────────────────────────────────────
#  MODELS
# ──────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    song:         str
    artist:       str
    popularity:   str  = "balanced"
    genre_switch: bool = True


class RefreshRequest(BaseModel):
    refresh_token: str


class BlacklistAddRequest(BaseModel):
    artist: str


# ──────────────────────────────────────────────────────────────────
#  ROUTES — Auth
# ──────────────────────────────────────────────────────────────────
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
            f"&rt={tok.get('refresh_token','')}"
            f"&exp={tok.get('expires_in', 3600)}"
        )
    except Exception:
        return RedirectResponse("/?auth_error=token_exchange_failed")


@app.post("/api/refresh")
def api_refresh(req: RefreshRequest):
    try:
        d = do_refresh(req.refresh_token)
        return {"access_token":  d["access_token"],
                "expires_in":    d.get("expires_in", 3600),
                "refresh_token": d.get("refresh_token", req.refresh_token)}
    except Exception:
        raise HTTPException(401, "Token refresh failed.")


# ──────────────────────────────────────────────────────────────────
#  ROUTES — Blacklist
# ──────────────────────────────────────────────────────────────────
@app.get("/api/blacklist")
def get_blacklist():
    return {"blacklist": sorted(_blacklist)}


@app.post("/api/blacklist")
def add_blacklist(req: BlacklistAddRequest):
    name = req.artist.strip()
    if not name:
        raise HTTPException(400, "Artist name cannot be empty.")
    _blacklist.add(name.lower())
    return {"blacklist": sorted(_blacklist), "added": name}


@app.delete("/api/blacklist")
def del_blacklist(artist: str = Query(...)):
    _blacklist.discard(artist.strip().lower())
    return {"blacklist": sorted(_blacklist)}


# ──────────────────────────────────────────────────────────────────
#  ROUTES — Views
# ──────────────────────────────────────────────────────────────────
@app.get("/api/views")
def get_views():
    return {"views": _view_count}


@app.post("/api/views/increment")
def inc_views():
    global _view_count
    _view_count += 1
    return {"views": _view_count}


# ──────────────────────────────────────────────────────────────────
#  ROUTES — Recommend
#  Worst-case Spotify API calls: 3 (seed + artist + year)
#  With caching: 0-3 depending on what's already cached
# ──────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────
#  ROUTES — Recommend
#  Speed: pick bucket type FIRST, then fire exactly ONE pool call.
#  Total Spotify calls per request: 2 (seed + one pool), both cached.
# ──────────────────────────────────────────────────────────────────
@app.post("/api/recommend")
def recommend(req: SearchRequest):
    # ── 1. Seed lookup (1 call) ──────────────────────────────────
    seed = search_track(req.song.strip(), req.artist.strip())
    if not seed:
        raise HTTPException(404,
            f"Could not find '{req.song}' by '{req.artist}' on Spotify. "
            "Try checking the spelling or using the exact Spotify track name.")

    seed_year = int(seed["album"]["release_date"][:4])
    seed_id   = seed["id"]
    artist_nm = seed["artists"][0]["name"]

    # ── 2. Pick bucket type FIRST (no API calls yet) ─────────────
    if not req.genre_switch:
        # Stay on same artist — only option
        bucket_choices = ["artist", "artist", "artist", "same_year"]
    else:
        bucket_choices = ["artist", "same_year", "adj_year"]

    bucket = random.choice(bucket_choices)

    # ── 3. Fetch ONLY that one pool (1 call) ─────────────────────
    if bucket == "artist":
        pool   = filter_tracks(_artist_pool(artist_nm, seed_id))
        reason = "Same Artist"
    elif bucket == "same_year":
        pool   = filter_tracks(_year_pool(seed_year, seed_id))
        reason = "Same Year"
    else:  # adj_year
        yr     = random.choice([seed_year - 1, seed_year + 1])
        pool   = filter_tracks(_year_pool(yr, seed_id))
        reason = "±1 Year"

    # ── 4. If chosen bucket is empty, try the others in order ────
    if not pool:
        fallbacks = [
            ("artist",    lambda: filter_tracks(_artist_pool(artist_nm, seed_id)),    "Same Artist"),
            ("same_year", lambda: filter_tracks(_year_pool(seed_year, seed_id)),      "Same Year"),
            ("adj_year",  lambda: filter_tracks(_year_pool(seed_year - 1, seed_id)), "±1 Year"),
        ]
        for fb_key, fb_fn, fb_reason in fallbacks:
            if fb_key == bucket:
                continue   # already tried this one
            pool = fb_fn()
            reason = fb_reason
            if pool:
                break

    if not pool:
        raise HTTPException(404,
            "No recommendations found. Try a different song or check the blacklist.")

    # ── 5. Apply popularity filter + pick ────────────────────────
    pick = random.choice(popularity_filter(pool, req.popularity))

    return {
        "seed":           fmt(seed),
        "recommendation": {**fmt(pick), "match_reason": reason},
    }


# ──────────────────────────────────────────────────────────────────
#  STATIC
# ──────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse("index.html")


@app.get("/{full_path:path}")
def catch_all(full_path: str):
    if full_path.startswith(("api/", "login", "callback")):
        raise HTTPException(404)
    return FileResponse("index.html")
