
from playwright.sync_api import sync_playwright
import asyncio
import json
import logging
import math
import re
import time


# 日志基本设置
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s',
    handlers=[
        logging.FileHandler('log.txt', mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


def get_cookie():
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
        with open('../cookies.json', 'w') as f:
            f.write(json.dumps(context.cookies()))
        page.close()
        context.close()
        browser.close()

def is_learned(text: str) -> bool:
    """判断课程是否已学习"""
    return re.search(r'重新学习', text) is not None


def time_to_seconds(duration: str) -> int:
    """时长转换为秒数"""
    pattern = r'(\d{1,2}:)?\d{1,2}:\d{1,2}'
    match = re.search(pattern, duration)
    if not match:
        return 0

    units = match.group().split(':')
    total_seconds = sum(int(unit) * 60 ** index for index, unit in enumerate(reversed(units)))
    return math.ceil(total_seconds / 10) * 10


def calculate_remaining_time(percentage: str, total_time: int) -> int:
    """计算当前课程剩余挂课时间"""
    match = re.search(r'(\d+)%', percentage)
    if match:
        percent_completed = int(match.group(1))
        remaining_time = total_time * (80 - percent_completed) / 100
    else:
        remaining_time = total_time * 0.8

    return min(math.ceil(remaining_time / 60) * 60, total_time)


async def timer(duration: int, interval: int = 10):
    """定时器"""
    duration = math.ceil(duration)
    logging.info(f'开始时间: {time.ctime()}')
    for elapsed in range(0, duration, interval):
        await asyncio.sleep(interval)
        logging.info(f'已学习 {elapsed + interval} / {duration} (秒)')
    logging.info(f'结束时间: {time.ctime()}')


async def block_learning(page):
    """板块内容学习"""
    await page.wait_for_load_state('load')
    await page.locator('.item.current-hover').last.wait_for()
    await page.locator('.item.current-hover').locator('.section-type').last.wait_for()

    learn_list = await page.locator('.item.current-hover', has_not_text='重新学习').all()
    for learn_item in learn_list:
        section_type = await learn_item.locator('.section-type').inner_text()
        if section_type == '课程':
            async with page.expect_popup() as page_info:
                await learn_item.click()
            page_detail = await page_info.value
            await page_detail.wait_for_load_state('load')
            await handle_course(page_detail)
            await page_detail.close()
        elif section_type == 'URL':
            logging.info('URL学习类型，存入文档单独审查')
            with open('./URL类型链接.txt', 'a+', encoding='utf-8') as wp:
                wp.write(f'{page.url} \n')
            async with page.expect_popup() as page_info:
                await learn_item.click()
            page_detail = await page_info.value
            timer_task = asyncio.create_task(timer(10, 1))
            await page_detail.wait_for_timeout(10 * 1000)  # For safety
            await timer_task
            await page_detail.close()
        else:
            logging.info('非课程类学习类型，存入文档单独审查')
            with open('./非课程类学习类型链接.txt', 'a+', encoding='utf-8') as wp:
                wp.write(f'{page.url} \n')


async def handle_course(page_detail):
    """课程内容学习"""
    await page_detail.locator('.item.pointer').last.wait_for()
    await page_detail.locator('dl.chapter-list-box.required').last.wait_for()
    chapter_boxes = await page_detail.locator('dl.chapter-list-box.required').all()

    for count, box in enumerate(chapter_boxes, start=1):
        section_type = await box.get_attribute('data-sectiontype')
        box_text = await box.inner_text()
        logging.info(f'课程信息: \n{box_text}\n')

        if is_learned(box_text):
            logging.info(f'课程{count}已学习，跳过该节\n')
            continue

        if section_type == '6':
            await handle_video(box, page_detail)
        elif section_type in ['1', '2']:
            await handle_document(box, page_detail)
        else:
            logging.info('非视频学习和文档学习类型，存入文档单独审查')
            with open('./考试链接.txt', 'a+', encoding='utf-8') as wp:
                wp.write(f'{page_detail.url} \n')

        logging.info(f'课程{count}学习完毕')


async def handle_video(box, page):
    """处理视频类型课程"""
    await box.locator('.item.pointer').click()
    await page.locator('.vjs-progress-control').first.wait_for()

    duration_element = page.locator('.vjs-duration-display')
    duration = time_to_seconds(await duration_element.inner_text())
    logging.info(f'课程总时长: {duration}秒')

    percent_complete = await box.locator('.item.pointer').inner_text()
    remaining = calculate_remaining_time(percent_complete, duration)
    logging.info(f'还需学习: {remaining}秒')

    timer_task = asyncio.create_task(timer(remaining))
    await page.wait_for_timeout(remaining * 1000)
    await timer_task


async def handle_document(box, page):
    """处理文档类型课程"""
    await box.locator('.item.pointer').click()
    await page.locator('.clearfix').first.wait_for()
    timer_task = asyncio.create_task(timer(10, 1))
    await page.wait_for_timeout(10 * 1000)
    await timer_task


async def is_completed(page):
    await page.wait_for_load_state('load')
    await page.locator('.item.current-hover').last.wait_for()
    await page.locator('.item.current-hover').locator('.section-type').last.wait_for()

    content = await page.locator('.item.current-hover', has_not_text='重新学习').filter(has_text='URL').all()
    return not bool(content)