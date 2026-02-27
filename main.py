import re, random, base64, time, secrets, threading
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
from urllib.parse import urlencode

try:
    import yt_dlp as _yt_dlp
    YT_OK = True
except ImportError:
    YT_OK = False

# -----------------------------
# Spotify Credentials (hardcoded for now)
# -----------------------------
SPOTIFY_CLIENT_ID = "1924460439a14115b48fc7d3d03e2e2a"
SPOTIFY_CLIENT_SECRET = "95a349e198c248448ed7e8ad1029410e"
"""
Spotify + YouTube DJ — FastAPI backend

Rate-limit fix: token bucket limits to 2 Spotify calls/sec proactively.
Never hits 429 in normal usage. 30-min cache further reduces calls.

New features:
  - YouTube Music: search + playlist import via yt-dlp
  - Spotify playlist import
  - /api/mixer/search — unified Spotify+YouTube search
  - /api/mixer/playlist — import Spotify or YouTube playlist
"""



REDIRECT_URI          = "https://spotify-ai-dj.onrender.com/callback"
SCOPES = "streaming user-read-email user-read-private user-read-playback-state user-modify-playback-state"

app = FastAPI()

# ─────────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────────
_blacklist:  set = set()
_view_count: int = 0

# ─────────────────────────────────────────────
#  CACHE  (30-min TTL — search results don't change that fast)
# ─────────────────────────────────────────────
_cache: dict = {}
TTL = 1800

def _cget(k):
    e = _cache.get(k)
    return e[0] if e and time.time() < e[1] else None

def _cset(k, v):
    _cache[k] = (v, time.time() + TTL)

# ─────────────────────────────────────────────
#  TOKEN BUCKET — proactive 2 calls/sec limit
#  This prevents 429s before they happen.
#  Even under load we never exceed the rate.
# ─────────────────────────────────────────────
class _TBucket:
    def __init__(self, rate=2.0, cap=5):
        self.rate = rate
        self.cap  = cap
        self.tok  = float(cap)
        self.last = time.time()
        self._lk  = threading.Lock()

    def wait(self):
        with self._lk:
            now = time.time()
            self.tok = min(self.cap, self.tok + (now - self.last) * self.rate)
            self.last = now
            if self.tok >= 1:
                self.tok -= 1
                return
            sleep = (1.0 - self.tok) / self.rate
            self.tok = 0
        time.sleep(sleep)

_bucket     = _TBucket(rate=2.0, cap=5)
_api_lock   = threading.Lock()
_hold_until = 0.0

# ─────────────────────────────────────────────
#  CLIENT CREDENTIALS TOKEN
# ─────────────────────────────────────────────
_cc = {"tok": None, "exp": 0}

def _token() -> str:
    if _cc["tok"] and time.time() < _cc["exp"] - 60:
        return _cc["tok"]
    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post("https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}"},
        data={"grant_type": "client_credentials"}, timeout=15)
    r.raise_for_status()
    d = r.json()
    _cc["tok"] = d["access_token"]
    _cc["exp"]  = time.time() + d["expires_in"]
    return _cc["tok"]

# ─────────────────────────────────────────────
#  SPOTIFY GET — bucket + lock + cache + 429 backup
# ─────────────────────────────────────────────
def sp_get(url: str, params: dict = None) -> dict:
    global _hold_until
    key = url + str(sorted((params or {}).items()))
    hit = _cget(key)
    if hit is not None:
        return hit

    with _api_lock:
        hit = _cget(key)
        if hit is not None:
            return hit

        for attempt in range(4):
            _bucket.wait()                           # proactive throttle
            gap = _hold_until - time.time()
            if gap > 0:
                time.sleep(gap + 0.1)
            try:
                r = requests.get(url,
                    headers={"Authorization": f"Bearer {_token()}"},
                    params=params, timeout=15)
                if r.status_code == 429:
                    wait = min(int(r.headers.get("Retry-After", "15")), 60)
                    _hold_until = time.time() + wait
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                data = r.json()
                _cset(key, data)
                return data
            except requests.HTTPError as e:
                if attempt < 3: time.sleep(1); continue
                raise HTTPException(502, f"Spotify error: {e}")
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < 3: time.sleep(2 * (attempt + 1)); continue
                raise HTTPException(503, f"Cannot reach Spotify: {e}")

        raise HTTPException(429, "Rate limited — please try again in a moment.")

# ─────────────────────────────────────────────
#  PREVIEW SCRAPER
# ─────────────────────────────────────────────
_pcache: dict = {}

