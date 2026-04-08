import json
import logging

from playwright.sync_api import sync_playwright

from core.config import (
    AUTO_LOGIN_DATA_TIME,
    BROWSER_CHANNEL,
    COOKIES_FILE,
    MYLEARNING_HOME,
    MYLEARNING_SSO_PATTERN,
    setup_logging,
)

# 日志配置
setup_logging()


# 获取cookies并保存到文件
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel=BROWSER_CHANNEL)
        context = browser.new_context()
        page = context.new_page()
        page.goto(MYLEARNING_HOME)
        page.wait_for_url(MYLEARNING_SSO_PATTERN, timeout=0)

        # 检测是否勾选30天内自动登录, 没有则勾上
        # 获取iframe
        iframe = page.locator("#esurfingloginiframe").content_frame
        # 等待自动登录选项区域可见
        iframe.locator("#j-auto-login-qr").wait_for()
        # 点击下拉箭头展开选项列表
        iframe.locator("#j-auto-group-qr .login-select").click()
        # 等待选项列表出现并点击30天选项
        iframe.locator("#j-auto-group-qr .login-option-list").wait_for()
        iframe.locator(
            f'#j-auto-group-qr .login-option-list .option[data-time="{AUTO_LOGIN_DATA_TIME}"]'
        ).click()

        iframe.locator("#j-auto-login-qr").click()
        logging.info("已勾选30天内自动登录")

        # 等待跳转到主页面
        page.wait_for_url(MYLEARNING_HOME, timeout=0)
        with open(COOKIES_FILE, "w") as f:
            f.write(json.dumps(context.cookies()))
            logging.info("已保存cookies")
        page.close()
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
