# settings_window._parse_hotkey 의 직렬화/역직렬화 안정성 테스트
"""기존 hotkey 문자열을 체크박스+키로 파싱하는 로직 검증."""
import unittest

from settings_window import _parse_hotkey


class TestParseHotkey(unittest.TestCase):
    def test_empty(self):
        state, key = _parse_hotkey("")
        self.assertEqual(key, "")
        self.assertFalse(any(state.values()))

    def test_simple_ctrl_shift_z(self):
        state, key = _parse_hotkey("ctrl+shift+z")
        # 좌/우 미지정 → 양쪽 모두 True
        self.assertTrue(state["left_ctrl"] and state["right_ctrl"])
        self.assertTrue(state["left_shift"] and state["right_shift"])
        self.assertFalse(state["left_alt"] or state["right_alt"])
        self.assertEqual(key, "z")

    def test_left_ctrl_right_shift_z(self):
        state, key = _parse_hotkey("left ctrl + right shift + z")
        self.assertTrue(state["left_ctrl"])
        self.assertFalse(state["right_ctrl"])
        self.assertFalse(state["left_shift"])
        self.assertTrue(state["right_shift"])
        self.assertEqual(key, "z")

    def test_lalt_lshift_a(self):
        state, key = _parse_hotkey("left alt + left shift + a")
        self.assertTrue(state["left_alt"])
        self.assertFalse(state["right_alt"])
        self.assertTrue(state["left_shift"])
        self.assertFalse(state["right_shift"])
        self.assertEqual(key, "a")

    def test_case_insensitive(self):
        state, key = _parse_hotkey("LEFT Ctrl + RIGHT shift + Z")
        self.assertTrue(state["left_ctrl"])
        self.assertTrue(state["right_shift"])
        self.assertEqual(key, "z")

    def test_no_modifiers_just_key(self):
        state, key = _parse_hotkey("f8")
        self.assertFalse(any(state.values()))
        self.assertEqual(key, "f8")


if __name__ == "__main__":
    unittest.main()
