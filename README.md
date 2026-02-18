# AI Year-Wise DJ

Backend prototype for an **AI DJ brain** that creates smooth transitions between Spotify tracks released in the same year (or within a configurable ±year window).

## What this backend does

- Searches tracks by year window using Spotify Web API.
- Fetches audio features + audio analysis for candidate tracks.
- Builds section-level energy fingerprints from Spotify analysis.
- Finds the best transition match between the currently playing track and next candidate songs.

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -e .
```

3. Create local secrets file from the example:

```bash
cp .env.example .env
```

4. Fill `.env` with Spotify credentials (`SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET`).

5. Run the CLI:

```bash
python -m ai_year_wise_dj.app --seed-track-id <spotify_track_id> --year 2018 --window 5
```

## Notes

- `.env` is ignored by git to prevent secret leakage; only `.env.example` is tracked.
- `window` controls the year search range (`year-window` to `year+window`).
- Matching currently uses section-level energy + tempo + loudness heuristics.
- Playback control hooks are represented as interfaces/placeholders for frontend or scheduler integration.

## GitHub Actions secrets

This project already reads `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` from environment variables.
So if you add them as repository secrets, GitHub Actions can pass them in automatically.

- Workflow file: `.github/workflows/ci.yml`
- Job `test`: runs unit tests and compile checks (no secrets required).
- Job `spotify-smoke-check`: optional manual run (`workflow_dispatch`) that maps repository secrets into env vars and executes the CLI.

> Note: GitHub Pages is static hosting, so it will **not** run this Python backend by itself.
> Use GitHub Actions, a server host (Render/Railway/Fly/EC2), or a container platform for runtime execution.


## Render next steps (recommended)

Since this project is currently a CLI backend (not a web server), deploy it on Render as a **Background Worker**.

1. Push this repo to GitHub.
2. In Render, create a new service from this repo using `render.yaml`.
3. In Render environment variables, set:
   - `SPOTIPY_CLIENT_ID`
   - `SPOTIPY_CLIENT_SECRET`
   - `SEED_TRACK_ID` (a valid Spotify track ID)
   - Optional tuning vars: `TARGET_YEAR`, `YEAR_WINDOW`, `TRACK_LIMIT`
4. Deploy and check worker logs for output from `python -m ai_year_wise_dj.app ...`.

### Important
- If you need a live endpoint for a frontend, next step is to add a small API service (e.g., FastAPI) and deploy it as a **Web Service** on Render.
- `render.yaml` currently targets one-off/worker execution of the CLI matcher.
