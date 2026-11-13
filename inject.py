"""번역문을 원래 입력란에 주입.

유니코드(한/중/일/베트남어 등)를 안전하게 넣기 위해 키 입력 대신
클립보드 + Ctrl+V 방식을 쓴다. 주입 전 클립보드를 백업하고 주입 후 복원한다.
대상 창에 포커스를 되돌리기 위해 AttachThreadInput 기법을 사용한다.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time

import keyboard
import pyperclip

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

DEBUG = False  # main 에서 --debug 시 True 로 설정


def _dlog(msg: str) -> None:
    if DEBUG:
        print(f"[inject] {msg}", flush=True)


# --- SendInput 으로 modifier keyup 직접 전송 (stuck modifier 해제용) ---
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_MOD_VKS = (
    0xA2,  # VK_LCONTROL
    0xA3,  # VK_RCONTROL
    0xA4,  # VK_LMENU  (Left Alt)
    0xA5,  # VK_RMENU
    0xA0,  # VK_LSHIFT
    0xA1,  # VK_RSHIFT
    0x5B,  # VK_LWIN
    0x5C,  # VK_RWIN
)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _INPUT_UNION)]


def release_modifiers() -> None:
    """OS 에 모든 modifier(Ctrl/Alt/Shift/Win)의 keyup 을 강제 전송한다.

    사용자가 단축키(예: Ctrl+Alt+Z)를 누른 상태로 콜백이 실행될 때,
    이후의 Ctrl+V 주입/팝업 입력에 modifier 가 stuck 으로 따라붙는 것을 막는다.
    이미 안 눌려 있던 키는 OS 가 무해하게 무시한다.
    """
    n = len(_MOD_VKS)
    InputArr = _INPUT * n
    inputs = InputArr()
    for i, vk in enumerate(_MOD_VKS):
        inputs[i].type = _INPUT_KEYBOARD
        inputs[i].ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=_KEYEVENTF_KEYUP,
                                   time=0, dwExtraInfo=None)
    user32.SendInput(n, ctypes.byref(inputs), ctypes.sizeof(_INPUT))


def force_foreground(hwnd: int) -> None:
    """주어진 창 핸들을 전경(foreground)으로 가져온다.

    Windows의 foreground lock 때문에 단순 SetForegroundWindow는 막히는 경우가
    많아, 더미 키 입력 + AttachThreadInput 으로 우회한다.
    """
    if not hwnd:
        return
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return
    keyboard.send("alt")  # foreground lock 완화용 더미 입력
    cur = kernel32.GetCurrentThreadId()
    tgt = user32.GetWindowThreadProcessId(fg, None)
    win = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(cur, tgt, True)
    user32.AttachThreadInput(cur, win, True)
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.SetFocus(hwnd)
    finally:
        user32.AttachThreadInput(cur, tgt, False)
        user32.AttachThreadInput(cur, win, False)


def paste_into(hwnd: int, text: str,
               focus_delay: float = 0.12,
               paste_delay: float = 0.25) -> None:
    """text 를 hwnd 창에 붙여넣는다. 호출 전 팝업은 닫혀 있어야 한다.

    이 함수는 sleep 을 포함하므로 UI 스레드가 아닌 워커 스레드에서 호출할 것.
    """
    if not text:
        return
    # 단축키의 Ctrl/Alt 가 OS 에서 아직 눌림으로 남아 있으면
    # 이어지는 Ctrl+V 가 Ctrl+Alt+V 로 해석돼 붙여넣기가 실패한다. 먼저 해제.
    release_modifiers()
    try:
        backup = pyperclip.paste()
    except Exception:
        backup = None
    _dlog(f"기존 클립보드 backup={backup[:30]!r}" if backup else "기존 클립보드 비어있음")

    pyperclip.copy(text)
    # f-string 은 _dlog 호출 전에 평가되므로, 클립보드 확인 읽기는 DEBUG 일 때만 한다
    # (그렇지 않으면 디버그가 꺼져 있어도 매번 클립보드를 더 읽어 대상 앱과 경합한다).
    if DEBUG:
        _dlog(f"클립보드에 복사한 번역문={text[:40]!r} / 확인={pyperclip.paste()[:40]!r}")
    force_foreground(hwnd)
    time.sleep(focus_delay)
    keyboard.send("ctrl+v")
    if DEBUG:
        _dlog(f"Ctrl+V 전송 (hwnd={hwnd}) / 현재 클립보드={pyperclip.paste()[:40]!r}")
    time.sleep(paste_delay)

    if backup is not None:
        try:
            pyperclip.copy(backup)
            _dlog("클립보드 복원 완료")
        except Exception:
            pass
