import base64
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =============================
# APP SETUP
# =============================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================
# HARDCODED SPOTIFY CREDENTIALS
# ⚠️ TESTING ONLY
# =============================

SPOTIFY_CLIENT_ID = "1924460439a14115b48fc7d3d03e2e2a"
SPOTIFY_CLIENT_SECRET = "95a349e198c248448ed7e8ad1029410e"

# =============================
# MODELS
# =============================
class SearchRequest(BaseModel):
    track_name: str
    artist_name: str

class NextTrackRequest(BaseModel):
    seed_track_id: str
    year: int
    window: int = 5

# =============================
# SPOTIFY AUTH
# =============================
def get_spotify_token():
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_base64 = base64.b64encode(auth_string.encode()).decode()

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
    )

    data = response.json()
    if "access_token" not in data:
        raise HTTPException(status_code=500, detail=f"Spotify auth failed: {data}")

    return data["access_token"]

# =============================
# SEARCH TRACK
# =============================
@app.post("/api/search")
def search_track(req: SearchRequest):
    token = get_spotify_token()
    query = f"track:{req.track_name} artist:{req.artist_name}"

    response = requests.get(
        "https://api.spotify.com/v1/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "type": "track", "limit": 1},
    )

    data = response.json()
    items = data.get("tracks", {}).get("items", [])
    if not items:
        raise HTTPException(status_code=404, detail="Track not found")

    track = items[0]

    return {
        "id": track.get("id", ""),
        "name": track.get("name", "Unknown"),
        "album": {"release_date": track.get("album", {}).get("release_date", "Unknown")},
        "artists": [a.get("name", "Unknown") for a in track.get("artists", [])],
        "popularity": track.get("popularity", 0),
        "duration_ms": track.get("duration_ms", 0)
    }

# =============================
# NEXT TRACK
# =============================
@app.post("/api/next-track")
def next_track(req: NextTrackRequest):
    token = get_spotify_token()

    response = requests.get(
        "https://api.spotify.com/v1/recommendations",
        headers={"Authorization": f"Bearer {token}"},
        params={"seed_tracks": req.seed_track_id, "limit": 10},
    )

    data = response.json()
    tracks = data.get("tracks", [])
    if not tracks:
        raise HTTPException(status_code=404, detail="No recommendations found")

    # Filter by year window
    min_year = req.year - req.window
    max_year = req.year + req.window

    candidates = []
    for track in tracks:
        release_date = track.get("album", {}).get("release_date", "0")
        release_year = int(release_date[:4]) if release_date else 0

        if min_year <= release_year <= max_year:
            score = 100 - abs(req.year - release_year)
            candidates.append({
                "id": track.get("id", ""),
                "name": track.get("name", "Unknown"),
                "artists": [a.get("name", "Unknown") for a in track.get("artists", [])],
                "year": release_year,
                "score": score
            })

    if not candidates:
        raise HTTPException(status_code=404, detail="No tracks in year window")

    best = sorted(candidates, key=lambda x: x["score"], reverse=True)[0]

    return {
        "next_track_id": best["id"],
        "name": best["name"],
        "artists": best["artists"],
        "year": best["year"],
        "score": best["score"],
        "reason": "Closest year match for smooth transition"
    }

# =============================
# HEALTH CHECK
# =============================
@app.get("/")
def root():
    return {"status": "AI DJ backend running"}
