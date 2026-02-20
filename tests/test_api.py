import unittest
from unittest.mock import MagicMock, patch

from ai_year_wise_dj.api import TrackSearchRequest, search_and_get_transitions


class ApiSearchTests(unittest.TestCase):
    def test_search_uses_song_artist_genre_and_exact_year(self) -> None:
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
        fake_spotify.artist = MagicMock(return_value={"genres": ["pop"]})

        request = TrackSearchRequest(track_name="Seed Song", artist_name="Seed Artist", genre="pop", year=2021, limit=20)
        with patch("ai_year_wise_dj.api.get_spotify_client", return_value=fake_spotify):
            response = search_and_get_transitions(request)

        self.assertEqual(response.starting_track.year, 2021)
        self.assertEqual(response.starting_track.genres, ["pop"])
        first_query = fake_spotify.search.call_args_list[0].kwargs["q"]
        second_query = fake_spotify.search.call_args_list[1].kwargs["q"]
        self.assertIn("track:Seed Song", first_query)
        self.assertIn("artist:Seed Artist", first_query)
        self.assertIn('genre:"pop"', first_query)
        self.assertIn("year:2021", first_query)
        self.assertIn('genre:"pop"', second_query)
        self.assertIn("year:2021", second_query)
        self.assertNotIn("-", first_query)
        self.assertNotIn("-", second_query)

    def test_fallback_query_uses_exact_year_only(self) -> None:
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
            {"tracks": {"items": []}},
        ])
        fake_spotify.artist = MagicMock(return_value={"genres": ["pop"]})

        request = TrackSearchRequest(track_name="Seed Song", artist_name="Seed Artist", genre="pop", year=2021, limit=20)
        with patch("ai_year_wise_dj.api.get_spotify_client", return_value=fake_spotify):
            search_and_get_transitions(request)

        fallback_query = fake_spotify.search.call_args_list[2].kwargs["q"]
        self.assertEqual(fallback_query, "year:2021")

    def test_year_and_genre_are_derived_from_starting_song_metadata(self) -> None:
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
            {"tracks": {"items": []}},
        ])
        fake_spotify.artist = MagicMock(return_value={"genres": ["rock"]})

        request = TrackSearchRequest(track_name="Seed Song", artist_name="Seed Artist", limit=20)
        with patch("ai_year_wise_dj.api.get_spotify_client", return_value=fake_spotify):
            response = search_and_get_transitions(request)

        first_query = fake_spotify.search.call_args_list[0].kwargs["q"]
        second_query = fake_spotify.search.call_args_list[1].kwargs["q"]
        self.assertEqual(first_query, "track:Seed Song artist:Seed Artist")
        self.assertEqual(second_query, 'genre:"rock" year:2019')
        fake_spotify.artist.assert_called_once_with("artist1")
        self.assertEqual(response.starting_track.year, 2019)
        self.assertEqual(response.starting_track.genres, ["rock"])


if __name__ == "__main__":
    unittest.main()
