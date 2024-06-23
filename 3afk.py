import asyncio
import json
import logging
import os
import re
import time
import traceback

from playwright.async_api import async_playwright

import func_module as fm

# 日志基本设置
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s',
    handlers=[
        logging.FileHandler('log.txt', mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


async def main():
    mark = 0
    if os.path.exists('./剩余未看课程链接.txt'):
        mark = 1
        with open('./剩余未看课程链接.txt', encoding='utf-8') as f:
            urls = f.readlines()
    else:
        with open('./学习链接.txt', encoding='utf-8') as f:
            urls = f.readlines()

    with open('cookies.json', 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--mute-audio'], channel='chrome')
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto(urls[0])
        await page.wait_for_url(re.compile(r'https://kc\.zhixueyun\.com/#/home-v\?id=\d+'), timeout=0)
        await page.close()
        for url in urls:
            page = await context.new_page()
            logging.info(f'当前学习链接为: {url.strip()}')
            await page.goto(url.strip())
            if 'subject' in url:
                try:
                    await fm.subject_learning(page)
                except Exception as e:
                    logging.error(f'发生错误: {str(e)}')
                    logging.error(traceback.format_exc())
                    # with open('./剩余未看课程链接.txt', 'a+', encoding='utf-8') as f:
                    #     f.write(url)
                    fm.save_to_file('剩余未看课程链接.txt', url.strip())
                    if mark == 1:
                        mark = 0
                finally:
                    await page.close()
                    
            elif 'course' in url:
                try:
                    await fm.course_learning(page)
                except Exception as e:
                    logging.error(f'发生错误: {str(e)}')
                    logging.error(traceback.format_exc())
                    # with open('./剩余未看课程链接.txt', 'a+', encoding='utf-8') as f:
                    #     f.write(url)
                    fm.save_to_file('剩余未看课程链接.txt', url.strip())
                    if mark == 1:
                        mark = 0
                finally:
                    await page.close()

        if os.path.exists('./URL类型链接.txt'):
            with open('./URL类型链接.txt', encoding='utf-8') as f:
                urls = f.readlines()
            with open('./剩余未看课程链接.txt', 'a+', encoding='utf-8') as f:
                for url in urls:
                    page = await context.new_page()
                    await page.goto(url.strip())
                    if await fm.is_subject_completed(page):
                        logging.info(f'URL类型链接: {url.strip()} 学习完成')
                    else:
                        f.write(url)
                    await page.close()
            os.remove('./URL类型链接.txt')

        await context.close()
        await browser.close()
        logging.info(f'自动挂课完成，当前时间为{time.ctime()}')
        if mark == 1:
            os.remove('./剩余未看课程链接.txt')


if __name__ == '__main__':
    asyncio.run(main())
