from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.abort import UserAbortRequested
from core.browser import create_browser_context
from core.config import (
    AFK_SLOW_MO,
    CLEANUP_FILES,
    EXAM_URLS_FILE,
    LEARNING_URLS_FILE,
    NO_PERMISSION_FILE,
    NON_COMPLIANT_FILE,
    RETRY_URLS_FILE,
    URL_TYPE_FILE,
)
from core.file_ops import del_file, is_compliant_url_regex, normalize_url, save_to_file
from core.learning import course_learning, is_subject_url_completed, subject_learning
from core.state import read_non_empty_lines


StatusCallback = Callable[[str], None]


@dataclass
class AfkBatch:
    urls: list[str]
    is_retry: bool


def _read_unique_lines(file_path: Path) -> list[str]:
    return list(dict.fromkeys(read_non_empty_lines(file_path)))


def _append_unique_lines(file_path: Path, urls: list[str]) -> list[str]:
    existing = set(read_non_empty_lines(file_path))
    added: list[str] = []
    for url in urls:
        if not url or url in existing:
            continue
        save_to_file(file_path, url)
        existing.add(url)
        added.append(url)
    return added


def _is_user_abort_exception(exc: BaseException) -> bool:
    return isinstance(exc, (UserAbortRequested, KeyboardInterrupt, asyncio.CancelledError))


def _is_target_closed_exception(exc: BaseException) -> bool:
    message = str(exc).lower()
    return exc.__class__.__name__ == "TargetClosedError" or any(
        marker in message
        for marker in (
            "target page, context or browser has been closed",
            "browser has been closed",
        )
    )


def _get_context_browser(context):
    browser = getattr(context, "browser", None)
    if callable(browser):
        try:
            return browser()
        except Exception:
            return None
    return browser


def _is_browser_connected(context) -> bool:
    browser = _get_context_browser(context)
    if browser is None:
        return False

    is_connected = getattr(browser, "is_connected", None)
    if callable(is_connected):
        try:
            return bool(is_connected())
        except Exception:
            return False
    return False


def prepare_afk_batch(
    *,
    retry_file: Path = RETRY_URLS_FILE,
    learning_file: Path = LEARNING_URLS_FILE,
    exam_file: Path = EXAM_URLS_FILE,
    cleanup_files: list[Path] = CLEANUP_FILES,
) -> AfkBatch:
    retry_urls = _read_unique_lines(retry_file)
    if retry_file.exists():
        del_file(retry_file)

    for file_path in cleanup_files:
        del_file(file_path)

    if retry_urls:
        return AfkBatch(urls=retry_urls, is_retry=True)

    del_file(exam_file)
    return AfkBatch(urls=_read_unique_lines(learning_file), is_retry=False)


async def _process_url(context, url: str, handler) -> bool:
    page = await context.new_page()
    try:
        await page.goto(url)
        await handler(page)
        return False
    except Exception as exc:
        if _is_target_closed_exception(exc):
            if _is_browser_connected(context):
                logging.info(f"当前学习标签页已关闭，已记录稍后重试: {url}")
                save_to_file(RETRY_URLS_FILE, url)
                return True
            raise UserAbortRequested() from None
        logging.error(f"发生错误: {exc}")
        logging.error(traceback.format_exc())
        if str(exc) == "无权限查看该资源":
            save_to_file(NO_PERMISSION_FILE, url)
            return False
        save_to_file(RETRY_URLS_FILE, url)
        return True
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def _recheck_url_type_links(context) -> None:
    url_type_links = _read_unique_lines(URL_TYPE_FILE)
    if not url_type_links:
        del_file(URL_TYPE_FILE)
        return

    del_file(URL_TYPE_FILE)
    for url in url_type_links:
        page = await context.new_page()
        try:
            await page.goto(url)
            if await is_subject_url_completed(page):
                logging.info(f"URL类型链接学习完成: {url}")
            else:
                logging.info(f"URL类型链接学习未完成: {url}")
                save_to_file(URL_TYPE_FILE, url)
        except Exception as exc:
            logging.error(f"复查 URL 类型链接失败: {exc}")
            logging.error(traceback.format_exc())
            save_to_file(URL_TYPE_FILE, url)
        finally:
            try:
                await page.close()
            except Exception:
                pass


async def run_afk_once(status_callback: StatusCallback | None = None) -> bool:
    batch = prepare_afk_batch()
    if not batch.urls:
        if status_callback:
            status_callback("未检测到可处理的学习链接")
        return False

    needs_retry = False
    normalized_urls = [normalize_url(raw_url.strip()) for raw_url in batch.urls]
    pending_start_index = 0

    try:
        async with create_browser_context(slow_mo=AFK_SLOW_MO) as (_, context):
            for index, url in enumerate(normalized_urls, start=1):
                pending_start_index = index - 1
                if status_callback:
                    status_callback(f"挂课 {index}/{len(normalized_urls)}: {url}")
                logging.info(f"({index}/{len(normalized_urls)})当前学习链接为: {url}")

                if not is_compliant_url_regex(url):
                    logging.info("不合规链接, 已存入不合规链接.txt")
                    save_to_file(NON_COMPLIANT_FILE, url)
                    pending_start_index = index
                    continue

                if "subject" in url:
                    error = await _process_url(context, url, subject_learning)
                elif "course" in url:
                    error = await _process_url(context, url, course_learning)
                else:
                    logging.info(f"无法识别的学习链接类型: {url}")
                    save_to_file(NON_COMPLIANT_FILE, url)
                    pending_start_index = index
                    continue

                if error:
                    needs_retry = True
                pending_start_index = index

            await _recheck_url_type_links(context)
            pending_start_index = len(normalized_urls)
    except BaseException as exc:
        if _is_user_abort_exception(exc):
            _append_unique_lines(RETRY_URLS_FILE, normalized_urls[pending_start_index:])
            message = str(exc) or "已保存当前和剩余学习链接，程序退出"
            logging.debug(f"用户主动终止挂课流程: {message}")
            raise UserAbortRequested(message) from None
        raise

    logging.info("本轮自动挂课完成")
    return needs_retry


async def run_afk_until_complete(status_callback: StatusCallback | None = None) -> None:
    round_index = 1
    while True:
        if round_index > 1 and status_callback:
            status_callback(f"检测到未完成课程，开始第 {round_index} 轮重试")
        retry = await run_afk_once(status_callback=status_callback)
        if not retry:
            return
        round_index += 1
