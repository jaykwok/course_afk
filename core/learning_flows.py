from __future__ import annotations

import asyncio
import logging
import traceback

from core.config import (
    EXAM_URLS_FILE,
    NO_PERMISSION_FILE,
    OTHER_TYPE_FILE,
    RETRY_URLS_FILE,
    SURVEY_TYPE_FILE,
    UNKNOWN_TYPE_FILE,
    URL_TYPE_FILE,
    URL_TYPE_WAIT,
)
from core.file_ops import save_to_file
from core.learning_common import check_permission, get_course_url, is_learned, timer
from core.learning_exam import check_exam_passed, handle_examination
from core.learning_handlers import handle_document, handle_h5, handle_video
from core.learning_popups import handle_rating_popup


async def handle_subject_exam_item(learn_item) -> str | None:
    status_texts = [
        status.strip()
        for status in await learn_item.locator("span.finished-status").all_inner_texts()
        if status.strip()
    ]
    completion_status = next((status for status in status_texts if "已完成" in status), None)
    if completion_status == "已完成":
        logging.info("学习主题考试已完成, 跳过")
        return None

    exam_url = await get_course_url(learn_item, section_type="exam")
    logging.info("学习主题考试类型, 存入考试链接")
    save_to_file(EXAM_URLS_FILE, exam_url)
    return exam_url


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
        if await learn_item.locator(".iconfont.m-right.icon-reload").count() > 0:
            continue

        section_type = await learn_item.locator(".section-type").inner_text()

        if section_type == "课程":
            async with page.expect_popup() as page_pop:
                await learn_item.locator(".inline-block.operation").click()
            page_detail = await page_pop.value
            try:
                await course_learning(page_detail, learn_item)
            except Exception as exc:
                logging.error(f"发生错误: {str(exc)}")
                logging.error(traceback.format_exc())
                if str(exc) == "无权限查看该资源":
                    save_to_file(NO_PERMISSION_FILE, await get_course_url(learn_item))
                else:
                    save_to_file(RETRY_URLS_FILE, await get_course_url(learn_item))
                    raise
            finally:
                await page_detail.close()

        elif section_type == "URL":
            logging.info("URL学习类型, 存入文档单独审查")
            save_to_file(URL_TYPE_FILE, page.url)
            async with page.expect_popup() as page_pop:
                await learn_item.locator(".inline-block.operation").click()
            page_detail = await page_pop.value
            timer_task = asyncio.create_task(
                timer(URL_TYPE_WAIT, 1, description="URL 类型学习等待")
            )
            await page_detail.wait_for_timeout(URL_TYPE_WAIT * 1000)
            await timer_task
            await page_detail.close()

        elif section_type == "考试":
            await handle_subject_exam_item(learn_item)

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

    if await _is_course_completed(page_detail):
        title = await page_detail.locator("span.course-title-text").inner_text()
        logging.info(f"<{title}>已学习完毕, 跳过该课程\n")
        return

    await page_detail.locator("dl.chapter-list-box.required").last.wait_for()
    chapter_locator = page_detail.locator("dl.chapter-list-box.required")
    chapter_count = await chapter_locator.count()

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
                exam_passed = await check_exam_passed(page_detail)
                if exam_passed:
                    logging.info("考试已通过, 跳过该节")
                    continue
                if learn_item:
                    await handle_examination(
                        page_detail,
                        learn_item,
                        exam_passed=exam_passed,
                    )
                else:
                    await handle_examination(page_detail, exam_passed=exam_passed)
            else:
                logging.info("未知课程学习类型, 存入文档单独审查")
                if learn_item:
                    save_to_file(UNKNOWN_TYPE_FILE, await get_course_url(learn_item))
                else:
                    save_to_file(UNKNOWN_TYPE_FILE, page_detail.url)
                continue
        except Exception as exc:
            logging.error(f"课程{count+1}学习失败: {str(exc)}")
            logging.error(traceback.format_exc())
            has_failed_box = True
            continue
        logging.info(f"课程{count+1}学习完毕")

    if has_failed_box:
        raise Exception("部分章节学习失败")


async def _is_course_completed(page):
    progress_element = page.locator("div.course-progress div.progress")
    progress_text = await progress_element.inner_text()
    return "100%" in progress_text
