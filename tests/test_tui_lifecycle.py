import threading
import unittest
from unittest.mock import patch

from core.abort import UserAbortRequested
from core.ui.tui_app import CourseTuiApp, YesNoScreen
from core.ui.tui_bridge import TuiFrontend


class PromptApp(CourseTuiApp):
    def _spawn_launcher_thread(self):
        pass


class TuiLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_enter_obeys_default_no_and_default_yes(self):
        for default, expected, focus in (("N", False, "no"), ("Y", True, "yes")):
            with self.subTest(default=default), patch("core.config.setup_logging"):
                app = PromptApp()
                async with app.run_test(size=(90, 22)) as pilot:
                    queue = await app.push_prompt(YesNoScreen("确认操作", default=default))
                    await pilot.pause()
                    self.assertEqual(app.focused.id, focus)
                    await pilot.press("enter")
                    self.assertIs(queue.get_nowait(), expected)

    async def test_application_exit_releases_blocked_prompt_thread(self):
        with patch("core.config.setup_logging"):
            app = PromptApp()
            frontend = TuiFrontend(app)
            outcome = []
            def worker():
                try:
                    frontend._prompt(YesNoScreen("确认操作"), cancellable=True)
                except UserAbortRequested:
                    outcome.append("stopped")
            async with app.run_test(size=(90, 22)) as pilot:
                thread = threading.Thread(target=worker, daemon=True)
                app._launcher_thread = thread
                thread.start()
                for _ in range(50):
                    await pilot.pause()
                    if isinstance(app.screen, YesNoScreen):
                        break
                self.assertIsInstance(app.screen, YesNoScreen)
                app.exit()
            self.assertFalse(thread.is_alive())
            self.assertEqual(outcome, ["stopped"])


if __name__ == "__main__":
    unittest.main()
