# 한국어 → 다국어 IME 번역 입력기 설계

작성일: 2026-06-02

## 개요

윈도우 트레이에 상주하는 입력기(IME 유사) 프로그램. 전역 단축키를 누르면 마우스
커서 근처에 작은 입력 팝업이 뜨고, 사용자가 글을 입력하면 OpenRouter LLM이 설정된
목표 언어로 번역하여, 원래 포커스가 있던 입력란에 자동으로 붙여넣는다.

중국어 병음 입력처럼 "한국어를 입력하면 선택한 언어로 변환되어 입력"되는 경험을
목표로 한다. 단, 진짜 TSF 기반 IME 대신 **전역 단축키 + 팝업 + 클립보드 주입**
방식으로 구현하여 모든 앱에서 안정적으로 동작하게 한다.

## 핵심 결정 사항

- **번역 엔진:** OpenRouter (OpenAI 호환 API), LLM 번역
- **기본 모델:** `google/gemini-2.0-flash-001` (저렴 + 다국어 번역 양호), 설정에서 변경 가능
- **목표 언어:** 영어 / 중국어 / 베트남어 / 한국어 중 1개 선택 (트레이 설정)
- **입력 언어:** 자동 감지 (무엇을 입력하든 목표 언어로 번역)
- **팝업 위치:** 단축키 → 마우스 커서 근처에 팝업 (기본 `Ctrl+Alt+Space`)
- **입력 방식:** 팝업 Enter = 번역 후 입력란에 붙여넣기까지만. 전송은 사용자가 직접.
- **텍스트 주입:** 클립보드 백업 → 번역문 복사 → 대상 창 포커스 복귀 → Ctrl+V → 클립보드 복원
- **언어/스택:** Python 3.14 + tkinter(내장, 팝업/설정 GUI) + pystray(트레이) +
  keyboard(전역 단축키/Ctrl+V) + pyperclip(클립보드) + urllib(stdlib, HTTP)
  - PySide6/requests는 Python 3.14용 wheel 부재/의존성 최소화 위해 채택하지 않음.

> 구현 메모(2026-06-02): 기본 모델은 `google/gemini-2.5-flash-lite` 로 확정.
> (`google/gemini-2.0-flash-001` 은 OpenRouter에 더 이상 존재하지 않아 404.
> 실제 호출로 영어/중국어/베트남어 번역 정상 확인.) 합성 키입력·포커스·전역
> 단축키는 자동 환경에서 검증 불가 → 사용자 데스크톱 수동 테스트 대상.

## 동작 흐름

1. 프로그램 실행 → 트레이 아이콘 상주, 전역 단축키 등록
2. 임의의 앱 입력란에 커서를 둔다
3. 단축키(`Ctrl+Alt+Space`)를 누른다 → 현재 포커스 창 핸들 저장, 마우스 좌표 획득
4. 마우스 근처에 항상-위(always-on-top) 입력 팝업이 뜨고 자동 포커스
5. 글 입력 후 Enter
6. OpenRouter로 번역 요청 → 결과 수신
7. 팝업이 닫히며 직전 창으로 포커스 복귀 → 번역문 자동 붙여넣기 (전송 안 함)
8. Esc는 취소

## 구성 모듈

| 모듈 | 역할 |
|------|------|
| `config.py` | `%APPDATA%\my-app-trans\config.json` 로드/저장. 기본값 생성 |
| `translator.py` | OpenRouter 호출 → 번역문 반환. 네트워크/키 오류 처리 |
| `inject.py` | 포커스 창 저장/복귀, 클립보드 백업·복원, Ctrl+V 주입 |
| `popup.py` | 마우스 근처 입력 팝업 (Enter/Esc, 상태/오류 표시) |
| `settings_window.py` | 설정 GUI (API 키/모델/목표 언어/단축키) |
| `main.py` | pystray 트레이 + 메뉴, 전역 단축키 등록, 스레드 큐 조율, 진입점 |

## 설정 파일 형식

위치: `%APPDATA%\my-app-trans\config.json` (앱 코드/깃 저장소 밖에 보관 → API 키 안전)

```json
{
  "openrouter_api_key": "",
  "model": "google/gemini-2.5-flash-lite",
  "target_language": "영어",
  "hotkey": "ctrl+alt+space"
}
```

목표 언어 후보: 영어, 중국어, 베트남어, 한국어

## 예외 처리

- API 키 없음/인증 오류 → 팝업에 오류 표시, 입력란에 주입하지 않음
- 인터넷/번역 실패 → 팝업에 오류 표시, 원문은 보존
- 빈 입력 Enter → 팝업만 닫기
- 클립보드는 주입 후 항상 원래 내용으로 복원
- 단축키 등록 실패 → 트레이 알림으로 안내

## 테스트 전략

