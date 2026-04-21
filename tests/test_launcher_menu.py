import unittest

from launcher import MANUAL_SELECTION_PROMPTS, MENU_OPTIONS


class LauncherMenuTests(unittest.TestCase):
    def test_menu_contains_manual_course_selection_option(self):
        self.assertIn("手动选择学习课程", MENU_OPTIONS)
        self.assertEqual(MENU_OPTIONS[0], "推荐流程 / 继续上次进度")

    def test_manual_selection_prompts_cover_signup_then_learning(self):
        joined = "\n".join(MANUAL_SELECTION_PROMPTS)
        self.assertIn("请粘贴入口链接", joined)
        self.assertIn("学习专区链接", joined)
        self.assertIn("如页面提示需要报名", joined)
        self.assertIn("再点击开始学习", joined)


if __name__ == "__main__":
    unittest.main()
