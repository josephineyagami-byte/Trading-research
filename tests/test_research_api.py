import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests

SCRIPTS = Path(__file__).resolve().parents[1] / "Backtest" / "backtest scripts & outputs"
sys.path.insert(0, str(SCRIPTS))
from research_api import ResearchAPIError, fetch_api, login_from_private_file


class ResearchAPITests(unittest.TestCase):
    def private_account(self, directory, data):
        path = Path(directory) / "account.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_normal_login_selects_one_account_and_does_not_persist_session(self):
        accounts = [{"username": "first", "password": "first-test-password"},
                    {"username": "second", "password": "second-test-password"}]
        response = Mock(status_code=200)
        response.cookies = requests.cookies.cookiejar_from_dict({"auth": "test-session"})
        response.json.return_value = {"username": "second"}
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = self.private_account(directory, accounts)
            original = path.read_bytes()
            with patch("research_api.requests.post", return_value=response) as post:
                with contextlib.redirect_stdout(output):
                    token = login_from_private_file("http://127.0.0.1:18080", path, "second")
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
        self.assertEqual(token, "test-session")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"], accounts[1])
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertNotIn("test-password", output.getvalue())
        self.assertNotIn("test-session", output.getvalue())

    def test_login_refuses_plaintext_before_reading_credentials(self):
        with patch("research_api.requests.post") as post:
            with self.assertRaisesRegex(ResearchAPIError, "public HTTP"):
                login_from_private_file("http://example.invalid", "/does/not/exist")
        post.assert_not_called()

    def test_login_rejects_shared_files_and_ambiguous_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.private_account(directory, [{"username": "a", "password": "test"},
                                                     {"username": "b", "password": "test"}])
            with patch("research_api.requests.post") as post:
                with self.assertRaisesRegex(ResearchAPIError, "exactly one"):
                    login_from_private_file("https://example.invalid", path)
                path.chmod(0o644)
                with self.assertRaisesRegex(ResearchAPIError, "chmod 600"):
                    login_from_private_file("https://example.invalid", path, "a")
            post.assert_not_called()

    def test_failed_login_is_not_retried_and_does_not_expose_password(self):
        for status in (401, 429, 302):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                path = self.private_account(directory, {"username": "test", "password": "test-secret"})
                with patch("research_api.requests.post", return_value=Mock(status_code=status)) as post:
                    with self.assertRaises(ResearchAPIError) as error:
                        login_from_private_file("https://example.invalid", path)
                self.assertEqual(post.call_count, 1)
                self.assertNotIn("test-secret", str(error.exception))

    def test_login_and_protected_read_over_real_loopback_http(self):
        class FixtureAPI(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                account = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path != "/api/auth/login" or account != {"username": "fixture", "password": "fixture-password"}:
                    self.send_error(401)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", "auth=fixture-session; HttpOnly; Path=/")
                self.end_headers()
                self.wfile.write(b'{"username":"fixture"}')

            def do_GET(self):
                if self.headers.get("Cookie") != "auth=fixture-session":
                    self.send_error(401)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"bars":[]}')

        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureAPI)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with tempfile.TemporaryDirectory() as directory:
                path = self.private_account(directory, {"username": "fixture", "password": "fixture-password"})
                token = login_from_private_file(base, path)
            with patch.dict(os.environ, {"US_STOCK_AUTH_COOKIE": token}):
                self.assertEqual(fetch_api(base, "/api/klines"), {"bars": []})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_cookie_is_sent_only_as_cookie_and_redirects_are_disabled(self):
        response = Mock(status_code=200)
        response.json.return_value = {"bars": []}
        with patch.dict(os.environ, {"US_STOCK_AUTH_COOKIE": "test-session-value"}):
            with patch("research_api.requests.get", return_value=response) as get:
                self.assertEqual(fetch_api("https://example.invalid/", "/api/klines", {"ticker": "MSFT"}), {"bars": []})
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://example.invalid/api/klines")
        self.assertEqual(kwargs["cookies"], {"auth": "test-session-value"})
        self.assertNotIn("test-session-value", args[0])
        self.assertFalse(kwargs["allow_redirects"])

    def test_missing_auth_is_an_explicit_failure_not_missing_flow(self):
        for status in (401, 403, 429, 302):
            with self.subTest(status=status), patch.dict(os.environ, {"US_STOCK_AUTH_COOKIE": ""}):
                with patch("research_api.requests.get", return_value=Mock(status_code=status)):
                    with self.assertRaises(ResearchAPIError):
                        fetch_api("https://example.invalid", "/api/main-flow")

    def test_public_http_cannot_receive_a_session_secret(self):
        with patch.dict(os.environ, {"US_STOCK_AUTH_COOKIE": "test-session-value"}):
            with patch("research_api.requests.get") as get:
                with self.assertRaisesRegex(ResearchAPIError, "public HTTP"):
                    fetch_api("http://example.invalid:8000", "/api/klines")
                get.assert_not_called()

    def test_loopback_tunnel_is_supported(self):
        response = Mock(status_code=200)
        response.json.return_value = []
        with patch.dict(os.environ, {"US_STOCK_AUTH_COOKIE": "test-session-value"}):
            with patch("research_api.requests.get", return_value=response):
                self.assertEqual(fetch_api("http://127.0.0.1:8000", "/api/klines"), [])

    def test_invalid_base_paths_and_cookie_fail_before_network(self):
        cases = [
            ("https://user:password@example.invalid", "/api/klines", ""),
            ("https://example.invalid?token=secret", "/api/klines", ""),
            ("https://example.invalid", "//other.invalid/klines", ""),
            ("https://example.invalid", "https://other.invalid/klines", ""),
            ("https://example.invalid", "/api/klines", "auth=value; other=value"),
        ]
        for base, path, cookie in cases:
            with self.subTest(base=base), patch.dict(os.environ, {"US_STOCK_AUTH_COOKIE": cookie}):
                with patch("research_api.requests.get") as get, self.assertRaises(ResearchAPIError):
                    fetch_api(base, path)
                get.assert_not_called()

    def test_request_exception_does_not_print_secret_or_return_zero(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"US_STOCK_AUTH_COOKIE": "test-session-value"}):
            with patch("research_api.requests.get", side_effect=requests.Timeout("test-session-value")):
                with contextlib.redirect_stdout(output):
                    result = fetch_api("https://example.invalid", "/api/main-flow")
        self.assertIsNone(result)
        self.assertNotIn("test-session-value", output.getvalue())

    def test_benchmark_auth_failure_cannot_silently_disable_confirmation(self):
        import signal_generator_v5_3 as v53
        frame = pd.DataFrame({"datetime": pd.date_range("2025-01-01", periods=2), "close": [10, 11]})
        with patch.object(v53.v4, "load_klines", side_effect=ResearchAPIError("HTTP 401")):
            with self.assertRaises(ResearchAPIError):
                v53.merge_relative_strength(frame, "MSFT", "1d", 300)

    def test_explicit_older_history_is_not_silently_truncated(self):
        import signal_generator_v4 as v4
        with patch.object(v4, "fetch", return_value=[]) as fetch:
            with contextlib.redirect_stdout(io.StringIO()):
                result = v4.load_main_flow("MSFT", "1d", 300, "2024-10-20", "2024-11-20")
        self.assertIsNone(result)
        self.assertEqual(fetch.call_args_list[0].args[1]["from"], "2024-10-20")
        self.assertEqual(fetch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
