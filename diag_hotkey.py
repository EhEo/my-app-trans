"""단축키 감지 진단 (L1 단독 테스트).

이 스크립트를 실행한 뒤, 아무 창에서나 Ctrl+Shift+Z 를 눌러보세요.
'HOTKEY DETECTED' 가 찍히면 keyboard 훅은 정상 → 문제는 팝업 표시/포커스 쪽.
한 번도 안 찍히면 keyboard 훅 문제 → 터미널을 '관리자 권한'으로 실행해 재시도.
"""
import time

import keyboard

count = 0


def hit():
    global count
    count += 1
    print(f"[{time.strftime('%H:%M:%S')}] HOTKEY DETECTED #{count}  (ctrl+shift+z)")


def main():
    print("=" * 60)
    print(__doc__)
    print("20초간 감지합니다. 지금 Ctrl+Shift+Z 를 눌러보세요...")
    print("=" * 60)
    keyboard.add_hotkey("ctrl+shift+z", hit)
    time.sleep(20)
    print("-" * 60)
    print(f"종료. 총 감지 횟수: {count}")
    if count == 0:
        print(">> 한 번도 감지 안 됨: keyboard 훅 미작동.")
        print(">> 해결: 이 터미널(PowerShell)을 '관리자 권한으로 실행' 후 다시 시도하세요.")
    else:
        print(">> 감지 정상! 단축키는 문제 없음 → 팝업 표시/포커스 쪽을 봐야 합니다.")


if __name__ == "__main__":
    main()
