import json
import re
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright

from core.config import (
    BROWSER_ARGS,
    BROWSER_CHANNEL,
    COOKIES_FILE,
    ZHIXUEYUN_HOME,
    ZHIXUEYUN_HOME_PATTERN,
)


@asynccontextmanager
async def create_browser_context(
    cookies_path=COOKIES_FILE, headless=False, slow_mo=None
):
    """浏览器初始化上下文管理器, 封装重复的启动/认证/关闭流程"""

    with open(cookies_path, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=BROWSER_ARGS,
            channel=BROWSER_CHANNEL,
            slow_mo=slow_mo,
        )
        context = await browser.new_context(no_viewport=True)
        await context.add_cookies(cookies)

        # 打开首页完成认证跳转
        page = await context.new_page()
        await page.goto(ZHIXUEYUN_HOME)
        await page.wait_for_url(
            re.compile(ZHIXUEYUN_HOME_PATTERN), timeout=0
        )
        await page.close()

        try:
            yield browser, context
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
