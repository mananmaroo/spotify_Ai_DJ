import os
import base64
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SPOTIFY_CLIENT_ID = os.getenv("1924460439a14115b48fc7d3d03e2e2a")
SPOTIFY_CLIENT_SECRET = os.getenv("95a349e198c248448ed7e8ad1029410e")


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
# SPOTIFY AUTH (SAFE)
# =============================

def get_spotify_token():
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Spotify credentials not set")

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

    if not data.get("tracks", {}).get("items"):
        raise HTTPException(status_code=404, detail="Track not found")

    track = data["tracks"]["items"][0]

    return {
        "id": track["id"],
        "name": track["name"],
        "album": {
            "release_date": track["album"]["release_date"]
        },
        "artists": [
            {"id": a["id"], "name": a["name"]}
            for a in track["artists"]
        ],
        "popularity": track["popularity"],
        "duration_ms": track["duration_ms"]
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
        params={
            "seed_tracks": req.seed_track_id,
            "limit": 10,
            "min_popularity": 20,
        },
    )

    data = response.json()

    if not data.get("tracks"):
        raise HTTPException(status_code=404, detail="No recommendations found")

    min_year = req.year - req.window
    max_year = req.year + req.window

    candidates = []

    for track in data["tracks"]:
        release_year = int(track["album"]["release_date"][:4])

        if min_year <= release_year <= max_year:
            score = 100 - abs(req.year - release_year)

            candidates.append({
                "id": track["id"],
                "name": track["name"],
                "artists": [a["name"] for a in track["artists"]],
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
