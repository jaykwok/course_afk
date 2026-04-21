import unittest

from launcher import MANUAL_SELECTION_PROMPTS, MENU_OPTIONS


class LauncherMenuTests(unittest.TestCase):
    def test_menu_matches_expected_labels_and_order(self):
        self.assertEqual(
            MENU_OPTIONS,
            [
                "推荐挂课流程（挂课+考试（如有）） / 继续上次进度",
                "仅挂课",
                "更新登录凭证 / 切换账号",
                "手动选择学习课程",
                "AI 自动考试",
                "人工考试",
                "查看当前状态与输出文件",
                "查看待学习链接状态",
                "退出",
            ],
        )

    def test_manual_selection_prompts_cover_signup_then_learning(self):
        joined = "\n".join(MANUAL_SELECTION_PROMPTS)
        self.assertIn("请粘贴入口链接", joined)
        self.assertIn("学习专区链接", joined)
        self.assertIn("如页面提示需要报名", joined)
        self.assertIn("再点击开始学习", joined)


if __name__ == "__main__":
    unittest.main()
