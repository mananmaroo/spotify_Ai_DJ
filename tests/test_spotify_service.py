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
    def test_safe_audio_features_returns_empty_dict_on_403(self) -> None:
        svc = _make_service()
        svc.client.audio_features = MagicMock(side_effect=_make_403_http_error())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc._safe_audio_features("track_id_abc")

        self.assertEqual(result, {})
        self.assertEqual(len(caught), 1)
        self.assertIn("audio-features", str(caught[0].message))
        self.assertIn("403", str(caught[0].message))

    def test_safe_audio_features_returns_empty_dict_on_403_spotify_exception(self) -> None:
        svc = _make_service()
        svc.client.audio_features = MagicMock(side_effect=_make_403_spotify_exception())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc._safe_audio_features("track_id_abc")

        self.assertEqual(result, {})
        self.assertEqual(len(caught), 1)
        self.assertIn("audio-features", str(caught[0].message))
        self.assertIn("403", str(caught[0].message))

    def test_safe_audio_analysis_returns_empty_dict_on_403(self) -> None:
        svc = _make_service()
        svc.client.audio_analysis = MagicMock(side_effect=_make_403_http_error())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc._safe_audio_analysis("track_id_abc")

        self.assertEqual(result, {})
        self.assertEqual(len(caught), 1)
        self.assertIn("audio-analysis", str(caught[0].message))
        self.assertIn("403", str(caught[0].message))

    def test_safe_audio_analysis_returns_empty_dict_on_403_spotify_exception(self) -> None:
        svc = _make_service()
        svc.client.audio_analysis = MagicMock(side_effect=_make_403_spotify_exception())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc._safe_audio_analysis("track_id_abc")

        self.assertEqual(result, {})
        self.assertEqual(len(caught), 1)
        self.assertIn("audio-analysis", str(caught[0].message))
        self.assertIn("403", str(caught[0].message))

    def test_safe_audio_features_re_raises_non_403_errors(self) -> None:
        svc = _make_service()
        response = Response()
        response.status_code = 500
        svc.client.audio_features = MagicMock(side_effect=HTTPError(response=response))

        with self.assertRaises(HTTPError):
            svc._safe_audio_features("track_id_abc")

    def test_safe_audio_features_re_raises_non_403_spotify_exception(self) -> None:
        svc = _make_service()
        svc.client.audio_features = MagicMock(
            side_effect=SpotifyException(http_status=500, code=-1, msg="server error")
        )

        with self.assertRaises(SpotifyException):
            svc._safe_audio_features("track_id_abc")

    def test_safe_audio_analysis_re_raises_non_403_errors(self) -> None:
        svc = _make_service()
        response = Response()
        response.status_code = 500
        svc.client.audio_analysis = MagicMock(side_effect=HTTPError(response=response))

        with self.assertRaises(HTTPError):
            svc._safe_audio_analysis("track_id_abc")

    def test_safe_audio_analysis_re_raises_non_403_spotify_exception(self) -> None:
        svc = _make_service()
        svc.client.audio_analysis = MagicMock(
            side_effect=SpotifyException(http_status=500, code=-1, msg="server error")
        )

        with self.assertRaises(SpotifyException):
            svc._safe_audio_analysis("track_id_abc")

    def test_hydrate_track_returns_empty_dicts_when_both_endpoints_are_403(self) -> None:
        svc = _make_service()
        fake_track = {"id": "t1", "name": "Song", "artists": [], "album": {"release_date": "2020-01-01"}}
        svc.client.track = MagicMock(return_value=fake_track)
        svc.client.audio_features = MagicMock(side_effect=_make_403_http_error())
        svc.client.audio_analysis = MagicMock(side_effect=_make_403_http_error())

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            track, features, analysis = svc.hydrate_track("t1")

        self.assertEqual(track, fake_track)
        self.assertEqual(features, {})
        self.assertEqual(analysis, {})

    def test_hydrate_track_returns_empty_dicts_when_both_endpoints_raise_spotify_exception_403(self) -> None:
        svc = _make_service()
        fake_track = {"id": "t1", "name": "Song", "artists": [], "album": {"release_date": "2020-01-01"}}
        svc.client.track = MagicMock(return_value=fake_track)
        svc.client.audio_features = MagicMock(side_effect=_make_403_spotify_exception())
        svc.client.audio_analysis = MagicMock(side_effect=_make_403_spotify_exception())

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            track, features, analysis = svc.hydrate_track("t1")

        self.assertEqual(track, fake_track)
        self.assertEqual(features, {})
        self.assertEqual(analysis, {})


