import unittest
from pathlib import Path

from core import config


class DistributionFilesTests(unittest.TestCase):
    def test_env_example_exists_and_uses_placeholder_values(self):
        env_example = config.PROJECT_ROOT / ".env.example"
        self.assertTrue(env_example.exists())

        content = env_example.read_text(encoding="utf-8")
        self.assertIn("DASHSCOPE_BASE_URL=", content)
        self.assertIn("DASHSCOPE_API_KEY=your_api_key_here", content)
        self.assertIn("MODEL_NAME=qwen3.6-plus", content)
        self.assertIn("AI_ENABLE_WEB_SEARCH=1", content)
        self.assertIn("默认关闭", content)
        self.assertIn("DEBUG_MODE=1", content)
        self.assertIn("SUPPRESS_STARTUP_BANNER=1", content)

    def test_run_bat_is_english_thin_launcher(self):
        run_bat = config.PROJECT_ROOT / "run.bat"
        content = run_bat.read_text(encoding="utf-8")

        self.assertIn("launcher.py", content)
        self.assertIn("GetConsoleMode", content)
        self.assertIn("SetConsoleMode", content)
        self.assertIn("title ChinaTelecom Course AFK", content)
        self.assertIn("mode con cols=96 lines=28 >nul", content)
        self.assertIn("ChinaTelecom Course AFK", content)
        self.assertIn("Missing virtual environment", content)
        self.assertIn("Starting launcher.py", content)
        self.assertIn("Launcher exited with code", content)

    def test_readme_recommends_bat_or_python_launcher(self):
        readme = (config.PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("run.bat", readme)
        self.assertIn("python launcher.py", readme)
        self.assertNotIn("run.ps1", readme)


if __name__ == "__main__":
    unittest.main()
