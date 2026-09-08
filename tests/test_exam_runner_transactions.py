import asyncio
from contextlib import asynccontextmanager, ExitStack
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from core.abort import UserCancelRequested
from core.exam import runner
from core.exam.answers import ExamAiConfigurationError
from core.exam.flow import ExamQuestionExtractionError
from core.learning.exam_api import CourseExamState
from core.queues.exam import append_exam_urls, read_exam_urls, remove_exam_url, has_ai_failed_model_config, record_ai_failed_model_config
from core.queues.history import pending_submission, record_submission_intent
from core.queues.manual_exam import append_manual_exam_entry, read_manual_exam_queue

COURSE = "https://kc.zhixueyun.com/#/study/course/detail/00000000-0000-0000-0000-000000000001"
PAPER = "https://kc.zhixueyun.com/#/exam/exam/answer-paper/00000000-0000-0000-0000-000000000002"
MODEL = {"model": "test", "request_type": "responses", "account": "account-a"}
NEW = CourseExamState(False, False, 5, 0, 5)


class Context:
    def __init__(self):
        self.pages = []
        self.closed = False

    async def new_page(self):
        page = AsyncMock()
        self.pages.append(page)
        return page

    @asynccontextmanager
    async def open(self):
        try:
            yield None, self
        finally:
            self.closed = True


