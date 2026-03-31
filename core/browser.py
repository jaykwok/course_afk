import json
import re
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright


@asynccontextmanager
async def create_browser_context(
    cookies_path="cookies.json", headless=False, slow_mo=None
):
    """浏览器初始化上下文管理器, 封装重复的启动/认证/关闭流程"""

    with open(cookies_path, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--mute-audio", "--start-maximized"],
            channel="msedge",
            slow_mo=slow_mo,
        )
        context = await browser.new_context(no_viewport=True)
        await context.add_cookies(cookies)

        # 打开首页完成认证跳转
        page = await context.new_page()
        await page.goto("https://kc.zhixueyun.com/")
        await page.wait_for_url(
            re.compile(r"https://kc\.zhixueyun\.com/#/home-v\?id=\d+"), timeout=0
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
