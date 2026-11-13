# 설치기가 번들된 초기 설정(API 키)을 언제 적용하고 언제 기존 설정을 지키는지 검증
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import installer  # noqa: E402


class TestApplySeed(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.seed = self.tmp / "seed_config.json"
        self.cfg = self.tmp / "appdata" / "config.json"

    def write_seed(self, data: dict) -> None:
        self.seed.write_text(json.dumps(data), encoding="utf-8")

    def read_cfg(self) -> dict:
        return json.loads(self.cfg.read_text(encoding="utf-8"))

    def test_no_seed_file_does_nothing(self):
        self.assertEqual(installer.apply_seed(self.seed, self.cfg), "")
        self.assertFalse(self.cfg.exists())

    def test_fresh_install_gets_key_and_defaults(self):
        self.write_seed({"openrouter_api_key": "sk-test", "model": "m/x"})
        msg = installer.apply_seed(self.seed, self.cfg)
        cfg = self.read_cfg()
        self.assertEqual(cfg["openrouter_api_key"], "sk-test")
        self.assertEqual(cfg["model"], "m/x")
        self.assertEqual(cfg["hotkey"], "ctrl+shift+z")  # 나머지는 기본값
        self.assertIn("API 키", msg)

    def test_existing_empty_key_is_filled_and_other_settings_kept(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text(json.dumps({"openrouter_api_key": "",
                                        "target_language": "베트남어"}), encoding="utf-8")
        self.write_seed({"openrouter_api_key": "sk-test"})
        installer.apply_seed(self.seed, self.cfg)
        cfg = self.read_cfg()
        self.assertEqual(cfg["openrouter_api_key"], "sk-test")
        self.assertEqual(cfg["target_language"], "베트남어")

    def test_existing_key_is_never_overwritten(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text(json.dumps({"openrouter_api_key": "sk-mine"}), encoding="utf-8")
        self.write_seed({"openrouter_api_key": "sk-test", "model": "m/x"})
        msg = installer.apply_seed(self.seed, self.cfg)
        self.assertEqual(self.read_cfg()["openrouter_api_key"], "sk-mine")
        self.assertIn("기존", msg)

    def test_broken_seed_is_ignored(self):
        self.seed.write_text("{not json", encoding="utf-8")
        self.assertEqual(installer.apply_seed(self.seed, self.cfg), "")


if __name__ == "__main__":
    unittest.main()
