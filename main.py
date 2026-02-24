# main.py
from __future__ import annotations
import os
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Backend modules
from spotify_service import SpotifyService
from analysis import build_track_fingerprint
from matcher import best_transition
from models import TrackFingerprint, TransitionCandidate

app = FastAPI(title="AI Year-Wise DJ")

# -----------------------------
# CORS Middleware
# -----------------------------
# Allow all origins for now, restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your Render frontend URL in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Helper function: token from headers
# -----------------------------
def get_token_from_header(request: Request) -> str:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing access token")
    return auth.split(" ")[1]

# -----------------------------
# API: Next track transition
# -----------------------------
@app.post("/next-track")
async def next_track(request: Request):
    """
    Input JSON:
    {
        "seed_track_id": "<spotify_track_id>",
        "year": 2018,         # optional
        "window": 5           # optional
    }
    Header: Authorization: Bearer <token>
    """
    body = await request.json()
    seed_track_id = body.get("seed_track_id")
    if not seed_track_id:
        raise HTTPException(status_code=400, detail="seed_track_id is required")

    year = body.get("year", 2018)
    window = body.get("window", 5)

    # Get Spotify token
    token = get_token_from_header(request)

    # Spotify service
    service = SpotifyService(token)

    # Hydrate seed track
    seed_track = service.hydrate_track(seed_track_id)
    seed_analysis = service.get_audio_analysis(seed_track_id)

    seed_fp = build_track_fingerprint(
        seed_track,
        audio_analysis=seed_analysis,
    )

    # Get recommendations
    rec_tracks = service.get_recommendations([seed_track_id], limit=25)

    fingerprints = []
    for track in rec_tracks:
        analysis = service.get_audio_analysis(track["id"])
        fp = build_track_fingerprint(track, audio_analysis=analysis)
        fingerprints.append(fp)

    match: Optional[TransitionCandidate] = best_transition(
        seed_fp,
        fingerprints,
        target_year=year,
        window=window
    )

    if not match:
        raise HTTPException(status_code=404, detail="No suitable transition found")

    return {
        "next_track_id": match.to_track_id,
        "score": match.score,
        "reason": match.reason,
    }

# -----------------------------
# Serve React frontend (Vite build)
# -----------------------------
DIST_DIR = "dist"

if os.path.exists(DIST_DIR):
    # Serve SPA with index.html fallback
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="static")
else:
    print(f"Warning: {DIST_DIR} directory does not exist. Frontend not mounted.")

# Optional fallback route (safe)
@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    file_path = os.path.join(DIST_DIR, full_path)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    index_path = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend not built yet."}
