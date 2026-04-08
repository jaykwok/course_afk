import asyncio
import logging
import math
import re
import time
import traceback

from core.config import (
    DOCUMENT_INITIAL_WAIT,
    DOCUMENT_SYNC_EXTRA_WAIT,
    EXAM_URLS_FILE,
    H5_TYPE_FILE,
    NO_PERMISSION_FILE,
    OTHER_TYPE_FILE,
    RETRY_URLS_FILE,
    SUBJECT_EXAM_FILE,
    SURVEY_TYPE_FILE,
    TIMER_DEFAULT_INTERVAL,
    UNKNOWN_TYPE_FILE,
    URL_TYPE_FILE,
    URL_TYPE_WAIT,
    VIDEO_SYNC_CHECK_INTERVAL,
    VIDEO_SYNC_EXTRA_WAIT,
    ZHIXUEYUN_COURSE_PREFIX,
    ZHIXUEYUN_EXAM_PREFIX,
)
from core.file_ops import save_to_file


async def check_permission(frame):
    """检查是否有权限查看资源"""
    try:
        text_content = await frame.content()
        return not (
            "您没有权限查看该资源" in text_content
            or "该资源已不存在" in text_content
            or "该资源已下架" in text_content
        )
    except Exception as e:
        logging.error(f"检查frame时出错: {e}")
        return False


def is_learned(text: str) -> bool:
    """判断课程是否已学习"""
    return re.search(r"需学|需再学", text) is None


def time_to_seconds(duration: str) -> int:
    """时长转换为秒数"""
    pattern = r"(\d+)?:\d{1,2}"
    match = re.search(pattern, duration)
    if not match:
        return 0

    units = match.group().split(":")
    total_seconds = sum(
        int(unit) * 60**index for index, unit in enumerate(reversed(units))
    )
    return math.ceil(total_seconds / 10) * 10


def calculate_remaining_time(text) -> tuple[int, int]:
    """计算当前课程剩余挂课时间"""
    pattern = r"(\d+:\d{1,2})"
    match = re.findall(pattern, text)
    if len(match) == 1:
        total_time = remaining_time = time_to_seconds(match[0])
    elif len(match) == 2:
        total_time = time_to_seconds(match[0])
        remaining_time = time_to_seconds(match[1])
    else:
        raise Exception(f"无法解析课程时长: {text}")

    return min(math.ceil(remaining_time / 60) * 60, total_time), total_time


async def timer(duration: int, interval: int = TIMER_DEFAULT_INTERVAL):
    """定时器"""
    duration = math.ceil(duration)
    logging.info(f"开始时间: {time.ctime()}")
    for elapsed in range(0, duration, interval):
        await asyncio.sleep(interval)
        logging.info(f"已学习 {elapsed + interval} / {duration} (秒)")
    logging.info(f"结束时间: {time.ctime()}")


async def check_exam_passed(page):
    """检测考试是否通过"""
    await page.wait_for_timeout(1000)
    try:
        # 判断是否在考试中状态
        status_element = await page.locator(".neer-status").count()
        if status_element > 0:
            highest_score_text = await page.locator(".neer-status").inner_text()
            if "考试中" in highest_score_text:
                logging.info("考试状态: 考试中")
                return False

        # 检查表格是否存在
        table_exists = await page.locator("div.tab-container table.table").count()
        if table_exists == 0:
            logging.info("考试状态: 未找到考试表格")
            return False

        # 确认第一行的状态单元格存在后再获取文本
        status_cell_element = page.locator(
            "div.tab-container table.table tbody tr:first-child td:nth-child(4)"
        )
        await status_cell_element.wait_for(state="visible", timeout=1500)

        if await status_cell_element.count() == 0:
            logging.info("首次进入考试页面, 未进行考试")
            return False

        status_cell = (await status_cell_element.inner_text(timeout=3000)).strip()

        if status_cell == "及格":
            logging.info("考试状态: 通过")
            return True
        elif status_cell == "待评卷":
            logging.info("考试状态: 待评卷")
            return True
        else:
            logging.info(f"考试状态: 未通过 ({status_cell})")
            return False
    except Exception as e:
        logging.error(f"获取考试状态时出错: {e}")
        return False


