"""한국어 -> 다국어 IME 번역 입력기 — 진입점.

트레이 상주 + 전역 단축키 + 마우스 근처 팝업 + 클립보드 주입.

스레드 모델:
- tkinter는 메인 스레드에서 mainloop 실행 (숨겨진 root).
- 전역 단축키(hotkey 스레드), 트레이(pystray 스레드), 번역/주입(워커 스레드)에서
  발생하는 모든 UI 작업은 thread-safe 큐에 콜백으로 넣고, 메인 스레드의 pump 루프가
  실행한다. (tkinter는 스레드 안전하지 않으므로 단일 창구로 일원화)
"""
from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes

import mouse
import pystray
import uiautomation as auto
from PIL import Image, ImageDraw, ImageFont

from config import LANGUAGES, load_config, save_config
from hotkey import HotkeyManager, parse_hotkey
from inject import paste_into, release_modifiers
from popup import Popup
from settings_window import SettingsWindow
from translator import TranslationError, prewarm, translate

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 단일 인스턴스 체크: OpenMutex 먼저 시도 → 존재하면 다른 인스턴스, 없으면 CreateMutex.
# (GetLastError 기반 판정은 PyInstaller onefile 환경에서 errno 가 reset 되어
#  중복 감지를 놓친다. OpenMutex 의 NULL/HANDLE 반환은 errno 와 무관해 안정적.)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.restype = wintypes.HANDLE
_k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenMutexW.restype = wintypes.HANDLE
_k32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]

# 단일 인스턴스 보장용 뮤텍스 핸들 — 프로세스가 살아있는 동안 열어 두기 위해
# 모듈 전역으로 참조를 유지한다(닫히면 다른 인스턴스가 실행될 수 있음).
_instance_mutex = None


def acquire_single_instance(name: str = "my-app-trans-singleton") -> bool:
    """이 프로세스가 첫 인스턴스이면 True, 이미 실행 중이면 False.

    원자성 보장: OpenMutexW 는 빠른-실패 최적화일 뿐, 실제 race-free 판정은
    CreateMutexW 의 GetLastError(ERROR_ALREADY_EXISTS) 로 한다. 두 프로세스가
    동시에 출발해도 OS 는 둘 중 하나에만 새 mutex 를 만들어 주고, 진 쪽은
    ALREADY_EXISTS 를 돌려받는다.
    """
    global _instance_mutex
    SYNCHRONIZE = 0x00100000
    ERROR_ALREADY_EXISTS = 183

    # 빠른 경로: 이미 다른 인스턴스가 있으면 즉시 종료
    existing = _k32.OpenMutexW(SYNCHRONIZE, False, name)
    if existing:
        _k32.CloseHandle(existing)
        return False

    # 원자적 경로: 생성과 동시에 이미 있었는지 검사 (race 안전)
    _instance_mutex = _k32.CreateMutexW(None, False, name)
    if not _instance_mutex:
        return False
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    return True


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


DEBUG = "--debug" in sys.argv

# MSAA(legacy IAccessible) state 비트
ST_READONLY = 0x40


