"""자동 감지 결정 로직(_evaluate_focus) 단위 테스트.

App 전체를 초기화하지 않고(=Tk/설정파일 부작용 없이) 메서드 로직만 검증한다.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402

EDIT = main.auto.ControlType.EditControl
DOC = main.auto.ControlType.DocumentControl
NONEDIT = main.auto.ControlType.ButtonControl
MY_PID = 4321
OTHER_PID = 1000


class FakeCtrl:
    """ValuePattern 미노출 (GetValuePattern 없음) → 타입 폴백 경로를 탄다."""
    def __init__(self, pid, ctype, rid):
        self.ProcessId = pid
        self.ControlType = ctype
        self.ControlTypeName = "EditControl"
        self._rid = rid

    def GetRuntimeId(self):
        return self._rid


class _FakeVP:
    def __init__(self, read_only):
        self.IsReadOnly = read_only


class CtrlVP:
    """ValuePattern 을 노출하는 컨트롤 (read_only 지정)."""
    def __init__(self, pid, ctype, rid, read_only):
        self.ProcessId = pid
        self.ControlType = ctype
        self.ControlTypeName = "X"
        self._rid = rid
        self._ro = read_only

    def GetRuntimeId(self):
        return self._rid

    def GetValuePattern(self):
        return _FakeVP(self._ro)


class _FakeLegacy:
    def __init__(self, state):
        self.State = state


class CtrlText:
    """ValuePattern 없이 TextPattern 만 노출 (채팅/에디터 입력류). state=legacy."""
    def __init__(self, ctype, has_text, state, rid=(1,)):
        self.ProcessId = OTHER_PID
        self.ControlType = ctype
        self.ControlTypeName = "T"
        self._rid = rid
        self._has_text = has_text
        self._state = state

    def GetRuntimeId(self):
        return self._rid

    def GetValuePattern(self):
        return None

    def GetTextPattern(self):
        return object() if self._has_text else None

    def GetLegacyIAccessiblePattern(self):
        return _FakeLegacy(self._state)


def make_app(caret=None):
    app = main.App.__new__(main.App)  # __init__ 우회 (Tk/config 생략)
    app._popup_active = False
    app._auto_last_key = None
    app._current_field_key = None
    app._last_trigger = 0.0
    # 기본은 캐럿 폴백 비활성(테스트 결정성 확보). caret 인자로 키를 주면 활성.
    app._caret_key = lambda *a: caret
    return app


class TestEvaluateFocus(unittest.TestCase):
    def test_editable_new_field_triggers(self):
        app = make_app()
        c = FakeCtrl(OTHER_PID, EDIT, (1, 2, 3))
        self.assertTrue(app._evaluate_focus(c, MY_PID, now=1000.0))
        self.assertEqual(app._auto_last_key, ("rid", (1, 2, 3)))

    def test_same_field_not_retriggered(self):
        app = make_app()
        c = FakeCtrl(OTHER_PID, EDIT, (1, 2, 3))
        self.assertTrue(app._evaluate_focus(c, MY_PID, now=1000.0))
        # 쿨다운 지난 뒤에도 같은 필드면 재트리거 안 됨 (dedupe)
        self.assertFalse(app._evaluate_focus(c, MY_PID, now=1002.0))

    def test_cooldown_blocks_immediate_retrigger(self):
        app = make_app()
        c1 = FakeCtrl(OTHER_PID, EDIT, (1,))
        c2 = FakeCtrl(OTHER_PID, EDIT, (2,))
        self.assertTrue(app._evaluate_focus(c1, MY_PID, now=1000.0))
        # 다른 필드라도 1초 이내면 쿨다운으로 막힘
        self.assertFalse(app._evaluate_focus(c2, MY_PID, now=1000.5))
        # 쿨다운 지나면 다른 필드는 트리거
        self.assertTrue(app._evaluate_focus(c2, MY_PID, now=1001.5))

    def test_own_process_ignored_and_state_preserved(self):
        app = make_app()
        app._auto_last_key = ("rid", (9,))
        own = FakeCtrl(MY_PID, EDIT, (5,))
        self.assertFalse(app._evaluate_focus(own, MY_PID, now=5000.0))
        # 우리 팝업 포커스는 상태를 건드리지 않아야 함 (루프 방지의 핵심)
        self.assertEqual(app._auto_last_key, ("rid", (9,)))

    def test_non_editable_resets_keys(self):
        app = make_app()
        app._auto_last_key = ("rid", (9,))
        app._current_field_key = ("rid", (9,))
        c = FakeCtrl(OTHER_PID, NONEDIT, (7,))
        self.assertFalse(app._evaluate_focus(c, MY_PID, now=5000.0))
        self.assertIsNone(app._auto_last_key)
        self.assertIsNone(app._current_field_key)

    def test_popup_active_blocks_but_tracks_field(self):
        app = make_app()
        app._popup_active = True
        c = FakeCtrl(OTHER_PID, EDIT, (3, 4))
        self.assertFalse(app._evaluate_focus(c, MY_PID, now=9000.0))
        # 팝업 중에도 현재 필드는 기록되어야 (단축키 경로가 읽음)
        self.assertEqual(app._current_field_key, ("rid", (3, 4)))

    def test_click_clears_dedupe_when_auto_on_and_no_popup(self):
        app = make_app()
        app.cfg = {"auto_mode": True}
        app._auto_last_key = ("rid", (1, 2, 3))
        app._last_trigger = 9999.0
        app._on_click()
        # 클릭 → 같은 필드 재트리거 가능하도록 키/쿨다운 초기화
        self.assertIsNone(app._auto_last_key)
        self.assertEqual(app._last_trigger, 0.0)

    def test_click_ignored_while_popup_active(self):
        app = make_app()
        app.cfg = {"auto_mode": True}
        app._popup_active = True
        app._auto_last_key = ("rid", (1, 2, 3))
        app._on_click()
        # 팝업이 떠 있는 동안의 클릭은 무시 (붙여넣기 후 재팝업 방지)
        self.assertEqual(app._auto_last_key, ("rid", (1, 2, 3)))

    def test_click_ignored_when_auto_off(self):
        app = make_app()
        app.cfg = {"auto_mode": False}
        app._auto_last_key = ("rid", (1, 2, 3))
        app._on_click()
        self.assertEqual(app._auto_last_key, ("rid", (1, 2, 3)))

    def test_click_retrigger_full_cycle(self):
        """필드에 팝업 → 같은 필드는 억제 → 클릭 후 재트리거 되는 전체 흐름."""
        app = make_app()
        app.cfg = {"auto_mode": True}
        c = FakeCtrl(OTHER_PID, EDIT, (1, 2, 3))
        self.assertTrue(app._evaluate_focus(c, MY_PID, now=1000.0))
        # 같은 필드 재포커스 → 억제
        self.assertFalse(app._evaluate_focus(c, MY_PID, now=1002.0))
        # 마우스 다시 클릭 → 초기화
        app._on_click()
        # 같은 필드라도 다시 팝업
        self.assertTrue(app._evaluate_focus(c, MY_PID, now=1003.0))

    # --- 편집 가능 판정 (_is_editable) ---
    def test_editable_value_pattern_not_readonly(self):
        # 어떤 타입이든 ValuePattern 비-읽기전용 → 입력란 (메신저 등)
        c = CtrlVP(OTHER_PID, NONEDIT, (1,), read_only=False)
        self.assertTrue(main.App._is_editable(c))

    def test_readonly_document_excluded(self):
        # ValuePattern 읽기전용 → 제외 (브라우저 탭 클릭 시 읽기전용 페이지)
        c = CtrlVP(OTHER_PID, DOC, (1,), read_only=True)
        self.assertFalse(main.App._is_editable(c))

    def test_document_without_value_pattern_excluded(self):
        # ValuePattern 없는 Document → 제외 (읽기전용 웹페이지)
        c = FakeCtrl(OTHER_PID, DOC, (1,))
        self.assertFalse(main.App._is_editable(c))

    def test_edit_without_value_pattern_included(self):
        # ValuePattern 없는 EditControl → 포함 (타입 폴백)
        c = FakeCtrl(OTHER_PID, EDIT, (1,))
        self.assertTrue(main.App._is_editable(c))

    def test_button_excluded(self):
        c = FakeCtrl(OTHER_PID, NONEDIT, (1,))
        self.assertFalse(main.App._is_editable(c))

    def test_editable_document_with_value_pattern_included(self):
        # 메모장처럼 ValuePattern(비-읽기전용) 가진 Document → 포함
        c = CtrlVP(OTHER_PID, DOC, (1,), read_only=False)
        self.assertTrue(main.App._is_editable(c))

    def test_textcontrol_with_textpattern_included(self):
        # TextControl + TextPattern + 읽기전용 아님 → 입력란 (채팅/에디터)
        c = CtrlText(main.auto.ControlType.TextControl, has_text=True, state=0x100004)
        self.assertTrue(main.App._is_editable(c))

    def test_textcontrol_readonly_excluded(self):
        # TextControl 인데 legacy READONLY → 제외 (라벨/읽기전용 본문)
        c = CtrlText(main.auto.ControlType.TextControl, has_text=True, state=0x40)
        self.assertFalse(main.App._is_editable(c))

    def test_textcontrol_without_textpattern_excluded(self):
        c = CtrlText(main.auto.ControlType.TextControl, has_text=False, state=0x100004)
        self.assertFalse(main.App._is_editable(c))

    # --- 캐럿 폴백 (_caret_key) ---
    def test_caret_fallback_triggers_when_uia_blind(self):
        # UIA가 입력란을 못 보는 앱(c=None 또는 비편집)이라도 캐럿이 있으면 트리거
        app = make_app(caret=("caret", 111, 222))
        self.assertTrue(app._evaluate_focus(None, MY_PID, now=1000.0))
        self.assertEqual(app._auto_last_key, ("caret", 111, 222))

    def test_caret_fallback_dedupe(self):
        app = make_app(caret=("caret", 111, 222))
        self.assertTrue(app._evaluate_focus(None, MY_PID, now=1000.0))
        # 같은 캐럿 필드 → 재트리거 안 됨
        self.assertFalse(app._evaluate_focus(None, MY_PID, now=1002.0))

    def test_uia_takes_priority_over_caret(self):
        # UIA가 편집 가능으로 보면 캐럿이 아니라 UIA 키를 쓴다
        app = make_app(caret=("caret", 9, 9))
        c = FakeCtrl(OTHER_PID, EDIT, (1, 2, 3))
        self.assertTrue(app._evaluate_focus(c, MY_PID, now=1000.0))
        self.assertEqual(app._auto_last_key, ("rid", (1, 2, 3)))

    def test_no_caret_no_uia_resets(self):
        app = make_app(caret=None)
        app._auto_last_key = ("rid", (9,))
        self.assertFalse(app._evaluate_focus(None, MY_PID, now=1000.0))
        self.assertIsNone(app._auto_last_key)

    def test_field_key_falls_back_to_hwnd(self):
        class NoRid:
            ProcessId = OTHER_PID
            NativeWindowHandle = 777

            def GetRuntimeId(self):
                raise RuntimeError("no runtime id")

        self.assertEqual(main.App._field_key(NoRid()), ("hwnd", OTHER_PID, 777))


if __name__ == "__main__":
    unittest.main()
