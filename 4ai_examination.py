import asyncio
import json
import logging
import os
import re
import time
import utils

from dotenv import load_dotenv
from openai import OpenAI
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

# 加载.env文件
load_dotenv()

# 配置DashScope Baseurl
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL")
# 配置DashScope API
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
# 配置大模型
model = os.getenv("MODEL_NAME")

# 初始化OpenAI客户端 (使用DashScope兼容模式)
client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
)


async def main():
    with open("./学习课程考试链接.txt", encoding="utf-8") as f:
        urls = f.readlines()

    with open("cookies.json", "r") as f:
        cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, args=["--mute-audio", "--start-maximized"], channel="msedge"
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
            is_thinking = False

            if "course" in url.strip():
                logging.info("当前考试位于课程链接中")
                # 课程链接考试
                while True:
                    await page1.locator(".top").first.wait_for(timeout=5000)
                    await page1.locator(".top").first.click()
                    await page1.locator(
                        'dl.chapter-list-box[data-sectiontype="9"]'
                    ).click()
                    await page1.locator(".tab-container").wait_for()
                    await page1.wait_for_timeout(1000)

                    # 获取考试限定次数
                    exam_button_locator = page1.locator(".btn.new-radius")
                    # 如果存在考试按钮, 判定是否为限定次数的考试且剩余次数小于等于3
                    if await exam_button_locator.count() > 0:
                        button_text = await exam_button_locator.inner_text()
                        if "剩余" in button_text:
                            # 使用正则表达式提取剩余次数
                            remain_count = re.search(r"剩余(\d+)次", button_text)
                            if remain_count:
                                remaining_attempts = int(remain_count.group(1))
                                if remaining_attempts <= 3:
                                    logging.info(
                                        f"当前考试剩余次数为{remaining_attempts}, 小于等于3次, 转为人工考试"
                                    )
                                    utils.save_to_file(
                                        "./人工考试链接.txt", url.strip()
                                    )
                                    await page1.close()
                                    break
                                else:
                                    logging.info(
                                        f"当前考试剩余次数为{remaining_attempts}, 大于3次, 继续AI考试"
                                    )
                            else:
                                logging.info("无法解析剩余次数, 转为人工考试处理")
                                utils.save_to_file("./人工考试链接.txt", url.strip())
                                await page1.close()
                                break
                        else:
                            logging.info("不限制考试次数, 继续AI考试")

                    # AI考试
                    # 如果存在考试记录
                    if await page1.locator(".neer-status").count() > 0:
                        if await utils.check_exam_passed(page1):
                            await page1.close()
                            is_thinking = False
                            break
                        # AI考试未通过, 尝试试用推理模式
                        else:
                            if is_thinking:
                                logging.info("AI考试未通过, 使用人工模式重新考试")
                                utils.save_to_file("./人工考试链接.txt", url.strip())
                                is_thinking = False
                                await page1.close()
                                break
                            else:
                                is_thinking = True
                                logging.info("使用推理模式重新考试")
                                await utils.wait_for_finish_test(
                                    client, model, page1, is_thinking
                                )
                                await page1.reload(wait_until="load")
                                await page1.wait_for_timeout(1500)
                                # 如果存在评价窗口, 则点击评价按钮
                                if await utils.handle_rating_popup(page1):
                                    logging.info("五星评价完成")
                                continue
                    else:
                        logging.info("开始考试")
                        await utils.wait_for_finish_test(
                            client, model, page1, is_thinking
                        )
                        await page1.reload(wait_until="load")
                        await page1.wait_for_timeout(1500)
                        # 如果存在评价窗口, 则点击评价按钮
                        if await utils.handle_rating_popup(page1):
                            logging.info("五星评价完成")
                        continue
            elif "exam" in url.strip():
                logging.info("当前考试位于试卷链接中")
                # 试卷链接考试
                exam_button_locator = page1.locator(
                    ".banner-handler-btn.themeColor-border-color.themeColor-background-color"
                )
                button_text = await exam_button_locator.inner_text()
                if "剩余" in button_text:
                    # 使用正则表达式提取剩余次数
                    remain_count = re.search(r"剩余(\d+)次", button_text)
                    if remain_count:
                        remaining_attempts = int(remain_count.group(1))
                        if remaining_attempts <= 1:
                            logging.info(
                                f"当前考试剩余次数为{remaining_attempts}, 小于等于1次, 转为人工考试"
                            )
                            utils.save_to_file("./人工考试链接.txt", url.strip())
                            await page1.close()
                            break
                        else:
                            logging.info(
                                f"当前考试剩余次数为{remaining_attempts}, 大于1次, 继续AI考试"
                            )
                    else:
                        logging.info("无法解析剩余次数, 转为人工考试处理")
                        utils.save_to_file("./人工考试链接.txt", url.strip())
                        await page1.close()
                        break
                else:
                    logging.info("不限制考试次数, 继续AI考试")

                logging.info("等待作答完毕并关闭页面")
                async with page1.expect_popup() as page2_info:
                    await exam_button_locator.click()
                page2 = await page2_info.value
                logging.info("等待作答完毕并关闭页面")
                await utils.ai_exam(client, model, page2, is_thinking, page1.url, False)

        await context.close()
        await browser.close()
        logging.info(f"\n考试完成, 当前时间为{time.ctime()}\n")
        # os.remove("./学习课程考试链接.txt")


if __name__ == "__main__":
    asyncio.run(main())
