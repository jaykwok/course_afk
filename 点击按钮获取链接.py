import asyncio
import json
import logging
import os
import re

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from core.logging_config import setup_logging

# 加载.env文件
load_dotenv()

# 日志配置
setup_logging()


def load_cookies_data(cookie_path):
    with open(cookie_path, "r") as f:
        return json.load(f)


def load_existing_urls(output_file):
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            urls = {line.strip() for line in f if line.strip()}
        if urls:
            logging.info(f"已从文件加载 {len(urls)} 个历史URL, 将自动跳过重复项")
        return urls
    except FileNotFoundError:
        return set()


def clean_url(url: str) -> str:
    """去除 URL 中 UUID 前的多余前缀, 如 99@@ 。

    例：/detail/99@@5df62a1e-... → /detail/5df62a1e-...
    """
    return re.sub(r"/(\w+@@)+", "/", url)


async def wait_for_browser_close(main_page, interval=1.0):
    while True:
        await asyncio.sleep(interval)
        try:
            await main_page.evaluate("1")
        except Exception:
            return


async def collect_urls(start_url, cookie_path):
    output_file = "学习链接_点击按钮.txt"
    collected_urls = load_existing_urls(output_file)

    async def handle_new_page(new_page):
        try:
            await new_page.wait_for_url(
                re.compile(r"^(?!about:blank).*"),
                timeout=15000,
            )
            await new_page.wait_for_load_state("load", timeout=15000)
            url = clean_url(new_page.url)

            if url and url != "about:blank":
                if url not in collected_urls:
                    collected_urls.add(url)
                    with open(output_file, "a+", encoding="utf-8") as f:
                        f.write(f"{url}\n")
                    logging.info(f"[+] 已保存 (共{len(collected_urls)}条): {url}")
                else:
                    logging.info(f"[=] 已存在, 跳过: {url}")

            await asyncio.sleep(1)
            await new_page.close()
            logging.info("新页面已关闭, 等待下一次点击...")

        except Exception as e:
            logging.error(f"处理新页面时发生错误: {str(e)}")
            try:
                await new_page.close()
            except Exception:
                pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="msedge",
            args=["--start-maximized"],
        )
        context = await browser.new_context(no_viewport=True)

        try:
            main_page = await context.new_page()

            cookies = load_cookies_data(cookie_path)
            await context.add_cookies(cookies)
            logging.info("成功加载cookies")

            await main_page.goto("https://kc.zhixueyun.com/")
            await main_page.wait_for_url(
                re.compile(r"https://kc\.zhixueyun\.com/#/home-v\?id=\d+"),
                timeout=0,
            )

            logging.info(f"正在访问起始页面: {start_url}")
            await main_page.goto(start_url)
            await main_page.wait_for_load_state("load")

            context.on(
                "page", lambda page: asyncio.ensure_future(handle_new_page(page))
            )
            logging.info("页面已就绪, 开始监听。请手动点击元素打开新页面。")
            logging.info("退出方式：关闭浏览器窗口 或 按 Ctrl+C")

            await wait_for_browser_close(main_page)
            logging.info("浏览器已关闭, 正在退出...")

        except (KeyboardInterrupt, asyncio.CancelledError):
            logging.info("收到退出信号, 正在退出...")
        except Exception as e:
            logging.error(f"发生错误: {str(e)}")
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
            logging.info(f"所有URL已��存到文件: {output_file}")
            logging.info(f"共收集到 {len(collected_urls)} 个唯一URL")


if __name__ == "__main__":
    start_url = os.getenv("START_URL")
    if not start_url:
        logging.error("请在.env文件中配置START_URL")
        exit(1)
    cookie_path = "cookies.json"
    try:
        asyncio.run(collect_urls(start_url, cookie_path))
    except KeyboardInterrupt:
        pass  # 已在协程内处理, 这里只负责抑制 Traceback
