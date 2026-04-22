import unittest
from unittest.mock import AsyncMock, patch


class _FakeNextButton:
    def __init__(self, class_name="next-disabled"):
        self._class_name = class_name
        self.click_calls = 0

    async def get_attribute(self, name):
        if name == "class":
            return self._class_name
        return None

    async def click(self):
        self.click_calls += 1


class _FakePage:
    def __init__(self, next_button=None):
        self._next_button = next_button or _FakeNextButton()

    async def wait_for_load_state(self, _state):
        return None

    async def wait_for_timeout(self, _milliseconds):
        return None

    async def wait_for_event(self, _event, timeout=0):
        return None

    def locator(self, selector):
        if selector == ".single-btn-next":
            return self._next_button
        raise KeyError(selector)


class ExamFlowLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_exam_logs_single_question_options_for_frontend_display(self):
        from core.exam_flow import ai_exam

        question_data = {
            "type": "single",
            "text": "测试单题",
            "options": [
                {"label": "A", "text": "选项一"},
                {"label": "B", "text": "选项二"},
            ],
        }
        page = _FakePage()

        with (
            patch("core.exam_flow.close_exam_notice_if_present", new=AsyncMock()),
            patch("core.exam_flow.detect_exam_mode", new=AsyncMock(return_value="single")),
            patch(
                "core.exam_flow.extract_single_question_data",
                new=AsyncMock(return_value=question_data),
            ),
            patch("core.exam_flow.get_ai_answers", new=AsyncMock(return_value=["A"])),
            patch("core.exam_flow.select_answers", new=AsyncMock()),
            patch("core.exam_flow.submit_exam", new=AsyncMock()),
            patch("core.exam_flow.logging.info") as mock_info,
        ):
            await ai_exam(object(), "test-model", page, "https://example.com/exam")

        mock_info.assert_any_call("当前题目: 测试单题")
        mock_info.assert_any_call("题目选项:\nA. 选项一\nB. 选项二")

    async def test_ai_exam_logs_multi_question_options_for_frontend_display(self):
        from core.exam_flow import ai_exam

        question_data = {
            "index": 0,
            "item_id": "item-1",
            "type": "single",
            "text": "测试多题",
            "options": [
                {"label": "A", "text": "甲"},
                {"label": "B", "text": "乙"},
            ],
        }
        page = _FakePage()

        with (
            patch("core.exam_flow.close_exam_notice_if_present", new=AsyncMock()),
            patch("core.exam_flow.detect_exam_mode", new=AsyncMock(return_value="multi")),
            patch(
                "core.exam_flow.extract_multi_questions_data",
                new=AsyncMock(return_value=[question_data]),
            ),
            patch("core.exam_flow.get_ai_answers", new=AsyncMock(return_value=["A"])),
            patch("core.exam_flow.select_answers", new=AsyncMock()),
            patch("core.exam_flow.logging.info") as mock_info,
        ):
            await ai_exam(
                object(),
                "test-model",
                page,
                "https://example.com/exam",
                auto_submit=False,
            )

        mock_info.assert_any_call("处理题目 1: 测试多题")
        mock_info.assert_any_call("题目 1 选项:\nA. 甲\nB. 乙")


if __name__ == "__main__":
    unittest.main()
