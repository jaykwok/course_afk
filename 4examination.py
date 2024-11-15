import asyncio
import json
import logging
import os
import re
import time

from playwright.async_api import async_playwright

# 日志基本设置
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s",
    handlers=[logging.FileHandler("log.txt", mode="w"), logging.StreamHandler()],
)


# 获取考试是否通过
async def check_exam_passed(page):
    # 获取最高分
    highest_score_text = await page.locator(".neer-status").inner_text()
    # 判断是否在考试中状态：如果是，那就重新考试
    if "考试中" in highest_score_text:
        return False
    # 获取最高分数值
    highest_score = int(highest_score_text.split("：")[1].replace("分", ""))
    # 判断最高成绩是否大于等于60分
    if highest_score >= 60:
        logging.info(f"考试状态: 通过")
        return True
    else:
        logging.info(f"考试状态: 未通过")
        return False


# 等待完成考试
async def wait_for_finish_test(page1):
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    await page2.wait_for_event("close", timeout=0)


async def main():
    with open("./学习课程考试链接.txt", encoding="utf-8") as f:
        urls = list(f.readlines())

    # Load the cookies
    with open("cookies.json", "r") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, args=["--mute-audio"], channel="chrome"
        )
        context = await browser.new_context()
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
                await page1.locator(".top").first.click()
                await page1.locator('dl.chapter-list-box[data-sectiontype="9"]').click()
                await page1.locator(".tab-container").wait_for()
                await page1.wait_for_timeout(3000)

                if await page1.locator(".neer-status").all():
                    if await check_exam_passed(page1):
                        await page1.close()
                        break
                    else:
                        logging.info("重新考试")
                        await wait_for_finish_test(page1)
                        await page1.reload(wait_until="load")
                        continue
                else:
                    logging.info("开始考试")
                    await wait_for_finish_test(page1)
                    await page1.reload(wait_until="load")
                    continue

        await context.close()
        await browser.close()
        logging.info(f"\n考试完成，当前时间为{time.ctime()}\n")
        os.remove("./考试链接.txt")


if __name__ == "__main__":
    asyncio.run(main())
