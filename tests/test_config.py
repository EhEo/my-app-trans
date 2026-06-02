import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402


class TestConfig(unittest.TestCase):
    def test_creates_defaults_when_missing(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            cfg = config.load_config(p)
            self.assertTrue(p.exists())
            self.assertEqual(cfg, config.DEFAULTS)

    def test_roundtrip_save_load(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            data = dict(config.DEFAULTS, openrouter_api_key="abc", target_language="중국어")
            config.save_config(data, p)
            loaded = config.load_config(p)
            self.assertEqual(loaded["openrouter_api_key"], "abc")
            self.assertEqual(loaded["target_language"], "중국어")

    def test_missing_keys_filled_with_defaults(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"target_language": "베트남어"}), encoding="utf-8")
            cfg = config.load_config(p)
            self.assertEqual(cfg["target_language"], "베트남어")
            self.assertEqual(cfg["model"], config.DEFAULTS["model"])
            self.assertEqual(cfg["hotkey"], config.DEFAULTS["hotkey"])

    def test_corrupt_file_returns_defaults(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text("{ not valid json", encoding="utf-8")
            cfg = config.load_config(p)
            self.assertEqual(cfg, config.DEFAULTS)

    def test_unknown_keys_ignored(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"unknown": 1, "model": "x/y"}), encoding="utf-8")
            cfg = config.load_config(p)
            self.assertNotIn("unknown", cfg)
            self.assertEqual(cfg["model"], "x/y")


if __name__ == "__main__":
    unittest.main()
