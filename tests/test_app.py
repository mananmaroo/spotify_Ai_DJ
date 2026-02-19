import argparse
import os
import unittest

from ai_year_wise_dj.app import _env_int, resolve_seed_track_id


class _FakeService:
    def __init__(self, track: dict | None) -> None:
        self._track = track

    def find_starting_track(self, query_text: str, year: int, window: int = 5) -> dict | None:
        _ = (query_text, year, window)
        return self._track


class AppTests(unittest.TestCase):
    def test_resolve_seed_track_id_prefers_direct_id(self) -> None:
        args = argparse.Namespace(seed_track_id="abc123", seed_query=None, year=2018, window=5)
        resolved = resolve_seed_track_id(args, _FakeService(track=None))
        self.assertEqual(resolved, "abc123")

    def test_resolve_seed_track_id_uses_query_result(self) -> None:
        args = argparse.Namespace(seed_track_id=None, seed_query="blinding lights", year=2020, window=5)
        fake_track = {"id": "xyz789", "name": "Track", "artists": [{"name": "Artist"}]}
        resolved = resolve_seed_track_id(args, _FakeService(track=fake_track))
        self.assertEqual(resolved, "xyz789")

    def test_resolve_seed_track_id_raises_when_query_not_found(self) -> None:
        args = argparse.Namespace(seed_track_id=None, seed_query="missing", year=2020, window=5)
        with self.assertRaises(ValueError):
            resolve_seed_track_id(args, _FakeService(track=None))

    def test_env_int_uses_fallback_for_empty_and_invalid(self) -> None:
        original = os.environ.get("TARGET_YEAR")
        try:
            os.environ["TARGET_YEAR"] = ""
            self.assertEqual(_env_int("TARGET_YEAR", 2018), 2018)
            os.environ["TARGET_YEAR"] = "not-a-number"
            self.assertEqual(_env_int("TARGET_YEAR", 2018), 2018)
            os.environ["TARGET_YEAR"] = "2021"
            self.assertEqual(_env_int("TARGET_YEAR", 2018), 2021)
        finally:
            if original is None:
                os.environ.pop("TARGET_YEAR", None)
            else:
                os.environ["TARGET_YEAR"] = original


if __name__ == "__main__":
    unittest.main()
