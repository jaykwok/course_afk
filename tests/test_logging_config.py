import logging
import unittest
from unittest.mock import patch
from os import environ

from core import config


class LoggingConfigTests(unittest.TestCase):
    def setUp(self):
        self.root_logger = logging.getLogger()
        self.original_handlers = self.root_logger.handlers[:]
        self.original_level = self.root_logger.level
        self.original_flag = getattr(config, "_LOGGING_CONFIGURED", False)
        self.root_logger.handlers.clear()
        config._LOGGING_CONFIGURED = False

    def tearDown(self):
        for handler in self.root_logger.handlers[:]:
            self.root_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        self.root_logger.handlers.extend(self.original_handlers)
        self.root_logger.setLevel(self.original_level)
        config._LOGGING_CONFIGURED = self.original_flag

    def test_setup_logging_uses_info_level_console_handler(self):
        config.setup_logging()
        handlers = logging.getLogger().handlers
        self.assertEqual(len(handlers), 2)
        self.assertEqual(handlers[1].level, logging.INFO)

    def test_setup_logging_is_idempotent(self):
        config.setup_logging()
        first_count = len(logging.getLogger().handlers)
        config.setup_logging()
        self.assertEqual(len(logging.getLogger().handlers), first_count)

    def test_setup_logging_silences_asyncio_debug_logs(self):
        config.setup_logging()
        self.assertEqual(logging.getLogger("asyncio").level, logging.WARNING)

    def test_setup_logging_can_skip_startup_banner(self):
        with patch("core.config._log_startup_banner") as mock_banner:
            config.setup_logging(show_startup_banner=False)
        mock_banner.assert_not_called()

    def test_setup_logging_can_skip_startup_banner_via_env(self):
        with patch.dict(environ, {"SUPPRESS_STARTUP_BANNER": "1"}, clear=False):
            with patch("core.config._log_startup_banner") as mock_banner:
                config.setup_logging()
        mock_banner.assert_not_called()

    def test_setup_logging_uses_debug_console_level_when_debug_mode_enabled(self):
        with patch.dict(environ, {"DEBUG_MODE": "1"}, clear=False):
            config.setup_logging()
        handlers = logging.getLogger().handlers
        self.assertEqual(handlers[1].level, logging.DEBUG)

    def test_build_console_handler_upgrades_console_streams_to_utf8_when_possible(self):
        class DummyStream:
            def __init__(self, encoding):
                self.encoding = encoding
                self.errors = "strict"

            def reconfigure(self, **kwargs):
                self.encoding = kwargs.get("encoding", self.encoding)
                self.errors = kwargs.get("errors", self.errors)

        class DummyRichHandler(logging.Handler):
            def __init__(self, *args, **kwargs):
                super().__init__()

        stdout = DummyStream("gbk")
        stderr = DummyStream("gbk")

        with (
            patch.object(config.sys, "stdout", stdout),
            patch.object(config.sys, "stderr", stderr),
            patch("rich.logging.RichHandler", DummyRichHandler),
        ):
            handler = config._build_console_handler()

        self.assertIsInstance(handler, DummyRichHandler)
        self.assertEqual(stdout.encoding, "utf-8")
        self.assertEqual(stderr.encoding, "utf-8")
        self.assertEqual(stdout.errors, "replace")
        self.assertEqual(stderr.errors, "replace")

    def test_build_console_handler_falls_back_to_plain_handler_when_console_stays_non_utf8(self):
        class DummyStream:
            def __init__(self, encoding):
                self.encoding = encoding
                self.errors = "strict"

            def reconfigure(self, **kwargs):
                self.errors = kwargs.get("errors", self.errors)

        class DummyRichHandler(logging.Handler):
            def __init__(self, *args, **kwargs):
                super().__init__()

        stdout = DummyStream("gbk")
        stderr = DummyStream("gbk")

        with (
            patch.object(config.sys, "stdout", stdout),
            patch.object(config.sys, "stderr", stderr),
            patch("rich.logging.RichHandler", DummyRichHandler),
        ):
            handler = config._build_console_handler()

        self.assertIsInstance(handler, logging.StreamHandler)
        self.assertNotIsInstance(handler, DummyRichHandler)
        self.assertEqual(stdout.encoding, "gbk")
        self.assertEqual(stderr.encoding, "gbk")
        self.assertEqual(stdout.errors, "replace")
        self.assertEqual(stderr.errors, "replace")

    def test_disable_windows_console_input_modes_clears_quick_edit_and_insert(self):
        class FakeKernel32:
            def __init__(self):
                self.mode = 0x0067
                self.set_mode = None

            def GetStdHandle(self, handle):
                self.handle = handle
                return 123

            def GetConsoleMode(self, handle, mode_ref):
                mode_ref._obj.value = self.mode
                return 1

            def SetConsoleMode(self, handle, mode):
                self.set_mode = mode
                return 1

        fake_kernel32 = FakeKernel32()
        fake_ctypes = type(
            "FakeCtypes",
            (),
            {
                "windll": type("FakeWindll", (), {"kernel32": fake_kernel32})(),
                "c_uint": config.ctypes.c_uint,
                "byref": config.ctypes.byref,
            },
        )()

        with (
            patch.object(config.sys, "platform", "win32"),
            patch.object(config, "ctypes", fake_ctypes),
        ):
            config._disable_windows_console_input_modes()

        self.assertEqual(fake_kernel32.handle, -10)
        self.assertIsNotNone(fake_kernel32.set_mode)
        self.assertEqual(fake_kernel32.set_mode & 0x0040, 0)
        self.assertEqual(fake_kernel32.set_mode & 0x0020, 0)
        self.assertNotEqual(fake_kernel32.set_mode & 0x0080, 0)


if __name__ == "__main__":
    unittest.main()
