"""마우스 커서 근처에 뜨는 번역 입력 팝업.

Enter = 제출(번역 요청), Esc = 취소.
모든 메서드는 tkinter 메인 스레드에서 호출되어야 한다.
"""
from __future__ import annotations

import ctypes
import tkinter as tk
from typing import Callable

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# 라이트 테마
BG = "#ffffff"          # 본문 배경
FG = "#202124"          # 본문 글자
ACCENT = "#1a73e8"      # 포커스/강조
ERR = "#d93025"         # 오류
BORDER = "#c0c4cc"      # 팝업 외곽선
SUBTLE = "#5f6368"      # 안내문구(회색)
ENTRY_BORDER = "#dadce0"


class Popup:
    def __init__(self, root: tk.Tk, on_submit: Callable[[str], None],
                 on_close: Callable[[], None] | None = None) -> None:
        self.root = root
        self.on_submit = on_submit
        self.on_close = on_close
        self._submitted = False
        self._closed = False
        self._ready = False  # 생성 직후 포커스 흔들림으로 자동 닫히는 것 방지

        win = tk.Toplevel(root)
        self.win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=BORDER)  # 얇은 외곽선

        # 마우스 커서 근처에 배치
        x, y = root.winfo_pointerxy()
        win.geometry(f"+{x + 12}+{y + 16}")

        frame = tk.Frame(win, bg=BG, padx=9, pady=7)
        frame.pack(padx=1, pady=1)  # 1px 외곽선

        tk.Label(frame, text="Enter 번역·삽입  ·  Esc 취소",
                 bg=BG, fg=SUBTLE, font=("Segoe UI", 8)).pack(anchor="w")

        self.entry = tk.Entry(frame, width=34, font=("Segoe UI", 11),
                              bg=BG, fg=FG, insertbackground=FG,
                              relief="flat", highlightthickness=1,
                              highlightbackground=ENTRY_BORDER,
                              highlightcolor=ACCENT)
        self.entry.pack(fill="x", pady=(4, 2), ipady=3)

        self.status = tk.Label(frame, text="", bg=BG, fg=ACCENT,
                               font=("Segoe UI", 8))
        self.status.pack(anchor="w")

        win.bind("<Return>", self._submit)
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<FocusOut>", self._on_focus_out)

        win.update_idletasks()
        win.deiconify()
        self._force_foreground()
        # 일부 환경에선 한 번에 포커스를 못 가져오므로 여러 번 재시도 + 준비완료 표시
        win.after(60, self._force_foreground)
        win.after(150, self._force_foreground)
        win.after(600, self._mark_ready)

    def _force_foreground(self) -> None:
        """Windows의 포커스 가로채기 제한을 우회해 팝업을 전경으로 가져온다."""
        if not self.win.winfo_exists():
            return
        try:
            hwnd = self.win.winfo_id()
            fg = _user32.GetForegroundWindow()
            cur = _kernel32.GetCurrentThreadId()
            fg_thread = _user32.GetWindowThreadProcessId(fg, None)
            if fg_thread and fg_thread != cur:
                _user32.AttachThreadInput(cur, fg_thread, True)
                _user32.BringWindowToTop(hwnd)
                _user32.SetForegroundWindow(hwnd)
                _user32.SetActiveWindow(hwnd)
                _user32.SetFocus(hwnd)
                _user32.AttachThreadInput(cur, fg_thread, False)
            else:
                _user32.SetForegroundWindow(hwnd)
                _user32.SetFocus(hwnd)
        except Exception:
            pass
        self.win.lift()
        self.win.attributes("-topmost", True)
        self.win.focus_force()
        self.entry.focus_set()

    def _mark_ready(self) -> None:
        self._ready = True

    def _on_focus_out(self, _event) -> None:
        # 생성 직후(_ready=False)나 번역 중에는 자동으로 닫지 않는다.
        # 사용자가 의도적으로 다른 창을 클릭해 포커스를 잃었을 때만 취소.
        if self._ready and not self._submitted:
            self.close()

    def _submit(self, _event=None) -> None:
        if self._submitted:
            return
        text = self.entry.get().strip()
        if not text:
            self.close()
            return
        self._submitted = True
        self.entry.configure(state="disabled")
        self.set_status("번역 중...", ACCENT)
        self.on_submit(text)

    def set_status(self, message: str, color: str = ACCENT) -> None:
        if self.win.winfo_exists():
            self.status.configure(text=message, fg=color)

    def show_error(self, message: str) -> None:
        """번역 실패 시: 오류 표시 후 다시 입력할 수 있게 되돌린다."""
        if not self.win.winfo_exists():
            return
        self._submitted = False
        self.entry.configure(state="normal")
        self.entry.focus_set()
        self.set_status(message, ERR)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.win.winfo_exists():
            self.win.destroy()
        if self.on_close is not None:
            self.on_close()
