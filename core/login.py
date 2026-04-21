from __future__ import annotations

import json
import logging
from datetime import datetime

from playwright.sync_api import sync_playwright

from core.config import (
    AUTO_LOGIN_DATA_TIME,
    COOKIES_FILE,
    MYLEARNING_HOME,
    MYLEARNING_SSO_PATTERN,
)
from core.browser import build_browser_context_options, launch_sync_browser
from core.credential import (
    AccountProfile,
    extract_account_profile_from_sync_context,
    save_credential_metadata,
)


def login_and_save_credential() -> AccountProfile:
    with sync_playwright() as playwright:
        browser = launch_sync_browser(playwright, headless=False)
        context = browser.new_context(**build_browser_context_options(headless=False))
        page = context.new_page()
        try:
            page.goto(MYLEARNING_HOME)
            page.wait_for_url(MYLEARNING_SSO_PATTERN, timeout=0)

            iframe = page.locator("#esurfingloginiframe").content_frame
            iframe.locator("#j-auto-login-qr").wait_for()
            iframe.locator("#j-auto-group-qr .login-select").click()
            iframe.locator("#j-auto-group-qr .login-option-list").wait_for()
            iframe.locator(
                f'#j-auto-group-qr .login-option-list .option[data-time="{AUTO_LOGIN_DATA_TIME}"]'
            ).click()
            iframe.locator("#j-auto-login-qr").click()
            logging.info("已勾选30天内自动登录")

            page.wait_for_url(MYLEARNING_HOME, timeout=0)
            with open(COOKIES_FILE, "w", encoding="utf-8") as file:
                json.dump(context.cookies(), file, ensure_ascii=False, indent=2)
            logging.info("已保存登录凭证")

            profile = extract_account_profile_from_sync_context(context)
            save_credential_metadata(
                saved_at=datetime.now(),
                full_name=profile.full_name,
                account_name=profile.account_name,
            )
            logging.info(f"已更新登录凭证元数据，当前账号：{profile.label}")
            return profile
        finally:
            page.close()
            context.close()
            browser.close()
