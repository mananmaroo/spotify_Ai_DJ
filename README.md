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

