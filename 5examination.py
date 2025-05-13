import asyncio
import json
import logging
import os
import re
import time
import func_module as fm

from playwright.async_api import async_playwright

# 日志基本设置
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s",
    handlers=[
        logging.FileHandler("log.txt", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


# 等待完成考试
async def wait_for_finish_test(page1):
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    await page2.wait_for_event("close", timeout=0)


async def main():
    with open("./人工考试链接.txt", encoding="utf-8") as f:
        urls = set(f.readlines())

    # Load the cookies
    with open("cookies.json", "r") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, args=["--mute-audio", "--start-maximized"], channel="msedge"
        )
        context = await browser.new_context(no_viewport=True)
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto("https://kc.zhixueyun.com/")
        await page.wait_for_url(
            re.compile(r"https://kc\.zhixueyun\.com/#/home-v\?id=\d+"), timeout=0
        )
        await page.close()
        for url in urls:
            page1 = await context.new_page()
            logging.info(f"当前考试链接为: {url.strip()}")
            await page1.goto(url.strip())
            await page1.wait_for_load_state("load")

            while True:
                await page1.wait_for_timeout(1000)
                await page1.locator(".top").first.click()
                await page1.locator('dl.chapter-list-box[data-sectiontype="9"]').click()
                # 判断是否为第一次考试
                await page1.locator(".tab-container").wait_for()
                if await page1.locator(".neer-status").all():
                    if await fm.check_exam_passed(page1):
                        await page1.close()
                        break
                    else:
                        logging.info("重新考试")
                        await wait_for_finish_test(page1)
                        await page1.reload(wait_until="load")
                        await page1.wait_for_timeout(1500)
                        # 如果存在评价窗口, 则点击评价按钮
                        if await fm.handle_rating_popup(page1):
                            logging.info("五星评价完成")
                        continue
                else:
                    logging.info("开始考试")
                    await wait_for_finish_test(page1)
                    await page1.reload(wait_until="load")
                    await page1.wait_for_timeout(1500)
                    # 如果存在评价窗口, 则点击评价按钮
                    if await fm.handle_rating_popup(page1):
                        logging.info("五星评价完成")
                    continue

        await context.close()
        await browser.close()
        logging.info(f"考试完成, 当前时间为{time.ctime()}\n")
        os.remove("./人工考试链接.txt")


if __name__ == "__main__":
    asyncio.run(main())
