from __future__ import annotations

import logging
import re
import traceback
from typing import Callable

from openai import OpenAI

from core.abort import UserAbortRequested
from core.browser import create_browser_context
from core.config import (
    COURSE_EXAM_ATTEMPT_THRESHOLD,
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    EXAM_URLS_FILE,
    MANUAL_EXAM_FILE,
    MODEL_NAME,
    PAPER_EXAM_ATTEMPT_THRESHOLD,
)
from core.exam_engine import ai_exam, wait_for_finish_test
from core.exam_answers import ExamAiConfigurationError
from core.file_ops import del_file, save_to_file
from core.learning import check_exam_passed, handle_rating_popup
from core.state import read_non_empty_lines


StatusCallback = Callable[[str], None]

COURSE_EXAM_BUTTON = ".btn.new-radius"
PAPER_EXAM_BUTTON = (
    ".banner-handler-btn.themeColor-border-color.themeColor-background-color"
)


def parse_remaining_attempts(button_text: str) -> int | None:
    match = re.search(r"剩余(\d+)次", button_text)
    if not match:
        return None
    return int(match.group(1))


def should_route_exam_to_manual(button_text: str, threshold: int) -> bool:
    if "剩余" not in button_text:
        return False
    remaining = parse_remaining_attempts(button_text)
    if remaining is None:
        return True
    return remaining <= threshold


def _build_exam_client() -> tuple[OpenAI, str]:
    client = OpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
    )
    return client, MODEL_NAME


async def _is_direct_answer_paper_page(page) -> bool:
    try:
        await page.locator(".question-type-item, .single-title, .single-btns").first.wait_for(
            timeout=5000
        )
        return True
    except Exception:
        return False


async def _can_continue_ai_exam(
    button_locator,
    *,
    threshold: int,
    url: str,
) -> bool:
    button_text = await button_locator.inner_text()
    if "剩余" not in button_text:
        logging.info("不限制考试次数, 继续 AI 自动考试")
        return True

    remaining = parse_remaining_attempts(button_text)
    if remaining is None:
        logging.info("无法解析剩余次数, 转为人工考试处理")
        save_to_file(MANUAL_EXAM_FILE, url.strip())
        return False

    if remaining <= threshold:
        logging.info(
            f"当前考试剩余次数为 {remaining}, 小于等于 {threshold} 次, 转为人工考试"
        )
        save_to_file(MANUAL_EXAM_FILE, url.strip())
        return False

    logging.info(f"当前考试剩余次数为 {remaining}, 大于 {threshold} 次, 继续 AI 自动考试")
    return True


async def _open_course_exam_tab(page) -> None:
    await page.locator(".top").first.wait_for(timeout=5000)
    await page.locator(".top").first.click()
    await page.locator('dl.chapter-list-box[data-sectiontype="9"]').click()
    await page.locator(".tab-container").wait_for()
    await page.wait_for_timeout(1000)


async def _handle_exam_result(page) -> None:
    await page.reload(wait_until="load")
    await page.wait_for_timeout(1500)
    if await handle_rating_popup(page):
        logging.info("五星评价完成")


async def _run_course_ai_exam(page, url: str, client: OpenAI, model: str) -> None:
    while True:
        await _open_course_exam_tab(page)

        exam_button = page.locator(COURSE_EXAM_BUTTON)
        if await exam_button.count() > 0:
            can_continue = await _can_continue_ai_exam(
                exam_button,
                threshold=COURSE_EXAM_ATTEMPT_THRESHOLD,
                url=url,
            )
            if not can_continue:
                return

        if await page.locator(".neer-status").count() > 0:
            if await check_exam_passed(page):
                return
            logging.info("AI 自动考试未通过, 转为人工考试")
            save_to_file(MANUAL_EXAM_FILE, url.strip())
            return

        logging.info("开始 AI 自动考试")
        await wait_for_finish_test(client, model, page)
        await _handle_exam_result(page)


async def _run_paper_ai_exam(page, url: str, client: OpenAI, model: str) -> None:
    if await _is_direct_answer_paper_page(page):
        logging.info("试卷页已直接进入答题页, 继续 AI 自动考试")
        await ai_exam(client, model, page, page.url, auto_submit=True)
        return

    exam_button = page.locator(PAPER_EXAM_BUTTON)
    await exam_button.wait_for(timeout=5000)

    can_continue = await _can_continue_ai_exam(
        exam_button,
        threshold=PAPER_EXAM_ATTEMPT_THRESHOLD,
        url=url,
    )
    if not can_continue:
        return

    logging.info("等待作答完毕并关闭试卷考试页面")
    async with page.expect_popup() as popup_info:
        await exam_button.click()
    popup = await popup_info.value
    await ai_exam(client, model, popup, page.url, auto_submit=False)