def get_preview(tid: str) -> Optional[str]:
    if tid in _pcache:
        return _pcache[tid]
    try:
        r = requests.get(f"https://open.spotify.com/embed/track/{tid}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=8)
        m = re.search(r'"audioPreview"\s*:\s*\{"url"\s*:\s*"(https://[^"]+)"', r.text)
        if not m:
            m = re.search(r'"preview_url"\s*:\s*"(https://[^"]+)"', r.text)
        url = m.group(1) if m else None
    except Exception:
        url = None
    _pcache[tid] = url
    return url

# ─────────────────────────────────────────────
#  FILTERS
# ─────────────────────────────────────────────
_GOOD = {"album", "single", "compilation"}

def _keep(t: dict) -> bool:
    if t.get("type") != "track": return False
    if t.get("album", {}).get("album_type", "").lower() not in _GOOD: return False
    return not any(a.get("name", "").lower() in _blacklist for a in t.get("artists", []))

# ─────────────────────────────────────────────
#  OAUTH
# ─────────────────────────────────────────────
def _post_tok(data: dict) -> dict:
    creds = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    r = requests.post("https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data=data, timeout=15)
    r.raise_for_status()
    return r.json()

def exchange_code(c):  return _post_tok({"grant_type": "authorization_code", "code": c, "redirect_uri": REDIRECT_URI})
def do_refresh(rt):    return _post_tok({"grant_type": "refresh_token", "refresh_token": rt})

# ─────────────────────────────────────────────
#  SPOTIFY SEARCH HELPERS
# ─────────────────────────────────────────────
YEAR_TERMS = ["love", "night", "feel", "time", "new", "life", "back", "good"]

def find_seed(song: str, artist: str) -> Optional[dict]:
    for q in [f"{song} {artist}", song]:
        try:
            d = sp_get("https://api.spotify.com/v1/search",
                       {"q": q, "type": "track", "limit": 10, "market": "US"})
            items = d.get("tracks", {}).get("items", [])
            if not items: continue
            al = artist.lower()
            for item in items:
                if any(a["name"].lower() == al for a in item.get("artists", [])):
                    return item
            for item in items:
                if any(al in a["name"].lower() or a["name"].lower() in al
                       for a in item.get("artists", [])):
                    return item
            if q == song: return items[0]
        except HTTPException: raise
        except Exception: continue
    return None

def artist_pool(name: str, excl: str) -> list:
    try:
        d = sp_get("https://api.spotify.com/v1/search",
                   {"q": name, "type": "track", "limit": 10, "market": "US"})
        return [t for t in d.get("tracks", {}).get("items", [])
                if t["id"] != excl and _keep(t)]
    except Exception:
        return []

def year_pool(yr: int, excl: str) -> list:
    try:
        d = sp_get("https://api.spotify.com/v1/search",
                   {"q": f"{random.choice(YEAR_TERMS)} year:{yr}",
                    "type": "track", "limit": 10, "market": "US"})
        return [t for t in d.get("tracks", {}).get("items", [])
                if t["id"] != excl and _keep(t)]
    except Exception:
        return []

# ─────────────────────────────────────────────
#  FORMAT HELPERS
# ─────────────────────────────────────────────
def fmt_sp(t: dict, fetch_preview: bool = True) -> dict:
    alb  = t.get("album", {})
    imgs = alb.get("images", [])
    rel  = alb.get("release_date", "")
    return {
        "source":      "spotify",
        "id":          t["id"],
        "uri":         t.get("uri") or f"spotify:track:{t['id']}",
        "name":        t["name"],
        "artist":      ", ".join(a["name"] for a in t.get("artists", [])),
        "album":       alb.get("name", ""),
        "year":        rel[:4] if rel else "?",
        "preview_url": get_preview(t["id"]) if fetch_preview else None,
        "spotify_url": t.get("external_urls", {}).get("spotify", ""),
        "image":       imgs[0]["url"] if imgs else "",
        "duration_ms": t.get("duration_ms", 0),
        "popularity":  t.get("popularity", 0),
    }

def fmt_yt(e: dict) -> dict:
    dur   = int(e.get("duration") or 0) * 1000
    thumb = ""
    if isinstance(e.get("thumbnails"), list) and e["thumbnails"]:
        thumb = e["thumbnails"][-1].get("url", "")
    elif e.get("thumbnail"):
        thumb = str(e["thumbnail"])
    return {
        "source":      "youtube",
        "id":          e.get("id", ""),
        "uri":         "",
        "name":        e.get("title", ""),
        "artist":      e.get("uploader", "") or e.get("channel", ""),
        "album":       "",
        "year":        str(e.get("release_year", "")) if e.get("release_year") else "",
        "preview_url": None,
        "youtube_url": f"https://youtube.com/watch?v={e.get('id', '')}",
        "image":       thumb,
        "duration_ms": dur,
        "popularity":  0,
    }

# ─────────────────────────────────────────────
#  YOUTUBE HELPERS
# ─────────────────────────────────────────────
def yt_search(q: str, n: int = 8) -> list:
    if not YT_OK: return []
    key = f"yts:{q}:{n}"
    hit = _cget(key)
    if hit: return hit
    try:
        opts = {
            "quiet": True, "no_warnings": True,
            "extract_flat": "in_playlist", "skip_download": True,
            "default_search": f"ytsearch{n}",
        }
        with _yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(q, download=False)
            entries = info.get("entries") or ([info] if info.get("id") else [])
            results = []
            for e in entries:
                if not e or not e.get("id"): continue
                dur = int(e.get("duration") or 0) * 1000
                thumb = ""
                tlist = e.get("thumbnails") or []
                if tlist: thumb = tlist[-1].get("url","") if isinstance(tlist[0],dict) else str(tlist[-1])
                elif e.get("thumbnail"): thumb = str(e["thumbnail"])
                results.append({
                    "source":"youtube","id":e["id"],"uri":"",
                    "name": e.get("title",""),"artist": e.get("uploader","") or e.get("channel",""),
                    "album":"","year":"","preview_url":None,
                    "youtube_url":f"https://youtube.com/watch?v={e['id']}",
                    "image":thumb,"duration_ms":dur,"popularity":0,
                })
            _cset(key, results)
            return results
    except Exception:
        return []


def yt_playlist_items(url: str) -> list:
    if not YT_OK:
        raise HTTPException(501, "yt-dlp not available on this server.")
    key = f"ytpl:{url}"
    hit = _cget(key)
    if hit: return hit
    try:
        opts = {
            "quiet": True, "no_warnings": True,
            "extract_flat": True, "skip_download": True,
        }
        with _yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get("entries") or []
            results = []
            for e in entries:
                if not e or not e.get("id"): continue
                dur = int(e.get("duration") or 0) * 1000
                thumb = ""
                tlist = e.get("thumbnails") or []
                if tlist: thumb = tlist[-1].get("url","") if isinstance(tlist[0],dict) else str(tlist[-1])
                elif e.get("thumbnail"): thumb = str(e["thumbnail"])
                results.append({
                    "source":"youtube","id":e["id"],"uri":"",
                    "name": e.get("title",""),"artist": e.get("uploader","") or e.get("channel",""),
                    "album":"","year":"","preview_url":None,
                    "youtube_url":f"https://youtube.com/watch?v={e['id']}",
                    "image":thumb,"duration_ms":dur,"popularity":0,
                })
            results = results[:300]
            _cset(key, results)
            return results
    except Exception as e:
        raise HTTPException(400, f"Could not load YouTube playlist: {e}")


def sp_playlist_items(pid: str) -> list:
    tracks = []
    url    = f"https://api.spotify.com/v1/playlists/{pid}/tracks"
    params = {"limit": 100, "market": "US"}
    while url and len(tracks) < 500:
        try:
            d = sp_get(url, params)
            params = None   # 'next' URL already has all params encoded
            for item in d.get("items", []):
                t = item.get("track")
                if t and t.get("type") == "track" and t.get("id"):
                    tracks.append(fmt_sp(t, fetch_preview=False))
            url = d.get("next")
        except Exception:
            break
    return tracks

# ─────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────
def popularity_filter(tracks: list, mode: str) -> list:
    if mode == "popular":
        hi = [t for t in tracks if t.get("popularity", 0) >= 60]
        return hi or tracks
    if mode == "underground":
        lo = [t for t in tracks if t.get("popularity", 0) < 40]
        return lo or tracks
    mid = [t for t in tracks if 30 <= t.get("popularity", 50) <= 70]
    return mid or tracks

class SearchReq(BaseModel):
    song:       str
    artist:     str
    popularity: str = "balanced"   # popular | balanced | underground

class RefreshReq(BaseModel):
    refresh_token: str

class BLReq(BaseModel):
    artist: str

class MxSearchReq(BaseModel):
    query:  str
    source: str = "both"   # spotify | youtube | both
    limit:  int = 8

class MxPlaylistReq(BaseModel):
    url: str

# ─────────────────────────────────────────────
#  ROUTES — auth
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
#  ROUTES — blacklist
# ─────────────────────────────────────────────
@app.get("/api/blacklist")
def get_bl(): return {"blacklist": sorted(_blacklist)}

@app.post("/api/blacklist")
def add_bl(req: BLReq):
    n = req.artist.strip()
    if not n: raise HTTPException(400, "Empty.")
    _blacklist.add(n.lower())
    return {"blacklist": sorted(_blacklist)}

@app.delete("/api/blacklist")
def del_bl(artist: str = Query(...)):
    _blacklist.discard(artist.strip().lower())
    return {"blacklist": sorted(_blacklist)}

# ─────────────────────────────────────────────
#  ROUTES — views
# ─────────────────────────────────────────────
@app.get("/api/views")
def get_views(): return {"views": _view_count}

@app.post("/api/views/increment")
def inc_views():
    global _view_count
    _view_count += 1
    return {"views": _view_count}

# ─────────────────────────────────────────────
#  ROUTES — AI DJ recommend
#  Max 2 Spotify calls (seed + one pool), both cached
# ─────────────────────────────────────────────
@app.post("/api/recommend")
def recommend(req: SearchReq):
    seed = find_seed(req.song.strip(), req.artist.strip())
    if not seed:
        raise HTTPException(404,
            f"Couldn't find '{req.song}' by '{req.artist}'. "
            "Use the exact title as it appears on Spotify.")

    sid = seed["id"]
    yr  = int(seed["album"]["release_date"][:4])
    nm  = seed["artists"][0]["name"]

    if random.random() < 0.6:
        pool = artist_pool(nm, sid);  reason = "Same Artist"
        if not pool: pool = year_pool(yr, sid); reason = "Same Year"
    else:
        pool = year_pool(yr, sid);    reason = "Same Year"
        if not pool: pool = artist_pool(nm, sid); reason = "Same Artist"

    if not pool:
        raise HTTPException(404, "No recommendations found. Try a different song.")

    pick = random.choice(popularity_filter(pool, req.popularity))
    return {
        "seed":           fmt_sp(seed),
        "recommendation": {**fmt_sp(pick), "match_reason": reason},
    }

# ─────────────────────────────────────────────
#  ROUTES — Mixer search
# ─────────────────────────────────────────────
@app.post("/api/mixer/search")
def mixer_search(req: MxSearchReq):
    q = req.query.strip()
    if not q: raise HTTPException(400, "Empty query.")
    results = []
    if req.source in ("spotify", "both"):
        try:
            d = sp_get("https://api.spotify.com/v1/search",
                       {"q": q, "type": "track", "limit": req.limit, "market": "US"})
            results += [fmt_sp(t) for t in d.get("tracks", {}).get("items", []) if _keep(t)]
        except Exception:
            pass
    if req.source in ("youtube", "both"):
        results += yt_search(q, req.limit)
    return {"results": results}

# ─────────────────────────────────────────────
#  ROUTES — Mixer playlist import
# ─────────────────────────────────────────────
@app.post("/api/mixer/playlist")
def mixer_playlist(req: MxPlaylistReq):
    url = req.url.strip()
    if "spotify.com/playlist/" in url:
        m = re.search(r"playlist/([A-Za-z0-9]+)", url)
        if not m: raise HTTPException(400, "Invalid Spotify playlist URL.")
        tracks = sp_playlist_items(m.group(1))
        return {"source": "spotify", "tracks": tracks, "count": len(tracks)}
    elif "youtube.com" in url or "music.youtube.com" in url:
        tracks = yt_playlist_items(url)
        return {"source": "youtube", "tracks": tracks, "count": len(tracks)}
    else:
        raise HTTPException(400, "Paste a Spotify playlist URL or a YouTube playlist URL.")

@app.get("/api/client-id")
def client_id_r(): return {"client_id": SPOTIFY_CLIENT_ID}

# ─────────────────────────────────────────────
#  STATIC — must be last
# ─────────────────────────────────────────────

@app.post("/api/yt/recommend")
def yt_recommend(req: SearchReq):
    results = yt_search(f"{req.song.strip()} {req.artist.strip()}", 8)
    if not results:
        raise HTTPException(404, f"Couldn't find \"{req.song}\" by \"{req.artist}\" on YouTube.")
    seed = results[0]
    if random.random() < 0.6:
        pool   = [t for t in yt_search(seed["artist"], 12) if t["id"] != seed["id"]]
        reason = "Same Artist"
    else:
        yr     = seed.get("year") or "2020"
        pool   = [t for t in yt_search(f"music {yr}", 12) if t["id"] != seed["id"]]
        reason = "Same Year"
    if not pool:
        raise HTTPException(404, "No YouTube recommendations found. Try a different song.")
    return {"seed": seed, "recommendation": {**random.choice(pool), "match_reason": reason}}

@app.get("/api/preview/{track_id}")
def preview_api(track_id: str):
    """Lazy preview URL fetch — called per-track when about to play."""
    return {"preview_url": get_preview(track_id)}

@app.get("/")
def index(): return FileResponse("index.html")

@app.get("/{path:path}")
def static(path: str):
    if path.startswith("api/") or path in ("login", "callback"):
        raise HTTPException(404)
    return FileResponse("index.html")
