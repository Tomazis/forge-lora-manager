import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lora_manager.assets import _image_urls, ensure_examples, list_examples
from lora_manager.civitai import page_url


class AssetsTests(unittest.TestCase):
    def test_ensure_examples_keeps_a_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("lora_manager.assets.examples_dir_for", return_value=tmp):
                with patch("lora_manager.assets.download_bytes", side_effect=lambda url, dest: dest + ".png"):
                    items = ensure_examples("abc", [
                        {"url": "http://example/a.png", "type": "image"},
                        {"url": "http://example/b.png", "type": "image"},
                    ])
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["file"], "000.png")
            self.assertEqual(items[1]["file"], "001.png")

    def test_empty_index_falls_back_to_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "index.json"), "w", encoding="utf-8") as fh:
                fh.write("[]")
            with open(os.path.join(tmp, "000.png"), "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
            with patch("lora_manager.assets.examples_dir_for", return_value=tmp):
                items = list_examples("abc")
            self.assertEqual(items[0]["file"], "000.png")

    def test_rewrites_civitai_image_host(self):
        urls = _image_urls({"url": "https://image.civitai.com/x/uuid/original=true/1.jpeg"})
        self.assertTrue(any("image.civitai.red" in u for u in urls))

    def test_civitai_page_url_matches_comfy(self):
        self.assertEqual(page_url(123, 456), "https://civitai.red/models/123?modelVersionId=456")
        self.assertEqual(page_url(123, None), "https://civitai.red/models/123")
        self.assertEqual(page_url(None, 456), "https://civitai.red")


if __name__ == "__main__":
    unittest.main()
