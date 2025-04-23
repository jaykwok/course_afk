import asyncio
import json

from collections import defaultdict
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


# 通过获取网页内容，解析出所有链接并保存到文件中
async def main():
    url = "https://cms.mylearning.cn/safe/topic/resource/2025/zycp/pc.html"
    with open("./cookies.json", "r") as f:
        cookies = json.load(f)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="msedge")
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

                # 去掉链接中的fragment部分，它可能包含 '?' 和 '&' 符号
                fragment = parsed_url.fragment
                if fragment.startswith("/"):
                    fragment = fragment[1:]

                # 分割fragment以获取查询参数
                fragment_parts = fragment.split("?", 1)
                if len(fragment_parts) > 1:
                    # 拿到查询参数并解析成字典格式
                    query_params = parse_qs(fragment_parts[1])

                    business_id = query_params.get("businessId", [None])[0]
                    business_type = query_params.get("businessType", [None])[0]

                    if business_type == "1":
                        links[link.text.strip()].append(
                            "https://kc.zhixueyun.com/#/study/course/detail/"
                            + business_id
                        )
                    elif business_type == "2":
                        links[link.text.strip()].append(
                            "https://kc.zhixueyun.com/#/study/subject/detail/"
                            + business_id
                        )
                    else:
                        print(f"未知链接类型: {parsed_url}")
                else:
                    print(f"No query parameters in fragment: {fragment}")
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


# 运行主程序
if __name__ == "__main__":
    asyncio.run(main())
