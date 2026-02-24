import os
import base64
import requests
from fastapi import FastAPI
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

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# ----------- MODELS -----------

class SearchRequest(BaseModel):
    track_name: str
    artist_name: str

class NextTrackRequest(BaseModel):
    seed_track_id: str
    year: int
    window: int = 5


# ----------- SPOTIFY AUTH -----------

def get_spotify_token():
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

    url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": f"Basic {auth_base64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}

    result = requests.post(url, headers=headers, data=data)
    json_result = result.json()
    return json_result["access_token"]


# ----------- SEARCH TRACK -----------

@app.post("/api/search")
def search_track(req: SearchRequest):
    token = get_spotify_token()

    query = f"track:{req.track_name} artist:{req.artist_name}"
    url = f"https://api.spotify.com/v1/search?q={query}&type=track&limit=1"

    headers = {"Authorization": f"Bearer {token}"}
    result = requests.get(url, headers=headers)
    data = result.json()

    if not data["tracks"]["items"]:
        return {"error": "Track not found"}

    track = data["tracks"]["items"][0]

    # Return SAFE cleaned object (no genres anywhere)
    return {
        "id": track["id"],
        "name": track["name"],
        "album": {
            "release_date": track["album"]["release_date"]
        },
        "artists": [
            {
                "id": artist["id"],
                "name": artist["name"]
            }
            for artist in track["artists"]
        ],
        "popularity": track["popularity"],
        "duration_ms": track["duration_ms"]
    }


# ----------- NEXT TRACK -----------

@app.post("/api/next-track")
def get_next_track(req: NextTrackRequest):
    token = get_spotify_token()

    min_year = req.year - req.window
    max_year = req.year + req.window

    url = (
        f"https://api.spotify.com/v1/recommendations?"
        f"seed_tracks={req.seed_track_id}"
        f"&min_popularity=20"
        f"&limit=10"
    )

    headers = {"Authorization": f"Bearer {token}"}
    result = requests.get(url, headers=headers)
    data = result.json()

    if not data["tracks"]:
        return {"error": "No recommendations found"}

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
        return {"error": "No tracks in year window"}

    best_track = sorted(candidates, key=lambda x: x["score"], reverse=True)[0]

    return {
        "next_track_id": best_track["id"],
        "name": best_track["name"],
        "artists": best_track["artists"],
        "year": best_track["year"],
        "score": best_track["score"],
        "reason": "Closest year match for smooth transition"
    }
