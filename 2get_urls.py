import asyncio
import json
from collections import defaultdict

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


async def main():
    url = 'https://cms.mylearning.cn/safe/topic/resource/2020/zhjtxtzq/pc.html'
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

    links = defaultdict(list)
    # 查找所有链接
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and 'kc.zhixueyun.com' in href:
            links[link.text.strip()].append(href.strip())

    # 打印结果
    count = 0
    with open(f'{file_name}.txt', 'w+', encoding='utf-8') as f:
        for link_type, link_list in links.items():
            print(f'{link_type}: ')
            for link in link_list:
                print(link)
                f.write(link + '\n')
                count += 1
    print(f'需要学习的链接总数为: {count}条')
    # link_types = ['产品介绍', '案例分享', '解决方案', '装维交付', '营销工具', '营销指引', '短视频', '更多', '']
    # exclude_types = set(links.keys()).difference(set(link_types))
    # if bool(exclude_types):
    #     for exclude_type in exclude_types:
    #         print(f'\n排除课程类型有: {exclude_type}')
    #         links.pop(exclude_type)
    # else:
    #     print('\n课程类型已全部覆盖')


if __name__ == '__main__':
    asyncio.run(main())
