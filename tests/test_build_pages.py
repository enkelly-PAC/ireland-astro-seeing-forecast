import tempfile
import unittest
from pathlib import Path

from scripts.build_pages import build_pages


class TestBuildPages(unittest.TestCase):
    def test_builds_project_safe_frontend_with_api_configuration(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            index_path = build_pages(output, "https://forecast.example.com/")
            content = index_path.read_text(encoding="utf-8")

            self.assertIn(
                '<meta name="astro-api-base" '
                'content="https://forecast.example.com">',
                content,
            )
            self.assertIn(
                '<meta name="astro-hosting-mode" content="pages">',
                content,
            )
            self.assertIn('src="assets/seeing-moon-clavius.webp', content)
            self.assertNotIn('src="/assets/', content)
            self.assertTrue((output / ".nojekyll").exists())
            self.assertTrue((output / "assets" / "planet-saturn.webp").exists())

    def test_rejects_non_https_public_api(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "must use HTTPS"):
                build_pages(Path(temporary_directory), "http://example.com")


if __name__ == "__main__":
    unittest.main()
