import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


class FakeLoginFrame:
    @property
    def content_frame(self):
        return self

    def locator(self, _selector):
        return self

    def wait_for(self):
        return None

    def click(self):
        return None


class FakeLoginPage:
    def goto(self, _url):
        return None

    def wait_for_url(self, _pattern, timeout=0):
        return None

    def locator(self, _selector):
        return FakeLoginFrame()

    def close(self):
        return None


class FakeLoginContext:
    def __init__(self):
        self.page = FakeLoginPage()

    def new_page(self):
        return self.page

    def cookies(self):
        return []

    def close(self):
        return None


class FakeLoginBrowser:
    def __init__(self):
        self.new_context_calls = []
        self.context = FakeLoginContext()

    def new_context(self, **kwargs):
        self.new_context_calls.append(kwargs)
        return self.context

    def close(self):
        return None


class LoginTests(unittest.TestCase):
    def test_login_uses_no_viewport_context_for_visible_browser(self):
        from core.login import login_and_save_credential

        fake_browser = FakeLoginBrowser()
        fake_profile = SimpleNamespace(
            full_name="测试账号",
            account_name="tester",
            label="测试账号（tester）",
        )

        with TemporaryDirectory() as tmp:
            cookies_file = Path(tmp) / "cookies.json"
            with (
                patch("core.login.COOKIES_FILE", cookies_file),
                patch("core.login.launch_sync_browser", return_value=fake_browser),
                patch("core.login.extract_account_profile_from_sync_context", return_value=fake_profile),
                patch("core.login.save_credential_metadata"),
                patch("core.login.sync_playwright"),
            ):
                profile = login_and_save_credential()

        self.assertEqual(profile.label, fake_profile.label)
        self.assertEqual(fake_browser.new_context_calls, [{"no_viewport": True}])


if __name__ == "__main__":
    unittest.main()
