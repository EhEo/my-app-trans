# Windows 네이티브 RegisterHotKey 로 Ctrl+Shift+Z 잡히는지 진단 (1회용)
"""keyboard 라이브러리 우회 진단.

keyboard 라이브러리(저수준 WH_KEYBOARD_LL 훅)가 동작하지 않을 때, Windows
네이티브 RegisterHotKey 가 잡히는지 확인한다. 잡히면 라이브러리 교체로
fix 가능, 안 잡히면 시스템/권한 차원의 문제.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)

import os

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_ALT = 0x0001
VK_Z = 0x5A
VK_F8 = 0x77
WM_HOTKEY = 0x0312
HOTKEY_ID = 1

# 환경변수 DIAG_KEY=F8 또는 CTRLALTZ 로 키 조합을 바꿀 수 있다(기본: CTRLSHIFTZ)
_KEYS = {
    "CTRLSHIFTZ": (MOD_CONTROL | MOD_SHIFT, VK_Z, "Ctrl+Shift+Z"),
    "F8": (0, VK_F8, "F8"),
    "CTRLALTZ": (MOD_CONTROL | MOD_ALT, VK_Z, "Ctrl+Alt+Z"),
}
_diag_key = os.environ.get("DIAG_KEY", "CTRLSHIFTZ")
MODS, VK, KEY_NAME = _KEYS.get(_diag_key, _KEYS["CTRLSHIFTZ"])

user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
user32.RegisterHotKey.restype = wt.BOOL
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wt.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND,
                                 ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
user32.PeekMessageW.restype = wt.BOOL


def main() -> None:
    print("=" * 60)
    print(f"Windows 네이티브 RegisterHotKey 진단 - 대상 키: {KEY_NAME}")
    print("=" * 60)
    ok = user32.RegisterHotKey(None, HOTKEY_ID, MODS, VK)
    if not ok:
        err = ctypes.get_last_error()
        print(f">> RegisterHotKey 실패: error={err}")
        print(">> error=1409 'Hot key is already registered' 면 다른 앱이 점유 중")
        return
    print(f"등록 성공. 30초간 감지합니다. 지금 {KEY_NAME} 를 눌러보세요...")
    msg = wt.MSG()
    start = time.time()
    count = 0
    try:
        while time.time() - start < 30:
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE
                if msg.message == WM_HOTKEY:
                    count += 1
                    print(f"[{time.strftime('%H:%M:%S')}] HOTKEY DETECTED #{count}")
            time.sleep(0.03)
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
    print("-" * 60)
    print(f"종료. 총 감지: {count}")
    if count == 0:
        print(">> RegisterHotKey 도 0회 → 다른 앱이 단축키 점유 또는 시스템 정책 문제")
    else:
        print(">> RegisterHotKey 정상 동작 → keyboard 라이브러리를 교체하면 됩니다")


if __name__ == "__main__":
    main()
