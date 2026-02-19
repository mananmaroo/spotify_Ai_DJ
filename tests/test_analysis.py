import unittest

from ai_year_wise_dj.analysis import build_track_fingerprint


def _fake_track(track_id: str = "t1", release_date: str = "2020-01-01",
                popularity: int = 65, duration_ms: int = 210_000) -> dict:
    return {
        "id": track_id,
        "name": "Test Song",
        "artists": [{"name": "Test Artist"}],
        "album": {"release_date": release_date},
        "popularity": popularity,
        "duration_ms": duration_ms,
    }


class BuildTrackFingerprintTests(unittest.TestCase):
    def test_has_audio_features_false_when_both_empty(self) -> None:
        fp = build_track_fingerprint(_fake_track(), audio_features={}, audio_analysis={})
        self.assertFalse(fp.has_audio_features)

    def test_has_audio_features_true_when_features_present(self) -> None:
        features = {"energy": 0.8, "tempo": 120.0, "loudness": -5.0}
        fp = build_track_fingerprint(_fake_track(), audio_features=features, audio_analysis={})
        self.assertTrue(fp.has_audio_features)

    def test_has_audio_features_true_when_sections_present(self) -> None:
        analysis = {"sections": [{"energy": 0.7, "tempo": 110.0, "loudness": -6.0}]}
        fp = build_track_fingerprint(_fake_track(), audio_features={}, audio_analysis=analysis)
        self.assertTrue(fp.has_audio_features)

    def test_popularity_extracted_from_track(self) -> None:
        fp = build_track_fingerprint(_fake_track(popularity=72), audio_features={}, audio_analysis={})
        self.assertEqual(fp.popularity, 72)

    def test_duration_ms_extracted_from_track(self) -> None:
        fp = build_track_fingerprint(_fake_track(duration_ms=195_000), audio_features={}, audio_analysis={})
        self.assertEqual(fp.duration_ms, 195_000)

    def test_popularity_defaults_to_zero_when_missing(self) -> None:
        track = _fake_track()
        del track["popularity"]
        fp = build_track_fingerprint(track, audio_features={}, audio_analysis={})
        self.assertEqual(fp.popularity, 0)

    def test_duration_ms_defaults_to_zero_when_missing(self) -> None:
        track = _fake_track()
        del track["duration_ms"]
        fp = build_track_fingerprint(track, audio_features={}, audio_analysis={})
        self.assertEqual(fp.duration_ms, 0)


if __name__ == "__main__":
    unittest.main()
