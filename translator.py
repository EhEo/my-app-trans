"""OpenRouter LLM을 이용한 번역.

입력 텍스트를 목표 언어로 번역하여 문자열로 반환한다.
네트워크/인증/응답 형식 오류는 TranslationError 로 감싸서 올린다.

연결 재사용: 호출마다 SSL 컨텍스트·DNS·TCP·TLS 를 새로 만드는 비용(콜드 기준
0.2~0.6초)을 없애려고 HTTPS 연결 하나를 모듈 전역으로 유지한다. 팝업이 뜰 때
prewarm() 으로 미리 연결해 두면 사용자가 타이핑하는 동안 연결 수립이 끝난다.
"""
from __future__ import annotations

import http.client
import json
import ssl
import threading
import time

from config import LANGUAGES

HOST = "openrouter.ai"
PATH = "/api/v1/chat/completions"
API_URL = f"https://{HOST}{PATH}"
TIMEOUT = 30
# 이 시간(초) 이상 놀던 연결은 서버가 이미 닫았을 수 있으므로 쓰기 전에 새로 맺는다.
STALE_AFTER = 45.0

# 연결 상태 — 모두 _lock 을 잡은 채로만 읽고 쓴다(워커/prewarm 스레드 공유).
_lock = threading.Lock()
_conn: http.client.HTTPSConnection | None = None
_last_used = 0.0
_ssl_ctx: ssl.SSLContext | None = None


class TranslationError(Exception):
    """번역 실패(키 없음/네트워크/응답 오류)를 나타낸다."""


def _build_messages(text: str, target_language: str) -> list[dict]:
    lang = LANGUAGES.get(target_language, target_language)
    system = (
        f"You are a translation engine. Translate the user's message into {lang}. "
        "Detect the source language automatically. "
        "Output ONLY the translated text, with no quotes, no explanations, "
        "and no extra commentary. Preserve the original tone."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]


def _new_connection() -> http.client.HTTPSConnection:
    """새 HTTPS 연결 객체(아직 미연결). SSL 컨텍스트는 한 번만 만들어 재사용한다."""
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = ssl.create_default_context()
    return http.client.HTTPSConnection(HOST, timeout=TIMEOUT, context=_ssl_ctx)


def _drop() -> None:
    """현재 연결을 닫고 버린다. _lock 을 잡은 상태에서 호출."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
    _conn = None


def _ensure_connected() -> tuple[http.client.HTTPSConnection, bool]:
    """열린 연결을 돌려준다. (conn, reused) — reused 는 이미 열려 있던 연결인지 여부.

    닫혔거나 STALE_AFTER 이상 놀던 연결은 버리고 새로 맺는다. _lock 을 잡은 상태에서 호출.
    """
    global _conn, _last_used
    if _conn is not None and (
            _conn.sock is None or time.monotonic() - _last_used > STALE_AFTER):
        _drop()
    if _conn is not None:
        return _conn, True
    conn = _new_connection()
    conn.connect()
    _conn = conn
    _last_used = time.monotonic()
    return conn, False


def prewarm() -> None:
    """번역 서버와의 연결을 미리 맺어 둔다(백그라운드 스레드에서 호출).

    실패해도 조용히 무시한다 — 실제 번역 때 다시 연결을 시도하고 그때 오류를 보여준다.
    """
    with _lock:
        try:
            _ensure_connected()
        except Exception:
            _drop()


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def translate(text: str, target_language: str, api_key: str, model: str,
              timings: dict | None = None) -> str:
    """text 를 target_language 로 번역해서 반환한다.

    timings 에 dict 를 넘기면 단계별 소요 시간을 채운다:
    connect_ms(재사용이면 0), reused, ttfb_ms(첫 바이트), total_ms, retried(재시도 시).

    Raises:
        TranslationError: 키 없음/네트워크 오류/응답 파싱 실패 시.
    """
    global _last_used
    if not api_key:
        raise TranslationError("OpenRouter API 키가 없습니다. 설정을 확인하세요.")
    if not text.strip():
        return ""

    t = timings if timings is not None else {}
    payload = {
        "model": model,
        "messages": _build_messages(text, target_language),
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # OpenRouter 권장(선택) 헤더 — 호출 출처 식별용
        "HTTP-Referer": "https://github.com/local/my-app-trans",
        "X-Title": "my-app-trans",
    }

    status, body = 0, ""
    t0 = time.perf_counter()
    with _lock:
        for attempt in (1, 2):
            reused = False
            try:
                tc = time.perf_counter()
                conn, reused = _ensure_connected()
                t["reused"] = reused
                t["connect_ms"] = 0 if reused else _ms(tc)
                ts = time.perf_counter()
                conn.request("POST", PATH, body=data, headers=headers)
                resp = conn.getresponse()
                first = resp.read(1)
                t["ttfb_ms"] = _ms(ts)
                body = (first + resp.read()).decode("utf-8", "replace")
                status = resp.status
                _last_used = time.monotonic()
                break
            except TimeoutError as e:
                # 타임아웃은 재시도하지 않는다(30초 대기가 두 번 겹치지 않게).
                _drop()
                raise TranslationError(f"네트워크 오류: 응답 시간 초과 ({TIMEOUT}초)") from e
            except (OSError, http.client.HTTPException) as e:
                _drop()
                # 재사용하던 연결이 서버 쪽에서 닫혀 있던 경우만 새 연결로 한 번 더 시도.
                if reused and attempt == 1:
                    t["retried"] = True
                    continue
                raise TranslationError(f"네트워크 오류: {e}") from e
    t["total_ms"] = _ms(t0)

    if status >= 400:
        raise TranslationError(f"HTTP {status}: {body[:300]}")
    try:
        result = json.loads(body)
        return result["choices"][0]["message"]["content"].strip()
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        raise TranslationError(f"응답 형식 오류: {body[:300]}") from e
