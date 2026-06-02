import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import translator  # noqa: E402


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def fake_urlopen(body: str):
    return lambda req, timeout=None: FakeResponse(body.encode("utf-8"))


class TestTranslator(unittest.TestCase):
    def test_success_parses_content(self):
        body = '{"choices":[{"message":{"content":"Hello there"}}]}'
        with mock.patch.object(translator.urllib.request, "urlopen", fake_urlopen(body)):
            out = translator.translate("안녕", "영어", "key", "model/x")
        self.assertEqual(out, "Hello there")

    def test_strips_whitespace(self):
        body = '{"choices":[{"message":{"content":"  你好  "}}]}'
        with mock.patch.object(translator.urllib.request, "urlopen", fake_urlopen(body)):
            out = translator.translate("안녕", "중국어", "key", "model/x")
        self.assertEqual(out, "你好")

    def test_missing_key_raises(self):
        with self.assertRaises(translator.TranslationError):
            translator.translate("안녕", "영어", "", "model/x")

    def test_empty_text_returns_empty(self):
        self.assertEqual(translator.translate("   ", "영어", "key", "model/x"), "")

    def test_http_error_raises_translation_error(self):
        def raise_http(req, timeout=None):
            raise urllib.error.HTTPError(
                "url", 401, "Unauthorized", {}, io.BytesIO(b'{"error":"bad key"}'))

        with mock.patch.object(translator.urllib.request, "urlopen", raise_http):
            with self.assertRaises(translator.TranslationError):
                translator.translate("안녕", "영어", "key", "model/x")

    def test_bad_response_shape_raises(self):
        body = '{"unexpected":"shape"}'
        with mock.patch.object(translator.urllib.request, "urlopen", fake_urlopen(body)):
            with self.assertRaises(translator.TranslationError):
                translator.translate("안녕", "영어", "key", "model/x")


if __name__ == "__main__":
    unittest.main()
