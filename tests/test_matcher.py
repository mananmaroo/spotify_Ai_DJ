import unittest

from ai_year_wise_dj.matcher import best_transition
from ai_year_wise_dj.models import TrackFingerprint


class MatcherTests(unittest.TestCase):
    def test_best_transition_prefers_same_year_when_enabled(self) -> None:
        current = TrackFingerprint(
            track_id="a",
            track_name="A",
            artist_names=["Artist"],
            release_year=2020,
            section_energies=[0.1, 0.8],
            section_tempos=[0.2, 0.7],
            section_loudness=[0.2, 0.9],
        )

        same_year = TrackFingerprint(
            track_id="b",
            track_name="B",
            artist_names=["Artist"],
            release_year=2020,
            section_energies=[0.11, 0.81],
            section_tempos=[0.21, 0.71],
            section_loudness=[0.19, 0.89],
        )

        diff_year = TrackFingerprint(
            track_id="c",
            track_name="C",
            artist_names=["Artist"],
            release_year=2021,
            section_energies=[0.1, 0.8],
            section_tempos=[0.2, 0.7],
            section_loudness=[0.2, 0.9],
        )

        result = best_transition(current, [diff_year, same_year], enforce_same_year=True)

        self.assertIsNotNone(result)
        self.assertEqual(result.to_track_id, "b")

    def test_best_transition_can_use_cross_year_when_allowed(self) -> None:
        current = TrackFingerprint(
            track_id="a",
            track_name="A",
            artist_names=["Artist"],
            release_year=2020,
            section_energies=[0.0],
            section_tempos=[0.0],
            section_loudness=[0.0],
        )

        diff_year = TrackFingerprint(
            track_id="c",
            track_name="C",
            artist_names=["Artist"],
            release_year=2021,
            section_energies=[0.0],
            section_tempos=[0.0],
            section_loudness=[0.0],
        )

        result = best_transition(current, [diff_year], enforce_same_year=False)

        self.assertIsNotNone(result)
        self.assertEqual(result.to_track_id, "c")


if __name__ == "__main__":
    unittest.main()
