import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class RecommendedFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_recommended_flow_returns_manual_exam_pending_without_callback(self):
        from core.workflows import run_recommended_flow

        state = SimpleNamespace(
            has_credential=True,
            credential_expired=False,
            learning_count=1,
            exam_count=1,
            manual_exam_count=0,
        )

        with (
            patch("core.workflows.collect_project_state", return_value=state),
            patch("core.workflows.run_afk_workflow", AsyncMock(return_value=True)),
            patch("core.workflows.run_ai_exam_workflow", AsyncMock(return_value=2)),
        ):
            result = await run_recommended_flow()

        self.assertEqual(result, "manual-exam-pending")


if __name__ == "__main__":
    unittest.main()
