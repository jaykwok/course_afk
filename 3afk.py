import asyncio
import logging
import time
import traceback

from core.browser import create_browser_context
from core.file_ops import del_file, is_compliant_url_regex, save_to_file
from core.learning import (
    course_learning,
    is_subject_url_completed,
    subject_learning,
)
from core.logging_config import setup_logging

# 设置学习文件路径
learning_file = "./学习链接.txt"

# 日志配置
setup_logging()

# 需要在每次全新运行时清理的中间文件
CLEANUP_FILES = [
    "./学习主题考试链接.txt",
    "./调研类型链接.txt",
    "./URL类型链接.txt",
    "./h5课程类型链接.txt",
    "./非课程及考试类学习类型链接.txt",
    "./未知类型链接.txt",
]


async def process_url(context, url, handler):
    """
    统一的URL处理流程，包含错误处理。

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
            save_to_file("无权限资源链接.txt", url.strip())
            return False
        else:
            save_to_file("剩余未看课程链接.txt", url.strip())
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

    if os.path.exists("./剩余未看课程链接.txt"):
        needs_retry = True
        with open("./剩余未看课程链接.txt", encoding="utf-8") as f:
            urls = set(line for line in f if line.strip())
        os.remove("./剩余未看课程链接.txt")
    else:
        # 首次运行, 清理旧文件
        if os.path.exists("./学习课程考试链接.txt"):
            os.remove("./学习课程考试链接.txt")
        with open(learning_file, encoding="utf-8") as f:
            urls = [line for line in f if line.strip()]

    for file in CLEANUP_FILES:
        del_file(file)

    # 重置重试标识（仅在首次运行时）
    if not needs_retry:
        needs_retry = False

    async with create_browser_context(slow_mo=3000) as (browser, context):
        for count, url in enumerate(urls, start=1):
            logging.info(f"({count}/{len(urls)})当前学习链接为: {url.strip()}")

            if not is_compliant_url_regex(url.strip()):
                logging.info("不合规链接, 已存入不合规链接.txt")
                save_to_file("不合规链接.txt", url.strip())
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
        if os.path.exists("./URL类型链接.txt"):
            with open("./URL类型链接.txt", encoding="utf-8") as f:
                url_type_links = set(line for line in f if line.strip())
            os.remove("./URL类型链接.txt")
            for url in url_type_links:
                page = await context.new_page()
                await page.goto(url.strip())
                try:
                    if await is_subject_url_completed(page):
                        logging.info(f"URL类型链接: {url.strip()} 学习完成")
                    else:
                        logging.info(f"URL类型链接: {url.strip()} 学习未完成")
                        save_to_file("URL类型链接.txt", url.strip())
                except Exception as e:
                    logging.error(f"发生错误: {str(e)}")
                    logging.error(traceback.format_exc())
                    # 修复: 原代码使用已关闭的文件句柄 f.write(url)
                    save_to_file("URL类型链接.txt", url.strip())
                finally:
                    await page.close()

        # 如果未出现错误且残留文件存在, 则删除
        if os.path.exists("./剩余未看课程链接.txt") and not needs_retry:
            os.remove("./剩余未看课程链接.txt")

        logging.info(f"自动挂课完成, 当前时间为{time.ctime()}")

    return needs_retry


if __name__ == "__main__":
    while True:
        retry = asyncio.run(main())
        if not retry:
            break