async def run_ai_exam_batch(status_callback: StatusCallback | None = None) -> int:
    urls = list(dict.fromkeys(read_non_empty_lines(EXAM_URLS_FILE)))
    if not urls:
        return 0

    client, model = _build_exam_client()
    async with create_browser_context() as (_, context):
        for index, url in enumerate(urls, start=1):
            page = await context.new_page()
            try:
                if status_callback:
                    status_callback(f"AI 考试 {index}/{len(urls)}: {url}")
                logging.info(f"当前考试链接为: {url}")
                await page.goto(url)
                await page.wait_for_load_state("load")

                if "course" in url:
                    await _run_course_ai_exam(page, url, client, model)
                elif "exam" in url:
                    await _run_paper_ai_exam(page, url, client, model)
                else:
                    logging.info("未知考试链接类型, 转为人工考试")
                    save_to_file(MANUAL_EXAM_FILE, url)
            except UserAbortRequested:
                raise
            except ExamAiConfigurationError:
                raise
            except Exception as exc:
                logging.error(f"AI 自动考试失败: {exc}")
                logging.error(traceback.format_exc())
                save_to_file(MANUAL_EXAM_FILE, url)
            finally:
                await page.close()

    del_file(EXAM_URLS_FILE)
    return len(read_non_empty_lines(MANUAL_EXAM_FILE))


async def _wait_for_manual_course_test(page) -> None:
    async with page.expect_popup() as popup_info:
        await page.locator(COURSE_EXAM_BUTTON).click()
    popup = await popup_info.value
    logging.info("等待手动考试完成并关闭页面")
    await popup.wait_for_event("close", timeout=0)


async def _wait_for_manual_paper_test(page) -> None:
    exam_button = page.locator(PAPER_EXAM_BUTTON)
    await exam_button.wait_for(timeout=5000)
    async with page.expect_popup() as popup_info:
        await exam_button.click()
    popup = await popup_info.value
    logging.info("等待手动试卷考试完成并关闭页面")
    await popup.wait_for_event("close", timeout=0)


async def _run_manual_course_exam(page, url: str) -> None:
    while True:
        await page.wait_for_timeout(1000)
        await _open_course_exam_tab(page)
        if await page.locator(".neer-status").count() > 0:
            if await check_exam_passed(page):
                return
            logging.info(f"课程考试未通过，重新考试: {url}")
            await _wait_for_manual_course_test(page)
        else:
            logging.info(f"开始手动课程考试: {url}")
            await _wait_for_manual_course_test(page)

        await page.reload(wait_until="load")
        await page.wait_for_timeout(1500)
        if await handle_rating_popup(page):
            logging.info("五星评价完成")


async def _run_manual_paper_exam(page, url: str) -> None:
    logging.info(f"开始手动试卷考试: {url}")
    await _wait_for_manual_paper_test(page)


async def run_manual_exam_batch(
    status_callback: StatusCallback | None = None,
    manual_exam_file=MANUAL_EXAM_FILE,
) -> int:
    urls = list(dict.fromkeys(read_non_empty_lines(manual_exam_file)))
    if not urls:
        return 0

    processed = 0
    remaining_urls: list[str] = []
    async with create_browser_context() as (_, context):
        for index, url in enumerate(urls, start=1):
            page = await context.new_page()
            try:
                if status_callback:
                    status_callback(f"人工考试 {index}/{len(urls)}: {url}")
                logging.info(f"当前人工考试链接为: {url}")
                await page.goto(url)
                await page.wait_for_load_state("load")

                if "course" in url:
                    await _run_manual_course_exam(page, url)
                elif "exam" in url:
                    await _run_manual_paper_exam(page, url)
                else:
                    logging.info("未知人工考试链接类型, 保留待处理")
                    remaining_urls.append(url)
                    continue

                processed += 1
            except Exception as exc:
                logging.error(f"人工考试流程失败: {exc}")
                logging.error(traceback.format_exc())
                remaining_urls.append(url)
            finally:
                await page.close()

    if remaining_urls:
        with open(manual_exam_file, "w", encoding="utf-8") as file:
            for url in remaining_urls:
                file.write(f"{url}\n")
    else:
        del_file(manual_exam_file)

    return processed
