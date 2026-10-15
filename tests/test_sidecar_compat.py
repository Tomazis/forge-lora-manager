import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lora_manager.assets import is_weight_url
from lora_manager.metadata import load_record, merge_api, save_record


class SidecarCompatTests(unittest.TestCase):
    def test_forge_extra_networks_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = os.path.join(tmp, "style.safetensors")
            open(model, "wb").write(b"x")
            rec = merge_api(load_record(model), {"id": 9, "baseModel": "Pony", "trainedWords": ["tok"]})
            save_record(rec)
            with open(os.path.splitext(model)[0] + ".json", encoding="utf-8") as fh:
                forge = json.load(fh)
        for key in ("activation text", "preferred weight", "notes", "sd version", "description"):
            self.assertIn(key, forge)
        self.assertEqual(forge["activation text"], "tok")

    def test_comfy_metadata_schema_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = os.path.join(tmp, "style.safetensors")
            open(model, "wb").write(b"x")
            rec = merge_api(
                load_record(model),
                {"id": 9, "modelId": 3, "baseModel": "Pony", "trainedWords": ["tok"], "model": {"name": "Style"}},
            )
            rec["sha256"] = "deadbeef"
            save_record(rec)
            with open(os.path.splitext(model)[0] + ".metadata.json", encoding="utf-8") as fh:
                comfy = json.load(fh)
        for key in ("file_name", "model_name", "file_path", "size", "sha256", "base_model", "civitai", "notes"):
            self.assertIn(key, comfy)
        self.assertEqual(comfy["civitai"]["trainedWords"], ["tok"])
        self.assertEqual(comfy["civitai"]["id"], 9)

    def test_weight_urls_are_rejected(self):
        self.assertTrue(is_weight_url("https://civitai.red/api/download/models/123"))
        self.assertTrue(is_weight_url("https://example.com/foo.safetensors"))
        self.assertFalse(is_weight_url("https://image.civitai.com/x/preview.jpeg"))


if __name__ == "__main__":
    unittest.main()