- `translator.py`: OpenRouter 호출을 mock하여 단위 테스트 (정상/오류 경로)
- `config.py`: JSON 저장·로드, 기본값 생성 단위 테스트
- `inject.py` / `popup.py` / `tray.py`: 윈도우 GUI·시스템 의존 → 수동 테스트
  (메모장, 브라우저, 메신저에서 실제 동작 확인)

## 자동 감지 모드 (2026-06-02 추가)

설정의 `auto_mode` 가 켜지면, 단축키 없이도 텍스트 입력란 포커스 시 팝업이 자동으로
뜬다. 구현: `main.py` 의 백그라운드 폴링 스레드(`_auto_loop`)가 0.4초마다
`uiautomation.GetFocusedControl()` 로 포커스된 컨트롤을 확인.

- 편집 가능 판정(`_is_editable`), 우선순위:
  1) UIA **ValuePattern 비-읽기전용** → 입력란 (검색창/주소창/메모장 등 대부분)
  2) `EditControl` → 입력란 (패턴 없어도 인정)
  3) `TextControl` + **TextPattern** + legacy state 비-READONLY → 입력란
     (일부 채팅/에디터 입력은 TextControl 로만 노출됨)
  → 읽기전용 웹페이지 Document·버튼·탭·라벨 제외(오발동 방지).
  (`GetTextEditPattern`은 uiautomation 2.0.29에 없어 미사용.)
- **캐럿 폴백(`_caret_key`)**: UIA로 입력란을 못 본 경우, 전경 창 스레드의
  `GetGUIThreadInfo`로 **시스템 텍스트 커서(hwndCaret) 존재 여부**를 확인해 입력
  중으로 판정. 표준 커서를 쓰는 앱(WeChat 등 다수 네이티브 앱)을 폭넓게 잡는다.
  자기 프로세스·커서 없음·읽기전용 페이지(커서 없음)는 제외. 키는
  `('caret', 전경hwnd, hwndCaret)`. (Notepad 스레드에서 hwndCaret 감지 확인.)
- **한계**: 자체 커서를 그리는 일부 Electron 앱(예: 가능성 높음 Claude 데스크탑)은
  시스템 커서가 없어 UIA·캐럿 둘 다 실패할 수 있음 → 그런 앱은 단축키 사용.
- 판정 구조: `_detect`(UIA→캐럿) → `_apply_focus`(dedupe/쿨다운). `_apply_focus`는
  순수 로직이라 단위 테스트 대상.
- 무한 루프 방지: 자기 프로세스(`ProcessId == os.getpid()`) 이벤트 무시
- 중복 방지: `(ProcessId, NativeWindowHandle, BoundingRectangle)` 키로 dedupe,
  팝업이 떠 있거나 트리거 직후 1초 쿨다운에는 무시
- 의존성: `uiautomation`, `comtypes`, `mouse` (Python 3.14 설치 확인됨)
- 제약: 검색창·주소창도 편집 컨트롤이라 함께 트리거됨. 일부 앱은 인식 불가.
  진단: `diag_autodetect.py`
- 클릭 재트리거: 전역 좌클릭(`mouse.on_button`) 시 `_auto_last_key`/쿨다운을
  초기화 → 같은 입력란을 다시 클릭하면 팝업 재등장. 단 `_popup_active` 중에는
  무시(붙여넣기 후 자동 포커스 복귀로 인한 재팝업 방지). 콜백은 tkinter 미접촉.

## Esc 취소 안정화 (2026-06-02 추가)

팝업이 키보드 포커스를 못 가졌거나 하위 앱(메신저 등)이 Esc를 선점하면, Esc가
그 앱으로 전달돼 창이 닫히는 문제가 있었다. 해결: 팝업이 열린 동안 전역 Esc 후크
(`keyboard.add_hotkey('esc', ..., suppress=True)`)를 걸어 Esc를 가로채 팝업만 닫고
하위 앱으로 넘기지 않는다. 팝업이 닫히면(`_on_popup_closed`) 후크를 해제한다.
추가로 팝업 포커스 확보를 강화(SetActiveWindow/SetFocus + 재시도 3회).

## 진단 도구

- `diag_hotkey.py` — 단축키 감지(L1) 단독 확인 (관리자 권한 필요 여부 판별)
- `diag_autodetect.py` — 포커스된 컨트롤 타입 출력 (어떤 앱이 인식되는지 확인)
- `main.py --debug` — L1→L3→L4→AUTO 단계별 로그

## 향후 확장(YAGNI: 지금은 안 함)

- "붙여넣기 후 자동 전송" 옵션
- 팝업에서 목표 언어 즉석 전환
- 텍스트 캐럿 좌표 추적(앱별 불안정)
- 자동 감지에서 검색창/주소창 제외(휴리스틱)
