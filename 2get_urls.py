import asyncio
import json

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


async def main():
    url = 'https://cms.mylearning.cn/safe/topic/resource/2024/zxzq/pc.html'
    with open('./cookies.json', 'r') as f:
        cookies = json.load(f)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=False)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto(url, wait_until='load')
        await page.wait_for_url(url, timeout=0)
        html_content = await page.content()
        file_name = await page.title()
        await browser.close()

    soup = BeautifulSoup(html_content, 'html.parser')

    # 定义要提取的链接类型
    # link_types = ['产品介绍', '案例分享', '解决方案', '装维交付', '营销工具', '营销指引', '短视频', '更多']
    link_types = ['产品介绍', '案例分享', '解决方案', '营销工具', '营销指引', '短视频', '更多']

    # 初始化字典存储链接
    links = {link_type: [] for link_type in link_types}

    # 查找所有链接
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and 'kc.zhixueyun.com' in href:
            for link_type in link_types:
                if link.text.strip() == link_type:
                    links[link_type].append(href.strip())

    # 打印结果
    with open(f'{file_name}.txt', 'w+', encoding='utf-8') as f:
        for link_type, link_list in links.items():
            print(f'{link_type}: ')
            for link in link_list:
                print(link)
                f.write(link + '\n')


if __name__ == '__main__':
    asyncio.run(main())
