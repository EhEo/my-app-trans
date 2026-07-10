# hotkey.parse_hotkey 의 (mods, vk) 변환 검증 — RegisterHotKey 상수 조합 정확성
"""단축키 문자열 → (mods, vk) 순수 변환 로직 검증.

스레드/Win32 등록 부분은 실기기 검증 대상이라 여기서 다루지 않는다.
"""
import unittest

from hotkey import (MOD_ALT, MOD_CONTROL, MOD_SHIFT, parse_hotkey)

VK_Z = 0x5A
VK_SPACE = 0x20
VK_F8 = 0x77


class TestParseHotkey(unittest.TestCase):
    def test_ctrl_shift_z(self):
        self.assertEqual(parse_hotkey("ctrl+shift+z"),
                         (MOD_CONTROL | MOD_SHIFT, VK_Z))

    def test_left_right_compat_folds(self):
        # 좌/우 표기(호환)는 통합 플래그로 접힌다
        self.assertEqual(parse_hotkey("left ctrl + left shift + z"),
                         (MOD_CONTROL | MOD_SHIFT, VK_Z))

    def test_ctrl_alt_space(self):
        self.assertEqual(parse_hotkey("ctrl+alt+space"),
                         (MOD_CONTROL | MOD_ALT, VK_SPACE))

    def test_function_key(self):
        self.assertEqual(parse_hotkey("f8"), (0, VK_F8))

    def test_no_norepeat_in_result(self):
        # MOD_NOREPEAT(0x4000)는 등록 시점에 붙으므로 파싱 결과엔 없어야 한다
        mods, _vk = parse_hotkey("ctrl+shift+z")
        self.assertEqual(mods & 0x4000, 0)

    def test_invalid_no_key(self):
        self.assertIsNone(parse_hotkey("ctrl+shift"))

    def test_invalid_unknown_token(self):
        self.assertIsNone(parse_hotkey("ctrl+shift+nope"))

    def test_empty(self):
        self.assertIsNone(parse_hotkey(""))


if __name__ == "__main__":
    unittest.main()