class SearchTracksTests(unittest.TestCase):
    def test_search_uses_page_limit_at_most_20(self) -> None:
        """Each search page must request no more than _SEARCH_PAGE_LIMIT results."""
        svc = _make_service()
        svc.client.search = MagicMock(return_value={"tracks": {"items": []}})

        svc.search_tracks_by_year_window(year=2020, window=5, limit=50)

        call_args = svc.client.search.call_args
        called_limit = call_args.kwargs.get("limit") or (call_args.args[1] if len(call_args.args) > 1 else None)
        self.assertIsNotNone(called_limit)
        self.assertLessEqual(called_limit, SpotifyService._SEARCH_PAGE_LIMIT)

    def test_search_passes_market_parameter(self) -> None:
        """search calls must include a non-None market to avoid Spotify 400 errors."""
        svc = _make_service()
        svc.client.search = MagicMock(return_value={"tracks": {"items": []}})

        svc.search_tracks_by_year_window(year=2020, window=5, limit=20)

        call_args = svc.client.search.call_args
        called_market = call_args.kwargs.get("market")
        self.assertIsNotNone(called_market)
        self.assertIsInstance(called_market, str)
        self.assertGreater(len(called_market), 0)

    def test_find_starting_track_passes_market_parameter(self) -> None:
        """find_starting_track must pass a non-None market to avoid Spotify 400 errors."""
        svc = _make_service()
        fake_track = {"id": "t1", "name": "Song"}
        svc.client.search = MagicMock(return_value={"tracks": {"items": [fake_track]}})

        svc.find_starting_track("Song", year=2020)

        call_args = svc.client.search.call_args
        called_market = call_args.kwargs.get("market")
        self.assertIsNotNone(called_market)
        self.assertIsInstance(called_market, str)
        self.assertGreater(len(called_market), 0)

    def test_search_returns_empty_list_on_400_http_error(self) -> None:
        svc = _make_service()
        svc.client.search = MagicMock(side_effect=_make_400_http_error())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc.search_tracks_by_year_window(year=2020, window=5, limit=25)

        self.assertEqual(result, [])
        self.assertEqual(len(caught), 1)
        self.assertIn("400", str(caught[0].message))

    def test_search_returns_empty_list_on_400_spotify_exception(self) -> None:
        svc = _make_service()
        svc.client.search = MagicMock(side_effect=_make_400_spotify_exception())

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc.search_tracks_by_year_window(year=2020, window=5, limit=25)

        self.assertEqual(result, [])
        self.assertEqual(len(caught), 1)
        self.assertIn("400", str(caught[0].message))

    def test_search_returns_collected_tracks_on_later_page_400(self) -> None:
        """If the first page succeeds but a later page hits 400, return what was collected."""
        svc = _make_service()
        first_page = {"tracks": {"items": [{"id": f"t{i}"} for i in range(SpotifyService._SEARCH_PAGE_LIMIT)]}}
        svc.client.search = MagicMock(side_effect=[first_page, _make_400_spotify_exception()])

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = svc.search_tracks_by_year_window(year=2020, window=5, limit=40)

        self.assertEqual(len(result), 20)
        self.assertEqual(len(caught), 1)

    def test_search_re_raises_non_400_errors(self) -> None:
        svc = _make_service()
        response = Response()
        response.status_code = 500
        svc.client.search = MagicMock(side_effect=HTTPError(response=response))

        with self.assertRaises(HTTPError):
            svc.search_tracks_by_year_window(year=2020, window=5, limit=25)


if __name__ == "__main__":
    unittest.main()
