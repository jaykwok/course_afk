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


class BrowserControllerPageTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_controller_page_reuses_existing_open_page(self):
        class FakeBrowser:
            def is_connected(self):
                return True

        class FakePage:
            def __init__(self):
                self.goto_calls = []
                self.closed = False
                self.handlers = {}

            async def goto(self, url, wait_until="load"):
                self.goto_calls.append((url, wait_until))

            def is_closed(self):
                return self.closed

            def on(self, event, handler):
                self.handlers[event] = handler

        class FakeContext:
            def __init__(self):
                self.browser = FakeBrowser()
                self.pages = []

            async def new_page(self):
                page = FakePage()
                self.pages.append(page)
                return page

        context = FakeContext()
        try:
            first_page = await browser.ensure_controller_page(context)
            second_page = await browser.ensure_controller_page(context)
        finally:
            browser.release_controller_page(context)

        self.assertIs(first_page, second_page)
        self.assertEqual(len(context.pages), 1)
        self.assertEqual(
            first_page.goto_calls,
            [(browser.MYLEARNING_HOME, "load")],
        )

    async def test_ensure_controller_page_recreates_closed_controller_tab(self):
        class FakeBrowser:
            def is_connected(self):
                return True

        class FakePage:
            def __init__(self):
                self.goto_calls = []
                self.closed = False
                self.handlers = {}

            async def goto(self, url, wait_until="load"):
                self.goto_calls.append((url, wait_until))

            def is_closed(self):
                return self.closed

            def on(self, event, handler):
                self.handlers[event] = handler

            async def close(self):
                self.closed = True
                close_handler = self.handlers.get("close")
                if close_handler is not None:
                    close_handler()

        class FakeContext:
            def __init__(self):
                self.browser = FakeBrowser()
                self.pages = []

            async def new_page(self):
                page = FakePage()
                self.pages.append(page)
                return page

        context = FakeContext()
        try:
            first_page = await browser.ensure_controller_page(context)
            await first_page.close()
            await asyncio.sleep(0)
            second_page = await browser.ensure_controller_page(context)
        finally:
            browser.release_controller_page(context)

        self.assertIsNot(first_page, second_page)
        self.assertEqual(len(context.pages), 2)
        self.assertEqual(
            second_page.goto_calls,
            [(browser.MYLEARNING_HOME, "load")],
        )


if __name__ == "__main__":
    unittest.main()
