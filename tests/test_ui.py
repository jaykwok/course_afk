import asyncio
import unittest
from unittest.mock import AsyncMock, patch


class FakeProgress:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.add_task_calls = []
        self.update_calls = []
        self.refresh_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def add_task(self, description, total):
        self.add_task_calls.append((description, total))
        return "task-1"

    def update(self, task_id, advance):
        self.update_calls.append((task_id, advance))

    def refresh(self):
        self.refresh_calls += 1


class UiProgressTests(unittest.TestCase):
    def test_wait_with_progress_uses_manual_refresh_steps(self):
        from core.ui import wait_with_progress

        fake_sleep = AsyncMock()
        created_progress = []

        def make_progress(*args, **kwargs):
            progress = FakeProgress(*args, **kwargs)
            created_progress.append(progress)
            return progress

        with (
            patch("core.ui.Progress", side_effect=make_progress),
            patch("asyncio.sleep", fake_sleep),
        ):
            asyncio.run(wait_with_progress(3, description="视频学习进度", step=2))

        progress = created_progress[0]
        self.assertFalse(progress.kwargs.get("auto_refresh", True))
        self.assertEqual(progress.add_task_calls, [("视频学习进度", 3)])
        self.assertEqual(progress.update_calls, [("task-1", 2), ("task-1", 1)])
        self.assertEqual(progress.refresh_calls, 3)
        self.assertEqual(
            [call.args[0] for call in fake_sleep.await_args_list],
            [2, 1],
        )


if __name__ == "__main__":
    unittest.main()
