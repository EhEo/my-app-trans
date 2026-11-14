"""마우스 커서 근처에 뜨는 번역 입력 팝업.

Enter = 제출(번역 요청), Esc = 취소.
하단의 언어 드롭다운으로 목표 언어를 바로 바꿀 수 있다.
모든 메서드는 tkinter 메인 스레드에서 호출되어야 한다.
"""
from __future__ import annotations

import ctypes
import os
import tkinter as tk
from ctypes import wintypes
from typing import Callable

from ui import (ACCENT, CARD, ERR, HAIRLINE, OUTLINE, TEXT1, TEXT3,
                font_family, keycap)

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_imm32 = ctypes.windll.imm32
_dwmapi = ctypes.windll.dwmapi


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

FONT_SIZE = 11          # 입력 글자 크기(pt) — IME 조합 글꼴도 이 크기로 맞춘다
META_SIZE = 9           # 하단 줄(언어·상태) 글자 크기
PAD = 12                # 카드 안쪽 여백(px, 4px 격자)
STATUS_MAX = 140        # 상태/오류 메시지 최대 길이 — 넘으면 말줄임

# DWM: Win11 둥근 모서리와 테두리 색 (Win10 은 지원하지 않아 호출이 실패한다)
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_BORDER_COLOR = 34
_DWMWCP_ROUND = 2


