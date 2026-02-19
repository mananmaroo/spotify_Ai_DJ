from __future__ import annotations

import argparse
import os

from ai_year_wise_dj.analysis import build_track_fingerprint
from ai_year_wise_dj.config import load_local_env_file
from ai_year_wise_dj.matcher import best_transition


def _env_int(name: str, fallback: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Year-Wise DJ matcher")
    seed_group = parser.add_mutually_exclusive_group(required=True)
    seed_group.add_argument("--seed-track-id", help="Currently playing track id")
    seed_group.add_argument(
        "--seed-query",
        help="Track search text used to find a starting track automatically",
    )
    parser.add_argument(
        "--year",
        type=int,
        nargs="?",
        default=_env_int("TARGET_YEAR", 2018),
        const=_env_int("TARGET_YEAR", 2018),
        help="Target release year (defaults to TARGET_YEAR env or 2018)",
    )
    parser.add_argument(
        "--window",
        type=int,
        nargs="?",
        default=_env_int("YEAR_WINDOW", 5),
        const=_env_int("YEAR_WINDOW", 5),
        help="Year window (+/-) (defaults to YEAR_WINDOW env or 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        nargs="?",
        default=_env_int("TRACK_LIMIT", 25),
        const=_env_int("TRACK_LIMIT", 25),
        help="Number of candidate tracks (defaults to TRACK_LIMIT env or 25)",
    )
    return parser.parse_args()


def resolve_seed_track_id(args: argparse.Namespace, service: object) -> str:
    if args.seed_track_id:
        return args.seed_track_id

    seed_track = service.find_starting_track(args.seed_query, year=args.year, window=args.window)
    if not seed_track or not seed_track.get("id"):
        raise ValueError(
            "Unable to find a starting track from --seed-query. "
            "Try a more specific query or pass --seed-track-id directly."
        )

    artist_names = ", ".join(a.get("name", "") for a in seed_track.get("artists", []))
    print(f"Resolved starting track: {seed_track.get('name')} - {artist_names} ({seed_track.get('id')})")
    return seed_track["id"]


def main() -> None:
    load_local_env_file()
    args = parse_args()
    from ai_year_wise_dj.spotify_service import SpotifyService

    service = SpotifyService()

    seed_track_id = resolve_seed_track_id(args, service)
    seed_track = service.hydrate_track(seed_track_id)
    seed_fp = build_track_fingerprint(seed_track)

    # Use Spotify's recommendations API seeded with the current track, then
    # filter and score by year window, popularity gradient, and duration.
    rec_tracks = service.get_recommendations([seed_track_id], limit=args.limit)
    if not rec_tracks:
        # Fall back to year-window search when recommendations returns nothing.
        search_results = service.search_tracks_by_year_window(args.year, window=args.window, limit=args.limit)
        candidate_ids = [t["id"] for t in search_results if t.get("id")]
        rec_tracks = service.hydrate_tracks(candidate_ids)

    fingerprints = [build_track_fingerprint(t) for t in rec_tracks if t.get("id")]

    match = best_transition(seed_fp, fingerprints, target_year=args.year, window=args.window)
    if not match:
        print("No suitable transition match found.")
        return

    print("Next transition match")
    print(f"From track: {match.from_track_id}")
    print(f"To track:   {match.to_track_id}")
    print(f"Score:      {match.score:.4f}")
    print(f"Why:        {match.reason}")


if __name__ == "__main__":
    main()
