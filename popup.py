"""마우스 커서 근처에 뜨는 번역 입력 팝업.

Enter = 제출(번역 요청), Esc = 취소.
모든 메서드는 tkinter 메인 스레드에서 호출되어야 한다.
"""
from __future__ import annotations

import ctypes
import tkinter as tk
from typing import Callable

from ui import font_family

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_imm32 = ctypes.windll.imm32


class _LOGFONTW(ctypes.Structure):
    """IME 조합 글꼴 지정용 LOGFONTW."""
    _fields_ = [
        ("lfHeight", ctypes.c_long),
        ("lfWidth", ctypes.c_long),
        ("lfEscapement", ctypes.c_long),
        ("lfOrientation", ctypes.c_long),
        ("lfWeight", ctypes.c_long),
        ("lfItalic", ctypes.c_byte),
        ("lfUnderline", ctypes.c_byte),
        ("lfStrikeOut", ctypes.c_byte),
        ("lfCharSet", ctypes.c_byte),
        ("lfOutPrecision", ctypes.c_byte),
        ("lfClipPrecision", ctypes.c_byte),
        ("lfQuality", ctypes.c_byte),
        ("lfPitchAndFamily", ctypes.c_byte),
        ("lfFaceName", ctypes.c_wchar * 32),
    ]

# 라이트 테마
BG = "#fdfdfc"          # 본문(안쪽 카드) 배경
OUTER = "#eeeeec"       # 바깥 창(사각형) 배경 — 둥근 카드 코너에 비치는 색
FG = "#202124"          # 본문 글자
ACCENT = "#1a73e8"      # 포커스/강조
ERR = "#d93025"         # 오류
CARD_OUTLINE = "#d8d8d4"  # 안쪽 카드 외곽선
SUBTLE = "#5f6368"      # 안내문구(회색)
ENTRY_BG = "#fdfdfc"    # 입력칸 배경
ENTRY_BORDER = "#dadce0"
CORNER_RADIUS = 12      # 안쪽 카드 모서리 R값(px)


def _round_rect_points(x1, y1, x2, y2, r):
    """둥근 사각형 폴리곤 좌표(smooth=True 와 함께 사용)."""
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


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
        fam = font_family(root)
        self.fam = fam
        self.font_size = 10
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=OUTER)  # 바깥 창은 사각형(둥글지 않음)

        # 마우스 커서 근처에 배치
        x, y = root.winfo_pointerxy()
        win.geometry(f"+{x + 12}+{y + 16}")

        # 안쪽 카드만 둥근 모서리: Canvas 위에 둥근 사각형을 그리고 내용을 임베드
        pad = 8  # 카드 안쪽 여백
        canvas = tk.Canvas(win, bg=OUTER, highlightthickness=0)
        canvas.pack()

        # 내용은 canvas 의 자식으로 만들어 임베드 렌더링을 보장
        content = tk.Frame(canvas, bg=BG)

        self.entry = tk.Entry(content, width=32, font=(fam, 10),
                              bg="#ffffff", fg=FG, insertbackground=FG,
                              relief="solid", bd=1,
                              highlightthickness=0)
        self.entry.pack(fill="x", ipady=3)

        bottom = tk.Frame(content, bg=BG)
        bottom.pack(fill="x", pady=(3, 0))
        tk.Label(bottom, text="Enter 번역·삽입 · Esc 취소", bg=BG, fg=SUBTLE,
                 font=(fam, 6, "bold")).pack(side="right")
        self.status = tk.Label(bottom, text="", bg=BG, fg=ACCENT,
                               font=(fam, 8), anchor="w")
        self.status.pack(side="left", fill="x", expand=True)

        content.update_idletasks()
        cw = content.winfo_reqwidth() + 2 * pad
        ch = content.winfo_reqheight() + 2 * pad
        canvas.config(width=cw, height=ch)
        canvas.create_polygon(
            _round_rect_points(0, 0, cw - 1, ch - 1, CORNER_RADIUS),
            smooth=True, fill=BG, outline=CARD_OUTLINE)
        canvas.create_window(pad, pad, anchor="nw", window=content)

        win.bind("<Return>", self._submit)
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<FocusOut>", self._on_focus_out)
        # 한글 조합 중 글꼴/크기가 위젯과 다르게 보이는 문제 방지:
        # IME 조합 글꼴을 입력칸 글꼴과 동일하게 지정
        self.entry.bind("<FocusIn>", self._apply_ime_font)

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
        self._apply_ime_font()

    def _apply_ime_font(self, *_event) -> None:
        """IME 조합(미확정) 글꼴을 입력칸 글꼴과 동일하게 맞춘다.

        지정하지 않으면 한글 조합 중 글자가 OS 기본 글꼴/큰 크기로 보인다.
        """
        try:
            if not self.win.winfo_exists():
                return
            dpi = self.win.winfo_fpixels("1i")  # 인치당 픽셀
            px = int(round(self.font_size * dpi / 72.0))
            lf = _LOGFONTW()
            lf.lfHeight = -px
            lf.lfWeight = 400
            lf.lfCharSet = 1  # DEFAULT_CHARSET (Pretendard가 한글 포함)
            lf.lfFaceName = self.fam[:31]
            hwnd = self.entry.winfo_id()
            himc = _imm32.ImmGetContext(hwnd)
            if himc:
                _imm32.ImmSetCompositionFontW(himc, ctypes.byref(lf))
                _imm32.ImmReleaseContext(hwnd, himc)
        except Exception:
            pass

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
