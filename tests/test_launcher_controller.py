import unittest


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


if __name__ == "__main__":
    unittest.main()
