"""Browser validation of the prototype dashboard with Playwright.

This is opt-in: it runs only when ``PSEC_UI_TESTS=1`` and Playwright (plus a browser)
is installed, so the default offline suite stays fast and dependency-light. Use
``scripts/run-tests.sh --ui`` to install the dev deps + browser and run it.

It boots the dashboard with the scripted demo controller (no microphone/KoboldCPP) and
checks behavior the offline tests cannot: that the transcript renders and grows, the
controls and panels are wired, the sensitivity options round-trip through the real form to
the backend, and Clear empties the transcript.
"""

from __future__ import annotations

import os
import socket
import threading
import unittest

from tests.audio_stubs import install_audio_dependency_stubs

install_audio_dependency_stubs()

UI_TESTS_ENABLED = os.getenv("PSEC_UI_TESTS") == "1"

try:  # pragma: no cover - import guard
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(UI_TESTS_ENABLED, "set PSEC_UI_TESTS=1 to run browser UI tests")
@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "playwright is not installed")
class DashboardUiTests(unittest.TestCase):
    def setUp(self) -> None:
        from pysecretary.config import SecretaryConfig
        from pysecretary.prototype import create_demo_controller
        from pysecretary.web.server import PrototypeHTTPServer, _make_handler

        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}/"
        self.controller = create_demo_controller(SecretaryConfig())
        self.server = PrototypeHTTPServer(("127.0.0.1", self.port), _make_handler(self.controller))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch()
        except Exception as exc:  # pragma: no cover - missing browser binary
            self._pw.stop()
            self.skipTest(f"no Playwright browser available: {exc}")
        self.page = self.browser.new_page()

    def tearDown(self) -> None:
        try:
            self.browser.close()
        finally:
            self._pw.stop()
            self.controller.stop()
            self.server.shutdown()
            self.server.server_close()

    def _backend_state(self) -> dict:
        return self.page.request.get(f"{self.url}api/state").json()

    def test_transcript_grows_and_shows_full_text(self) -> None:
        self.page.goto(self.url)
        self.page.click("#start-button")
        # The scripted demo emits three turns; the transcript must accumulate all of them,
        # proving real-time growth and full-text visibility (not just the last statement).
        self.page.wait_for_function(
            "document.getElementById('transcript').textContent.includes('important details')",
            timeout=15000,
        )
        transcript = self.page.inner_text("#transcript")
        self.assertIn("automatic voice prototype", transcript)
        self.assertIn("important details", transcript)
        self.assertNotIn(" um ", f" {transcript} ")

    def test_controls_and_panels_are_present(self) -> None:
        self.page.goto(self.url)
        for selector in ("#start-button", "#stop-button", "#clear-button", "#transcript"):
            self.assertTrue(self.page.query_selector(selector), f"missing {selector}")
        # Not running at load: Stop disabled, Start enabled.
        self.assertTrue(self.page.is_disabled("#stop-button"))
        self.assertTrue(self.page.is_enabled("#start-button"))
        # Diagnostics/settings panel exists with all sensitivity inputs.
        for opt in ("#opt-energy", "#opt-peak", "#opt-silence", "#opt-minspeech", "#opt-maxturn"):
            self.assertTrue(self.page.query_selector(opt), f"missing {opt}")

    def test_sensitivity_option_round_trips_to_backend(self) -> None:
        self.page.goto(self.url)
        # Inputs are populated from the backend worker_options (default energy 0.006).
        self.page.wait_for_function("document.getElementById('opt-energy').value !== ''", timeout=10000)
        # Expand the collapsed details so the form is interactable, then change + apply.
        self.page.eval_on_selector("details", "el => el.open = true")
        self.page.fill("#opt-energy", "0.123")
        self.page.click("#options-apply")
        # The change must reach the backend via the UpdateWorkerOption command.
        self.page.wait_for_function(
            f"fetch('{self.url}api/state').then(r => r.json()).then(s => s.worker_options.energy_threshold === 0.123)",
            timeout=10000,
        )
        self.assertEqual(self._backend_state()["worker_options"]["energy_threshold"], 0.123)

    def test_clear_button_empties_transcript(self) -> None:
        self.page.goto(self.url)
        self.page.click("#start-button")
        self.page.wait_for_function(
            "document.getElementById('transcript').textContent.includes('important details')",
            timeout=15000,
        )
        self.page.click("#clear-button")
        self.page.wait_for_function(
            "!document.getElementById('transcript').textContent.includes('important details')",
            timeout=10000,
        )
        self.assertEqual(self._backend_state()["smoothed_text"], "")


if __name__ == "__main__":
    unittest.main()
