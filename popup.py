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
        self.pad = 8  # 카드 안쪽 여백
        canvas = tk.Canvas(win, bg=OUTER, highlightthickness=0)
        canvas.pack()
        self.canvas = canvas
        # 크기/위치는 전적으로 geometry() 로만 제어한다(자동 전파가 위쪽 성장을
        # 덮어쓰지 않도록). 창 크기는 아래에서 명시적으로 지정한다.
        win.pack_propagate(False)

        # 내용은 canvas 의 자식으로 만들어 임베드 렌더링을 보장
        content = tk.Frame(canvas, bg=BG)
        self.content = content

        # 멀티라인 입력란: 자동 줄바꿈(wrap)으로 두 줄 이상이 되면 높이를 키운다.
        # (단일행 Entry 의 1.5배 너비 = 48자). MAX_LINES 까지 자란다.
        self.MAX_LINES = 6
        self._cur_lines = 1
        self.text = tk.Text(content, width=48, height=1, font=(fam, 10),
                            wrap="word", bg="#ffffff", fg=FG,
                            insertbackground=FG, relief="solid", bd=1,
                            highlightthickness=0, padx=4, pady=2, undo=True)
        self.text.pack(fill="x")

        bottom = tk.Frame(content, bg=BG)
        bottom.pack(fill="x", pady=(3, 0))
        tk.Label(bottom, text="Enter 번역·삽입 · Esc 취소", bg=BG, fg=SUBTLE,
                 font=(fam, 6, "bold")).pack(side="right")
        self.status = tk.Label(bottom, text="", bg=BG, fg=ACCENT,
                               font=(fam, 8), anchor="w")
        self.status.pack(side="left", fill="x", expand=True)

        content.update_idletasks()
        cw = content.winfo_reqwidth() + 2 * self.pad
        ch = content.winfo_reqheight() + 2 * self.pad
        canvas.config(width=cw, height=ch)
        self._poly = canvas.create_polygon(
            _round_rect_points(0, 0, cw - 1, ch - 1, CORNER_RADIUS),
            smooth=True, fill=BG, outline=CARD_OUTLINE)
        self._embed = canvas.create_window(self.pad, self.pad, anchor="nw",
                                           window=content)

        # 위로 자라게 하려면 '아래 모서리'의 화면상 위치를 고정 기준으로 둔다.
        # 높이가 늘면 그만큼 창의 top 을 위로 올려 bottom 을 유지한다.
        self._x = x + 12
        self._bottom = (y + 16) + ch
        win.geometry(f"{cw}x{ch}+{self._x}+{y + 16}")

        # Enter = 제출(줄바꿈 삽입 안 함), Shift+Enter = 수동 줄바꿈
        self.text.bind("<Return>", self._submit)
        self.text.bind("<KP_Enter>", self._submit)
        self.text.bind("<Shift-Return>", self._on_shift_return)
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<FocusOut>", self._on_focus_out)
        # 입력 변화 시 줄 수에 맞춰 입력란 높이를 위로 키운다.
        self.text.bind("<KeyRelease>", self._auto_grow)
        # 한글 조합 중 글꼴/크기가 위젯과 다르게 보이는 문제 방지:
        # IME 조합 글꼴을 입력칸 글꼴과 동일하게 지정
        self.text.bind("<FocusIn>", self._apply_ime_font)

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
        self.text.focus_set()
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
            hwnd = self.text.winfo_id()
            himc = _imm32.ImmGetContext(hwnd)
            if himc:
                _imm32.ImmSetCompositionFontW(himc, ctypes.byref(lf))
                _imm32.ImmReleaseContext(hwnd, himc)
        except Exception:
            pass

    def _on_shift_return(self, _event=None):
        # 수동 줄바꿈은 기본 동작(개행 삽입)을 허용한 뒤 높이를 다시 맞춘다.
        self.win.after(1, self._auto_grow)
        return None

    def _auto_grow(self, _event=None) -> None:
        """입력 줄 수(자동 줄바꿈 포함)에 맞춰 입력란 높이를 조정한다."""
        if not self.win.winfo_exists():
            return
        try:
            self.text.update_idletasks()
            cnt = self.text.count("1.0", "end-1c", "displaylines")
        except Exception:
            return
        if isinstance(cnt, (tuple, list)):
            n = cnt[0] if cnt else 0
        else:
            n = cnt or 0
        lines = max(1, min(self.MAX_LINES, int(n) + 1))
        if lines == self._cur_lines:
            return
        self._cur_lines = lines
        self.text.configure(height=lines)
        self._relayout()

    def _relayout(self) -> None:
        """입력란 높이 변화에 맞춰 둥근 카드/창 크기를 다시 그리고,
        아래 모서리를 고정한 채 창을 위로 키운다."""
        if not self.win.winfo_exists():
            return
        self.content.update_idletasks()
        cw = self.content.winfo_reqwidth() + 2 * self.pad
        ch = self.content.winfo_reqheight() + 2 * self.pad
        self.canvas.config(width=cw, height=ch)
        self.canvas.coords(
            self._poly,
            *_round_rect_points(0, 0, cw - 1, ch - 1, CORNER_RADIUS))
        # canvas 크기 변경이 예약한 geometry 전파를 먼저 소진시킨 뒤,
        # 위치(위로 성장)를 마지막에 확정해야 전파가 top 을 되돌리지 못한다.
        self.win.update_idletasks()
        new_y = max(0, self._bottom - ch)   # bottom 고정 → 위로 성장
        self.win.geometry(f"{cw}x{ch}+{self._x}+{new_y}")
        self.win.update_idletasks()

    def _mark_ready(self) -> None:
        self._ready = True

    def _on_focus_out(self, _event) -> None:
        # 생성 직후(_ready=False)나 번역 중에는 자동으로 닫지 않는다.
        # 사용자가 의도적으로 다른 창을 클릭해 포커스를 잃었을 때만 취소.
        if self._ready and not self._submitted:
            self.close()

    def _submit(self, _event=None) -> str:
        # "break" 를 돌려 Text 기본 동작(개행 삽입)을 막고 제출로만 처리한다.
        if self._submitted:
            return "break"
        text = self.text.get("1.0", "end-1c").strip()
        if not text:
            self.close()
            return "break"
        self._submitted = True
        self.text.configure(state="disabled")
        self.set_status("번역 중...", ACCENT)
        self.on_submit(text)
        return "break"

    def set_status(self, message: str, color: str = ACCENT) -> None:
        if self.win.winfo_exists():
            self.status.configure(text=message, fg=color)

    def show_error(self, message: str) -> None:
        """번역 실패 시: 오류 표시 후 다시 입력할 수 있게 되돌린다."""
        if not self.win.winfo_exists():
            return
        self._submitted = False
        self.text.configure(state="normal")
        self.text.focus_set()
        self.set_status(message, ERR)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.win.winfo_exists():
            self.win.destroy()
        if self.on_close is not None:
            self.on_close()
