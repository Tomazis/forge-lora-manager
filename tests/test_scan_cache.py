import os
import tempfile
import unittest
from unittest.mock import patch

from lora_manager import scan


class ScanCacheTests(unittest.TestCase):
    def setUp(self):
        scan.invalidate_scan_cache()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        open(os.path.join(self.root, "alpha.safetensors"), "wb").close()
        os.makedirs(os.path.join(self.root, "clothes"))
        open(os.path.join(self.root, "clothes", "beta.safetensors"), "wb").close()

    def tearDown(self):
        scan.invalidate_scan_cache()
        self.tmp.cleanup()

    def test_find_lora_uses_cache_not_second_walk(self):
        with patch("lora_manager.scan.lora_roots", return_value=[self.root]):
            first = scan.find_lora("alpha.safetensors")
            self.assertIsNotNone(first)
            self.assertEqual(first["name"], "alpha")
            with patch("lora_manager.scan.os.walk", side_effect=AssertionError("walked again")):
                again = scan.find_lora("clothes/beta.safetensors")
            self.assertIsNotNone(again)
            self.assertEqual(again["name"], "beta")

    def test_invalidate_forces_rescan(self):
        with patch("lora_manager.scan.lora_roots", return_value=[self.root]):
            scan.cached_loras()
            open(os.path.join(self.root, "gamma.safetensors"), "wb").close()
            scan.invalidate_scan_cache()
            row = scan.find_lora("gamma.safetensors")
            self.assertIsNotNone(row)
            self.assertEqual(row["name"], "gamma")


if __name__ == "__main__":
    unittest.main()
