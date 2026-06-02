"""OpenRouter LLM을 이용한 번역.

입력 텍스트를 목표 언어로 번역하여 문자열로 반환한다.
네트워크/인증/응답 형식 오류는 TranslationError 로 감싸서 올린다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from config import LANGUAGES

API_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = 30


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


def translate(text: str, target_language: str, api_key: str, model: str) -> str:
    """text 를 target_language 로 번역해서 반환한다.

    Raises:
        TranslationError: 키 없음/네트워크 오류/응답 파싱 실패 시.
    """
    if not api_key:
        raise TranslationError("OpenRouter API 키가 없습니다. 설정을 확인하세요.")
    if not text.strip():
        return ""

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
    req = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise TranslationError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise TranslationError(f"네트워크 오류: {e.reason}") from e

    try:
        result = json.loads(body)
        return result["choices"][0]["message"]["content"].strip()
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        raise TranslationError(f"응답 형식 오류: {body[:300]}") from e
