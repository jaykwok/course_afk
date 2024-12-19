from playwright.sync_api import sync_playwright
import json
from datetime import datetime
import time
import re


def load_cookies(context, cookie_path):
    """加载cookies文件"""
    try:
        with open(cookie_path, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print("成功加载cookies")
    except Exception as e:
        print(f"加载cookies时发生错误: {str(e)}")
        return False
    return True


def wait_for_zhixueyun_redirect(page, timeout=30000):
    """等待知学云页面重定向完成"""
    url = page.url
    uuid = url.split("/")[-1]
    try:
        # 等待URL包含特定前缀
        page.wait_for_url(
            re.compile(
                rf"^https://kc\.zhixueyun\.com/#/paas-container\?paasurl=website.*{uuid}"
            ),
            timeout=0,
        )
        return True
    except Exception as e:
        print(f"等待重定向超时: {str(e)}")
        return False


def collect_urls(start_url, cookie_path):
    with sync_playwright() as p:
        # 启动浏览器，设置窗口大小
        browser = p.chromium.launch(
            channel="chrome", headless=False, args=["--start-maximized"]  # 最大化窗口
        )
        context = browser.new_context()

        # 创建存储URL的文件
        output_file = f"点击按钮弹出网页链接获取.txt"
        # 存储已收集的URL
        collected_urls = set()

        try:
            # 创建新页面并加载cookies
            page = context.new_page()
            if not load_cookies(context, cookie_path):
                raise Exception("加载cookies失败")

            # 访问起始页面
            page.goto("https://kc.zhixueyun.com/")
            page.wait_for_url(
                re.compile(r"https://kc\.zhixueyun\.com/#/home-v\?id=\d+"),
                timeout=0,
            )
            page.close()

            # 打开新页面访问目标URL
            page = context.new_page()
            print(f"正在访问页面: {start_url}")
            page.goto(start_url)

            # 等待重定向完成
            if not wait_for_zhixueyun_redirect(page):
                raise Exception("页面重定向失败")

            # 等待页面完全加载
            print("等待页面完全加载...")
            page.wait_for_load_state("networkidle")

            # 等待iframe加载
            iframe_locator = page.frame_locator("#paasIframe")

            while True:
                print('输入"1"以继续获取链接')
                flag = input()
                if flag == "1":
                    break

            # 查找所有"继续学习"和"开始学习"按钮
            print("开始查找学习按钮...")
            study_buttons = iframe_locator.locator(
                'button:has-text("继续学习"), button:has-text("开始学习")'
            ).all()

            if not study_buttons:
                print("当前页面没有找到学习按钮")

            print(f"找到 {len(study_buttons)} 个按钮")

            for i, button in enumerate(study_buttons, 1):
                try:
                    # 确保按钮可见和可点击
                    button.scroll_into_view_if_needed()
                    button.wait_for(state="visible", timeout=5000)

                    print(f"正在点击第 {i} 个按钮")

                    # 等待新页面打开
                    with context.expect_page() as new_page_info:
                        button.click()

                    # 获取新页面
                    new_page = new_page_info.value
                    new_page.wait_for_load_state("load")

                    # 获取URL
                    url = new_page.url
                    if url not in collected_urls:
                        collected_urls.add(url)
                        with open(output_file, "a", encoding="utf-8") as f:
                            f.write(f"{url}\n")
                        print(f"已保存新URL: {url}")

                    # 关闭新页面
                    new_page.close()

                    # 短暂等待，避免操作过快
                    time.sleep(1)

                except Exception as e:
                    print(f"处理按钮 {i} 时发生错误: {str(e)}")
                    continue

        except Exception as e:
            print(f"发生错误: {str(e)}")

        finally:
            # 关闭浏览器
            context.close()
            browser.close()
            print(f"\n所有URL已保存到文件: {output_file}")
            print(f"共收集到 {len(collected_urls)} 个唯一URL")


if __name__ == "__main__":
    # 设置起始页面URL和cookie文件路径
    start_url = "https://kc.zhixueyun.com/#/train-new/class-detail/db0f911c-7214-499b-a006-02ad9b803e8f"  # 替换为实际的起始URL
    cookie_path = "cookies.json"  # 替换为实际的cookie文件路径
    collect_urls(start_url, cookie_path)
