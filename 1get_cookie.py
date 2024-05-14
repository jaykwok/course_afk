import json

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel='chrome')
    context = browser.new_context()
    page = context.new_page()
    page.goto('https://cms.mylearning.cn/safe/topic/resource/2024/zxzq/pc.html')
    frame = page.frame_locator('#esurfingloginiframe')
    auto_login = frame.locator('#j-auto-login-qr')
    # 检测是否勾选一周内自动登录，没有则勾上
    if not auto_login.is_checked():
        auto_login.click()
        print('已勾选一周内自动登录')
    print(f'是否一周内自动登录: {auto_login.is_checked()}')
    page.wait_for_url('https://cms.mylearning.cn/safe/topic/resource/2024/zxzq/pc.html', timeout=0)
    with open('cookies.json', 'w') as f:
        f.write(json.dumps(context.cookies()))
    page.close()
    context.close()
    browser.close()