async def handle_rating_popup(page):
    """监测评分弹窗, 选择五星并提交"""
    try:
        dialog = page.locator(".ant-modal-content")
        try:
            await dialog.wait_for(state="visible", timeout=1500)
            logging.info("检测到评分弹窗")
        except Exception as e:
            logging.debug(f"未检测到评分弹窗: {e}")
            return False

        stars_container = dialog.locator("ul.ant-rate")
        await stars_container.wait_for(state="visible", timeout=1000)

        try:
            fifth_star = dialog.locator("ul.ant-rate li:nth-child(5) div[role='radio']")
            await fifth_star.wait_for(state="visible", timeout=1000)

            await page.evaluate(
                "document.querySelector('ul.ant-rate').scrollIntoView({block: 'center'})"
            )

            await fifth_star.click(force=True)
            logging.info("已点击第五颗星星")
        except Exception as e:
            logging.warning(f"点击星星失败: {e}")

        await page.wait_for_timeout(500)

        try:
            confirm_button = page.get_by_role("button", name="确 定")
            await confirm_button.click()
            logging.info("已点击确定按钮")
            return True
        except Exception as e:
            logging.error(f"点击确定按钮时出错: {e}")
            return False

    except Exception as e:
        logging.error(f"处理评分弹窗时出错: {e}")
        return False


async def is_course_completed(page):
    """检查课程进度是否100%"""
    progress_element = page.locator("div.course-progress div.progress")
    progress_text = await progress_element.inner_text()
    return "100%" in progress_text


async def get_course_url(learn_item, section_type="course"):
    """根据学习项构造课程或考试URL"""
    course_id = await learn_item.get_attribute("data-resource-id")
    if section_type == "exam":
        prefix = ZHIXUEYUN_EXAM_PREFIX
    else:
        prefix = ZHIXUEYUN_COURSE_PREFIX
    return str(prefix + course_id)


async def subject_learning(page):
    """主题内容学习"""

    await page.wait_for_load_state("networkidle")

    if not await check_permission(page.main_frame):
        raise Exception("无权限查看该资源")

    await page.locator(".item.current-hover").last.wait_for()
    await page.locator(".item.current-hover").locator(".section-type").last.wait_for()

    learn_locator = page.locator(".item.current-hover")
    learn_count = await learn_locator.count()

    for i in range(learn_count):
        learn_item = learn_locator.nth(i)

        # 跳过已学完(重新学习)的项
        if await learn_item.locator(".iconfont.m-right.icon-reload").count() > 0:
            continue

        section_type = await learn_item.locator(".section-type").inner_text()

        if section_type == "课程":
            async with page.expect_popup() as page_pop:
                await learn_item.locator(".inline-block.operation").click()
            page_detail = await page_pop.value
            try:
                await course_learning(page_detail, learn_item)
            except Exception as e:
                logging.error(f"发生错误: {str(e)}")
                logging.error(traceback.format_exc())
                if str(e) == "无权限查看该资源":
                    save_to_file(NO_PERMISSION_FILE, await get_course_url(learn_item))
                else:
                    save_to_file(
                        RETRY_URLS_FILE, await get_course_url(learn_item)
                    )
                    raise
            finally:
                await page_detail.close()

        elif section_type == "URL":
            logging.info("URL学习类型, 存入文档单独审查")
            save_to_file(URL_TYPE_FILE, page.url)
            async with page.expect_popup() as page_pop:
                await learn_item.locator(".inline-block.operation").click()
            page_detail = await page_pop.value
            timer_task = asyncio.create_task(timer(URL_TYPE_WAIT, 1))
            await page_detail.wait_for_timeout(URL_TYPE_WAIT * 1000)
            await timer_task
            await page_detail.close()

        elif section_type == "考试":
            status_texts = await page.locator(
                "div.text-overflow.inline-block.m-left span.finished-status"
            ).all_inner_texts()
            completion_status = next(
                (status for status in status_texts if "已完成" in status), None
            )
            if completion_status == "已完成":
                continue
            else:
                logging.info("学习主题考试类型, 存入文档")
                save_to_file(SUBJECT_EXAM_FILE, page.url)

        elif section_type == "调研":
            logging.info("调研学习类型, 存入文档单独审查")
            save_to_file(SURVEY_TYPE_FILE, await get_course_url(learn_item))

        else:
            logging.info("非课程及考试类学习类型, 存入文档单独审查")
            save_to_file(OTHER_TYPE_FILE, page.url)


