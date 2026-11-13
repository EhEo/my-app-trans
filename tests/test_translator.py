# translator 의 응답 파싱·오류 처리·연결 재사용/재시도/prewarm 을 가짜 연결로 검증
import http.client
import io
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import translator  # noqa: E402


class FakeResponse(io.BytesIO):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(body.encode("utf-8"))
        self.status = status


class FakeConn:
    """http.client.HTTPSConnection 대역. script 의 항목을 요청마다 하나씩 소비한다.

    항목이 (status, body) 면 그 응답을, 예외면 getresponse 에서 그 예외를 던진다
    (실제로 서버가 닫은 유휴 연결은 응답을 읽을 때 RemoteDisconnected 가 난다).
    """

    def __init__(self, script: list, connect_error: Exception | None = None) -> None:
        self.script = script
        self.connect_error = connect_error
        self.sock = None
        self.requests = 0

    def connect(self) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.sock = object()

    def request(self, method, path, body=None, headers=None) -> None:
        self.requests += 1
        self._item = self.script.pop(0)

    def getresponse(self):
        if isinstance(self._item, BaseException):
            raise self._item
        return FakeResponse(*self._item)

    def close(self) -> None:
        self.sock = None


def ok(content: str) -> tuple[int, str]:
    return 200, '{"choices":[{"message":{"content":"%s"}}]}' % content


class TranslatorTestBase(unittest.TestCase):
    def setUp(self) -> None:
        translator._conn = None
        translator._last_used = 0.0
        translator._last_activity = 0.0
        translator._warming = False
        self.conns: list[FakeConn] = []

    def tearDown(self) -> None:
        translator._conn = None

    def use_conns(self, *conns: FakeConn):
        """_new_connection 이 호출될 때마다 conns 를 순서대로 돌려주게 한다."""
        pending = list(conns)

        def factory():
            c = pending.pop(0)
            self.conns.append(c)
            return c

        return mock.patch.object(translator, "_new_connection", factory)


class TestTranslatorParsing(TranslatorTestBase):
    def test_success_parses_content(self):
        with self.use_conns(FakeConn([ok("Hello there")])):
            out = translator.translate("안녕", "영어", "key", "model/x")
        self.assertEqual(out, "Hello there")

    def test_strips_whitespace(self):
        with self.use_conns(FakeConn([ok("  你好  ")])):
            out = translator.translate("안녕", "중국어", "key", "model/x")
        self.assertEqual(out, "你好")

    def test_missing_key_raises(self):
        with self.assertRaises(translator.TranslationError):
            translator.translate("안녕", "영어", "", "model/x")

    def test_empty_text_returns_empty(self):
        self.assertEqual(translator.translate("   ", "영어", "key", "model/x"), "")

    def test_http_error_raises_translation_error(self):
        with self.use_conns(FakeConn([(401, '{"error":"bad key"}')])):
            with self.assertRaises(translator.TranslationError) as cm:
                translator.translate("안녕", "영어", "key", "model/x")
        self.assertIn("401", str(cm.exception))

    def test_bad_response_shape_raises(self):
        with self.use_conns(FakeConn([(200, '{"unexpected":"shape"}')])):
            with self.assertRaises(translator.TranslationError):
                translator.translate("안녕", "영어", "key", "model/x")


class TestConnectionReuse(TranslatorTestBase):
    def test_second_call_reuses_connection(self):
        timings: dict = {}
        with self.use_conns(FakeConn([ok("a"), ok("b")])):
            translator.translate("x", "영어", "key", "m")
            translator.translate("y", "영어", "key", "m", timings=timings)
        self.assertEqual(len(self.conns), 1)
        self.assertTrue(timings["reused"])
        self.assertEqual(timings["connect_ms"], 0)
        self.assertIn("ttfb_ms", timings)
        self.assertIn("total_ms", timings)

    def test_stale_reused_connection_is_retried_once(self):
        stale = FakeConn([ok("a"), http.client.RemoteDisconnected("closed")])
        fresh = FakeConn([ok("again")])
        timings: dict = {}
        with self.use_conns(stale, fresh):
            translator.translate("x", "영어", "key", "m")
            out = translator.translate("y", "영어", "key", "m", timings=timings)
        self.assertEqual(out, "again")
        self.assertTrue(timings.get("retried"))
        self.assertFalse(timings["reused"])

    def test_fresh_connection_error_is_not_retried(self):
        with self.use_conns(FakeConn([ConnectionResetError("boom")])):
            with self.assertRaises(translator.TranslationError):
                translator.translate("x", "영어", "key", "m")
        self.assertEqual(len(self.conns), 1)

    def test_timeout_on_reused_connection_is_not_retried(self):
        conn = FakeConn([ok("a"), TimeoutError("timed out")])
        with self.use_conns(conn):
            translator.translate("x", "영어", "key", "m")
            with self.assertRaises(translator.TranslationError):
                translator.translate("y", "영어", "key", "m")
        self.assertEqual(len(self.conns), 1)

    def test_idle_connection_is_replaced_before_use(self):
        first, second = FakeConn([ok("a")]), FakeConn([ok("b")])
        with self.use_conns(first, second):
            translator.translate("x", "영어", "key", "m")
            translator._last_used = time.monotonic() - translator.STALE_AFTER - 1
            translator.translate("y", "영어", "key", "m")
        self.assertEqual(len(self.conns), 2)
        self.assertIsNone(first.sock)  # 오래된 연결은 닫혔다

    def test_http_error_keeps_connection(self):
        with self.use_conns(FakeConn([(500, "oops")]), FakeConn([ok("b")])):
            with self.assertRaises(translator.TranslationError):
                translator.translate("x", "영어", "key", "m")
            # HTTP 오류는 연결 문제가 아니므로 같은 연결을 계속 쓴다
            self.assertIsNotNone(translator._conn)


