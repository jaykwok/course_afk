import asyncio
import logging
import os
import time

from core.browser import create_browser_context
from core.config import MANUAL_EXAM_FILE, setup_logging
from core.learning import check_exam_passed, handle_rating_popup

# 日志配置
setup_logging()


async def wait_for_manual_test(page1):
    """等待用户手动完成考试"""
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    await page2.wait_for_event("close", timeout=0)


async def main():
    with open(MANUAL_EXAM_FILE, encoding="utf-8") as f:
        urls = set(line for line in f if line.strip())

    async with create_browser_context() as (browser, context):
        for url in urls:
            page1 = await context.new_page()
            logging.info(f"当前考试链接为: {url.strip()}")
            await page1.goto(url.strip())
            await page1.wait_for_load_state("load")

            while True:
                await page1.wait_for_timeout(1000)
                await page1.locator(".top").first.click()
                await page1.locator(
                    'dl.chapter-list-box[data-sectiontype="9"]'
                ).click()
                await page1.locator(".tab-container").wait_for()
                if await page1.locator(".neer-status").all():
                    if await check_exam_passed(page1):
                        await page1.close()
                        break
                    else:
                        logging.info("重新考试")
                        await wait_for_manual_test(page1)
                        await page1.reload(wait_until="load")
                        await page1.wait_for_timeout(1500)
                        if await handle_rating_popup(page1):
                            logging.info("五星评价完成")
                        continue
                else:
                    logging.info("开始考试")
                    await wait_for_manual_test(page1)
                    await page1.reload(wait_until="load")
                    await page1.wait_for_timeout(1500)
                    if await handle_rating_popup(page1):
                        logging.info("五星评价完成")
                    continue

        logging.info(f"考试完成, 当前时间为{time.ctime()}\n")
        os.remove(MANUAL_EXAM_FILE)


if __name__ == "__main__":
    asyncio.run(main())
