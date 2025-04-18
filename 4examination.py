import asyncio
import json
import logging
import os
import re
import time

from playwright.async_api import async_playwright

# 日志基本设置
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s",
    handlers=[
        logging.FileHandler("log.txt", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


# 获取考试是否通过
# async def check_exam_passed(page):
#     # 获取最高分
#     highest_score_text = await page.locator(".neer-status").inner_text()
#     # 判断是否在考试中状态：如果是，那就重新考试
#     if "考试中" in highest_score_text:
#         return False
#     # 获取最高分数值
#     highest_score = int(highest_score_text.split("：")[1].replace("分", ""))
#     # 判断最高成绩是否大于等于80分
#     if highest_score >= 80:
#         logging.info(f"考试状态: 通过")
#         return True
#     else:
#         logging.info(f"考试状态: 未通过")
#         return False


async def check_exam_passed(page):
    # 判断是否在考试中状态
    highest_score_text = await page.locator(".neer-status").inner_text()
    if "考试中" in highest_score_text:
        logging.info("考试状态: 考试中")
        return False

    # 获取表格中最新一条记录的状态（第一行）
    try:
        # 定位到表格主体中的第一行的状态单元格
        status_cell = await page.locator(
            "div.tab-container table.table tbody tr:first-child td:nth-child(4)"
        ).inner_text()
        status_cell = status_cell.strip()

        if status_cell == "及格":
            logging.info("考试状态: 通过")
            return True
        else:
            logging.info(f"考试状态: 未通过 ({status_cell})")
            return False
    except Exception as e:
        logging.error(f"获取考试状态时出错: {e}")
        return False


# 等待完成考试
async def wait_for_finish_test(page1):
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    await page2.wait_for_event("close", timeout=0)


async def handle_rating_popup(page):
    """监测评分弹窗，选择五星并提交"""
    try:
        # 等待弹窗出现，使用更长的超时时间
        dialog_selector = "div[role='dialog']"
        try:
            await page.wait_for_selector(dialog_selector, timeout=5000, state="visible")
            logging.info("检测到评分弹窗")
        except Exception as e:
            logging.debug(f"未检测到评分弹窗: {e}")
            return False

        # 给弹窗内容足够的加载时间
        await page.wait_for_timeout(1500)

        # 确保星星容器已加载
        stars_container = "ul.ant-rate"
        await page.wait_for_selector(stars_container, timeout=3000, state="visible")

        try:
            fifth_star = "ul.ant-rate li:nth-child(5) div[role='radio']"
            await page.wait_for_selector(fifth_star, state="visible", timeout=2000)

            # 确保星星在视图中
            await page.evaluate(
                "document.querySelector('ul.ant-rate').scrollIntoView({block: 'center'})"
            )

            # 使用force参数确保点击
            await page.click(fifth_star, force=True)
            logging.info("已点击第五颗星星")

        except Exception as e:
            logging.warning(f"方法1点击星星失败: {e}")
        # 等待足够时间让按钮变为可用状态
        await page.wait_for_timeout(1500)

        # 检查按钮状态并点击
        try:
            # 点击确定按钮
            await page.get_by_role("button", name="确 定").click()
            logging.info("已点击确定按钮")
            return True

        except Exception as e:
            logging.error(f"点击确定按钮时出错: {e}")
            return False

    except Exception as e:
        logging.error(f"处理评分弹窗时出错: {e}")
        return False


async def main():
    with open("./学习课程考试链接.txt", encoding="utf-8") as f:
        urls = list(f.readlines())

    # Load the cookies
    with open("cookies.json", "r") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, args=["--mute-audio", "--start-maximized"], channel="chrome"
        )
        context = await browser.new_context(no_viewport=True)
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto("https://kc.zhixueyun.com/")
        await page.wait_for_url(
            re.compile(r"https://kc\.zhixueyun\.com/#/home-v\?id=\d+"), timeout=0
        )
        await page.close()
        for url in urls:
            page1 = await context.new_page()
            logging.info(f"当前考试链接为: {url.strip()}")
            await page1.goto(url.strip())
            await page1.wait_for_load_state("load")

            while True:
                await page1.wait_for_timeout(1000)
                await page1.locator(".top").first.click()
                await page1.locator('dl.chapter-list-box[data-sectiontype="9"]').click()
                # 判断是否为第一次考试
                await page1.locator(".tab-container").wait_for()
                if await page1.locator(".neer-status").all():
                    if await check_exam_passed(page1):
                        await page1.close()
                        break
                    else:
                        logging.info("重新考试")
                        await wait_for_finish_test(page1)
                        await page1.reload(wait_until="load")
                        await page1.wait_for_timeout(1500)
                        # 如果存在评价窗口，则点击评价按钮
                        if await handle_rating_popup(page1):
                            logging.info("五星评价完成")
                        continue
                else:
                    logging.info("开始考试")
                    await wait_for_finish_test(page1)
                    await page1.reload(wait_until="load")
                    await page1.wait_for_timeout(1500)
                    # 如果存在评价窗口，则点击评价按钮
                    if await handle_rating_popup(page1):
                        logging.info("五星评价完成")
                    continue

        await context.close()
        await browser.close()
        logging.info(f"\n考试完成，当前时间为{time.ctime()}\n")
        os.remove("./学习课程考试链接.txt")


if __name__ == "__main__":
    asyncio.run(main())
