import asyncio
import logging
import math
import re
import time
import traceback

# 日志基本设置
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s',
    handlers=[
        logging.FileHandler('log.txt', mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)


def save_to_file(filename, url):
    """将链接保存到指定文件"""

    with open(filename, 'a+', encoding='utf-8') as wp:
        logging.info(f'写入{filename}完毕\n')
        wp.write(f'{url}\n')


def is_learned(text: str) -> bool:
    """判断课程是否已学习"""

    return re.search(r'需学|需再学', text) is None


def time_to_seconds(duration: str) -> int:
    """时长转换为秒数"""

    pattern = r'(\d+)?:\d{1,2}'
    match = re.search(pattern, duration)
    if not match:
        return 0

    units = match.group().split(':')
    total_seconds = sum(int(unit) * 60 ** index for index, unit in enumerate(reversed(units)))
    return math.ceil(total_seconds / 10) * 10


def calculate_remaining_time(text) -> int:
    """计算当前课程剩余挂课时间"""

    pattern = r'(\d+:\d{1,2})'
    match = re.findall(pattern, text)
    total_time = time_to_seconds(match[0])
    remaining_time = time_to_seconds(match[1])

    return min(math.ceil(remaining_time / 60) * 60, total_time), total_time


async def timer(duration: int, interval: int = 10):
    """定时器"""

    duration = math.ceil(duration)
    logging.info(f'开始时间: {time.ctime()}')
    for elapsed in range(0, duration, interval):
        await asyncio.sleep(interval)
        logging.info(f'已学习 {elapsed + interval} / {duration} (秒)')
    logging.info(f'结束时间: {time.ctime()}')


async def check_for_pass_grade(page):
    # 首先定位到包含表格的div
    table_container = page.locator('div.tab-container table')

    # 在表格中查找包含"及格"文本的单元格
    pass_cell = await table_container.locator('td:has-text("及格")').all()

    # 检查是否找到了"及格"
    if pass_cell:
        return True
    else:
        return False


async def is_course_completed(page):
    # 定位到包含进度信息的元素
    progress_element = page.locator('div.course-progress div.progress')

    # 获取元素的文本内容
    progress_text = await progress_element.inner_text()
    if '100%' in progress_text:
        return True
    else:
        return False


async def subject_learning(page):
    """主题内容学习"""

    await page.wait_for_load_state('load')
    await page.wait_for_timeout(3000)
    await page.locator('.item.current-hover').last.wait_for()
    await page.locator('.item.current-hover').locator('.section-type').last.wait_for()

    learn_list = await page.locator('.item.current-hover', has_not_text='重新学习').all()
    if learn_list:
        for learn_item in learn_list:
            section_type = await learn_item.locator('.section-type').inner_text()
            if section_type == '课程':
                async with page.expect_popup() as page_pop:
                    await learn_item.locator('.inline-block.operation').click()
                page_detail = await page_pop.value
                try:
                    await course_learning(page_detail)
                except Exception as e:
                    logging.error(f'发生错误: {str(e)}')
                    logging.error(traceback.format_exc())
                    save_to_file('剩余未看课程链接.txt', page_detail.url)
                finally:
                    await page_detail.close()
            elif section_type == 'URL':
                logging.info('URL学习类型，存入文档单独审查')
                save_to_file('URL类型链接.txt', page.url)
                async with page.expect_popup() as page_pop:
                    await learn_item.locator('.inline-block.operation').click()
                page_detail = await page_pop.value
                timer_task = asyncio.create_task(timer(10, 1))
                await page_detail.wait_for_timeout(10 * 1000)  # For safety
                await timer_task
                await page_detail.close()
            else:
                logging.info('非课程类学习类型，存入文档单独审查')
                save_to_file('非课程类学习类型链接.txt', page.url)


async def course_learning(page_detail):
    """课程内容学习"""

    await page_detail.wait_for_load_state('load')
    if await is_course_completed(page_detail):
        title = await page_detail.locator('span.course-title-text').inner_text()
        logging.info(f'{title}已学习完毕，跳过该课程\n')
        return
    await page_detail.wait_for_timeout(3000)
    await page_detail.locator('dl.chapter-list-box.required').last.wait_for()
    chapter_boxes = await page_detail.locator('dl.chapter-list-box.required').all()

    for count, box in enumerate(chapter_boxes, start=1):
        section_type = await box.get_attribute('data-sectiontype')
        box_text = await box.locator('.text-overflow').inner_text()
        logging.info(f'课程信息: \n{box_text}\n')

        if section_type == '6':
            progress_text = await box.locator('.section-item-wrapper').inner_text()
            if is_learned(progress_text):
                logging.info(f'课程{count}已学习，跳过该节\n')
                continue
            await handle_video(box, page_detail)

        elif section_type in ['1', '2']:
            await handle_document(box, page_detail)

        elif section_type == '9':
            # 处理考试类型课程
            await box.locator('.section-item-wrapper').click()
            await page_detail.wait_for_timeout(3 * 1000)
            if not await check_for_pass_grade(page_detail):
                logging.info('考试链接类型，存入文档')
                save_to_file('考试链接.txt', page_detail.url)
            else:
                logging.info(f'课程{count}已学习，跳过该节\n')

        else:
            logging.info('非视频学习和文档学习类型，存入文档单独审查')
            save_to_file('未知类型链接.txt', page_detail.url)
        logging.info(f'课程{count}学习完毕')


async def handle_video(box, page):
    """处理视频类型课程"""

    await box.locator('.section-item-wrapper').click()
    await page.wait_for_timeout(3 * 1000)
    resume_button = await page.locator('.register-mask-layer').all()
    if resume_button:
        await resume_button[0].click()
    await page.locator('.vjs-progress-control').first.wait_for()
    await page.locator('.vjs-duration-display').wait_for()

    remaining, duration = calculate_remaining_time(await box.locator('.section-item-wrapper').inner_text())
    logging.info(f'课程总时长: {duration}秒')
    logging.info(f'还需学习: {remaining}秒')

    timer_task = asyncio.create_task(timer(remaining))
    await page.wait_for_timeout(remaining * 1000)
    await timer_task


async def handle_document(box, page):
    """处理文档类型课程"""

    await box.locator('.section-item-wrapper').click()
    await page.wait_for_timeout(3 * 1000)
    # await page.locator('.clearfix').first.wait_for()
    await page.locator('.textLayer').first.wait_for()
    timer_task = asyncio.create_task(timer(10, 1))
    await page.wait_for_timeout(10 * 1000)
    await timer_task


async def is_subject_completed(page):
    """判断Subject是否学习完毕"""

    await page.wait_for_load_state('load')
    await page.locator('.item.current-hover').last.wait_for()
    await page.locator('.item.current-hover').locator('.section-type').last.wait_for()

    content = await page.locator('.item.current-hover', has_not_text='重新学习').filter(has_text='URL').all()
    return not bool(content)