class TestPrewarm(TranslatorTestBase):
    def test_prewarm_then_translate_reuses(self):
        timings: dict = {}
        with self.use_conns(FakeConn([ok("hi")])):
            translator.prewarm()
            translator.translate("x", "영어", "key", "m", timings=timings)
        self.assertEqual(len(self.conns), 1)
        self.assertTrue(timings["reused"])

    def test_prewarm_swallows_connect_error(self):
        with self.use_conns(FakeConn([], connect_error=OSError("offline"))):
            translator.prewarm()  # 예외가 새어 나오지 않아야 한다
        self.assertIsNone(translator._conn)

    def test_slow_prewarm_does_not_block_translate(self):
        """prewarm 의 connect 가 매달려 있어도 번역은 기다리지 않고 자기 연결로 진행한다."""
        entered, release = threading.Event(), threading.Event()

        class SlowConn(FakeConn):
            def connect(self):
                entered.set()
                release.wait(5)
                super().connect()

        slow, fast = SlowConn([]), FakeConn([ok("done")])
        with self.use_conns(slow, fast):
            th = threading.Thread(target=translator.prewarm)
            th.start()
            self.assertTrue(entered.wait(2))
            out = translator.translate("x", "영어", "key", "m")  # 블록되면 여기서 멈춘다
            self.assertEqual(out, "done")
            release.set()
            th.join(2)
        self.assertIs(translator._conn, fast)  # 늦게 끝난 prewarm 은 자기 연결을 버린다
        self.assertIsNone(slow.sock)

    def test_prewarm_keeps_existing_live_connection(self):
        with self.use_conns(FakeConn([ok("a")])):
            translator.prewarm()
            translator.prewarm()
        self.assertEqual(len(self.conns), 1)


class TestWarmup(TranslatorTestBase):
    def test_warmup_sends_one_token_request_on_separate_connection(self):
        warm = FakeConn([ok("h")])
        with self.use_conns(warm):
            self.assertTrue(translator.warmup("key", "m"))
        self.assertEqual(warm.requests, 1)
        self.assertIsNone(translator._conn)  # 번역용 연결은 건드리지 않는다
        self.assertIsNone(warm.sock)         # 예열 연결은 닫고 버린다

    def test_warmup_skipped_right_after_translation(self):
        with self.use_conns(FakeConn([ok("a")])):
            translator.translate("x", "영어", "key", "m")
            self.assertFalse(translator.warmup("key", "m"))
        self.assertEqual(len(self.conns), 1)

    def test_warmup_runs_again_after_idle(self):
        with self.use_conns(FakeConn([ok("a")]), FakeConn([ok("h")])):
            translator.translate("x", "영어", "key", "m")
            translator._last_activity = time.monotonic() - translator.WARM_AFTER - 1
            self.assertTrue(translator.warmup("key", "m"))

    def test_warmup_needs_key_and_model(self):
        self.assertFalse(translator.warmup("", "m"))
        self.assertFalse(translator.warmup("key", ""))

    def test_warmup_failure_is_swallowed_and_releases_flag(self):
        with self.use_conns(FakeConn([ConnectionResetError("x")])):
            self.assertFalse(translator.warmup("key", "m"))
        self.assertFalse(translator._warming)

    def test_only_one_warmup_at_a_time(self):
        translator._warming = True
        self.assertFalse(translator.warmup("key", "m"))

    def test_inflight_warmup_does_not_block_translate(self):
        entered, release = threading.Event(), threading.Event()

        class SlowWarm(FakeConn):
            def getresponse(self):
                entered.set()
                release.wait(5)
                return super().getresponse()

        with self.use_conns(SlowWarm([ok("h")]), FakeConn([ok("done")])):
            th = threading.Thread(target=translator.warmup, args=("key", "m"))
            th.start()
            self.assertTrue(entered.wait(2))
            self.assertEqual(translator.translate("x", "영어", "key", "m"), "done")
            release.set()
            th.join(2)


if __name__ == "__main__":
    unittest.main()
