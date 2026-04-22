import unittest
from unittest.mock import patch


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_recommended_flow_returns_manual_exam_pending_without_callback(self):
        from core.workflows import run_recommended_flow

        with patch(
            "core.workflows.collect_project_state",
            return_value=type(
                "State",
                (),
                {
                    "has_credential": True,
                    "credential_expired": False,
                    "learning_count": 1,
                    "exam_count": 1,
                    "manual_exam_count": 0,
                },
            )(),
        ), patch(
            "core.workflows.run_afk_workflow",
            return_value=True,
        ), patch(
            "core.workflows.run_ai_exam_workflow",
            return_value=1,
        ):
            result = await run_recommended_flow()

        self.assertEqual(result, "manual-exam-pending")

    async def test_format_status_error_message_sanitizes_raw_playwright_error(self):
        from core.workflows import _format_status_error_message

        message = _format_status_error_message(
            "记录新页面链接失败",
            RuntimeError(
                "Locator.wait_for: Timeout 3000ms exceeded.\n"
                "Call log:\n"
                '  - waiting for locator(".single-btns") to be visible\n'
            ),
        )

        self.assertEqual(message, "记录新页面链接失败")


if __name__ == "__main__":
    unittest.main()
