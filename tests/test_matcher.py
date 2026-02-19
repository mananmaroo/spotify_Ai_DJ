import unittest

from ai_year_wise_dj.matcher import best_transition, _metadata_score
from ai_year_wise_dj.models import TrackFingerprint


def _make_fingerprint(track_id: str, release_year: int = 2020, popularity: int = 50,
                      duration_ms: int = 210_000, has_audio_features: bool = True) -> TrackFingerprint:
    return TrackFingerprint(
        track_id=track_id,
        track_name=track_id.upper(),
        artist_names=["Artist"],
        artist_ids=["artist1"],
        release_year=release_year,
        section_energies=[0.5],
        section_tempos=[0.5],
        section_loudness=[0.5],
        popularity=popularity,
        duration_ms=duration_ms,
        has_audio_features=has_audio_features,
    )




class MatcherTests(unittest.TestCase):
    def test_best_transition_prefers_closer_year(self) -> None:
        current = _make_fingerprint("a", release_year=2020, popularity=60)
        same_year = _make_fingerprint("b", release_year=2020, popularity=62)
        diff_year = _make_fingerprint("c", release_year=2015, popularity=62)

        result = best_transition(current, [diff_year, same_year], target_year=2020, window=2)

        self.assertIsNotNone(result)
        self.assertEqual(result.to_track_id, "b")

    def test_best_transition_prefers_closer_popularity(self) -> None:
        current = _make_fingerprint("a", release_year=2020, popularity=50)
        close_pop = _make_fingerprint("b", release_year=2020, popularity=52)
        far_pop = _make_fingerprint("c", release_year=2020, popularity=10)

        result = best_transition(current, [far_pop, close_pop], target_year=2020, window=2)

        self.assertIsNotNone(result)
        self.assertEqual(result.to_track_id, "b")

    def test_best_transition_skips_same_track(self) -> None:
        current = _make_fingerprint("a", release_year=2020)

        result = best_transition(current, [current], target_year=2020, window=2)

        self.assertIsNone(result)

    def test_best_transition_returns_none_for_empty_candidates(self) -> None:
        current = _make_fingerprint("a", release_year=2020)
        result = best_transition(current, [], target_year=2020, window=2)
        self.assertIsNone(result)

    def test_best_transition_scores_include_reason(self) -> None:
        current = _make_fingerprint("a", release_year=2020, popularity=50)
        candidate = _make_fingerprint("b", release_year=2020, popularity=55)

        result = best_transition(current, [candidate], target_year=2020, window=2)

        self.assertIsNotNone(result)
        self.assertIn("popularityΔ=", result.reason)
        self.assertIn("yearΔ=", result.reason)
        self.assertIn("durationΔ=", result.reason)

    # ------------------------------------------------------------------
    # Metadata fallback tests (has_audio_features=False)
    # ------------------------------------------------------------------

    def test_metadata_score_identical_tracks_is_one(self) -> None:
        fp = _make_fingerprint("a", popularity=70, duration_ms=200_000)
        score, reason = _metadata_score(fp, fp)
        self.assertAlmostEqual(score, 1.0)
        self.assertIn("popularityΔ", reason)
        self.assertIn("durationΔ", reason)

    def test_metadata_score_decreases_with_popularity_difference(self) -> None:
        from_fp = _make_fingerprint("a", popularity=50, duration_ms=200_000)
        close = _make_fingerprint("b", popularity=55, duration_ms=200_000)
        far = _make_fingerprint("c", popularity=100, duration_ms=200_000)
        score_close, _ = _metadata_score(from_fp, close)
        score_far, _ = _metadata_score(from_fp, far)
        self.assertGreater(score_close, score_far)

    def test_best_transition_uses_metadata_when_no_audio_features(self) -> None:
        current = _make_fingerprint("seed", popularity=60, duration_ms=200_000, has_audio_features=False)
        close = _make_fingerprint("close", popularity=62, duration_ms=205_000, has_audio_features=False)
        far = _make_fingerprint("far", popularity=20, duration_ms=100_000, has_audio_features=False)

        result = best_transition(current, [far, close], enforce_same_year=False)

        self.assertIsNotNone(result)
        self.assertEqual(result.to_track_id, "close")
        self.assertIn("popularityΔ", result.reason)

    def test_best_transition_skips_candidates_without_audio_when_seed_has_audio(self) -> None:
        """When the seed has audio features, candidates without them are skipped."""
        current = _make_fingerprint("seed", has_audio_features=True)
        no_audio = _make_fingerprint("no_audio", has_audio_features=False)

        result = best_transition(current, [no_audio], enforce_same_year=False)

        self.assertIsNone(result)

    def test_best_transition_returns_none_when_only_self_in_list_no_audio(self) -> None:
        current = _make_fingerprint("seed", has_audio_features=False)
        result = best_transition(current, [current], enforce_same_year=False)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
