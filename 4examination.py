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
    format='%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s',
    handlers=[
        logging.FileHandler('log.txt', mode='w'),
        logging.StreamHandler()
    ]
)


# 获取考试是否通过
async def check_exam_passed(page):
    # 获取最新的考试记录（表格的第一行）
    # 获取所有考试记录
    exam_rows = await page.locator(".table.tbody.tr").all()

    if not exam_rows:
        logging.warning("未找到考试记录")
        return False

    # 获取最新的考试记录（表格的第一行）
    latest_exam = exam_rows[0]

    # 获取状态
    status_element = latest_exam.locator("td").nth(3)
    await status_element.wait_for(state="visible", timeout=5000)
    status = await status_element.inner_text()

    logging.info(f"考试状态: {status}")

    # 判断是否通过
    return status.strip() == "及格"


# 等待完成考试
async def wait_for_finish_test(page1):
    async with page1.expect_popup() as page2_info:
        await page1.locator('.btn.new-radius').click()
    page2 = await page2_info.value
    logging.info('等待作答完毕并关闭页面')
    await page2.wait_for_event('close', timeout=0)


async def main():
    with open('./考试链接.txt', encoding='utf-8') as f:
        urls = list(f.readlines())

    # Load the cookies
    with open("cookies.json", "r") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--mute-audio"], channel="chrome")
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto(urls[0])
        await page.wait_for_url(re.compile(r'https://kc\.zhixueyun\.com/#/home-v\?id=\d+'), timeout=0)
        await page.close()
        for url in urls:
            while True:
                page1 = await context.new_page()
                logging.info(f'当前考试链接为: {url.strip()}')
                await page1.goto(url.strip())
                await page1.wait_for_load_state('load')
                await page1.locator(".top").first.click()
                await page1.locator('dl.chapter-list-box[data-sectiontype="9"]').click()
                await page1.locator('.tab-container').wait_for()
                await page1.wait_for_timeout(3000)
                if await check_exam_passed(page1):
                    logging.info('当前考试通过')
                    await page1.close()
                    break
                else:
                    logging.info('考试未通过，重新考试')
                    await wait_for_finish_test(page1)
                    await page1.wait_for_timeout(3000)
                    await page1.close()
                    continue

        await context.close()
        await browser.close()
        logging.info(f'\n考试完成，当前时间为{time.ctime()}\n')
        os.remove('./考试链接.txt')


if __name__ == '__main__':
    asyncio.run(main())
