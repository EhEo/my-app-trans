"""붙여넣기(주입) 자체 테스트 — 회원님이 직접 보고 확인하는 용도.

실행하면 6초 카운트다운이 시작됩니다. 그 사이에 메모장이나 브라우저 입력창 등
'글을 넣고 싶은 곳'을 클릭해 커서를 두세요. 카운트다운이 끝나면 그 창에
샘플 문장이 자동으로 붙여넣어집니다.

  python selftest_inject.py
"""
import ctypes
import time

from inject import paste_into

user32 = ctypes.windll.user32

SAMPLE = "你好 — 붙여넣기 테스트 OK ✓"


def main() -> None:
    print(__doc__)
    for i in range(6, 0, -1):
        print(f"  {i}초 후 현재 포커스된 창에 붙여넣습니다... (지금 대상 창을 클릭하세요)")
        time.sleep(1)
    hwnd = user32.GetForegroundWindow()
    print(f"대상 창 핸들: {hwnd}")
    paste_into(hwnd, SAMPLE)
    print("완료. 대상 창에 문장이 들어갔는지 확인하세요.")


if __name__ == "__main__":
    main()