def _colorref(hex_color: str) -> int:
    """'#rrggbb' → Win32 COLORREF(0x00bbggrr)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return r | (g << 8) | (b << 16)


def _round_native(win: tk.Toplevel) -> bool:
    """Win11 DWM 으로 창 모서리를 둥글게 하고 외곽선 색을 지정한다. 성공 여부 반환.

    tk 폴리곤은 안티에일리어싱이 안 돼 둥근 모서리가 계단처럼 보이므로 OS 에 맡긴다.
    실패(Win10 등)하면 호출자가 사각 카드 + 헤어라인으로 그린다.
    """
    try:
        hwnd = _user32.GetParent(win.winfo_id()) or win.winfo_id()
        pref = ctypes.c_int(_DWMWCP_ROUND)
        if _dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd),
                                         _DWMWA_WINDOW_CORNER_PREFERENCE,
                                         ctypes.byref(pref), ctypes.sizeof(pref)) != 0:
            return False
        color = wintypes.DWORD(_colorref(OUTLINE))
        _dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), _DWMWA_BORDER_COLOR,
                                      ctypes.byref(color), ctypes.sizeof(color))
        return True
    except Exception:
        return False


def _lang_label(lang: str) -> str:
    """언어 버튼 문구 — '베트남어로 ▾'. 목표 언어 이름이 모두 '…어'로 끝나 '로'가 맞다."""
    return f"{lang}로 ▾"


class Popup:
    def __init__(self, root: tk.Tk, on_submit: Callable[[str], None],
                 on_close: Callable[[], None] | None = None,
                 languages: list[str] | None = None,
                 language: str = "",
                 on_language_change: Callable[[str], None] | None = None) -> None:
        self.root = root
        self.on_submit = on_submit
        self.on_close = on_close
        self.on_language_change = on_language_change
        self._submitted = False
        self._closed = False
        self._ready = False  # 생성 직후 포커스 흔들림으로 자동 닫히는 것 방지

        win = tk.Toplevel(root)
        self.win = win
        fam = font_family(root)
        self.fam = fam
        self.font_size = FONT_SIZE
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=CARD)

        # 마우스 커서 근처에 배치
        x, y = root.winfo_pointerxy()
        win.geometry(f"+{x + 12}+{y + 16}")

        # 카드: Canvas 에 외곽선 사각형을 그리고 내용을 임베드한다.
        # 모서리는 아래에서 Win11 DWM 으로 둥글게 하고, 실패하면 사각 + 헤어라인으로 둔다.
        self.pad = PAD
        canvas = tk.Canvas(win, bg=CARD, highlightthickness=0)
        canvas.pack()
        self.canvas = canvas
        # 크기/위치는 전적으로 geometry() 로만 제어한다(자동 전파가 위쪽 성장을
        # 덮어쓰지 않도록). 창 크기는 아래에서 명시적으로 지정한다.
        win.pack_propagate(False)

        # 내용은 canvas 의 자식으로 만들어 임베드 렌더링을 보장
        content = tk.Frame(canvas, bg=CARD)
        self.content = content

        # 멀티라인 입력란: 자동 줄바꿈(wrap)으로 두 줄 이상이 되면 높이를 키운다.
        # 팝업 자체가 입력창이므로 테두리 없이 카드 위에 바로 쓴다. MAX_LINES 까지 자란다.
        self.MAX_LINES = 6
        self._cur_lines = 1
        self.text = tk.Text(content, width=44, height=1, font=(fam, FONT_SIZE),
                            wrap="word", bg=CARD, fg=TEXT1,
                            insertbackground=TEXT1, relief="flat", bd=0,
                            highlightthickness=0, padx=0, pady=0, undo=True)
        self.text.pack(fill="x")

        # 상태/오류 줄 — 메시지가 있을 때만 보인다(set_status 에서 pack/forget).
        # 하단 줄과 분리하고 줄바꿈해서, 긴 오류가 팝업 폭을 밀어내지 않게 한다.
        self.status = tk.Label(content, text="", bg=CARD, fg=ACCENT,
                               font=(fam, META_SIZE), anchor="w", justify="left")

        self._sep = tk.Frame(content, bg=HAIRLINE, height=1)
        self._sep.pack(fill="x", pady=(PAD, 8))

        bottom = tk.Frame(content, bg=CARD)
        bottom.pack(fill="x")
        # 키 안내: [Enter] 번역  [Esc] 취소 — 키캡은 이 앱의 시그니처 요소
        hint = tk.Frame(bottom, bg=CARD)
        hint.pack(side="right")
        keys = (("Enter", "번역"), ("Esc", "취소"))
        if languages:
            keys = (("Shift+Tab", "언어"),) + keys
        for i, (key, label) in enumerate(keys):
            keycap(hint, key, fam).pack(side="left", padx=(12 if i else 0, 4))
            tk.Label(hint, text=label, bg=CARD, fg=TEXT3,
                     font=(fam, META_SIZE)).pack(side="left")
        # 목표 언어 드롭다운 — 여기서 바꾸면 이번 번역부터 바로 적용된다.
        self._lang_btn: tk.Menubutton | None = None
        if languages:
            self._lang_var = tk.StringVar(value=language)
            mb = tk.Menubutton(bottom, text=_lang_label(language), bg=CARD, fg=ACCENT,
                               font=(fam, META_SIZE), relief="flat", cursor="hand2",
                               activebackground=CARD, activeforeground=ACCENT,
                               takefocus=0, padx=0, pady=0, bd=0)
            menu = tk.Menu(mb, tearoff=0, font=(fam, META_SIZE + 1))
            for lang in languages:
                menu.add_radiobutton(label=lang, variable=self._lang_var,
                                     value=lang,
                                     command=lambda l=lang: self._set_language(l))
            mb.configure(menu=menu)
            mb.pack(side="left")
            self._lang_btn = mb

        content.update_idletasks()
        # 상태 줄은 입력란 폭에서 줄바꿈 — 폭이 늘어나 레이아웃이 깨지지 않는다.
        self.status.configure(wraplength=self.text.winfo_reqwidth())
        cw = content.winfo_reqwidth() + 2 * self.pad
        ch = content.winfo_reqheight() + 2 * self.pad
        canvas.config(width=cw, height=ch)
        self._poly = canvas.create_rectangle(0, 0, cw - 1, ch - 1,
                                             fill=CARD, outline=OUTLINE)
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
        # Shift+Tab = 목표 언어를 다음 것으로 순환. 위젯에 직접 묶어 "break" 해야
        # Text 클래스 기본 동작과 'all' 의 포커스 이동(tk_focusPrev)이 실행되지 않는다.
        self._languages = list(languages or [])
        self.text.bind("<Shift-Tab>", self._cycle_language)
        # tk 기본 바인딩('all' 태그)은 단독 Alt keyup/F10 을 메뉴 활성화로 해석해
        # 첫 Menubutton 메뉴를 자동으로 연다. inject.release_modifiers() 가 팝업 직전
        # Alt keyup 을 주입하므로 언어 메뉴가 저절로 열린다 → toplevel 바인딩이
        # 'all' 보다 먼저 실행되므로 "break" 로 차단한다.
        win.bind("<F10>", lambda e: "break")
        win.bind("<KeyRelease-Alt_L>", lambda e: "break")
        win.bind("<KeyRelease-Alt_R>", lambda e: "break")
        win.bind("<FocusOut>", self._on_focus_out)
        # 입력 변화 시 줄 수에 맞춰 입력란 높이를 위로 키운다.
        self.text.bind("<KeyRelease>", self._auto_grow)
        # 한글 조합 중 글꼴/크기가 위젯과 다르게 보이는 문제 방지:
        # IME 조합 글꼴을 입력칸 글꼴과 동일하게 지정
        self.text.bind("<FocusIn>", self._apply_ime_font)

        win.update_idletasks()
        win.deiconify()
        # Win11: OS 가 모서리를 둥글게 하고 외곽선도 그리므로 캔버스 외곽선은 숨긴다.
        if _round_native(win):
            canvas.itemconfigure(self._poly, outline=CARD)
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
        """입력란 높이 변화에 맞춰 카드/창 크기를 다시 그리고,
        아래 모서리를 고정한 채 창을 위로 키운다."""
        if not self.win.winfo_exists():
            return
        self.content.update_idletasks()
        cw = self.content.winfo_reqwidth() + 2 * self.pad
        ch = self.content.winfo_reqheight() + 2 * self.pad
        self.canvas.config(width=cw, height=ch)
        self.canvas.coords(self._poly, 0, 0, cw - 1, ch - 1)
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
        # 언어 메뉴를 열 때도 FocusOut 이 발생하므로 즉시 닫지 않고,
        # 잠시 뒤 전경 창이 '다른 프로세스'로 넘어갔을 때만 취소한다.
        if self._ready and not self._submitted:
            self.win.after(80, self._close_if_foreground_lost)

    def _close_if_foreground_lost(self) -> None:
        """전경 창이 우리 프로세스가 아니면(다른 앱 클릭) 팝업을 닫는다."""
        if self._closed or self._submitted or not self.win.winfo_exists():
            return
        try:
            fg = _user32.GetForegroundWindow()
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            if pid.value == os.getpid():
                return  # 팝업/언어 메뉴 등 우리 창이 여전히 전경 → 유지
        except Exception:
            pass
        self.close()

    def _set_language(self, lang: str) -> None:
        """언어 드롭다운 선택 — 표시 갱신 후 상위(App)에 알리고 입력란에 재포커스."""
        if self._lang_btn is not None:
            self._lang_btn.configure(text=_lang_label(lang))
        if self.on_language_change is not None:
            self.on_language_change(lang)
        self.text.focus_set()

    def _cycle_language(self, _event=None) -> str:
        """Shift+Tab — 목록의 다음 언어로 바꾼다(마지막 다음은 처음). 번역 중엔 무시."""
        if self._submitted or not self._languages:
            return "break"
        cur = self._lang_var.get()
        i = self._languages.index(cur) if cur in self._languages else -1
        nxt = self._languages[(i + 1) % len(self._languages)]
        self._lang_var.set(nxt)
        self._set_language(nxt)
        return "break"

    def _submit(self, _event=None) -> str:
        # "break" 를 돌려 Text 기본 동작(개행 삽입)을 막고 제출로만 처리한다.
        if self._submitted:
            return "break"
        text = self.text.get("1.0", "end-1c").strip()
        if not text:
            self.close()
            return "break"
        self._submitted = True
        # 번역 중에는 입력이 잠겼다는 것을 글자색으로 보여준다.
        self.text.configure(state="disabled", fg=TEXT3)
        self.set_status("번역 중…", ACCENT)
        self.on_submit(text)
        return "break"

    def set_status(self, message: str, color: str = ACCENT) -> None:
        """상태 줄을 보이거나(메시지 있음) 숨긴다. 줄이 생기면 팝업이 위로 자란다."""
        if not self.win.winfo_exists():
            return
        if len(message) > STATUS_MAX:
            message = message[:STATUS_MAX - 1] + "…"
        self.status.configure(text=message, fg=color)
        if message and not self.status.winfo_ismapped():
            self.status.pack(fill="x", pady=(8, 0), before=self._sep)
        elif not message:
            self.status.pack_forget()
        self._relayout()

    def show_error(self, message: str) -> None:
        """번역 실패 시: 오류 표시 후 다시 입력할 수 있게 되돌린다."""
        if not self.win.winfo_exists():
            return
        self._submitted = False
        self.text.configure(state="normal", fg=TEXT1)
        self.text.focus_set()
        self.set_status(message, ERR)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # 언어 메뉴가 열린 상태에서 전역 Esc 후크로 닫으면 Toplevel 만 destroy 되고
        # 네이티브 메뉴 창이 화면에 고아로 남는다 → 먼저 EndMenu() 로 닫는다.
        try:
            _user32.EndMenu()
        except Exception:
            pass
        if self.win.winfo_exists():
            self.win.destroy()
        if self.on_close is not None:
            self.on_close()
