import asyncio
import json
import logging
import os
import re
import time
import traceback

from playwright.async_api import async_playwright

import func_module as fm

# 设置学习文件路径
learning_file = './学习链接.txt'

# 设置是否学习过程中存在未知错误的标识：0为未发生错误，1为发生了错误
mark = 0

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
    global mark
    # 每一次运行main函数的时候，重置标识为0
    mark = 0
    if os.path.exists('./剩余未看课程链接.txt'):
        with open('./剩余未看课程链接.txt', encoding='utf-8') as f:
            urls = f.readlines()
        # 读取文件中保存的链接后，便删除文件，便于后续重写并追加新的未学习的链接
        os.remove('./剩余未看课程链接.txt')
    else:
        with open(learning_file, encoding='utf-8') as f:
            urls = f.readlines()

    with open('cookies.json', 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--mute-audio'], channel='chrome', slow_mo=3000)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto('https://kc.zhixueyun.com/')
        await page.wait_for_url(re.compile(r'https://kc\.zhixueyun\.com/#/home-v\?id=\d+'), timeout=0)
        await page.close()
        for url in urls:
            page = await context.new_page()
            logging.info(f'当前学习链接为: {url.strip()}')
            await page.goto(url.strip())
            if 'subject' in url:
                try:
                    mark = await fm.subject_learning(page, mark)
                except Exception as e:
                    logging.error(f'发生错误: {str(e)}')
                    logging.error(traceback.format_exc())
                    fm.save_to_file('剩余未看课程链接.txt', url.strip())
                    if mark == 0:
                        mark = 1
                finally:
                    await page.close()

            elif 'course' in url:
                try:
                    await fm.course_learning(page)
                except Exception as e:
                    logging.error(f'发生错误: {str(e)}')
                    logging.error(traceback.format_exc())
                    fm.save_to_file('剩余未看课程链接.txt', url.strip())
                    if mark == 0:
                        mark = 1
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

        # 如果未出现错误且文本文档存在，则删除文本文档
        if os.path.exists('./剩余未看课程链接.txt') and mark == 0:
            os.remove('./剩余未看课程链接.txt')

        await context.close()
        await browser.close()
        logging.info(f'自动挂课完成，当前时间为{time.ctime()}')


if __name__ == '__main__':
    while True:
        asyncio.run(main())
        if mark == 0:
            break
