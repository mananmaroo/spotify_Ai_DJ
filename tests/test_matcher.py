import unittest

from ai_year_wise_dj.matcher import best_transition
from ai_year_wise_dj.models import TrackFingerprint


def _make_fp(track_id: str, release_year: int, popularity: int = 50, duration_ms: int = 200_000) -> TrackFingerprint:
    return TrackFingerprint(
        track_id=track_id,
        track_name=track_id.upper(),
        artist_names=["Artist"],
        artist_ids=["artist_id"],
        release_year=release_year,
        popularity=popularity,
        duration_ms=duration_ms,
    )


class MatcherTests(unittest.TestCase):
    def test_best_transition_prefers_closer_year(self) -> None:
        current = _make_fp("a", release_year=2020, popularity=60)
        same_year = _make_fp("b", release_year=2020, popularity=62)
        diff_year = _make_fp("c", release_year=2015, popularity=62)

        result = best_transition(current, [diff_year, same_year], target_year=2020, window=2)

        self.assertIsNotNone(result)
        self.assertEqual(result.to_track_id, "b")

    def test_best_transition_prefers_closer_popularity(self) -> None:
        current = _make_fp("a", release_year=2020, popularity=50)
        close_pop = _make_fp("b", release_year=2020, popularity=52)
        far_pop = _make_fp("c", release_year=2020, popularity=10)

        result = best_transition(current, [far_pop, close_pop], target_year=2020, window=2)

        self.assertIsNotNone(result)
        self.assertEqual(result.to_track_id, "b")

    def test_best_transition_skips_same_track(self) -> None:
        current = _make_fp("a", release_year=2020)

        result = best_transition(current, [current], target_year=2020, window=2)

        self.assertIsNone(result)

    def test_best_transition_returns_none_for_empty_candidates(self) -> None:
        current = _make_fp("a", release_year=2020)
        result = best_transition(current, [], target_year=2020, window=2)
        self.assertIsNone(result)

    def test_best_transition_scores_include_reason(self) -> None:
        current = _make_fp("a", release_year=2020, popularity=50)
        candidate = _make_fp("b", release_year=2020, popularity=55)

        result = best_transition(current, [candidate], target_year=2020, window=2)

        self.assertIsNotNone(result)
        self.assertIn("popularityΔ=", result.reason)
        self.assertIn("yearΔ=", result.reason)
        self.assertIn("durationΔ=", result.reason)


if __name__ == "__main__":
    unittest.main()
