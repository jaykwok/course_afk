import asyncio
import logging
import os
import re
import time

from dotenv import load_dotenv
from openai import OpenAI

from core.browser import create_browser_context
from core.exam_engine import ai_exam, wait_for_finish_test
from core.file_ops import save_to_file
from core.learning import check_exam_passed, handle_rating_popup
from core.logging_config import setup_logging

# 日志配置
setup_logging()

# 加载.env文件
load_dotenv()

# 配置DashScope
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
model = os.getenv("MODEL_NAME")

# 初始化OpenAI客户端
client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
)


async def check_remaining_attempts(button_locator, threshold: int, url: str) -> bool:
    """
    检查考试剩余次数是否满足AI考试条件。

    Returns:
        True 如果可以继续AI考试, False 如果应转为人工考试
    """
    button_text = await button_locator.inner_text()
    if "剩余" not in button_text:
        logging.info("不限制考试次数, 继续AI考试")
        return True

    match = re.search(r"剩余(\d+)次", button_text)
    if not match:
        logging.info("无法解析剩余次数, 转为人工考试处理")
        save_to_file("./人工考试链接.txt", url.strip())
        return False

    remaining = int(match.group(1))
    if remaining <= threshold:
        logging.info(f"当前考试剩余次数为{remaining}, 小于等于{threshold}次, 转为人工考试")
        save_to_file("./人工考试链接.txt", url.strip())
        return False

    logging.info(f"当前考试剩余次数为{remaining}, 大于{threshold}次, 继续AI考试")
    return True


async def handle_exam_result(page1, url, is_thinking):
    """处理考试后的结果检查和重试逻辑"""
    await page1.reload(wait_until="load")
    await page1.wait_for_timeout(1500)
    if await handle_rating_popup(page1):
        logging.info("五星评价完成")


async def main():
    with open("./学习课程考试链接.txt", encoding="utf-8") as f:
        urls = f.readlines()

    async with create_browser_context() as (browser, context):
        for url in urls:
            page1 = await context.new_page()
            logging.info(f"当前考试链接为: {url.strip()}")
            await page1.goto(url.strip())
            await page1.wait_for_load_state("load")
            is_thinking = False

            if "course" in url.strip():
                logging.info("当前考试位于课程链接中")
                while True:
                    await page1.locator(".top").first.wait_for(timeout=5000)
                    await page1.locator(".top").first.click()
                    await page1.locator(
                        'dl.chapter-list-box[data-sectiontype="9"]'
                    ).click()
                    await page1.locator(".tab-container").wait_for()
                    await page1.wait_for_timeout(1000)

                    # 检查剩余次数
                    exam_button_locator = page1.locator(".btn.new-radius")
                    if await exam_button_locator.count() > 0:
                        can_continue = await check_remaining_attempts(
                            exam_button_locator, threshold=3, url=url
                        )
                        if not can_continue:
                            await page1.close()
                            break

                    # AI考试流程
                    if await page1.locator(".neer-status").count() > 0:
                        if await check_exam_passed(page1):
                            await page1.close()
                            is_thinking = False
                            break
                        else:
                            if is_thinking:
                                logging.info("AI考试未通过, 使用人工模式重新考试")
                                save_to_file("./人工考试链接.txt", url.strip())
                                is_thinking = False
                                await page1.close()
                                break
                            else:
                                is_thinking = True
                                logging.info("使用推理模式重新考试")
                                await wait_for_finish_test(
                                    client, model, page1, is_thinking
                                )
                                await handle_exam_result(page1, url, is_thinking)
                                continue
                    else:
                        logging.info("开始考试")
                        await wait_for_finish_test(
                            client, model, page1, is_thinking
                        )
                        await handle_exam_result(page1, url, is_thinking)
                        continue

            elif "exam" in url.strip():
                logging.info("当前考试位于试卷链接中")
                exam_button_locator = page1.locator(
                    ".banner-handler-btn.themeColor-border-color.themeColor-background-color"
                )

                # 检查剩余次数
                can_continue = await check_remaining_attempts(
                    exam_button_locator, threshold=1, url=url
                )
                if not can_continue:
                    await page1.close()
                    # 修复: 原代码为 break, 会跳出整个 for 循环
                    continue

                logging.info("等待作答完毕并关闭页面")
                async with page1.expect_popup() as page2_info:
                    await exam_button_locator.click()
                page2 = await page2_info.value
                logging.info("等待作答完毕并关闭页面")
                await ai_exam(client, model, page2, is_thinking, page1.url, False)

        logging.info(f"\n考试完成, 当前时间为{time.ctime()}\n")


if __name__ == "__main__":
    asyncio.run(main())
