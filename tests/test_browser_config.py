import asyncio
import unittest
from unittest.mock import AsyncMock

from core import browser


class BrowserLaunchConfigTests(unittest.TestCase):
    def test_build_browser_launch_options_uses_channel_for_chromium(self):
        with (
            unittest.mock.patch.object(browser, "BROWSER_TYPE", "chromium"),
            unittest.mock.patch.object(browser, "BROWSER_CHANNEL", "msedge"),
            unittest.mock.patch.object(
                browser, "BROWSER_ARGS", ["--mute-audio", "--start-maximized"]
            ),
        ):
            options = browser.build_browser_launch_options(headless=False, slow_mo=300)

        self.assertEqual(options["channel"], "msedge")
        self.assertEqual(options["args"], ["--mute-audio", "--start-maximized"])
        self.assertEqual(options["slow_mo"], 300)
        self.assertFalse(options["headless"])

    def test_build_browser_launch_options_skips_channel_and_args_for_webkit(self):
        with (
            unittest.mock.patch.object(browser, "BROWSER_TYPE", "webkit"),
            unittest.mock.patch.object(browser, "BROWSER_CHANNEL", "safari"),
            unittest.mock.patch.object(
                browser, "BROWSER_ARGS", ["--mute-audio", "--start-maximized"]
            ),
        ):
            options = browser.build_browser_launch_options(headless=True)

        self.assertEqual(options, {"headless": True})

    def test_build_browser_context_options_uses_no_viewport_for_visible_browser(self):
        self.assertEqual(
            browser.build_browser_context_options(headless=False),
            {"no_viewport": True},
        )

    def test_build_browser_context_options_keeps_headless_context_default(self):
        self.assertEqual(browser.build_browser_context_options(headless=True), {})

    def test_launch_async_browser_uses_selected_browser_type(self):
        fake_browser = object()
        fake_launcher = type("FakeLauncher", (), {"launch": AsyncMock(return_value=fake_browser)})()
        fake_playwright = type(
            "FakePlaywright",
            (),
            {"webkit": fake_launcher},
        )()

        with (
            unittest.mock.patch.object(browser, "BROWSER_TYPE", "webkit"),
            unittest.mock.patch.object(browser, "BROWSER_CHANNEL", None),
            unittest.mock.patch.object(browser, "BROWSER_ARGS", []),
        ):
            launched = asyncio.run(browser.launch_async_browser(fake_playwright, headless=True))

        self.assertIs(launched, fake_browser)
        fake_launcher.launch.assert_awaited_once_with(headless=True)


if __name__ == "__main__":
    unittest.main()
