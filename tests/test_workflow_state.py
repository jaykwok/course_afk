import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.state import recommend_next_step


class WorkflowStateTests(unittest.TestCase):
    def test_read_non_empty_lines_deduplicates_while_preserving_order(self):
        from core.state import read_non_empty_lines

        with TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "links.txt"
            file_path.write_text(
                "\n".join(
                    [
                        "https://example.com/exam/1",
                        "",
                        "https://example.com/exam/2",
                        "https://example.com/exam/1",
                        "https://example.com/exam/3",
                        "https://example.com/exam/2",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                read_non_empty_lines(file_path),
                [
                    "https://example.com/exam/1",
                    "https://example.com/exam/2",
                    "https://example.com/exam/3",
                ],
            )

    def test_collect_project_state_counts_unique_links_only(self):
        from core.state import collect_project_state

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            learning_file = root / "learning.txt"
            exam_file = root / "exam.txt"
            manual_exam_file = root / "manual.txt"

            learning_file.write_text(
                "https://example.com/course/1\nhttps://example.com/course/1\n",
                encoding="utf-8",
            )
            exam_file.write_text(
                "https://example.com/exam/1\nhttps://example.com/exam/1\nhttps://example.com/exam/2\n",
                encoding="utf-8",
            )
            manual_exam_file.write_text(
                "https://example.com/manual/1\nhttps://example.com/manual/1\n",
                encoding="utf-8",
            )

            with (
                patch("core.state.LEARNING_URLS_FILE", learning_file),
                patch("core.state.EXAM_URLS_FILE", exam_file),
                patch("core.state.MANUAL_EXAM_FILE", manual_exam_file),
                patch("core.state.has_valid_credential", return_value=(True, False)),
            ):
                state = collect_project_state()

        self.assertEqual(state.learning_count, 1)
        self.assertEqual(state.exam_count, 2)
        self.assertEqual(state.manual_exam_count, 1)

    def test_recommend_manual_course_selection_when_no_learning_links(self):
        self.assertEqual(
            recommend_next_step(
                has_credential=True,
                learning_count=0,
                exam_count=0,
                manual_exam_count=0,
            ),
            "手动选择学习课程",
        )


if __name__ == "__main__":
    unittest.main()
