"""번역문을 원래 입력란에 주입.

유니코드(한/중/일/베트남어 등)를 안전하게 넣기 위해 키 입력 대신
클립보드 + Ctrl+V 방식을 쓴다. 주입 전 클립보드를 백업하고 주입 후 복원한다.
대상 창에 포커스를 되돌리기 위해 AttachThreadInput 기법을 사용한다.
"""
from __future__ import annotations

import ctypes
import time

import keyboard
import pyperclip

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


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
    try:
        backup = pyperclip.paste()
    except Exception:
        backup = None

    pyperclip.copy(text)
    force_foreground(hwnd)
    time.sleep(focus_delay)
    keyboard.send("ctrl+v")
    time.sleep(paste_delay)

    if backup is not None:
        try:
            pyperclip.copy(backup)
        except Exception:
            pass