async def course_learning(page_detail, learn_item=None):
    """课程内容学习"""

    await page_detail.wait_for_load_state("load")

    if await check_permission(page_detail.main_frame):
        if await handle_rating_popup(page_detail):
            logging.info("五星评价完成")
    else:
        raise Exception("无权限查看该资源")

    if await is_course_completed(page_detail):
        title = await page_detail.locator("span.course-title-text").inner_text()
        logging.info(f"<{title}>已学习完毕, 跳过该课程\n")
        return

    await page_detail.locator("dl.chapter-list-box.required").last.wait_for()
    chapter_locator = page_detail.locator("dl.chapter-list-box.required")
    chapter_count = await chapter_locator.count()

    # 预先检查所有章节是否已学习
    all_learned = True
    has_non_detectable_types = False

    for i in range(chapter_count):
        box = chapter_locator.nth(i)
        section_type = await box.get_attribute("data-sectiontype")
        if section_type in ["1", "2", "3", "5", "6"]:
            progress_text = await box.locator(".section-item-wrapper").inner_text()
            if not is_learned(progress_text):
                all_learned = False
                break
        else:
            has_non_detectable_types = True

    if all_learned and not has_non_detectable_types:
        logging.info("所有章节已学习完毕, 跳过该课程")
        return

    has_failed_box = False
    for count in range(chapter_count):
        box = chapter_locator.nth(count)
        section_type = await box.get_attribute("data-sectiontype")
        box_text = await box.locator(".text-overflow").inner_text()
        logging.info(f"课程信息: \n{box_text}\n")

        if section_type in ["1", "2", "3", "5", "6"]:
            progress_text = await box.locator(".section-item-wrapper").inner_text()
            if is_learned(progress_text):
                logging.info(f"课程{count+1}已学习, 跳过该节\n")
                continue

        if await handle_rating_popup(page_detail):
            logging.info("五星评价完成")
        await box.locator(".section-item-wrapper").wait_for()
        await box.locator(".section-item-wrapper").click()

        try:
            if section_type in ["5", "6"]:
                logging.info("该课程为视频类型")
                await handle_video(box, page_detail)
            elif section_type in ["1", "2", "3"]:
                logging.info("该课程为文档、网页类型")
                await handle_document(page_detail, box)
            elif section_type == "4":
                logging.info("该课程为h5类型")
                await handle_h5(page_detail, learn_item)
            elif section_type == "9":
                logging.info("该课程为考试类型")
                if await check_exam_passed(page_detail):
                    logging.info("考试已通过, 跳过该节")
                    continue
                else:
                    if learn_item:
                        await handle_examination(page_detail, learn_item)
                    else:
                        await handle_examination(page_detail)
            else:
                logging.info("未知课程学习类型, 存入文档单独审查")
                if learn_item:
                    save_to_file(UNKNOWN_TYPE_FILE, await get_course_url(learn_item))
                else:
                    save_to_file(UNKNOWN_TYPE_FILE, page_detail.url)
                continue
        except Exception as e:
            logging.error(f"课程{count+1}学习失败: {str(e)}")
            logging.error(traceback.format_exc())
            has_failed_box = True
            continue
        logging.info(f"课程{count+1}学习完毕")

    if has_failed_box:
        raise Exception("部分章节学习失败")


async def check_and_handle_rating_popup(page):
    """检查并处理视频内课程质量评价弹窗"""
    try:
        popup_exists = (
            await page.locator(
                "div.split-section-detail-header--interact:has-text('互动练习')"
            ).count()
            > 0
        )

        if popup_exists:
            logging.info("检测到课程质量评价弹窗")
            skip_button = page.locator("button:has-text('跳 过')")
            if await skip_button.count() > 0:
                await skip_button.click()
                logging.info("已点击'跳过'按钮")
                await page.wait_for_timeout(1000)
                return True
    except Exception as e:
        logging.warning(f"处理评价弹窗时出错: {str(e)}")

    return False


async def check_rating_popup_periodically(page, duration, interval=30):
    """定期检查视频内评价弹窗, 持续指定时间"""
    elapsed = 0
    while elapsed < duration:
        wait_time = min(interval, duration - elapsed)
        await asyncio.sleep(wait_time)
        await check_and_handle_rating_popup(page)
        elapsed += wait_time


