from __future__ import annotations

import argparse

from ai_year_wise_dj.analysis import build_track_fingerprint
from ai_year_wise_dj.config import load_local_env_file
from ai_year_wise_dj.matcher import best_transition
from ai_year_wise_dj.spotify_service import SpotifyService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Year-Wise DJ matcher")
    seed_group = parser.add_mutually_exclusive_group(required=True)
    seed_group.add_argument("--seed-track-id", help="Currently playing track id")
    seed_group.add_argument(
        "--seed-query",
        help="Track search text used to find a starting track automatically",
    )
    parser.add_argument("--year", type=int, required=True, help="Target release year")
    parser.add_argument("--window", type=int, default=5, help="Year window (+/-)")
    parser.add_argument("--limit", type=int, default=25, help="Number of candidate tracks")
    parser.add_argument(
        "--allow-cross-year",
        action="store_true",
        help="Allow matching outside exact year if within window",
    )
    return parser.parse_args()


def resolve_seed_track_id(args: argparse.Namespace, service: SpotifyService) -> str:
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
    args = parse_args()
    load_local_env_file()
    service = SpotifyService()

    seed_track_id = resolve_seed_track_id(args, service)
    seed_track, seed_features, seed_analysis = service.hydrate_track(seed_track_id)
    seed_fp = build_track_fingerprint(seed_track, seed_features, seed_analysis)

    search_results = service.search_tracks_by_year_window(args.year, window=args.window, limit=args.limit)
    candidate_ids = [t["id"] for t in search_results if t.get("id")]

    hydrated = service.hydrate_tracks(candidate_ids)
    fingerprints = [build_track_fingerprint(track, features, analysis) for track, features, analysis in hydrated]

    match = best_transition(seed_fp, fingerprints, enforce_same_year=not args.allow_cross_year)
    if not match:
        print("No suitable transition match found.")
        return

    print("Next transition match")
    print(f"From track: {match.from_track_id} (section {match.from_section_index})")
    print(f"To track:   {match.to_track_id} (section {match.to_section_index})")
    print(f"Score:      {match.score:.4f}")
    print(f"Why:        {match.reason}")


if __name__ == "__main__":
    main()
