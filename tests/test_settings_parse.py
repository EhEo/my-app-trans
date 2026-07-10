# settings_window._parse_hotkey 의 통합(좌/우 접힘) 파싱 안정성 테스트
"""기존 hotkey 문자열을 통합 Ctrl/Shift/Alt 체크박스 + 키로 파싱하는 로직 검증."""
import unittest

from settings_window import _parse_hotkey


class TestParseHotkey(unittest.TestCase):
    def test_empty(self):
        state, key = _parse_hotkey("")
        self.assertEqual(key, "")
        self.assertFalse(any(state.values()))

    def test_simple_ctrl_shift_z(self):
        state, key = _parse_hotkey("ctrl+shift+z")
        self.assertTrue(state["ctrl"])
        self.assertTrue(state["shift"])
        self.assertFalse(state["alt"])
        self.assertEqual(key, "z")

    def test_left_right_folds_to_unified(self):
        # 좌/우 표기 입력은 통합 True 로 접힌다
        state, key = _parse_hotkey("left ctrl + right shift + z")
        self.assertTrue(state["ctrl"])
        self.assertTrue(state["shift"])
        self.assertFalse(state["alt"])
        self.assertEqual(key, "z")

    def test_lalt_lshift_a(self):
        state, key = _parse_hotkey("left alt + left shift + a")
        self.assertTrue(state["alt"])
        self.assertTrue(state["shift"])
        self.assertFalse(state["ctrl"])
        self.assertEqual(key, "a")

    def test_case_insensitive(self):
        state, key = _parse_hotkey("LEFT Ctrl + RIGHT shift + Z")
        self.assertTrue(state["ctrl"])
        self.assertTrue(state["shift"])
        self.assertEqual(key, "z")

    def test_no_modifiers_just_key(self):
        state, key = _parse_hotkey("f8")
        self.assertFalse(any(state.values()))
        self.assertEqual(key, "f8")


if __name__ == "__main__":
    unittest.main()
