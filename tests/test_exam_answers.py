import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class ExamAnswerTests(unittest.TestCase):
    def test_build_question_prompt_includes_type_text_and_options(self):
        from core.exam_answers import build_question_prompt

        prompt = build_question_prompt(
            {
                "type": "single",
                "text": "中国电信的英文缩写是什么？",
                "options": [
                    {"label": "A", "text": "CT"},
                    {"label": "B", "text": "CU"},
                ],
            }
        )

        self.assertIn("单选题", prompt)
        self.assertIn("中国电信的英文缩写是什么？", prompt)
        self.assertIn("A. CT", prompt)
        self.assertIn("B. CU", prompt)

    def test_normalize_ai_answer_text_handles_judge_and_ordering_and_multi(self):
        from core.exam_answers import normalize_ai_answer_text

        self.assertEqual(normalize_ai_answer_text("judge", "答案：正确"), ["正确"])
        self.assertEqual(normalize_ai_answer_text("ordering", "正确顺序是 ACBD"), ["A", "C", "B", "D"])
        self.assertEqual(normalize_ai_answer_text("multiple", "我选 A、C、A、D"), ["A", "C", "D"])


class ExamAnswerResponsesApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_ai_answers_uses_responses_web_search_when_enabled(self):
        from core import exam_answers

        create = Mock(return_value=SimpleNamespace(output_text="A"))
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        question_data = {
            "type": "single",
            "text": "中国电信的英文缩写是什么？",
            "options": [
                {"label": "A", "text": "CT"},
                {"label": "B", "text": "CU"},
            ],
        }

        with patch.object(exam_answers, "AI_RESPONSE_TOOLS", [{"type": "web_search"}]):
            answers = await exam_answers.get_ai_answers(client, "qwen3.6-plus", question_data)

        self.assertEqual(answers, ["A"])
        create.assert_called_once()
        self.assertEqual(create.call_args.kwargs["model"], "qwen3.6-plus")
        self.assertEqual(create.call_args.kwargs["tools"], [{"type": "web_search"}])

    async def test_get_ai_answers_omits_tools_when_web_search_disabled(self):
        from core import exam_answers

        create = Mock(return_value=SimpleNamespace(output_text="A"))
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        question_data = {
            "type": "single",
            "text": "中国电信的英文缩写是什么？",
            "options": [
                {"label": "A", "text": "CT"},
                {"label": "B", "text": "CU"},
            ],
        }

        with patch.object(exam_answers, "AI_RESPONSE_TOOLS", None):
            answers = await exam_answers.get_ai_answers(client, "qwen3.6-plus", question_data)

        self.assertEqual(answers, ["A"])
        create.assert_called_once()
        self.assertNotIn("tools", create.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
