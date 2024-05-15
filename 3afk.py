import asyncio
import json
import logging
import math
import os
import re
import time
import traceback

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


# 判断课程是否已学习
def isLearned(text):
    match = re.search(r'重新学习', text)
    if match:
        return True
    else:
        return False


# 时长转换为秒数
def time2sec(t):
    pattern = r'(\d{1,2}:)?\d{1,2}:\d{1,2}'
    match = re.search(pattern, t)
    t = match.group()
    temp = t.split(':')
    result = 0
    for i in range(len(temp)):
        result += int(temp[len(temp) - i - 1]) * 60 ** i
    result = math.ceil(result / 10) * 10
    return result


# 计算当前课程剩余挂课时间
def remaining_time(pc, t):
    match = re.search(r'(\d+)%', pc)
    if match:
        pc = int(match.group(1))
        remain = t * (80 - pc) / 100
        remain = math.ceil(remain / 60) * 60
        if remain < t:
            return remain
        else:
            return t
    else:
        remain = math.ceil(t * 0.8 / 60) * 60
        if remain < t:
            return remain
        else:
            return t


async def timer(t, interval=10):
    t = math.ceil(t)
    logging.info(f'开始时间: {time.ctime()}')
    for elapsed in range(0, t, interval):
        await asyncio.sleep(interval)
        logging.info(f'已学习 {elapsed + interval} / {t} (秒)')
    logging.info(f'结束时间: {time.ctime()}')


# 板块内容学习
async def block_learning(page1):
    # 等待特定元素出现
    # await page1.wait_for_timeout(3 * 1000)
    await page1.wait_for_load_state('load')
    await page1.locator('.item.current-hover').last.wait_for()
    await page1.locator('.item.current-hover').locator('.section-type').last.wait_for()

    # 获取需要学习的链接列表
    # learn_list = await page1.get_by_text(re.compile(r'开始学习|继续学习')).all()
    learn_list = await page1.locator('.item.current-hover', has_not_text='重新学习').all()
    if learn_list:
        for learn_content in learn_list:
            if await learn_content.locator('.section-type').inner_text() == '课程':
                async with page1.expect_popup() as page2_info:
                    await learn_content.click()
                page2 = await page2_info.value
                # try:
                #     await course_learning(page2)
                # except Exception as e:
                #     print(f'出错页面为: {page2.url}\n错误信息为: {e}\n')
                # finally:
                #     await page2.close()
                await course_learning(page2)
                await page2.close()
            elif await learn_content.locator('.section-type').inner_text() == 'URL':
                logging.info('URL学习类型，存入文档单独审查')
                with open('./URL类型链接.txt', 'a+') as wp:
                    wp.write(f'{page1.url} \n')
                async with page1.expect_popup() as page2_info:
                    await learn_content.click()
                page2 = await page2_info.value
                timer_task = asyncio.create_task(timer(10, 1))
                await page2.wait_for_timeout(10 * 1000)
                await timer_task
                await page2.close()

            else:
                logging.info('非课程类学习类型，存入文档单独审查')
                with open('./非课程类学习类型链接.txt', 'a+') as wp:
                    wp.write(f'{page1.url} \n')


# 课程内容学习
async def course_learning(page2):
    await (page2.locator('.item.pointer')).last.wait_for()
    await (page2.locator('dl.chapter-list-box.required')).last.wait_for()
    chapter_list_boxes = await page2.locator('dl.chapter-list-box.required').all()
    logging.info(f'chapter_list_boxes: {chapter_list_boxes}\n')
    count = 1
    for box in chapter_list_boxes:
        # 获取学习类型参数
        section_type = await box.get_attribute('data-sectiontype')
        text = await box.inner_text()
        logging.info(f'课程信息: \n{text}\n')
        if isLearned(text):
            logging.info(f'课程{count}已学习，跳过该节\n')
            continue

        # 根据不同的 data-sectiontype 执行不同的操作
        if section_type == '6':
            # 执行操作1
            logging.info('课程类型为视频类型')
            await (box.locator('.item.pointer')).click()
            await (page2.locator('.vjs-progress-control')).first.wait_for()
            await page2.wait_for_timeout(3 * 1000)
            logging.info(await (box.locator('.item.pointer')).inner_text())
            duration_element = page2.locator('.vjs-duration-display')
            duration = time2sec(await duration_element.inner_text())
            logging.info(f'课程总时长: {duration}秒')
            remain = remaining_time(await box.locator('.item.pointer').inner_text(), duration)
            logging.info(f'还需学习: {remain}秒')
            timer_task = asyncio.create_task(timer(remain))
            await page2.wait_for_timeout(remain * 1000)
            await timer_task

        elif section_type in ['1', '2']:
            # 执行操作2
            logging.info('课程类型为文档类型')
            await (box.locator('.item.pointer')).click()
            await (page2.locator('.clearfix')).first.wait_for()
            timer_task = asyncio.create_task(timer(10, 1))
            await page2.wait_for_timeout(10 * 1000)
            await timer_task
        # 添加其他可能的情况
        else:
            logging.info('非视频学习和文档学习类型，存入文档单独审查')
            with open('./考试链接.txt', 'a+') as wp:
                wp.write(f'{page2.url} \n')
        logging.info(f'课程{count}学习完毕')
        count += 1


async def isCompleted(page1):
    await page1.wait_for_load_state('load')
    await page1.locator('.item.current-hover').last.wait_for()
    await page1.locator('.item.current-hover').locator('.section-type').last.wait_for()
    content = await page1.locator('.item.current-hover', has_not_text='重新学习').filter(has_text='URL').all()
    if content:
        logging.info(f'URL类型链接未学习完成: {content}')
        return False
    else:
        return True


async def main():
    mark = 0
    if not os.path.exists('./剩余未看课程链接.txt'):
        with open('./战新产品规模发展专区.txt', encoding='utf-8') as f:
            urls = f.readlines()
    else:
        mark = 1
        with open('./剩余未看课程链接.txt', encoding='utf-8') as f:
            urls = f.readlines()

    # Load the cookies
    with open('cookies.json', 'r') as f:
        cookies = json.loads(f.read())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--mute-audio'], channel='chrome')
        context = await browser.new_context(viewport={'width': 800, 'height': 600})
        await context.add_cookies(cookies)
        for url in urls:
            page1 = await context.new_page()
            logging.info(f'当前学习板块链接为: {url.strip()}')
            await page1.goto(url.strip())
            try:
                await block_learning(page1)
            except Exception as e:
                logging.error(f'发生错误: {str(e)}')
                logging.error(traceback.format_exc())
                with open('./剩余未看课程链接.txt', 'a+', encoding='utf-8') as f:
                    f.write(url)
                if mark == 1:
                    mark = 0
            finally:
                await page1.close()

        if os.path.exists('./URL类型链接.txt'):
            with open('./URL类型链接.txt', encoding='UTF-8') as f:
                urls = f.readlines()
            with open('./剩余未看课程链接.txt', 'a+', encoding='utf-8') as f:
                for url in urls:
                    page1 = await context.new_page()
                    await page1.goto(url.strip())
                    if await isCompleted(page1):
                        logging.info(f'URL类型链接: {url.strip()}\n学习完成')
                    else:
                        f.write(url)
                    await page1.close()
            os.remove('./URL类型链接.txt')

        await context.close()
        await browser.close()
        logging.info(f'\n自动挂课完成，当前时间为{time.ctime()}\n')
        if mark == 1:
            os.remove('./剩余未看课程链接.txt')


if __name__ == '__main__':
    asyncio.run(main())
