import json
import re

from playwright.sync_api import sync_playwright


# 获取cookies并保存到文件
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="msedge")
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.mylearning.cn/p5/index.html")
        page.wait_for_url("**/sso/login**", timeout=0)

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
            '#j-auto-group-qr .login-option-list .option[data-time="3"]'
        ).click()

        iframe.locator("#j-auto-login-qr").click()
        print("已勾选30天内自动登录")

        # 等待跳转到主页面
        page.wait_for_url("https://www.mylearning.cn/p5/index.html", timeout=0)
        with open("cookies.json", "w") as f:
            f.write(json.dumps(context.cookies()))
            print("已保存cookies")
        page.close()
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
