from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.abort import WafBlockError
from core.app import workflows


def state(*, learning=0, exams=0, manual=0, failures=0, credential=True):
    return SimpleNamespace(has_credential=credential, credential_expired=False,
        learning_count=learning, exam_count=exams, manual_exam_count=manual,
        learning_failure_count=failures)


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.read_failures = patch.object(workflows, "read_learning_failures", return_value=[])
        self.read_failures.start()
        self.addCleanup(self.read_failures.stop)

    async def test_ai_workflow_defaults_to_manual_submit_and_forwards_opt_in(self):
        for requested in (None, False, True):
            with self.subTest(requested=requested), patch.object(workflows, "collect_project_state", return_value=state(exams=2)), patch.object(workflows, "run_ai_exam_batch", new=AsyncMock(return_value=1)) as batch:
                result = await workflows.run_ai_exam_workflow(**({"auto_submit": requested} if requested is not None else {}))
                self.assertEqual(result, 1)
                batch.assert_awaited_once_with(status_callback=None, auto_submit=requested is True)

    async def test_recommended_rereads_queues_after_each_stage(self):
        ask = Mock(return_value=False)
        snapshots = [state(learning=1), state(exams=1), state()]
        with patch.object(workflows, "collect_project_state", side_effect=snapshots), patch.object(workflows, "is_ai_configured", return_value=True), patch.object(workflows, "run_afk_workflow", new=AsyncMock()) as learning, patch.object(workflows, "run_ai_exam_workflow", new=AsyncMock()) as exam:
            self.assertEqual(await workflows.run_recommended_flow(ask_auto_submit=ask), "done")
        learning.assert_awaited_once()
        exam.assert_awaited_once_with(status_callback=None, auto_submit=False)
        ask.assert_called_once_with()

    async def test_existing_exam_without_learning_is_processed(self):
        snapshots = [state(exams=2), state(exams=2), state()]
        with patch.object(workflows, "collect_project_state", side_effect=snapshots), patch.object(workflows, "is_ai_configured", return_value=True), patch.object(workflows, "run_afk_workflow", new=AsyncMock()) as learning, patch.object(workflows, "run_ai_exam_workflow", new=AsyncMock()) as exam:
            self.assertEqual(await workflows.run_recommended_flow(), "done")
        learning.assert_not_awaited()
        exam.assert_awaited_once_with(status_callback=None, auto_submit=False)

    async def test_manual_queue_created_by_ai_is_reported(self):
        snapshots = [state(exams=1), state(exams=1), state(manual=1)]
        with patch.object(workflows, "collect_project_state", side_effect=snapshots), patch.object(workflows, "is_ai_configured", return_value=True), patch.object(workflows, "run_ai_exam_workflow", new=AsyncMock()):
            self.assertEqual(await workflows.run_recommended_flow(), "manual-exam-pending")

    async def test_pending_work_is_never_reported_as_done(self):
        for pending in (state(learning=1), state(exams=1), state(failures=1)):
            with self.subTest(pending=pending), patch.object(workflows, "collect_project_state", side_effect=[state(exams=1), state(exams=1), pending]), patch.object(workflows, "is_ai_configured", return_value=True), patch.object(workflows, "run_ai_exam_workflow", new=AsyncMock()):
                self.assertEqual(await workflows.run_recommended_flow(), "learning-pending")

    async def test_waf_stops_before_exam_or_submit_prompt(self):
        ask = Mock()
        with patch.object(workflows, "collect_project_state", return_value=state(learning=1, exams=1)), patch.object(workflows, "run_afk_workflow", new=AsyncMock(side_effect=WafBlockError())), patch.object(workflows, "run_ai_exam_workflow", new=AsyncMock()) as exam:
            self.assertEqual(await workflows.run_recommended_flow(ask_auto_submit=ask), "blocked")
        exam.assert_not_awaited()
        ask.assert_not_called()

    async def test_without_ai_configuration_no_exam_or_prompt_is_started(self):
        ask = Mock()
        with patch.object(workflows, "collect_project_state", return_value=state(exams=1)), patch.object(workflows, "is_ai_configured", return_value=False), patch.object(workflows, "run_ai_exam_workflow", new=AsyncMock()) as exam:
            self.assertEqual(await workflows.run_recommended_flow(ask_auto_submit=ask), "ai-not-configured")
        exam.assert_not_awaited()
        ask.assert_not_called()

    async def test_existing_manual_queue_is_reported(self):
        with patch.object(workflows, "collect_project_state", return_value=state(manual=1)):
            self.assertEqual(await workflows.run_recommended_flow(), "manual-exam-pending")

    async def test_pending_url_review_runs_without_normal_learning_queue(self):
        with patch.object(workflows, "read_learning_failures", return_value=[SimpleNamespace(reason="url_type_pending")]), patch.object(workflows, "collect_project_state", side_effect=[state(failures=1), state()]), patch.object(workflows, "run_afk_workflow", new=AsyncMock()) as learning:
            self.assertEqual(await workflows.run_recommended_flow(), "afk-only")
        learning.assert_awaited_once()

    async def test_format_status_error_message_sanitizes_raw_playwright_error(self):
        message = workflows._format_status_error_message("记录新页面链接失败", RuntimeError("Locator.wait_for: Timeout 3000ms exceeded.\nCall log:\n  - waiting for locator"))
        self.assertEqual(message, "记录新页面链接失败")


class RefreshCredentialTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_credential_returns_login_result_without_profile_fallback(self):
        from core.auth.credential import AccountProfile
        messages = []
        profile = AccountProfile()
        with patch.object(workflows, "login_and_save_credential", new=AsyncMock(return_value=profile)) as login:
            result = await workflows.refresh_credential(status_callback=messages.append)
        self.assertIs(result, profile)
        self.assertEqual(messages, ["正在打开浏览器，请完成登录"])
        login.assert_awaited_once_with(confirm_same_account=None)


if __name__ == "__main__":
    unittest.main()
