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

3. Export Spotify credentials:

```bash
export SPOTIPY_CLIENT_ID="..."
export SPOTIPY_CLIENT_SECRET="..."
```

4. Run the CLI:

```bash
python -m ai_year_wise_dj.app --seed-track-id <spotify_track_id> --year 2018 --window 5
```

## Notes

- `window` controls the year search range (`year-window` to `year+window`).
- Matching currently uses section-level energy + tempo + loudness heuristics.
- Playback control hooks are represented as interfaces/placeholders for frontend or scheduler integration.