async def handle_video(box, page):
    """处理视频类型课程"""

    # 点击可能出现的继续播放按钮
    resume_button = await page.locator(".register-mask-layer").all()
    if resume_button:
        await resume_button[0].click()
    await page.locator(".vjs-progress-control").first.wait_for()
    await page.locator(".vjs-duration-display").wait_for()

    # 初次检查评价弹窗
    await check_and_handle_rating_popup(page)

    remaining, duration = calculate_remaining_time(
        await box.locator(".section-item-wrapper").inner_text()
    )
    logging.info(f"课程总时长: {duration} 秒")
    logging.info(f"还需学习: {remaining} 秒")

    # 等待计算的剩余时间, 同时定期检查评价弹窗
    # page.wait_for_timeout 保持 Playwright 连接活跃以维持视频播放状态
    timer_task = asyncio.create_task(timer(remaining))
    popup_check_task = asyncio.create_task(
        check_rating_popup_periodically(page, remaining)
    )
    await page.wait_for_timeout(remaining * 1000)
    await timer_task
    await popup_check_task

    # 确认课程进度是否已同步到服务器
    logging.info("课程学习完毕, 确认课程进度同步状态...")
    current_text = await box.locator(".section-item-wrapper").inner_text()
    if is_learned(current_text):
        logging.info("课程进度已同步到服务器")
        return

    # 额外等待最多 VIDEO_SYNC_EXTRA_WAIT 秒, 以便同步课程进度
    for i in range(0, VIDEO_SYNC_EXTRA_WAIT, VIDEO_SYNC_CHECK_INTERVAL):
        await check_and_handle_rating_popup(page)

        current_text = await box.locator(".section-item-wrapper").inner_text()
        if is_learned(current_text):
            logging.info(f"课程进度已同步到服务器, 额外等待 {i} 秒")
            return

        logging.info(
            f"课程进度仍未同步完成, 已额外等待 {i + VIDEO_SYNC_CHECK_INTERVAL} 秒, 继续等待..."
        )
        await page.wait_for_timeout(VIDEO_SYNC_CHECK_INTERVAL * 1000)

    current_text = await box.locator(".section-item-wrapper").inner_text()
    if not is_learned(current_text):
        logging.info(f"超时: 已额外等待{VIDEO_SYNC_EXTRA_WAIT}秒, 课程进度仍未同步")
        raise Exception("课程进度未能在额外等待时间内同步完成")


async def handle_document(page, box):
    """处理文档、网页类型课程"""
    await page.locator("[class*='fullScreen-content']").first.wait_for()
    await timer(DOCUMENT_INITIAL_WAIT, 1)

    # 确认课程进度是否已同步到服务器
    logging.info("课程学习完毕, 确认课程进度同步状态...")
    current_text = await box.locator(".section-item-wrapper").inner_text()
    if is_learned(current_text):
        logging.info("课程进度已同步到服务器")
        return

    # 额外等待最多 DOCUMENT_SYNC_EXTRA_WAIT 秒
    for i in range(1, DOCUMENT_SYNC_EXTRA_WAIT + 1):
        await page.wait_for_timeout(1000)
        current_text = await box.locator(".section-item-wrapper").inner_text()
        if is_learned(current_text):
            logging.info(f"课程进度已同步到服务器, 额外等待 {i} 秒")
            return
        logging.info(f"课程进度仍未同步完成, 已额外等待 {i} 秒, 继续等待...")

    logging.info(f"超时: 已额外等待{DOCUMENT_SYNC_EXTRA_WAIT}秒, 课程进度仍未同步")
    raise Exception("课程进度未能在额外等待时间内同步完成")


async def handle_h5(page, learn_item):
    """处理h5类型课程"""
    logging.info("h5课程类型, 存入文档")
    save_to_file(H5_TYPE_FILE, await get_course_url(learn_item))


async def handle_examination(page, learn_item=None):
    """处理考试类型课程"""
    if await check_exam_passed(page):
        logging.info("考试已通过, 跳过该节")
    else:
        if learn_item:
            logging.info("学习课程考试类型, 存入文档")
            save_to_file(EXAM_URLS_FILE, await get_course_url(learn_item))
            logging.info(f"链接: {await get_course_url(learn_item)}\n")
        else:
            logging.info("学习课程考试类型, 存入文档")
            save_to_file(EXAM_URLS_FILE, page.url)
            logging.info(f"链接: {page.url}\n")


async def is_subject_url_completed(page):
    """判断学习主题中的URL是否学习完毕"""
    await page.wait_for_load_state("load")
    await page.locator(".item.current-hover").last.wait_for()
    await page.locator(".item.current-hover").locator(".section-type").last.wait_for()

    content = (
        await page.locator(".item.current-hover", has_not_text="重新学习")
        .filter(has_text="URL")
        .all()
    )
    return not bool(content)
