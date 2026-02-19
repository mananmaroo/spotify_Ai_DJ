import unittest
import warnings
from unittest.mock import MagicMock, patch

from requests.exceptions import HTTPError
from requests.models import Response
from spotipy.exceptions import SpotifyException

from ai_year_wise_dj.spotify_service import SpotifyService


def _make_403_http_error() -> HTTPError:
    response = Response()
    response.status_code = 403
    return HTTPError(response=response)


def _make_403_spotify_exception() -> SpotifyException:
    return SpotifyException(http_status=403, code=-1, msg="https://api.spotify.com/v1/audio-features/")


def _make_400_http_error() -> HTTPError:
    response = Response()
    response.status_code = 400
    return HTTPError(response=response)


def _make_400_spotify_exception() -> SpotifyException:
    return SpotifyException(http_status=400, code=-1, msg="https://api.spotify.com/v1/search")


def _make_service() -> SpotifyService:
    """Return a SpotifyService with a mocked spotipy client (no network calls)."""
    with patch("ai_year_wise_dj.spotify_service.SpotifyClientCredentials"), \
         patch("ai_year_wise_dj.spotify_service.spotipy.Spotify"), \
         patch.dict("os.environ", {"SPOTIPY_CLIENT_ID": "x", "SPOTIPY_CLIENT_SECRET": "y"}):
        svc = SpotifyService()
    return svc


class SpotifyServiceHydrateTests(unittest.TestCase):
    def test_hydrate_track_returns_track_dict(self) -> None:
        svc = _make_service()
        fake_track = {"id": "t1", "name": "Song", "artists": [], "album": {"release_date": "2020-01-01"}}
        svc.client.track = MagicMock(return_value=fake_track)

        track = svc.hydrate_track("t1")

        self.assertEqual(track, fake_track)

    def test_hydrate_tracks_returns_list_of_dicts(self) -> None:
        svc = _make_service()
        fake_track = {"id": "t1", "name": "Song", "artists": [], "album": {"release_date": "2020-01-01"}}
        svc.client.track = MagicMock(return_value=fake_track)

        result = svc.hydrate_tracks(["t1", "t1"])

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], fake_track)


class RecommendationsTests(unittest.TestCase):
    def test_get_recommendations_returns_tracks(self) -> None:
        svc = _make_service()
        fake_tracks = [{"id": "r1"}, {"id": "r2"}]
        svc.client.recommendations = MagicMock(return_value={"tracks": fake_tracks})

        result = svc.get_recommendations(["seed_id"], limit=20)

        self.assertEqual(result, fake_tracks)
        svc.client.recommendations.assert_called_once_with(seed_tracks=["seed_id"], limit=20)

    def test_get_recommendations_truncates_seed_to_five(self) -> None:
        svc = _make_service()
        svc.client.recommendations = MagicMock(return_value={"tracks": []})

        svc.get_recommendations(["a", "b", "c", "d", "e", "f", "g"], limit=10)

        called_seeds = svc.client.recommendations.call_args.kwargs["seed_tracks"]
        self.assertLessEqual(len(called_seeds), 5)

    def test_get_recommendations_returns_empty_list_on_error(self) -> None:
        svc = _make_service()
        svc.client.recommendations = MagicMock(side_effect=_make_403_http_error())

        result = svc.get_recommendations(["seed_id"], limit=20)

        self.assertEqual(result, [])


class SearchTracksTests(unittest.TestCase):
    def test_search_uses_page_limit_at_most_20(self) -> None:
        """Each search page must request no more than _SEARCH_PAGE_LIMIT results."""
        svc = _make_service()
        svc.client.search = MagicMock(return_value={"tracks": {"items": []}})

        svc.search_tracks_by_year_window(year=2020, window=5, limit=50)

        call_args = svc.client.search.call_args
        called_limit = call_args.kwargs.get("limit") or (call_args.args[1] if len(call_args.args) > 1 else None)
        self.assertIsNotNone(called_limit)
        self.assertLessEqual(called_limit, SpotifyService.SEARCH_PAGE_LIMIT)

    def test_search_returns_empty_list_on_400_http_error(self) -> None:
        svc = _make_service()
        svc.client.search = MagicMock(side_effect=_make_400_http_error())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc.search_tracks_by_year_window(year=2020, window=5, limit=25)

        self.assertEqual(result, [])
        self.assertGreaterEqual(len(caught), 1)
        self.assertTrue(any("400" in str(w.message) for w in caught))

    def test_search_returns_empty_list_on_400_spotify_exception(self) -> None:
        svc = _make_service()
        svc.client.search = MagicMock(side_effect=_make_400_spotify_exception())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc.search_tracks_by_year_window(year=2020, window=5, limit=25)

        self.assertEqual(result, [])
        self.assertGreaterEqual(len(caught), 1)
        self.assertTrue(any("400" in str(w.message) for w in caught))

    def test_search_returns_collected_tracks_when_some_years_fail_with_400(self) -> None:
        """If the first year succeeds but later years hit 400, return what was collected."""
        svc = _make_service()
        # year=2020, window=5 → 11 years (2015..2025)
        # per_year_limit = max(1, 40 // 11) = 3
        per_year_limit = max(1, 40 // 11)
        first_page = {"tracks": {"items": [{"id": f"t{i}"} for i in range(per_year_limit)]}}
        side_effects = [first_page] + [_make_400_spotify_exception()] * 10
        svc.client.search = MagicMock(side_effect=side_effects)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc.search_tracks_by_year_window(year=2020, window=5, limit=40)

        self.assertEqual(len(result), per_year_limit)
        self.assertGreaterEqual(len(caught), 1)
        self.assertTrue(any("400" in str(w.message) for w in caught))

    def test_search_re_raises_non_400_errors(self) -> None:
        svc = _make_service()
        response = Response()
        response.status_code = 500
        svc.client.search = MagicMock(side_effect=HTTPError(response=response))

        with self.assertRaises(HTTPError):
            svc.search_tracks_by_year_window(year=2020, window=5, limit=25)


if __name__ == "__main__":
    unittest.main()
