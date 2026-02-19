import os
import tempfile
import unittest
from pathlib import Path

from ai_year_wise_dj.config import load_local_env_file


class ConfigTests(unittest.TestCase):
    def test_load_local_env_file_loads_missing_values_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                """
# comment
SPOTIPY_CLIENT_ID=test-id
SPOTIPY_CLIENT_SECRET=test-secret
KEEP_ME=from_file
                """.strip(),
                encoding="utf-8",
            )

            original_keep = os.environ.get("KEEP_ME")
            os.environ["KEEP_ME"] = "existing"
            os.environ.pop("SPOTIPY_CLIENT_ID", None)
            os.environ.pop("SPOTIPY_CLIENT_SECRET", None)
            try:
                load_local_env_file(str(env_path))
                self.assertEqual(os.environ.get("SPOTIPY_CLIENT_ID"), "test-id")
                self.assertEqual(os.environ.get("SPOTIPY_CLIENT_SECRET"), "test-secret")
                self.assertEqual(os.environ.get("KEEP_ME"), "existing")
            finally:
                os.environ.pop("SPOTIPY_CLIENT_ID", None)
                os.environ.pop("SPOTIPY_CLIENT_SECRET", None)
                if original_keep is None:
                    os.environ.pop("KEEP_ME", None)
                else:
                    os.environ["KEEP_ME"] = original_keep


if __name__ == "__main__":
    unittest.main()