def log(msg: str) -> None:
    if DEBUG:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class App:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.q: "queue.Queue" = queue.Queue()

        self.root = tk.Tk()
        self.root.withdraw()  # 보이지 않는 루트

        self._popup: Popup | None = None
        self._settings: SettingsWindow | None = None
        # RegisterHotKey 엔진: id=1 은 번역 단축키, id=2 는 팝업 Esc(열림 동안만 등록).
        self._hotkeys = HotkeyManager()
        self._hotkeys.set_callback(1, self._on_hotkey)
        self._hotkeys.set_callback(2, lambda: self.post(self._cancel_popup))
        self._hotkeys.start()
        self.icon: pystray.Icon | None = None

        # 자동 감지 모드 상태
        self._auto_running = False
        self._auto_thread: threading.Thread | None = None
        self._last_trigger = 0.0
        self._popup_active = False        # 메인 스레드에서만 갱신 (스레드 안전)
        self._auto_last_key = None        # 이미 팝업을 띄운 필드 (중복 방지)
        self._current_field_key = None    # 폴링이 갱신하는 현재 포커스 필드 키
        # 단축키 재진입 방지 — 콜백 진입 즉시 set, 팝업 닫힐 때 clear.
        # 키 자동반복으로 콜백이 큐잉되어 두 번째 콜이 첫 팝업을 target 으로 잡는 버그 방지.
        self._hotkey_inflight = False

    # --- 메인 스레드 큐 ---
    def post(self, fn) -> None:
        """다른 스레드에서 메인 스레드 작업을 예약한다."""
        self.q.put(fn)

    def _pump(self) -> None:
        try:
            while True:
                fn = self.q.get_nowait()
                try:
                    fn()
                except Exception as e:  # 개별 콜백 오류로 루프가 죽지 않도록
                    print("[pump] error:", e)
        except queue.Empty:
            pass
        self.root.after(50, self._pump)

    # --- 팝업 / 번역 / 주입 ---
    def _on_hotkey(self) -> None:
        """전역 단축키 콜백 (HotkeyManager 스레드에서 실행).

        재진입 가드: 키 자동반복이나 이미 떠 있는 팝업 상황에서 콜백이
        중복 큐잉되어 두 번째 콜이 첫 팝업을 target 으로 잡는 버그를 막는다.
        modifier 해제 대기 루프는 이제 hotkey 전용 스레드에서 돌므로 시스템 입력을
        블로킹하지 않는다. modifier 가 떼지기를 짧게 기다린 뒤 (auto-repeat 으로 다시
        down 되는 것 방지) 메인 스레드로 한 번만 show_popup 을 예약한다.
        """
        if self._hotkey_inflight or self._popup_active:
            log("L1: 단축키 무시 (이미 in-flight 또는 팝업 활성)")
            return
        self._hotkey_inflight = True
        deadline = time.time() + 0.5
        while time.time() < deadline:
            ctrl = user32.GetAsyncKeyState(0x11) & 0x8000
            alt = user32.GetAsyncKeyState(0x12) & 0x8000
            shift = user32.GetAsyncKeyState(0x10) & 0x8000
            if not (ctrl or alt or shift):
                break
            time.sleep(0.02)
        log("L1: 단축키 감지됨 -> 큐에 show_popup 예약")
        self.post(self.show_popup)

    def show_popup(self) -> None:
        # 팝업을 띄우기 직전의 전경 창 = 글을 넣을 대상
        target_hwnd = user32.GetForegroundWindow()
        log(f"L3/L4: show_popup 실행 (대상 hwnd={target_hwnd})")
        # 사용자가 타이핑하는 동안 번역 서버 연결(DNS/TCP/TLS)을 미리 맺어 둔다.
        threading.Thread(target=prewarm, daemon=True).start()
        try:
            # 단축키의 Ctrl/Alt 가 OS 상태에 남아 있으면 팝업 입력란에서
            # 한글 첫 글자가 단축키로 가로채여 입력이 안 된다. 먼저 강제 해제.
            release_modifiers()
            if self._popup is not None and self._popup.win.winfo_exists():
                self._popup.close()
            # 자동/단축키 어느 경로든: 현재 필드를 '처리됨'으로 기록 → 붙여넣기 후 재팝업 방지
            self._popup_active = True
            self._auto_last_key = self._current_field_key
            self._last_trigger = time.time()
            self._popup = Popup(
                self.root,
                on_submit=lambda text: self._start_translation(self._popup, text, target_hwnd),
                on_close=self._on_popup_closed,
                languages=list(LANGUAGES.keys()),
                language=self.cfg.get("target_language", "영어"),
                on_language_change=self._set_target_language,
            )
            self._register_esc()  # Esc가 하위 앱(메신저 등)으로 새지 않게 전역 가로채기
            log("L4: 팝업 생성 완료")
        except Exception:
            # 예외 시 플래그가 영구 래치되면 이후 단축키가 영영 무반응 → 복구 후 재-raise.
            self._popup_active = False
            self._hotkey_inflight = False
            raise

    def _register_esc(self) -> None:
        """팝업이 열린 동안 Esc를 전역에서 가로채 팝업만 닫는다.

        팝업이 키보드 포커스를 못 가졌거나 하위 앱이 Esc를 선점하는 경우에도
        Esc가 그 앱(메신저 등)으로 전달돼 창이 닫히는 문제를 막는다. RegisterHotKey
        는 등록된 동안 시스템 전체 Esc 를 소비하므로 기존 suppress=True 와 동일하다.
        """
        self._hotkeys.register(2, 0, 0x1B)  # 0x1B = VK_ESCAPE

    def _unregister_esc(self) -> None:
        self._hotkeys.unregister(2)

    def _cancel_popup(self) -> None:
        if self._popup is not None and self._popup.win.winfo_exists():
            self._popup.close()

    def _on_popup_closed(self) -> None:
        """팝업이 닫힐 때(메인 스레드) 호출 — 자동 감지 재개를 위한 상태 갱신."""
        self._unregister_esc()
        self._popup_active = False
        self._last_trigger = time.time()  # 닫힌 직후 쿨다운(붙여넣기 중 재팝업 방지)
        self._hotkey_inflight = False     # 다음 단축키 콜백 허용

    def _on_click(self, *_args) -> None:
        """전역 좌클릭 콜백 (mouse 스레드). tkinter 미접촉 — 플래그만 갱신.

        자동 모드에서 입력란을 '다시 클릭'하면 같은 필드라도 팝업이 다시 뜨도록
        중복방지 키와 쿨다운을 초기화한다. 팝업이 떠 있는 동안의 클릭은 무시하여
        (예: 팝업 안 클릭, 붙여넣기 직후) 원치 않는 재팝업을 막는다.
        """
        if not self.cfg.get("auto_mode") or self._popup_active:
            return
        self._auto_last_key = None
        self._last_trigger = 0.0

    def _set_target_language(self, lang: str) -> None:
        """팝업에서 목표 언어 변경 — 새 기본값으로 저장해 이후에도 유지한다."""
        self.cfg["target_language"] = lang
        save_config(self.cfg)
        log(f"목표 언어 변경: {lang}")

    def _start_translation(self, popup: Popup, text: str, target_hwnd: int) -> None:
        cfg = self.cfg
        t_submit = time.perf_counter()  # Enter 시점 — 단계별 지연 계측 기준

        def worker() -> None:
            timings: dict = {}
            try:
                translated = translate(
                    text, cfg["target_language"],
                    cfg["openrouter_api_key"], cfg["model"],
                    timings=timings,
                )
            except TranslationError as e:
                log(f"TIME: 번역 실패 {timings}")
                self.post(lambda: popup.show_error(str(e)))
                return
            except Exception as e:  # 예기치 못한 오류도 사용자에게 표시
                self.post(lambda: popup.show_error(f"오류: {e}"))
                return

            log(f"TIME: 번역 {timings}")
            log(f"번역결과({cfg.get('target_language')}): {translated[:50]!r}")
            if not translated:
                self.post(popup.close)
                return

            # 순서 보장: 메인 스레드에서 팝업을 '먼저 닫고' → 포커스 복귀 대기 → 주입.
            # (즉시 주입하면 팝업이 아직 떠 있어 Ctrl+V가 팝업으로 들어가는 경합 발생)
            self.post(lambda: self._finish_and_paste(popup, target_hwnd, translated, t_submit))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_and_paste(self, popup: Popup, target_hwnd: int, text: str,
                          t_submit: float) -> None:
        """메인 스레드: 팝업을 닫은 뒤, 포커스가 대상으로 돌아가면 주입한다."""
        popup.close()  # 먼저 확실히 닫아 포커스를 대상 창으로 반환
        # 주입은 sleep 을 포함하므로 워커 스레드에서, 포커스 복귀 후(150ms) 실행
        self.root.after(150, lambda: threading.Thread(
            target=self._paste_worker, args=(target_hwnd, text, t_submit),
            daemon=True).start())

    @staticmethod
    def _paste_worker(target_hwnd: int, text: str, t_submit: float) -> None:
        log(f"주입 시작(hwnd={target_hwnd}): {text[:50]!r}")
        log(f"TIME: Enter→주입 시작 {(time.perf_counter() - t_submit) * 1000:.0f}ms")
        try:
            paste_into(target_hwnd, text)
        except Exception as e:
            print("[inject] error:", e)
        # paste_into 는 Ctrl+V 뒤 클립보드 복원 대기(paste_delay)까지 포함한다.
        log(f"TIME: Enter→주입 완료 {(time.perf_counter() - t_submit) * 1000:.0f}ms")

    @staticmethod
    def _is_editable(c) -> bool:
        """컨트롤이 '실제로 편집 가능한 텍스트 입력란'인지 판정.

        타입(Edit/Document) 대신 UIA 패턴으로 본다:
        - ValuePattern 이 있고 읽기 전용이 아니면 편집 가능 (검색창/주소창/대부분 입력란)
        - ValuePattern 이 없으면 EditControl 만 편집 가능으로 간주
        이렇게 하면 읽기 전용 웹페이지(Document)·버튼·탭은 제외되고
        (탭/아이콘 클릭 시 오발동 방지), ValuePattern 을 노출하는 다양한 앱의
        입력란은 폭넓게 잡힌다.
        """
        # 1) ValuePattern: 가장 명확 (검색창/주소창/대부분 입력란/메모장)
        try:
            vp = c.GetValuePattern()
        except Exception:
            vp = None
        if vp is not None:
            try:
                return not bool(vp.IsReadOnly)
            except Exception:
                return True
        # 2) 타입/패턴 폴백
        try:
            ct = c.ControlType
        except Exception:
            return False
        if ct == auto.ControlType.EditControl:
            return True
        # 일부 채팅/에디터 입력은 TextControl + TextPattern 으로만 노출됨.
        # 읽기전용(라벨·읽기전용 본문)은 제외 → 페이지/탭 오발동 방지.
        if ct == auto.ControlType.TextControl:
            try:
                if c.GetTextPattern() is None:
                    return False
            except Exception:
                return False
            try:
                lg = c.GetLegacyIAccessiblePattern()
                if (getattr(lg, "State", 0) or 0) & ST_READONLY:
                    return False
            except Exception:
                pass
            return True
        return False

    @staticmethod
    def _field_key(c):
        """포커스된 컨트롤의 안정적인 식별자. RuntimeId 우선(붙여넣기에도 불변)."""
        try:
            rid = c.GetRuntimeId()
            if rid:
                return ("rid", tuple(rid))
        except Exception:
            pass
        try:
            return ("hwnd", c.ProcessId, c.NativeWindowHandle)
        except Exception:
            return None

    # --- 자동 감지 모드 (텍스트 입력란 포커스 시 자동 팝업) ---
    def _auto_loop(self) -> None:
        """백그라운드 폴링: 편집 가능한 컨트롤이 포커스되면 팝업을 띄운다.

        스레드 안전: 이 메서드는 tkinter 객체를 절대 만지지 않는다. 팝업 상태는
        메인 스레드가 갱신하는 self._popup_active(bool)만 읽고, 실제 팝업 생성은
        self.post()로 메인 스레드에 위임한다.

        - 자기 프로세스(팝업) 이벤트는 무시 → 무한 루프 방지
        - 같은 필드는 한 번만 트리거 (비편집 영역으로 갔다 와야 재트리거)
        - 팝업이 떠 있거나 직후(쿨다운)에는 트리거하지 않음
        - 단축키 경로와 키 추적을 공유 → 붙여넣기 후 같은 필드 재팝업 방지
        """
        my_pid = os.getpid()
        with auto.UIAutomationInitializerInThread(debug=False):
            auto.SetGlobalSearchTimeout(0.5)
            while self._auto_running:
                time.sleep(0.4)
                if not self.cfg.get("auto_mode"):
                    self._current_field_key = None
                    self._auto_last_key = None
                    continue
                try:
                    c = auto.GetFocusedControl()
                except Exception:
                    continue
                if self._evaluate_focus(c, my_pid, time.time()):
                    log(f"AUTO: 입력란 감지 {c.ControlTypeName} pid={c.ProcessId} -> 팝업")
                    self.post(self.show_popup)

    def _caret_key(self, my_pid: int):
        """전경 창에 텍스트 캐럿(시스템 커서)이 있으면 그 필드 키를 반환.

        UIA가 입력란을 노출하지 않는 앱(WeChat 등)에서도 '커서가 있으면 입력 중'을
        감지하는 폴백. 자기 프로세스(팝업)·캐럿 없음·읽기전용 페이지(커서 없음)는 제외.
        """
        try:
            fg = user32.GetForegroundWindow()
            if not fg:
                return None
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            if not tid or pid.value == my_pid:
                return None
            info = GUITHREADINFO()
            info.cbSize = ctypes.sizeof(GUITHREADINFO)
            if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
                return None
            if not info.hwndCaret:
                return None
            return ("caret", int(fg), int(info.hwndCaret))
        except Exception:
            return None

    def _detect(self, c, my_pid: int):
        """(editable, key) 반환. UIA 우선, 실패 시 캐럿 폴백.

        우리 팝업(자기 프로세스)이 포커스면 None 반환 → 호출자는 상태를 건드리지
        않고 무시한다(무한 루프 방지).
        """
        try:
            if c and c.ProcessId == my_pid:
                return None
        except Exception:
            pass
        try:
            if c and self._is_editable(c):
                return True, self._field_key(c)
        except Exception:
            pass
        ckey = self._caret_key(my_pid)
        if ckey is not None:
            return True, ckey
        return False, None

    def _apply_focus(self, editable: bool, key, now: float) -> bool:
        """(editable, key)로 팝업 트리거 여부 결정 + 상태 갱신 (순수 로직, 테스트 대상)."""
        if not editable:
            self._current_field_key = None
            self._auto_last_key = None
            return False
        self._current_field_key = key  # 단축키 경로가 읽을 수 있게 기록
        if self._popup_active or (now - self._last_trigger < 1.0):
            return False
        if key is None or key == self._auto_last_key:
            return False
        self._auto_last_key = key
        self._last_trigger = now
        return True

    def _evaluate_focus(self, c, my_pid: int, now: float) -> bool:
        """포커스된 컨트롤을 평가해 팝업을 띄울지 결정하고 상태를 갱신한다.

        UIA(_is_editable) → 캐럿(_caret_key) 폴백 순으로 입력란을 판정한다.
        True 면 호출자가 메인 스레드에 show_popup 을 위임한다.
        """
        det = self._detect(c, my_pid)
        if det is None:
            return False  # 우리 팝업이 포커스 → 상태 유지하고 무시
        editable, key = det
        return self._apply_focus(editable, key, now)

    # --- 설정 ---
    def show_settings(self) -> None:
        if self._settings is not None and self._settings.win.winfo_exists():
            self._settings.win.lift()
            self._settings.win.focus_force()
            return
        self._settings = SettingsWindow(self.root, self.cfg, on_save=self.apply_settings)

    def apply_settings(self, new_cfg: dict) -> str:
        """설정을 적용하고 결과 메시지를 돌려준다(설정창에 표시됨)."""
        old_hotkey = self.cfg.get("hotkey")
        self.cfg = new_cfg
        save_config(new_cfg)

        if new_cfg.get("hotkey") == old_hotkey:
            return "저장되었습니다."

        if self._register_hotkey():
            return f"저장됨 · 단축키: {new_cfg.get('hotkey')}"

        # 새 단축키 등록 실패 → 이전 단축키로 자동 복구 (단축키가 없어지지 않게)
        bad = new_cfg.get("hotkey")
        self.cfg = dict(new_cfg, hotkey=old_hotkey)
        save_config(self.cfg)
        self._register_hotkey()
        return f"'{bad}' 등록 실패(충돌/형식 오류) → 이전 '{old_hotkey}' 유지"

    # --- 전역 단축키 ---
    def _register_hotkey(self) -> bool:
        """현재 설정의 단축키를 등록한다. 성공 여부를 반환.

        파싱 실패(형식 오류)나 등록 실패(다른 앱 점유 = error 1409) 시 False 를
        돌려주면 apply_settings 가 이전 단축키로 자동 복구한다.
        """
        self._hotkeys.unregister(1)  # 재등록 전 기존 id=1 해제
        hk = self.cfg.get("hotkey") or "ctrl+alt+space"
        parsed = parse_hotkey(hk)
        if parsed is None:
            print(f"[hotkey] '{hk}' 파싱 실패 (형식 오류)")
            if self.icon is not None:
                self.icon.notify(f"단축키 '{hk}' 형식 오류", "번역 입력기")
            return False
        mods, vk = parsed
        if self._hotkeys.register(1, mods, vk):
            log(f"단축키 '{hk}' 등록 성공")
            return True
        print(f"[hotkey] '{hk}' 등록 실패 (충돌 — 다른 앱이 점유 중일 수 있음)")
        if self.icon is not None:
            self.icon.notify(f"단축키 '{hk}' 등록 실패", "번역 입력기")
        return False

    # --- 트레이 ---
    @staticmethod
    def _icon_font(size: int) -> ImageFont.FreeTypeFont:
        """한글+라틴을 또렷하게 그릴 TrueType 글꼴을 로드한다.

        Windows 기본 탑재 글꼴(맑은 고딕 → Segoe UI)을 순서대로 시도하고,
        모두 실패하면 PIL 기본 비트맵 글꼴로 떨어진다.
        """
        win = os.environ.get("WINDIR", r"C:\Windows")
        for name in ("malgunbd.ttf", "malgun.ttf", "segoeuib.ttf", "segoeui.ttf"):
            try:
                return ImageFont.truetype(os.path.join(win, "Fonts", name), size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _make_icon_image(self) -> Image.Image:
        """번역기 아이콘 — 겹친 두 카드에 '가'와 'A'를 새긴 형태.

        고해상도(256px)로 그려 트레이에서 축소될 때 매끄럽게 보이게 한다.
        """
        S = 256
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        blue = "#1a73e8"
        font = self._icon_font(86)

        # 뒤 카드(파랑) + 한글 '가'
        d.rounded_rectangle((24, 24, 150, 150), radius=24, fill=blue)
        d.text((87, 90), "가", font=font, fill="#ffffff", anchor="mm")

        # 앞 카드(흰색, 파란 테두리) + 라틴 'A'
        d.rounded_rectangle((106, 106, 232, 232), radius=24,
                            fill="#ffffff", outline=blue, width=6)
        d.text((169, 172), "A", font=font, fill=blue, anchor="mm")
        return img

    def _build_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("설정 열기", lambda: self.post(self.show_settings)),
            pystray.MenuItem("종료", lambda: self.post(self.quit)),
        )
        self.icon = pystray.Icon(
            "my-app-trans", self._make_icon_image(), "번역 입력기", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    # --- 종료 ---
    def quit(self) -> None:
        self._auto_running = False
        self._hotkeys.stop()
        try:
            mouse.unhook_all()
        except Exception:
            pass
        if self.icon is not None:
            self.icon.stop()
        self.root.quit()

    # --- 실행 ---
    def run(self) -> None:
        if DEBUG:
            import inject as _inject
            _inject.DEBUG = True
        self._register_hotkey()
        self._build_tray()
        self._auto_running = True
        self._auto_thread = threading.Thread(target=self._auto_loop, daemon=True)
        self._auto_thread.start()
        try:
            mouse.on_button(self._on_click, buttons=("left",), types=("down",))
        except Exception as e:
            print(f"[mouse] 클릭 감지 등록 실패: {e}")
        self.root.after(50, self._pump)
        if not self.cfg.get("openrouter_api_key"):
            print("경고: OpenRouter API 키가 설정되어 있지 않습니다. 트레이 > 설정에서 입력하세요.")
        auto_on = "켜짐" if self.cfg.get("auto_mode") else "꺼짐"
        print(f"번역 입력기 실행 중. 단축키: {self.cfg.get('hotkey')} | 목표 언어: {self.cfg.get('target_language')} | 자동감지: {auto_on}")
        self.root.mainloop()


if __name__ == "__main__":
    if not acquire_single_instance():
        # 이미 실행 중 — 콘솔이 없으므로 메시지박스로 알리고 종료한다.
        # 0x40=MB_ICONINFORMATION, 0x10000=MB_SETFOREGROUND, 0x40000=MB_TOPMOST
        user32.MessageBoxW(
            0,
            "번역 입력기가 이미 실행 중입니다.\n작업 표시줄의 트레이 아이콘을 확인하세요.",
            "번역 입력기",
            0x40 | 0x10000 | 0x40000,
        )
        sys.exit(0)
    App().run()
