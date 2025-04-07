import asyncio
import json
from collections import defaultdict
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


async def main():
    url = "https://cms.mylearning.cn/safe/topic/resource/2025/zycp/pc.html"
    with open("./cookies.json", "r") as f:
        cookies = json.load(f)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=False)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto(url, wait_until="load")
        await page.wait_for_url(url, timeout=0)
        html_content = await page.content()
        file_name = await page.title()
        await browser.close()

    soup = BeautifulSoup(html_content, "html.parser")

    links = defaultdict(list)
    # 查找所有链接
    for link in soup.find_all("a"):
        href = link.get("href")
        if href and "kc.zhixueyun.com" in href:
            if "/app/" in href:
                parsed_url = urlparse(href.strip())
                # 解析查询参数
                query_params = parse_qs(parsed_url.fragment)

                # 获取 businessId
                business_id = query_params.get("businessId", [None])[0]
                links[link.text.strip()].append(
                    "https://kc.zhixueyun.com/#/study/subject/detail/" + business_id
                )
            else:
                links[link.text.strip()].append(href.strip())

    # 打印结果
    count = 0
    with open(f"{file_name}.txt", "w+", encoding="utf-8") as f:
        for link_type, link_list in links.items():
            print(f"{link_type}: ")
            for link in link_list:
                print(link)
                f.write(link + "\n")
                count += 1
    print(f"需要学习的链接总数为: {count}条")


if __name__ == "__main__":
    asyncio.run(main())
