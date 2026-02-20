import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from ai_year_wise_dj.api import TrackSearchRequest, search_and_get_transitions


class ApiSearchTests(unittest.TestCase):
    def test_search_uses_song_and_artist_only(self) -> None:
        fake_spotify = MagicMock()
        fake_spotify.search = MagicMock(side_effect=[
            {
                "tracks": {
                    "items": [{
                        "id": "seed1",
                        "name": "Seed Song",
                        "artists": [{"name": "Seed Artist"}],
                        "album": {"release_date": "2021-01-01"},
                        "popularity": 50,
                        "duration_ms": 200_000,
                        "preview_url": "",
                    }]
                }
            },
            {
                "tracks": {
                    "items": [{
                        "id": "cand1",
                        "name": "Candidate Song",
                        "artists": [{"name": "Candidate Artist"}],
                        "album": {"release_date": "2021-02-02"},
                        "popularity": 48,
                        "duration_ms": 198_000,
                        "preview_url": "",
                    }]
                }
            },
        ])
        request = TrackSearchRequest(track_name="Seed Song", artist_name="Seed Artist", limit=20)
        with patch("ai_year_wise_dj.api.get_spotify_client", return_value=fake_spotify):
            response = search_and_get_transitions(request)

        self.assertEqual(response.starting_track.year, 2021)
        self.assertEqual(response.starting_track.genres, [])
        first_query = fake_spotify.search.call_args_list[0].kwargs["q"]
        second_query = fake_spotify.search.call_args_list[1].kwargs["q"]
        self.assertIn("track:Seed Song", first_query)
        self.assertIn("artist:Seed Artist", first_query)
        self.assertEqual(second_query, 'artist:"Seed Artist"')
        self.assertNotIn("genre:", first_query)
        self.assertNotIn("year:", first_query)
        self.assertNotIn("genre:", second_query)
        self.assertNotIn("year:", second_query)
        self.assertNotIn("-", first_query)
        self.assertNotIn("-", second_query)

    def test_second_query_targets_artist_only(self) -> None:
        fake_spotify = MagicMock()
        fake_spotify.search = MagicMock(side_effect=[
            {
                "tracks": {
                    "items": [{
                        "id": "seed1",
                        "name": "Seed Song",
                        "artists": [{"name": "Seed Artist"}],
                        "album": {"release_date": "2021-01-01"},
                        "popularity": 50,
                        "duration_ms": 200_000,
                        "preview_url": "",
                    }]
                }
            },
            {"tracks": {"items": []}},
        ])

        request = TrackSearchRequest(track_name="Seed Song", artist_name="Seed Artist", limit=20)
        with patch("ai_year_wise_dj.api.get_spotify_client", return_value=fake_spotify):
            search_and_get_transitions(request)

        second_query = fake_spotify.search.call_args_list[1].kwargs["q"]
        self.assertEqual(second_query, 'artist:"Seed Artist"')

    def test_no_genre_derivation_from_starting_song_metadata(self) -> None:
        fake_spotify = MagicMock()
        fake_spotify.search = MagicMock(side_effect=[
            {
                "tracks": {
                    "items": [{
                        "id": "seed1",
                        "name": "Seed Song",
                        "artists": [{"id": "artist1", "name": "Seed Artist"}],
                        "album": {"release_date": "2019-03-03"},
                        "popularity": 50,
                        "duration_ms": 200_000,
                        "preview_url": "",
                    }]
                }
            },
            {"tracks": {"items": []}},
        ])

        request = TrackSearchRequest(track_name="Seed Song", artist_name="Seed Artist", limit=20)
        with patch("ai_year_wise_dj.api.get_spotify_client", return_value=fake_spotify):
            response = search_and_get_transitions(request)

        first_query = fake_spotify.search.call_args_list[0].kwargs["q"]
        second_query = fake_spotify.search.call_args_list[1].kwargs["q"]
        self.assertEqual(first_query, "track:Seed Song artist:Seed Artist")
        self.assertEqual(second_query, 'artist:"Seed Artist"')
        self.assertEqual(response.starting_track.year, 2019)
        self.assertEqual(response.starting_track.genres, [])

    def test_returns_422_when_starting_track_release_year_is_invalid(self) -> None:
        fake_spotify = MagicMock()
        fake_spotify.search = MagicMock(return_value={
            "tracks": {
                "items": [{
                    "id": "seed1",
                    "name": "Seed Song",
                    "artists": [{"name": "Seed Artist"}],
                    "album": {"release_date": "unknown"},
                    "popularity": 50,
                    "duration_ms": 200_000,
                    "preview_url": "",
                }]
            }
        })

        request = TrackSearchRequest(track_name="Seed Song", artist_name="Seed Artist", limit=20)
        with patch("ai_year_wise_dj.api.get_spotify_client", return_value=fake_spotify):
            with self.assertRaises(HTTPException) as exc:
                search_and_get_transitions(request)

        self.assertEqual(exc.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
