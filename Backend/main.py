import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from spotify_service import SpotifyService
from analysis import build_track_fingerprint
from matcher import best_transition

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_token_from_header(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing access token")
    return auth.split(" ")[1]


@app.post("/next-track")
async def next_track(request: Request):
    body = await request.json()
    seed_track_id = body.get("seed_track_id")
    year = body.get("year", 2018)
    window = body.get("window", 5)

    token = get_token_from_header(request)
    service = SpotifyService(token)

    seed_track = service.hydrate_track(seed_track_id)
    seed_analysis = service.get_audio_analysis(seed_track_id)

    seed_fp = build_track_fingerprint(
        seed_track,
        audio_analysis=seed_analysis,
    )

    recs = service.get_recommendations(seed_track_id)

    fingerprints = []
    for track in recs:
        analysis = service.get_audio_analysis(track["id"])
        fp = build_track_fingerprint(track, audio_analysis=analysis)
        fingerprints.append(fp)

    match = best_transition(seed_fp, fingerprints, year, window)

    if not match:
        raise HTTPException(status_code=404, detail="No match found")

    return {
        "next_track_id": match.to_track_id,
        "score": match.score,
        "reason": match.reason,
    }