class TransactionFixture(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = Path(self.stack.enter_context(TemporaryDirectory()))
        self.exam_file = self.tmp / "exam.json"
        self.manual_file = self.tmp / "manual.json"
        self.client = AsyncMock()
        self.context = Context()
        for name, value in (("EXAM_URLS_FILE", self.exam_file), ("MANUAL_EXAM_FILE", self.manual_file)):
            self.stack.enter_context(patch.object(runner, name, value))
        self.stack.enter_context(patch.object(runner, "_build_exam_client", return_value=(self.client, "test")))
        self.stack.enter_context(patch.object(runner, "_build_ai_exam_model_config", return_value=MODEL))
        self.stack.enter_context(patch.object(runner, "_current_account", return_value=MODEL["account"]))
        self.stack.enter_context(patch.object(runner, "create_browser_context", self.context.open))

    def enqueue(self, urls=(COURSE, PAPER)):
        append_exam_urls(list(urls), file_path=self.exam_file)

    def manual(self):
        return read_manual_exam_queue(self.manual_file)

    def pending(self, url=PAPER, account="account-a"):
        return pending_submission(url, self.exam_file, account=account)


class TransactionTests(TransactionFixture):
    async def test_verified_item_is_checkpointed_before_next_item(self):
        self.enqueue()
        async def second(*_args, **_kwargs):
            self.assertEqual(read_exam_urls(self.exam_file), [PAPER])
            raise UserCancelRequested("stop")
        with patch.object(runner, "_run_course_ai_exam", new=AsyncMock(return_value=True)), patch.object(runner, "_run_paper_ai_exam", new=AsyncMock(side_effect=second)):
            with self.assertRaises(UserCancelRequested):
                await runner.run_ai_exam_batch()
        self.assertEqual(read_exam_urls(self.exam_file), [PAPER])
        self.client.close.assert_awaited_once()
        self.assertTrue(self.context.closed)
        for page in self.context.pages:
            page.close.assert_awaited_once()

    async def test_cancel_close_extract_and_config_failures_keep_current_and_remaining(self):
        class TargetClosedError(Exception):
            pass
        errors = [asyncio.CancelledError(), TargetClosedError(), ExamQuestionExtractionError("missing"), ExamAiConfigurationError("bad config")]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.enqueue()
                with patch.object(runner, "_run_course_ai_exam", new=AsyncMock(side_effect=error)):
                    with self.assertRaises((UserCancelRequested, ExamAiConfigurationError)):
                        await runner.run_ai_exam_batch()
                self.assertEqual(read_exam_urls(self.exam_file), [COURSE, PAPER])
                self.assertEqual(self.manual(), [])

    async def test_manual_destination_write_failure_preserves_ai_source(self):
        self.enqueue(("https://kc.zhixueyun.com/#/study/subject/detail/subject",))
        with patch.object(runner, "append_manual_exam_entry", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await runner.run_ai_exam_batch()
        self.assertEqual(len(read_exam_urls(self.exam_file)), 1)
        self.client.close.assert_awaited_once()

    async def test_source_removal_failure_leaves_a_recoverable_duplicate(self):
        url = "https://kc.zhixueyun.com/#/study/subject/detail/subject"
        self.enqueue((url,))
        with patch.object(runner, "remove_exam_url", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await runner.run_ai_exam_batch()
        self.assertEqual(read_exam_urls(self.exam_file), [url])
        self.assertEqual([item.url for item in self.manual()], [url])

    async def test_model_failure_survives_queue_removal_and_reimport(self):
        self.enqueue((COURSE,))
        record_ai_failed_model_config(COURSE, MODEL, file_path=self.exam_file)
        remove_exam_url(COURSE, file_path=self.exam_file)
        self.enqueue((COURSE,))
        with patch.object(runner, "_run_course_ai_exam", new=AsyncMock()) as exam:
            await runner.run_ai_exam_batch()
        exam.assert_not_awaited()
        self.assertEqual(read_exam_urls(self.exam_file), [])
        self.assertEqual(self.manual()[0].reason, "ai_failed")
        self.assertFalse(has_ai_failed_model_config(COURSE, {**MODEL, "account": "account-b"}, file_path=self.exam_file))

    async def test_manual_batch_removes_only_verified_items(self):
        for url in (COURSE, PAPER):
            append_manual_exam_entry(url, reason="review", reason_text="review", file_path=self.manual_file)
        async def second(*_args, **kwargs):
            self.assertEqual(kwargs["manual_exam_file"], self.manual_file)
            self.assertEqual([item.url for item in self.manual()], [PAPER])
            raise UserCancelRequested("closed")
        with patch.object(runner, "_run_manual_course_exam", new=AsyncMock(return_value=True)), patch.object(runner, "_run_manual_paper_exam", new=AsyncMock(side_effect=second)):
            with self.assertRaises(UserCancelRequested):
                await runner.run_manual_exam_batch(manual_exam_file=self.manual_file)
        self.assertEqual([item.url for item in self.manual()], [PAPER])


class PaperReconciliationTests(TransactionFixture):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(runner, "_raise_if_login_required", new=AsyncMock()))
        self.stack.enter_context(patch.object(runner, "_handle_attempt_limit_if_present", new=AsyncMock(return_value=False)))
        self.stack.enter_context(patch.object(runner, "_has_ready_answer_question", new=AsyncMock(return_value=True)))
        self.answer = self.stack.enter_context(patch.object(runner, "ai_exam", new=AsyncMock()))

    async def run_paper(self, before=NEW, after=None):
        with patch.object(runner, "_paper_state", new=AsyncMock(side_effect=[before, after])):
            return await runner._run_paper_ai_exam(object(), PAPER, self.client, "test")

    async def test_intent_is_durable_before_answering_and_verified_afterward(self):
        async def answer(*_args, **_kwargs):
            self.assertIsNotNone(self.pending())
        self.answer.side_effect = answer
        self.assertTrue(await self.run_paper(after=replace(NEW, passed=True)))
        self.answer.assert_awaited_once()
        self.assertIsNone(self.pending())

    async def test_unverified_previous_submission_prevents_another_attempt(self):
        record_submission_intent(PAPER, MODEL, self.exam_file)
        self.assertTrue(await self.run_paper())
        self.answer.assert_not_awaited()
        self.assertEqual(self.manual()[0].reason, "submission_unverified")
        self.assertIsNotNone(self.pending())

    async def test_submission_history_is_isolated_by_account(self):
        record_submission_intent(PAPER, {**MODEL, "account": "account-b"}, self.exam_file)
        await self.run_paper(after=replace(NEW, passed=True))
        self.answer.assert_awaited_once()
        self.assertIsNotNone(self.pending(account="account-b"))
        self.assertIsNone(self.pending())

    async def test_old_failure_cannot_be_attributed_to_this_attempt(self):
        failed = replace(NEW, submitted=True, record_id="old", used_attempts=1)
        await self.run_paper(before=failed, after=failed)
        self.assertEqual(self.manual()[0].reason, "submission_unverified")
        self.assertFalse(has_ai_failed_model_config(PAPER, MODEL, file_path=self.exam_file))
        self.assertIsNotNone(self.pending())

    async def test_new_failed_record_is_archived_without_automatic_retry(self):
        await self.run_paper(after=replace(NEW, submitted=True, record_id="new", used_attempts=1))
        self.answer.assert_awaited_once()
        self.assertEqual(self.manual()[0].reason, "ai_failed")
        self.assertTrue(has_ai_failed_model_config(PAPER, MODEL, file_path=self.exam_file))
        self.assertIsNone(self.pending())

    async def test_pending_grading_is_kept_for_manual_review(self):
        await self.run_paper(after=replace(NEW, pending_grading=True, submitted=True))
        self.assertEqual(self.manual()[0].reason, "pending_grading")
        self.assertFalse(has_ai_failed_model_config(PAPER, MODEL, file_path=self.exam_file))

    async def test_state_read_failure_before_exam_never_starts_answering(self):
        await self.run_paper(before=None)
        self.answer.assert_not_awaited()
        self.assertEqual(self.manual()[0].reason, "state_unknown")

    async def test_state_read_failure_after_exam_remains_unverified(self):
        await self.run_paper(after=None)
        self.assertEqual(self.manual()[0].reason, "submission_unverified")
        self.assertIsNotNone(self.pending())

    async def test_unknown_attempt_count_routes_to_manual(self):
        await self.run_paper(before=replace(NEW, allowed_attempts=None, used_attempts=None, remaining_attempts=None))
        self.answer.assert_not_awaited()
        self.assertEqual(len(self.manual()), 1)

    async def test_manual_review_uses_the_requested_history_directory(self):
        record_submission_intent(PAPER, MODEL, self.manual_file)
        with patch.object(runner, "_paper_state", new=AsyncMock(return_value=replace(NEW, passed=True))):
            self.assertTrue(await runner._run_manual_paper_exam(object(), PAPER, manual_exam_file=self.manual_file))
        self.assertIsNone(pending_submission(PAPER, self.manual_file, account=MODEL["account"]))

    async def test_auth_deadline_includes_slow_inner_operations(self):
        page = AsyncMock()
        page.url = PAPER
        async def slow(_page):
            await asyncio.sleep(10)
        with patch.object(runner, "_has_authorization_cookie", new=AsyncMock(return_value=True)), patch.object(runner, "_is_paper_entry_ready", new=slow):
            result = await asyncio.wait_for(runner._wait_for_target_route_after_auth(page, PAPER, timeout_ms=20), timeout=0.5)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
