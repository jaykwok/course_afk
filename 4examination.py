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


# 获取考试分数
def get_score(text):
    match = re.search(r'成绩(\d+)', text)
    if match:
        return int(match.group(1))  # 返回匹配到的数字
    else:
        return int(0)  # 如果未找到数字，则返回 0


# 等待完成考试
async def wait_for_finish_test(page1):
    async with page1.expect_popup() as page2_info:
        await page1.locator('.btn.new-radius').click()
    page2 = await page2_info.value
    logging.info('等待作答完毕并关闭页面')
    await page2.wait_for_event('close', timeout=0)


async def main():
    with open('./考试链接.txt', encoding='utf-8') as f:
        urls = set(f.readlines())

    # Load the cookies
    with open("cookies.json", "r") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--mute-audio"], channel="chrome")
        context = await browser.new_context()
        await context.add_cookies(cookies)
        for url in urls:
            while True:
                page1 = await context.new_page()
                logging.info(f'当前考试链接为: {url.strip()}')
                await page1.goto(url.strip())
                await page1.locator(".top").first.click()
                await page1.locator('dl.chapter-list-box[data-sectiontype="9"]').click()
                await page1.locator('.tab-container').wait_for()
                if get_score(await page1.locator('dl.chapter-list-box[data-sectiontype="9"]').locator(
                        '.item.pointer').inner_text()) >= 60:
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
