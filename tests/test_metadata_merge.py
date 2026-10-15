import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lora_manager.metadata import apply_user_edits, load_record, merge_api, normalize_words, save_record


def _touch_model(folder: str, name: str = "demo.safetensors") -> str:
    path = os.path.join(folder, name)
    with open(path, "wb") as fh:
        fh.write(b"fake")
    return path


class MetadataMergeTests(unittest.TestCase):
    def test_reads_forge_comfy_civitai_and_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _touch_model(tmp)
            stem = os.path.splitext(model)[0]
            with open(stem + ".json", "w", encoding="utf-8") as fh:
                json.dump({"activation text": "from_forge", "preferred weight": 0.7, "notes": "keep me"}, fh)
            with open(stem + ".metadata.json", "w", encoding="utf-8") as fh:
                json.dump({"civitai": {"trainedWords": ["from_comfy"]}, "notes": "comfy notes"}, fh)
            rec = load_record(model)
            self.assertEqual(rec["triggers"], ["from_forge"])
            self.assertEqual(rec["preferred_weight"], 0.7)
            self.assertEqual(rec["notes"], "keep me")

            os.remove(stem + ".json")
            rec = load_record(model)
            self.assertEqual(rec["triggers"], ["from_comfy"])

            os.remove(stem + ".metadata.json")
            with open(stem + ".civitai.info", "w", encoding="utf-8") as fh:
                json.dump({"trainedWords": ["civ_info"]}, fh)
            rec = load_record(model)
            self.assertEqual(rec["triggers"], ["civ_info"])

            os.remove(stem + ".civitai.info")
            with open(stem + ".txt", "w", encoding="utf-8") as fh:
                fh.write("alpha, beta\n")
            rec = load_record(model)
            self.assertEqual(rec["triggers"], ["alpha", "beta"])

    def test_sync_fills_empty_and_writes_both_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _touch_model(tmp)
            rec = load_record(model)
            rec = merge_api(
                rec,
                {
                    "id": 11,
                    "modelId": 22,
                    "baseModel": "Illustrious",
                    "trainedWords": ["foo", "bar"],
                    "model": {"name": "Demo", "description": "<p>hi</p>", "tags": ["style"]},
                    "images": [{"url": "http://example/1.png"}],
                },
            )
            rec["sha256"] = "abc"
            save_record(rec)
            stem = os.path.splitext(model)[0]
            with open(stem + ".json", encoding="utf-8") as fh:
                forge = json.load(fh)
            with open(stem + ".metadata.json", encoding="utf-8") as fh:
                comfy = json.load(fh)
            self.assertEqual(forge["activation text"], "foo, bar")
            self.assertEqual(forge["sd version"], "Illustrious")
            self.assertEqual(comfy["civitai"]["trainedWords"], ["foo", "bar"])
            self.assertEqual(comfy["base_model"], "Illustrious")
            self.assertEqual(comfy["modelDescription"], "<p>hi</p>")
            self.assertEqual(comfy["tags"], ["style"])

    def test_user_fields_survive_resync(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _touch_model(tmp)
            rec = load_record(model)
            rec = merge_api(rec, {"id": 1, "trainedWords": ["api_one"], "model": {}})
            rec = apply_user_edits(rec, triggers=["my_word"], notes="hand notes", preferred_weight=0.42)
            save_record(rec)
            rec = load_record(model)
            rec = merge_api(rec, {"id": 1, "trainedWords": ["api_two"], "model": {"description": "new"}})
            self.assertEqual(rec["triggers"], ["my_word"])
            self.assertEqual(rec["notes"], "hand notes")
            self.assertEqual(rec["preferred_weight"], 0.42)

    def test_existing_local_triggers_survive_first_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _touch_model(tmp)
            stem = os.path.splitext(model)[0]
            with open(stem + ".json", "w", encoding="utf-8") as fh:
                json.dump({"activation text": "local_only"}, fh)
            rec = merge_api(load_record(model), {"id": 1, "trainedWords": ["from_api"]})
            self.assertEqual(rec["triggers"], ["local_only"])

    def test_spaces_do_not_split_triggers(self):
        self.assertEqual(normalize_words("large breasts"), ["large breasts"])
        self.assertEqual(
            normalize_words("large breasts, looking at viewer"),
            ["large breasts", "looking at viewer"],
        )

    def test_triggers_update_when_user_did_not_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _touch_model(tmp)
            rec = load_record(model)
            rec = merge_api(rec, {"id": 1, "trainedWords": ["api_one"]})
            rec = merge_api(rec, {"id": 1, "trainedWords": ["api_two"]})
            self.assertEqual(rec["triggers"], ["api_two"])


if __name__ == "__main__":
    unittest.main()
