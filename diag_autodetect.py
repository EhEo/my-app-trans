"""자동 감지 진단 — 포커스된 컨트롤의 타입/패턴/판정을 자세히 보여준다.

실행한 뒤, 확인할 앱(메신저/브라우저/에디터 등)의 입력란을 클릭해 보세요.
'감지=True' 면 자동 감지 모드에서 그 입력란에 팝업이 뜹니다.

특히 '클릭해도 안 뜨는 입력란'을 클릭했을 때 찍히는 줄을 그대로 알려주시면
판정 기준을 그 앱에 맞게 넓혀드립니다.

  python diag_autodetect.py
"""
import os
import time

import uiautomation as auto

import main

# MSAA(legacy) state 비트
ST_READONLY = 0x40
ST_FOCUSABLE = 0x100000


def value_info(c):
    try:
        vp = c.GetValuePattern()
    except Exception:
        return "Value=X"
    if vp is None:
        return "Value=X"
    try:
        return f"Value=O(읽기전용={int(bool(vp.IsReadOnly))})"
    except Exception:
        return "Value=O(읽기전용=?)"


def text_info(c):
    try:
        return "Text=O" if c.GetTextPattern() is not None else "Text=X"
    except Exception:
        return "Text=X"


def legacy_info(c):
    try:
        lg = c.GetLegacyIAccessiblePattern()
        role = getattr(lg, "Role", None)
        state = getattr(lg, "State", 0) or 0
        ro = "읽기전용" if state & ST_READONLY else "쓰기가능"
        fo = "포커스가능" if state & ST_FOCUSABLE else "포커스불가"
        return f"role={role} state={hex(state)}({ro},{fo})"
    except Exception:
        return "legacy=X"


def main_diag():
    my_pid = os.getpid()
    print("=" * 78)
    print(__doc__)
    print("25초간 0.5초마다 포커스된 컨트롤을 출력합니다...")
    print("=" * 78)
    with auto.UIAutomationInitializerInThread(debug=False):
        auto.SetGlobalSearchTimeout(0.5)
        end = time.time() + 25
        last = None
        while time.time() < end:
            time.sleep(0.5)
            try:
                c = auto.GetFocusedControl()
                if not c or c.ProcessId == my_pid:
                    continue
                verdict = main.App._is_editable(c)
                line = (f"{c.ControlTypeName:16s} | {value_info(c):20s} | {text_info(c):7s} "
                        f"| {legacy_info(c):34s} | 감지={verdict}")
                if line != last:
                    mark = "  <== 입력란 ✓" if verdict else ""
                    print(f"[{time.strftime('%H:%M:%S')}] {line}{mark}")
                    last = line
            except Exception as e:
                print("err:", e)
    print("-" * 78)
    print("끝. 안 뜨던 입력란의 줄을 알려주세요 (특히 Value/Text/state 부분).")


if __name__ == "__main__":
    main_diag()
