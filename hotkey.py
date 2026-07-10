# Win32 RegisterHotKey 기반 전역 단축키 엔진 (keyboard LL 훅의 유령 키 잔류 버그 회피)
"""전역 단축키를 Windows 네이티브 RegisterHotKey 로 처리한다.

keyboard 라이브러리(WH_KEYBOARD_LL suppress 훅)는 잠금화면/UAC 등 보안
데스크톱 전환 때 key-up 이 소실되면 유령 키가 눌린 상태로 영구 잔류해 단축키가
영원히 무반응이 된다. RegisterHotKey 는 조합 판정을 OS 가 하므로 이 문제가 없다.

RegisterHotKey/UnregisterHotKey 는 등록한 스레드의 메시지 큐로 WM_HOTKEY 를
보내므로, 반드시 메시지 루프를 도는 전용 스레드에서 호출해야 한다. 다른 스레드의
등록 요청은 큐에 넣어 이 스레드가 처리하고 결과를 Event 로 동기 반환한다.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import queue
import threading
import time
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)

# RegisterHotKey modifier 플래그
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # 키를 누르고 있어도 재발동 안 함 (자동반복 억제)

WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
PM_NOREMOVE = 0x0000

user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
user32.RegisterHotKey.restype = wt.BOOL
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wt.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND,
                                ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
user32.PeekMessageW.restype = wt.BOOL
user32.VkKeyScanW.argtypes = [wt.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short


def _key_to_vk(key: str) -> int | None:
    """키 토큰을 가상 키 코드(VK)로 변환. 해석 불가 시 None."""
    if len(key) == 1:
        # VkKeyScanW: 하위 바이트가 VK, -1 이면 매핑 불가
        res = user32.VkKeyScanW(key)
        if res == -1:
            return None
        return res & 0xFF
    if key == "space":
        return 0x20
    if key in ("esc", "escape"):
        return 0x1B
    if key.startswith("f") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 24:
            return 0x70 + n - 1  # VK_F1 = 0x70
    return None


def parse_hotkey(hk: str) -> tuple[int, int] | None:
    """단축키 문자열을 (mods, vk) 로 변환. 순수 함수(단위 테스트 대상).

    좌/우 수식 토큰(left ctrl 등)은 통합 플래그로 접는다 — RegisterHotKey 는
    좌/우를 구분하지 않기 때문. 키가 없거나 해석 불가하면 None(MOD_NOREPEAT 는
    등록 시점에 붙이므로 여기서는 포함하지 않는다).
    """
    if not hk:
        return None
    parts = [p.strip().lower() for p in hk.replace("+", " + ").split("+")]
    parts = [p for p in parts if p]
    mods = 0
    vk: int | None = None
    for p in parts:
        if p in ("ctrl", "control", "left ctrl", "right ctrl",
                 "lctrl", "rctrl", "leftctrl", "rightctrl"):
            mods |= MOD_CONTROL
        elif p in ("shift", "left shift", "right shift",
                   "lshift", "rshift", "leftshift", "rightshift"):
            mods |= MOD_SHIFT
        elif p in ("alt", "left alt", "right alt",
                   "lalt", "ralt", "leftalt", "rightalt"):
            mods |= MOD_ALT
        elif p in ("win", "windows", "left windows", "right windows",
                   "lwin", "rwin"):
            mods |= MOD_WIN
        else:
            v = _key_to_vk(p)
            if v is None:
                return None
            vk = v
    if vk is None:
        return None
    return mods, vk


class _Request:
    """hotkey 스레드로 넘기는 등록/해제/종료 요청. 결과는 event 로 동기 반환."""

    def __init__(self, action: str, args: tuple) -> None:
        self.action = action
        self.args = args
        self.event = threading.Event()
        self.result = None


class HotkeyManager:
    """전용 스레드에서 메시지 루프를 돌며 RegisterHotKey 를 관리한다."""

    def __init__(self) -> None:
        self._requests: "queue.Queue[_Request]" = queue.Queue()
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._registered: set[int] = set()
        self._thread: threading.Thread | None = None
        self._running = False

    def set_callback(self, hotkey_id: int, fn: Callable[[], None]) -> None:
        """WM_HOTKEY(id) 수신 시 hotkey 스레드에서 호출할 콜백을 등록한다."""
        self._callbacks[hotkey_id] = fn

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def register(self, hotkey_id: int, mods: int, vk: int) -> bool:
        """단축키를 등록한다(동기). 성공 여부 반환.

        MOD_NOREPEAT 를 항상 OR — 키를 누르고 있을 때 WM_HOTKEY 가 반복 발동되는
        것을 막는다.
        """
        return bool(self._submit("register", (hotkey_id, mods | MOD_NOREPEAT, vk)))

    def unregister(self, hotkey_id: int) -> None:
        self._submit("unregister", (hotkey_id,))

    def stop(self) -> None:
        """등록된 단축키를 모두 해제하고 스레드를 종료한다."""
        if self._thread is None or not self._thread.is_alive():
            return
        self._submit("stop", ())
        self._thread.join(timeout=1.0)

    # --- 내부 ---
    def _submit(self, action: str, args: tuple):
        """요청을 큐에 넣고 hotkey 스레드가 처리할 때까지 기다려 결과를 돌려준다."""
        if self._thread is None or not self._thread.is_alive():
            return None
        req = _Request(action, args)
        self._requests.put(req)
        req.event.wait(timeout=2.0)
        return req.result

    def _handle_request(self, req: _Request) -> None:
        if req.action == "register":
            hid, mods, vk = req.args
            ok = bool(user32.RegisterHotKey(None, hid, mods, vk))
            if ok:
                self._registered.add(hid)
            req.result = ok
        elif req.action == "unregister":
            (hid,) = req.args
            if hid in self._registered:
                user32.UnregisterHotKey(None, hid)
                self._registered.discard(hid)
            req.result = None
        elif req.action == "stop":
            self._running = False
            req.result = None
        req.event.set()

    def _run(self) -> None:
        msg = wt.MSG()
        # 이 스레드에 메시지 큐를 강제로 생성한다 (RegisterHotKey 가 붙을 대상).
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        while self._running:
            # 1) 등록/해제/종료 요청 처리 (반드시 이 스레드에서 RegisterHotKey 호출)
            while True:
                try:
                    req = self._requests.get_nowait()
                except queue.Empty:
                    break
                self._handle_request(req)
            # 2) WM_HOTKEY 수신 → 콜백 호출 (기존 keyboard 콜백과 동일 계약)
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY:
                    cb = self._callbacks.get(int(msg.wParam))
                    if cb is not None:
                        try:
                            cb()
                        except Exception as e:  # 콜백 오류로 루프가 죽지 않도록
                            print("[hotkey] callback error:", e)
            time.sleep(0.03)
        # 종료: 남은 등록을 모두 해제
        for hid in list(self._registered):
            user32.UnregisterHotKey(None, hid)
        self._registered.clear()
