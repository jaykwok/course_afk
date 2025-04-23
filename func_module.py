import asyncio
import logging
import math
import os
import re
import time
import traceback

# 日志基本设置
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s",
    handlers=[
        logging.FileHandler("log.txt", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


def del_file(filename):
    if os.path.exists(filename):
        os.remove(filename)


def save_to_file(filename, url):
    """将链接保存到指定文件"""

    with open(filename, "a+", encoding="utf-8") as wp:
        logging.info(f"写入{filename}完毕\n")
        wp.write(f"{url}\n")


async def check_permisson(frame):
    try:
        # 在当前frame中查找文本
        text_content = await frame.content()
        if "您没有权限查看该资源" in text_content or "该资源已不存在" in text_content:
            return False
        else:
            return True
    except Exception as e:
        print(f"检查frame时出错: {e}")
        return False


def is_learned(text: str) -> bool:
    """判断课程是否已学习"""

    return re.search(r"需学|需再学", text) is None


def time_to_seconds(duration: str) -> int:
    """时长转换为秒数"""

    pattern = r"(\d+)?:\d{1,2}"
    match = re.search(pattern, duration)
    if not match:
        return 0

    units = match.group().split(":")
    total_seconds = sum(
        int(unit) * 60**index for index, unit in enumerate(reversed(units))
    )
    return math.ceil(total_seconds / 10) * 10


def calculate_remaining_time(text) -> tuple[int, int]:
    """计算当前课程剩余挂课时间"""

    pattern = r"(\d+:\d{1,2})"
    match = re.findall(pattern, text)
    if len(match) == 1:
        total_time = remaining_time = time_to_seconds(match[0])
    elif len(match) == 2:
        total_time = time_to_seconds(match[0])
        remaining_time = time_to_seconds(match[1])

    return min(math.ceil(remaining_time / 60) * 60, total_time), total_time


async def timer(duration: int, interval: int = 30):
    """定时器"""

    duration = math.ceil(duration)
    logging.info(f"开始时间: {time.ctime()}")
    for elapsed in range(0, duration, interval):
        await asyncio.sleep(interval)
        logging.info(f"已学习 {elapsed + interval} / {duration} (秒)")
    logging.info(f"结束时间: {time.ctime()}")


async def check_for_pass_grade(page):
    # 首先定位到包含表格的div
    table_container = page.locator("div.tab-container table")

    # 在表格中查找包含"及格"文本的单元格
    pass_cell = await table_container.locator('td:has-text("及格")').all()

    # 检查是否找到了"及格"
    if pass_cell:
        return True
    else:
        return False


async def handle_rating_popup(page):
    """监测评分弹窗，选择五星并提交"""
    try:
        # 等待弹窗出现，使用更长的超时时间
        dialog = page.locator(".ant-modal-content")
        try:
            await dialog.wait_for(state="visible", timeout=3000)
            logging.info("检测到评分弹窗")
        except Exception as e:
            logging.debug(f"未检测到评分弹窗: {e}")
            return False

        # 确保星星容器已加载
        stars_container = dialog.locator("ul.ant-rate")
        await stars_container.wait_for(state="visible", timeout=3000)

        try:
            fifth_star = dialog.locator("ul.ant-rate li:nth-child(5) div[role='radio']")
            await fifth_star.wait_for(state="visible", timeout=3000)

            # 确保星星在视图中
            await page.evaluate(
                "document.querySelector('ul.ant-rate').scrollIntoView({block: 'center'})"
            )

            # 使用 Locator 的 click 方法而不是 page.click
            await fifth_star.click(force=True)
            logging.info("已点击第五颗星星")

        except Exception as e:
            logging.warning(f"点击星星失败: {e}")

        # 等待足够时间让按钮变为可用状态
        await page.wait_for_timeout(500)

        # 检查按钮状态并点击
        try:
            # 点击确定按钮
            confirm_button = page.get_by_role("button", name="确 定")
            await confirm_button.click()
            logging.info("已点击确定按钮")
            return True

        except Exception as e:
            logging.error(f"点击确定按钮时出错: {e}")
            return False

    except Exception as e:
        logging.error(f"处理评分弹窗时出错: {e}")
        return False


async def is_course_completed(page):
    # 定位到包含进度信息的元素
    progress_element = page.locator("div.course-progress div.progress")

    # 获取元素的文本内容
    progress_text = await progress_element.inner_text()
    if "100%" in progress_text:
        return True
    else:
        return False


async def get_course_url(learn_item, section_type="course"):
    course_id = await learn_item.get_attribute("data-resource-id")
    if section_type == "exam":
        prefix = "https://kc.zhixueyun.com/#/exam/exam/answer-paper/"
    else:
        prefix = "https://kc.zhixueyun.com/#/study/course/detail/"

    return str(prefix + course_id)


async def subject_learning(page, mark):
    """主题内容学习"""

    await page.wait_for_load_state("load")
    # await page.wait_for_timeout(3000)

    # 检查是否有权限访问该资源
    if await check_permisson(page.main_frame):
        pass
    else:
        raise Exception(f"无权限查看该资源")

    await page.locator(".item.current-hover").last.wait_for()
    await page.locator(".item.current-hover").locator(".section-type").last.wait_for()

    # learn_list = await page.locator('.item.current-hover', has_not_text='重新学习').all()
    learn_list = await page.locator(
        ".item.current-hover", has_not=page.locator(".iconfont.m-right.icon-reload")
    ).all()

    if learn_list:
        for learn_item in learn_list:
            section_type = await learn_item.locator(".section-type").inner_text()

            if section_type == "课程":
                async with page.expect_popup() as page_pop:
                    await learn_item.locator(".inline-block.operation").click()
                page_detail = await page_pop.value
                try:
                    await course_learning(page_detail, learn_item)
                except Exception as e:
                    logging.error(f"发生错误: {str(e)}")
                    logging.error(traceback.format_exc())
                    mark = 1
                    save_to_file(
                        "剩余未看课程链接.txt", await get_course_url(learn_item)
                    )
                finally:
                    await page_detail.close()

            elif section_type == "URL":
                logging.info("URL学习类型，存入文档单独审查")
                save_to_file("URL类型链接.txt", await get_course_url(learn_item))
                async with page.expect_popup() as page_pop:
                    await learn_item.locator(".inline-block.operation").click()
                page_detail = await page_pop.value
                timer_task = asyncio.create_task(timer(10, 1))
                await page_detail.wait_for_timeout(10 * 1000)
                await timer_task
                await page_detail.close()

            elif section_type == "考试":
                # 获取所有匹配元素的文本内容
                status_texts = await page.locator(
                    "div.text-overflow.inline-block.m-left span.finished-status"
                ).all_inner_texts()
                # 查找并返回"已完成"状态
                completion_status = next(
                    (status for status in status_texts if "已完成" in status), None
                )
                if completion_status == "已完成":
                    continue
                else:
                    logging.info("学习主题考试类型，存入文档")
                    save_to_file(
                        "学习主题考试链接.txt",
                        await get_course_url(learn_item, section_type="exam"),
                    )

            elif section_type == "调研":
                logging.info("调研学习类型，存入文档单独审查")
                save_to_file("调研类型链接.txt", await get_course_url(learn_item))

            else:
                logging.info("非课程及考试类学习类型，存入文档单独审查")
                save_to_file(
                    "非课程及考试类学习类型链接.txt", await get_course_url(learn_item)
                )
    return mark


async def course_learning(page_detail, learn_item=None):
    """课程内容学习"""

    await page_detail.wait_for_load_state("load")

    # 检查是否有权限访问该资源
    if await check_permisson(page_detail.main_frame):
        # 如果存在课程五星评价窗口，则点击评价按钮
        if await handle_rating_popup(page_detail):
            logging.info("五星评价完成")
    else:
        raise Exception(f"无权限查看该资源")

    if await is_course_completed(page_detail):
        title = await page_detail.locator("span.course-title-text").inner_text()
        logging.info(f"<{title}>已学习完毕，跳过该课程\n")
        return

    await page_detail.locator("dl.chapter-list-box.required").last.wait_for()
    chapter_boxes = await page_detail.locator("dl.chapter-list-box.required").all()

    # 预先检查所有章节是否已学习
    all_learned = True
    has_non_detectable_types = False

    for box in chapter_boxes:
        section_type = await box.get_attribute("data-sectiontype")
        # 只检查可以预先判断的类型（视频和文档）
        if section_type in ["1", "2", "5", "6"]:
            progress_text = await box.locator(".section-item-wrapper").inner_text()
            if not is_learned(progress_text):
                all_learned = False
                break
        else:
            # 其他类型无法预先检测，标记需要处理
            has_non_detectable_types = True

    # 如果所有可检测章节已学习，且没有不可检测类型，则可跳过整个课程
    if all_learned and not has_non_detectable_types:
        logging.info("所有章节已学习完毕，跳过该课程")
        return

    # 处理各个章节
    for count, box in enumerate(chapter_boxes, start=1):
        section_type = await box.get_attribute("data-sectiontype")
        box_text = await box.locator(".text-overflow").inner_text()
        logging.info(f"课程信息: \n{box_text}\n")

        # 预先检查是否已学习(针对可检测的类型)
        if section_type in ["1", "2", "5", "6"]:
            progress_text = await box.locator(".section-item-wrapper").inner_text()
            if is_learned(progress_text):
                logging.info(f"课程{count}已学习，跳过该节\n")
                continue

        # 点击章节
        await box.locator(".section-item-wrapper").wait_for()
        await box.locator(".section-item-wrapper").click()

        # 根据章节类型处理
        if section_type in ["5", "6"]:
            # 处理视频类型课程
            logging.info("该课程为视频类型")
            await handle_video(box, page_detail)
        elif section_type in ["1", "2"]:
            # 处理文档类型课程
            logging.info("该课程为文档类型")
            await handle_document(page_detail)
        elif section_type == "4":
            # 处理h5类型课程
            logging.info("该课程为h5类型")
            await handle_h5(page_detail, learn_item)
        elif section_type == "9":
            # 处理考试类型课程
            logging.info("该课程为考试类型")
            if await check_for_pass_grade(page_detail):
                logging.info("考试已通过，跳过该节")
                continue
            else:
                if learn_item:
                    await handle_examination(page_detail, learn_item)
                else:
                    await handle_examination(page_detail)
        else:
            logging.info("未知课程学习类型，存入文档单独审查")
            if learn_item:
                save_to_file("未知类型链接.txt", await get_course_url(learn_item))
            else:
                save_to_file("未知类型链接.txt", page_detail.url)
            continue
        logging.info(f"课程{count}学习完毕")


async def check_and_handle_rating_popup(page):
    """检查并处理视频内课程质量评价弹窗"""
    try:
        # 使用快速超时检查弹窗是否存在，避免长时间等待
        popup_exists = (
            await page.locator(
                "div.split-section-detail-header--interact:has-text('互动练习')"
            ).count()
            > 0
        )

        if popup_exists:
            logging.info("检测到课程质量评价弹窗")
            # 点击"跳过"按钮
            skip_button = page.locator("button:has-text('跳 过')")
            if await skip_button.count() > 0:
                await skip_button.click()
                logging.info("已点击'跳过'按钮")
                # 短暂等待让界面响应
                await page.wait_for_timeout(1000)
                return True
    except Exception as e:
        logging.warning(f"处理评价弹窗时出错: {str(e)}")

    return False


async def check_rating_popup_periodically(page, duration, interval=30):
    """定期检查视频内评价弹窗，持续指定时间"""

    elapsed = 0
    while elapsed < duration:
        # 等待指定时间
        wait_time = min(interval, duration - elapsed)
        await asyncio.sleep(wait_time)

        # 检查并处理评价弹窗
        await check_and_handle_rating_popup(page)

        # 更新已经过的时间
        elapsed += wait_time


async def handle_video(box, page):
    """处理视频类型课程"""

    # 点击可能出现的继续播放按钮
    resume_button = await page.locator(".register-mask-layer").all()
    if resume_button:
        await resume_button[0].click()
    await page.locator(".vjs-progress-control").first.wait_for()
    await page.locator(".vjs-duration-display").wait_for()

    # 初次检查评价弹窗
    await check_and_handle_rating_popup(page)

    remaining, duration = calculate_remaining_time(
        await box.locator(".section-item-wrapper").inner_text()
    )
    logging.info(f"课程总时长: {duration} 秒")
    logging.info(f"还需学习: {remaining} 秒")

    # 等待计算的剩余时间，同时定期检查评价弹窗
    timer_task = asyncio.create_task(timer(remaining))
    popup_check_task = asyncio.create_task(
        check_rating_popup_periodically(page, remaining)
    )
    await page.wait_for_timeout(remaining * 1000)
    await timer_task
    await popup_check_task

    # 确认课程进度是否已同步到服务器
    logging.info("课程学习完毕，确认课程进度同步状态...")
    current_text = await box.locator(".section-item-wrapper").inner_text()
    if is_learned(current_text):
        logging.info(f"课程进度已同步到服务器")
        return

    # 额外等待最多5分钟，以便同步课程进度
    extra_wait_time = 5 * 60  # 额外等待5分钟同步状态
    check_interval = 10  # 每10秒检查一次

    for i in range(0, extra_wait_time, check_interval):
        # 每次检查前先检查评价弹窗
        await check_and_handle_rating_popup(page)

        # 检查是否还有"需再学"字样
        current_text = await box.locator(".section-item-wrapper").inner_text()
        if is_learned(current_text):
            logging.info(f"课程进度已同步到服务器，额外等待 {i} 秒")

            # 如果存在课程五星评价窗口，则点击评价按钮
            if await handle_rating_popup(page):
                logging.info("五星评价完成")

            return

        logging.info(
            f"课程进度仍未同步完成，已额外等待 {i + check_interval} 秒，继续等待..."
        )
        await page.wait_for_timeout(check_interval * 1000)

    # 如果5分钟后仍未完成，抛出异常
    current_text = await box.locator(".section-item-wrapper").inner_text()
    if not is_learned(current_text):
        logging.info(f"超时: 已额外等待5分钟，课程进度仍未同步")
        raise Exception("课程进度未能在额外等待时间内同步完成")


async def handle_document(page):
    """处理文档类型课程"""

    # await page.wait_for_timeout(3 * 1000)
    # await page.locator('.clearfix').first.wait_for()
    await page.locator(".image-text-water").first.wait_for()
    timer_task = asyncio.create_task(timer(10, 1))
    await page.wait_for_timeout(10 * 1000)
    await timer_task
    # 如果存在课程五星评价窗口，则点击评价按钮
    if await handle_rating_popup(page):
        logging.info("五星评价完成")


async def handle_h5(page, learn_item):
    """处理h5类型课程"""

    logging.info("h5课程类型，存入文档")
    save_to_file("h5课程类型链接.txt", await get_course_url(learn_item))


async def handle_examination(page, learn_item=None):
    """处理考试类型课程"""

    # await page_detail.wait_for_timeout(3 * 1000)
    if await check_for_pass_grade(page):
        logging.info("考试已通过，跳过该节")

    else:
        if learn_item:
            logging.info("学习课程考试类型，存入文档")
            save_to_file("学习课程考试链接.txt", await get_course_url(learn_item))
            logging.info(f"链接: {await get_course_url(learn_item)}\n")
        else:
            logging.info("学习课程考试类型，存入文档")
            save_to_file("学习课程考试链接.txt", page.url)
            logging.info(f"链接: {page.url}\n")


async def is_subject_completed(page):
    """判断Subject是否学习完毕"""

    await page.wait_for_load_state("load")
    await page.locator(".item.current-hover").last.wait_for()
    await page.locator(".item.current-hover").locator(".section-type").last.wait_for()

    content = (
        await page.locator(".item.current-hover", has_not_text="重新学习")
        .filter(has_text="URL")
        .all()
    )
    return not bool(content)
