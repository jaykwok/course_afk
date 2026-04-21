import unittest

from core.state import recommend_next_step


class WorkflowStateTests(unittest.TestCase):
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
