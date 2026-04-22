import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch


class AfkBatchPreparationTests(unittest.TestCase):
    def test_prepare_afk_batch_prefers_retry_urls_and_cleans_auxiliary_files(self):
        from core.afk_runner import prepare_afk_batch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            retry_file = root / "retry.txt"
            learning_file = root / "learning.txt"
            exam_file = root / "exam.txt"
            cleanup_one = root / "cleanup-one.txt"
            cleanup_two = root / "cleanup-two.txt"

            retry_file.write_text("https://a.example.com/1\n\nhttps://b.example.com/2\n", encoding="utf-8")
            learning_file.write_text("https://c.example.com/3\n", encoding="utf-8")
            exam_file.write_text("exam\n", encoding="utf-8")
            cleanup_one.write_text("x\n", encoding="utf-8")
            cleanup_two.write_text("y\n", encoding="utf-8")

            batch = prepare_afk_batch(
                retry_file=retry_file,
                learning_file=learning_file,
                exam_file=exam_file,
                cleanup_files=[cleanup_one, cleanup_two],
            )

            self.assertTrue(batch.is_retry)
            self.assertEqual(
                batch.urls,
                ["https://a.example.com/1", "https://b.example.com/2"],
            )
            self.assertFalse(retry_file.exists())
            self.assertTrue(exam_file.exists())
            self.assertFalse(cleanup_one.exists())
            self.assertFalse(cleanup_two.exists())

    def test_prepare_afk_batch_uses_learning_urls_for_fresh_run_and_clears_exam_file(self):
        from core.afk_runner import prepare_afk_batch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            retry_file = root / "retry.txt"
            learning_file = root / "learning.txt"
            exam_file = root / "exam.txt"

            learning_file.write_text("https://c.example.com/3\nhttps://d.example.com/4\n", encoding="utf-8")
            exam_file.write_text("exam\n", encoding="utf-8")

            batch = prepare_afk_batch(
                retry_file=retry_file,
                learning_file=learning_file,
                exam_file=exam_file,
                cleanup_files=[],
            )

            self.assertFalse(batch.is_retry)
            self.assertEqual(
                batch.urls,
                ["https://c.example.com/3", "https://d.example.com/4"],
            )
            self.assertFalse(exam_file.exists())


class AfkGracefulExitTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_afk_once_exits_without_saving_retry_urls_on_keyboard_interrupt(self):
        from core.abort import UserAbortRequested
        from core.afk_runner import AfkBatch, run_afk_once

        class FakeContext:
            pass

        class FakeBrowserContextManager:
            async def __aenter__(self):
                return None, FakeContext()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with TemporaryDirectory() as tmp:
            retry_file = Path(tmp) / "retry.txt"
            retry_file.write_text(
                "https://kc.zhixueyun.com/#/study/course/detail/a\n",
                encoding="utf-8",
            )
            batch = AfkBatch(
                urls=[
                    "https://kc.zhixueyun.com/#/study/course/detail/a",
                    "https://kc.zhixueyun.com/#/study/course/detail/b",
                    "https://kc.zhixueyun.com/#/study/course/detail/c",
                ],
                is_retry=False,
            )

            with (
                patch("core.afk_runner.RETRY_URLS_FILE", retry_file),
                patch("core.afk_runner.prepare_afk_batch", return_value=batch),
                patch(
                    "core.afk_runner.create_browser_context",
                    return_value=FakeBrowserContextManager(),
                ),
                patch("core.afk_runner.normalize_url", side_effect=lambda url: url),
                patch("core.afk_runner.is_compliant_url_regex", return_value=True),
                patch(
                    "core.afk_runner._process_url",
                    side_effect=[True, KeyboardInterrupt()],
                ),
            ):
                with self.assertRaises(UserAbortRequested) as ctx:
                    await run_afk_once()

            self.assertEqual(str(ctx.exception), "已收到 Ctrl+C，程序退出")
            self.assertEqual(
                retry_file.read_text(encoding="utf-8").splitlines(),
                ["https://kc.zhixueyun.com/#/study/course/detail/a"],
            )

    async def test_run_afk_once_skips_current_url_and_continues_when_only_course_tab_is_closed(self):
        from core.afk_runner import AfkBatch, run_afk_once

        class TargetClosedError(Exception):
            pass

        class FakeBrowser:
            def is_connected(self):
                return True

        class FakePage:
            async def goto(self, url, **kwargs):
                return None

            async def close(self):
                return None

            def on(self, _event, _handler):
                return None

        class FakeContext:
            def __init__(self):
                self.browser = FakeBrowser()

            async def new_page(self):
                return FakePage()

        class FakeBrowserContextManager:
            async def __aenter__(self):
                return None, FakeContext()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with TemporaryDirectory() as tmp:
            retry_file = Path(tmp) / "retry.txt"
            batch = AfkBatch(
                urls=[
                    "https://kc.zhixueyun.com/#/study/course/detail/a",
                    "https://kc.zhixueyun.com/#/study/course/detail/b",
                ],
                is_retry=False,
            )

            with (
                patch("core.afk_runner.RETRY_URLS_FILE", retry_file),
                patch("core.afk_runner.prepare_afk_batch", return_value=batch),
                patch(
                    "core.afk_runner.create_browser_context",
                    return_value=FakeBrowserContextManager(),
                ),
                patch("core.afk_runner.normalize_url", side_effect=lambda url: url),
                patch("core.afk_runner.is_compliant_url_regex", return_value=True),
                patch(
                    "core.afk_runner.course_learning",
                    new=AsyncMock(
                        side_effect=[
                            TargetClosedError(
                                "Target page, context or browser has been closed"
                            ),
                            None,
                        ]
                    ),
                ),
                patch("core.afk_runner._recheck_url_type_links", new=AsyncMock()),
                patch("core.afk_runner.logging.warning") as mock_warning,
            ):
                needs_retry = await run_afk_once()

            self.assertFalse(needs_retry)
            self.assertFalse(retry_file.exists())
            mock_warning.assert_not_called()

    async def test_run_afk_once_exits_without_saving_retry_urls_when_browser_window_is_closed(self):
        from core.abort import UserAbortRequested
        from core.afk_runner import AfkBatch, run_afk_once

        class TargetClosedError(Exception):
            pass

        class FakeBrowser:
            def is_connected(self):
                return False

        class FakePage:
            async def goto(self, url, **kwargs):
                return None

            async def close(self):
                return None

            def on(self, _event, _handler):
                return None

        class FakeContext:
            def __init__(self):
                self.browser = FakeBrowser()

            async def new_page(self):
                return FakePage()

        class FakeBrowserContextManager:
            async def __aenter__(self):
                return None, FakeContext()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with TemporaryDirectory() as tmp:
            retry_file = Path(tmp) / "retry.txt"
            batch = AfkBatch(
                urls=[
                    "https://kc.zhixueyun.com/#/study/course/detail/a",
                    "https://kc.zhixueyun.com/#/study/course/detail/b",
                ],
                is_retry=False,
            )

            with (
                patch("core.afk_runner.RETRY_URLS_FILE", retry_file),
                patch("core.afk_runner.prepare_afk_batch", return_value=batch),
                patch(
                    "core.afk_runner.create_browser_context",
                    return_value=FakeBrowserContextManager(),
                ),
                patch("core.afk_runner.normalize_url", side_effect=lambda url: url),
                patch("core.afk_runner.is_compliant_url_regex", return_value=True),
                patch(
                    "core.afk_runner.course_learning",
                    new=AsyncMock(
                        side_effect=TargetClosedError(
                            "Target page, context or browser has been closed"
                        )
                    ),
                ),
                patch("core.afk_runner.logging.warning") as mock_warning,
            ):
                with self.assertRaises(UserAbortRequested) as ctx:
                    await run_afk_once()

            self.assertEqual(str(ctx.exception), "已关闭浏览器窗口，程序退出")
            self.assertFalse(retry_file.exists())
            mock_warning.assert_not_called()


class ExamAttemptRoutingTests(unittest.TestCase):
    def test_parse_remaining_attempts_extracts_integer(self):
        from core.exam_runner import parse_remaining_attempts

        self.assertEqual(parse_remaining_attempts("开始考试 剩余12次"), 12)

    def test_parse_remaining_attempts_returns_none_when_unlimited(self):
        from core.exam_runner import parse_remaining_attempts

        self.assertIsNone(parse_remaining_attempts("开始考试"))

    def test_should_route_exam_to_manual_when_attempts_reach_threshold(self):
        from core.exam_runner import should_route_exam_to_manual

        self.assertTrue(should_route_exam_to_manual("继续考试 剩余3次", threshold=3))
        self.assertFalse(should_route_exam_to_manual("继续考试 剩余4次", threshold=3))

    def test_should_not_route_go_exam_button_to_manual(self):
        from core.exam_runner import should_route_exam_to_manual

        self.assertFalse(should_route_exam_to_manual("去考试", threshold=1))


class AiExamRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_ai_exam_batch_clears_exam_file_after_processing(self):
        from core.exam_runner import run_ai_exam_batch

        class FakePage:
            async def goto(self, url):
                return None

            async def wait_for_load_state(self, state):
                return None

            async def close(self):
                return None

        class FakeContext:
            async def new_page(self):
                return FakePage()

        class FakeBrowserContextManager:
            async def __aenter__(self):
                return None, FakeContext()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            exam_file = root / "exam.txt"
            manual_file = root / "manual.txt"
            exam_file.write_text(
                "https://kc.zhixueyun.com/#/study/course/detail/test-course\n",
                encoding="utf-8",
            )

            with (
                patch("core.exam_runner.EXAM_URLS_FILE", exam_file),
                patch("core.exam_runner.MANUAL_EXAM_FILE", manual_file),
                patch(
                    "core.exam_runner.create_browser_context",
                    return_value=FakeBrowserContextManager(),
                ),
                patch("core.exam_runner._build_exam_client", return_value=(object(), "test-model")),
                patch("core.exam_runner._run_course_ai_exam", new=AsyncMock(return_value=None)),
            ):
                manual_count = await run_ai_exam_batch()

            self.assertEqual(manual_count, 0)
            self.assertFalse(exam_file.exists())

    async def test_run_paper_ai_exam_uses_direct_answer_page_without_start_button(self):
        from core.exam_runner import _run_paper_ai_exam

        class FakeLocator:
            def __init__(self, *, count=0, text=""):
                self._count = count
                self._text = text

            @property
            def first(self):
                return self

            async def count(self):
                return self._count

            async def wait_for(self, timeout=0, state="visible"):
                if self._count <= 0:
                    raise AssertionError("wait_for should not be called for missing direct-answer selector")

            async def inner_text(self):
                return self._text

        class FakePage:
            def __init__(self):
                self.url = "https://kc.zhixueyun.com/#/exam/exam/answer-paper/test-paper"
                self._locators = {
                    ".banner-handler-btn.themeColor-border-color.themeColor-background-color": FakeLocator(count=0),
                    ".question-type-item": FakeLocator(count=5),
                    ".single-title": FakeLocator(count=0),
                    ".single-btns": FakeLocator(count=0),
                    ".question-type-item, .single-title, .single-btns": FakeLocator(count=1),
                }

            def locator(self, selector):
                return self._locators[selector]

        page = FakePage()
        client = object()

        with (
            patch("core.exam_runner.ai_exam", new=AsyncMock(return_value=None)) as mock_ai_exam,
            patch("core.exam_runner.save_to_file") as mock_save,
        ):
            await _run_paper_ai_exam(page, page.url, client, "test-model")

        mock_ai_exam.assert_awaited_once_with(
            client,
            "test-model",
            page,
            page.url,
            auto_submit=True,
        )
        mock_save.assert_not_called()

    async def test_run_ai_exam_batch_propagates_user_abort_requested(self):
        from core.abort import UserAbortRequested
        from core.exam_runner import run_ai_exam_batch

        class FakePage:
            def __init__(self):
                self.url = "https://kc.zhixueyun.com/#/exam/exam/answer-paper/test-paper"

            async def goto(self, url):
                return None

            async def wait_for_load_state(self, state):
                return None

            async def close(self):
                return None

        class FakeContext:
            async def new_page(self):
                return FakePage()

        class FakeBrowserContextManager:
            async def __aenter__(self):
                return None, FakeContext()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            exam_file = root / "exam.txt"
            manual_file = root / "manual.txt"
            exam_file.write_text(
                "https://kc.zhixueyun.com/#/exam/exam/answer-paper/test-paper\n",
                encoding="utf-8",
            )

            with (
                patch("core.exam_runner.EXAM_URLS_FILE", exam_file),
                patch("core.exam_runner.MANUAL_EXAM_FILE", manual_file),
                patch(
                    "core.exam_runner.create_browser_context",
                    return_value=FakeBrowserContextManager(),
                ),
                patch("core.exam_runner._build_exam_client", return_value=(object(), "test-model")),
                patch(
                    "core.exam_runner._run_paper_ai_exam",
                    new=AsyncMock(
                        side_effect=UserAbortRequested(
                            "考试已超过时长，系统已自动交卷，程序退出",
                            save_pending_urls=False,
                        )
                    ),
                ),
            ):
                with self.assertRaises(UserAbortRequested):
                    await run_ai_exam_batch()

    async def test_run_ai_exam_batch_propagates_exam_ai_configuration_error_without_saving_manual(self):
        from core.exam_answers import ExamAiConfigurationError
        from core.exam_runner import run_ai_exam_batch

        class FakePage:
            async def goto(self, url):
                return None

            async def wait_for_load_state(self, state):
                return None

            async def close(self):
                return None

        class FakeContext:
            async def new_page(self):
                return FakePage()

        class FakeBrowserContextManager:
            async def __aenter__(self):
                return None, FakeContext()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            exam_file = root / "exam.txt"
            manual_file = root / "manual.txt"
            exam_file.write_text(
                "https://kc.zhixueyun.com/#/study/course/detail/test-course\n",
                encoding="utf-8",
            )

            with (
                patch("core.exam_runner.EXAM_URLS_FILE", exam_file),
                patch("core.exam_runner.MANUAL_EXAM_FILE", manual_file),
                patch(
                    "core.exam_runner.create_browser_context",
                    return_value=FakeBrowserContextManager(),
                ),
                patch("core.exam_runner._build_exam_client", return_value=(object(), "test-model")),
                patch(
                    "core.exam_runner._run_course_ai_exam",
                    new=AsyncMock(
                        side_effect=ExamAiConfigurationError("AI 配置错误")
                    ),
                ),
            ):
                with self.assertRaises(ExamAiConfigurationError):
                    await run_ai_exam_batch()

            self.assertFalse(manual_file.exists())


if __name__ == "__main__":
    unittest.main()
