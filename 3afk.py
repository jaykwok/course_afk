import asyncio
import logging
import time
import traceback

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
    setup_logging,
)
from core.file_ops import del_file, is_compliant_url_regex, normalize_url, save_to_file
from core.learning import (
    course_learning,
    is_subject_url_completed,
    subject_learning,
)

# 日志配置
setup_logging()


async def process_url(context, url, handler):
    """
    统一的URL处理流程, 包含错误处理。

    Returns:
        True 如果发生了需要重试的错误, False 如果正常完成
    """
    page = await context.new_page()
    try:
        await page.goto(url.strip())
        await handler(page)
        return False
    except Exception as e:
        logging.error(f"发生错误: {str(e)}")
        logging.error(traceback.format_exc())
        if str(e) == "无权限查看该资源":
            save_to_file(NO_PERMISSION_FILE, url.strip())
            return False
        else:
            save_to_file(RETRY_URLS_FILE, url.strip())
            return True
    finally:
        await page.close()


async def main() -> bool:
    """
    主学习流程。

    Returns:
        True 如果存在未完成的课程需要重试, False 如果全部完成
    """
    import os

    needs_retry = False

    if os.path.exists(RETRY_URLS_FILE):
        needs_retry = True
        with open(RETRY_URLS_FILE, encoding="utf-8") as f:
            urls = set(line for line in f if line.strip())
        os.remove(RETRY_URLS_FILE)
    else:
        # 首次运行, 清理旧文件
        if os.path.exists(EXAM_URLS_FILE):
            os.remove(EXAM_URLS_FILE)
        with open(LEARNING_URLS_FILE, encoding="utf-8") as f:
            urls = [line for line in f if line.strip()]

    for file in CLEANUP_FILES:
        del_file(file)

    # 重置重试标识(仅在首次运行时)
    if not needs_retry:
        needs_retry = False

    async with create_browser_context(slow_mo=AFK_SLOW_MO) as (browser, context):
        for count, url in enumerate(urls, start=1):
            url = normalize_url(url.strip())
            logging.info(f"({count}/{len(urls)})当前学习链接为: {url}")

            if not is_compliant_url_regex(url):
                logging.info("不合规链接, 已存入不合规链接.txt")
                save_to_file(NON_COMPLIANT_FILE, url)
                continue

            if "subject" in url:
                error = await process_url(
                    context, url, lambda page: subject_learning(page)
                )
            elif "course" in url:
                error = await process_url(
                    context, url, lambda page: course_learning(page)
                )
            else:
                continue

            if error:
                needs_retry = True

        # 处理URL类型链接
        if os.path.exists(URL_TYPE_FILE):
            with open(URL_TYPE_FILE, encoding="utf-8") as f:
                url_type_links = set(line for line in f if line.strip())
            os.remove(URL_TYPE_FILE)
            for url in url_type_links:
                page = await context.new_page()
                await page.goto(url.strip())
                try:
                    if await is_subject_url_completed(page):
                        logging.info(f"URL类型链接: {url.strip()} 学习完成")
                    else:
                        logging.info(f"URL类型链接: {url.strip()} 学习未完成")
                        save_to_file(URL_TYPE_FILE, url.strip())
                except Exception as e:
                    logging.error(f"发生错误: {str(e)}")
                    logging.error(traceback.format_exc())
                    save_to_file(URL_TYPE_FILE, url.strip())
                finally:
                    await page.close()

        # 如果未出现错误且残留文件存在, 则删除
        if os.path.exists(RETRY_URLS_FILE) and not needs_retry:
            os.remove(RETRY_URLS_FILE)

        logging.info(f"自动挂课完成, 当前时间为{time.ctime()}")

    return needs_retry


if __name__ == "__main__":
    while True:
        retry = asyncio.run(main())
        if not retry:
            break
