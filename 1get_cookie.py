import json
import re

from playwright.sync_api import sync_playwright


# 获取cookies并保存到文件
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="msedge")
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://kc.zhixueyun.com/")

        # 检测是否勾选一周内自动登录, 没有则勾上
        frame = page.locator("iframe").content_frame
        auto_login = frame.locator("#j-auto-login-qr")
        if not auto_login.is_checked():
            auto_login.click()
            print("已勾选一周内自动登录")

        # 等待跳转到主页面
        page.wait_for_url(
            re.compile(r"https://kc\.zhixueyun\.com/#/home-v\?id=\d+"), timeout=0
        )
        with open("cookies.json", "w") as f:
            f.write(json.dumps(context.cookies()))
            print("已保存cookies")
        page.close()
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
