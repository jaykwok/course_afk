import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class LauncherControllerTests(unittest.TestCase):
    def test_choose_learning_zone_mode_returns_manual_when_no_learning_zone_urls(self):
        from core.launcher_controller import choose_learning_zone_mode

        self.assertEqual(
            choose_learning_zone_mode([], prompt_choice_func=lambda *args, **kwargs: 1),
            "manual",
        )

    def test_choose_learning_zone_mode_returns_auto_when_user_selects_first_option(self):
        from core.launcher_controller import choose_learning_zone_mode

        self.assertEqual(
            choose_learning_zone_mode(
                ["https://cms.mylearning.cn/safe/topic/resource/2025/zycp/pc.html"],
                prompt_choice_func=lambda *args, **kwargs: 1,
            ),
            "auto",
        )

    def test_choose_learning_zone_mode_returns_manual_when_user_selects_second_option(self):
        from core.launcher_controller import choose_learning_zone_mode

        self.assertEqual(
            choose_learning_zone_mode(
                ["https://cms.mylearning.cn/safe/topic/resource/2025/zycp/pc.html"],
                prompt_choice_func=lambda *args, **kwargs: 2,
            ),
            "manual",
        )

    def test_maybe_delete_empty_exam_queue_file_keeps_file_by_default(self):
        from core.launcher_controller import _maybe_delete_empty_exam_queue_file

        class FakeUi:
            def __init__(self):
                self.messages = []

            def prompt_yes_no(self, message, default="N"):
                self.messages.append((message, default))
                return False

            def show_success(self, message):
                self.messages.append(message)

        with TemporaryDirectory() as tmp:
            exam_file = Path(tmp) / "考试链接.txt"
            exam_file.write_text("", encoding="utf-8")
            ui = FakeUi()

            with patch("core.config.EXAM_URLS_FILE", exam_file):
                _maybe_delete_empty_exam_queue_file(ui)

            self.assertTrue(exam_file.exists())
            self.assertIn(("考试链接.txt 已空，是否删除该文件？", "N"), ui.messages)

    def test_maybe_delete_empty_exam_queue_file_deletes_file_when_user_confirms(self):
        from core.launcher_controller import _maybe_delete_empty_exam_queue_file

        class FakeUi:
            def __init__(self):
                self.messages = []

            def prompt_yes_no(self, message, default="N"):
                self.messages.append((message, default))
                return True

            def show_success(self, message):
                self.messages.append(message)

        with TemporaryDirectory() as tmp:
            exam_file = Path(tmp) / "考试链接.txt"
            exam_file.write_text("", encoding="utf-8")
            ui = FakeUi()

            with patch("core.config.EXAM_URLS_FILE", exam_file):
                _maybe_delete_empty_exam_queue_file(ui)

            self.assertFalse(exam_file.exists())
            self.assertIn("已删除空的考试链接.txt", ui.messages)


if __name__ == "__main__":
    unittest.main()
