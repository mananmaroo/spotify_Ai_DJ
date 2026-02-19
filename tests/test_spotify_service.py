import unittest
import warnings
from unittest.mock import MagicMock, patch

from requests.exceptions import HTTPError
from requests.models import Response

from ai_year_wise_dj.spotify_service import SpotifyService


def _make_403_http_error() -> HTTPError:
    response = Response()
    response.status_code = 403
    return HTTPError(response=response)


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

    def test_safe_audio_features_re_raises_non_403_errors(self) -> None:
        svc = _make_service()
        response = Response()
        response.status_code = 500
        svc.client.audio_features = MagicMock(side_effect=HTTPError(response=response))

        with self.assertRaises(HTTPError):
            svc._safe_audio_features("track_id_abc")

    def test_safe_audio_analysis_re_raises_non_403_errors(self) -> None:
        svc = _make_service()
        response = Response()
        response.status_code = 500
        svc.client.audio_analysis = MagicMock(side_effect=HTTPError(response=response))

        with self.assertRaises(HTTPError):
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


if __name__ == "__main__":
    unittest.main()
