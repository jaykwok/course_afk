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


def is_compliant_url_regex(url):
    """
    使用正则表达式判断URL是否符合指定的合规格式。

    合规格式: https://kc.zhixueyun.com/#/study/(course|subject)/detail/UUID

    Args:
    url: 待检查的URL字符串。

    Returns:
    True 如果URL合规, 否则 False。
    """

    # 正则表达式解释:
    # ^                                  匹配字符串开头
    # https://kc\.zhixueyun\.com/#/study/  匹配固定的前缀 (注意 . 和 # 需要转义, 虽然#在这里可能不必须, 但转义更安全)
    # (course|subject)                   匹配 "course" 或 "subject"
    # /detail/                           匹配 "/detail/"
    # [0-9a-fA-F]{8}                     匹配8个十六进制字符
    # -                                  匹配连字符
    # [0-9a-fA-F]{4}                     匹配4个十六进制字符
    # -                                  匹配连字符
    # [0-9a-fA-F]{4}                     匹配4个十六进制字符
    # -                                  匹配连字符
    # [0-9a-fA-F]{4}                     匹配4个十六进制字符
    # -                                  匹配连字符
    # [0-9a-fA-F]{12}                    匹配12个十六进制字符
    # $                                  匹配字符串结尾
    pattern = r"^https://kc\.zhixueyun\.com/#/study/(course|subject)/detail/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

    if re.match(pattern, url):
        return True
    else:
        return False


async def check_permisson(frame):
    try:
        # 在当前frame中查找文本
        text_content = await frame.content()
        if (
            "您没有权限查看该资源" in text_content
            or "该资源已不存在" in text_content
            or "该资源已下架" in text_content
        ):
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


# 检测考试是否通过
async def check_exam_passed(page):
    await page.wait_for_timeout(1000)
    try:
        # 判断是否在考试中状态
        status_element = await page.locator(".neer-status").count()
        if status_element > 0:
            highest_score_text = await page.locator(".neer-status").inner_text()
            if "考试中" in highest_score_text:
                logging.info("考试状态: 考试中")
                return False

        # 检查表格是否存在
        table_exists = await page.locator("div.tab-container table.table").count()
        if table_exists == 0:
            logging.info("考试状态: 未找到考试表格")
            return False

        # 确认第一行的状态单元格存在后再获取文本, 使用较短的超时时间
        status_cell_element = page.locator(
            "div.tab-container table.table tbody tr:first-child td:nth-child(4)"
        )

        await status_cell_element.wait_for(state="visible", timeout=1500)

        if await status_cell_element.count() == 0:
            logging.info("首次进入考试页面, 未进行考试")
            return False

        # 获取状态单元格文本
        status_cell = await page.locator(
            "div.tab-container table.table tbody tr:first-child td:nth-child(4)"
        ).inner_text(timeout=3000)
        status_cell = status_cell.strip()

        if status_cell == "及格":
            logging.info("考试状态: 通过")
            return True
        elif status_cell == "待评卷":
            logging.info("考试状态: 待评卷")
            return True
        else:
            logging.info(f"考试状态: 未通过 ({status_cell})")
            return False
    except Exception as e:
        logging.error(f"获取考试状态时出错: {e}")
        return False


async def handle_rating_popup(page):
    """监测评分弹窗, 选择五星并提交"""
    try:
        # 等待弹窗出现, 使用更长的超时时间
        dialog = page.locator(".ant-modal-content")
        try:
            await dialog.wait_for(state="visible", timeout=1500)
            logging.info("检测到评分弹窗")
        except Exception as e:
            logging.debug(f"未检测到评分弹窗: {e}")
            return False

        # 确保星星容器已加载
        stars_container = dialog.locator("ul.ant-rate")
        await stars_container.wait_for(state="visible", timeout=1000)

        try:
            fifth_star = dialog.locator("ul.ant-rate li:nth-child(5) div[role='radio']")
            await fifth_star.wait_for(state="visible", timeout=1000)

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
                    if str(e) == "无权限查看该资源":
                        save_to_file(
                            "无权限资源链接.txt", await get_course_url(learn_item)
                        )
                    else:
                        mark = 1
                        save_to_file(
                            "剩余未看课程链接.txt", await get_course_url(learn_item)
                        )
                finally:
                    await page_detail.close()

            elif section_type == "URL":
                logging.info("URL学习类型, 存入文档单独审查")
                save_to_file("URL类型链接.txt", page.url)
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
                    logging.info("学习主题考试类型, 存入文档")
                    save_to_file("学习主题考试链接.txt", page.url)

            elif section_type == "调研":
                logging.info("调研学习类型, 存入文档单独审查")
                save_to_file("调研类型链接.txt", await get_course_url(learn_item))

            else:
                logging.info("非课程及考试类学习类型, 存入文档单独审查")
                save_to_file("非课程及考试类学习类型链接.txt", page.url)
    return mark


async def course_learning(page_detail, learn_item=None):
    """课程内容学习"""

    await page_detail.wait_for_load_state("load")

    # 检查是否有权限访问该资源
    if await check_permisson(page_detail.main_frame):
        # 如果存在课程五星评价窗口, 则点击评价按钮
        if await handle_rating_popup(page_detail):
            logging.info("五星评价完成")
    else:
        raise Exception(f"无权限查看该资源")

    if await is_course_completed(page_detail):
        title = await page_detail.locator("span.course-title-text").inner_text()
        logging.info(f"<{title}>已学习完毕, 跳过该课程\n")
        return

    await page_detail.locator("dl.chapter-list-box.required").last.wait_for()
    chapter_boxes = await page_detail.locator("dl.chapter-list-box.required").all()

    # 预先检查所有章节是否已学习
    all_learned = True
    has_non_detectable_types = False

    for box in chapter_boxes:
        section_type = await box.get_attribute("data-sectiontype")
        # 只检查可以预先判断的类型（视频和文档）
        if section_type in ["1", "2", "3", "5", "6"]:
            progress_text = await box.locator(".section-item-wrapper").inner_text()
            if not is_learned(progress_text):
                all_learned = False
                break
        else:
            # 未知类型无法预先检测, 标记需要处理
            has_non_detectable_types = True

    # 如果所有已知类型章节已学习, 且没有未知类型章节, 则可跳过整个课程
    if all_learned and not has_non_detectable_types:
        logging.info("所有章节已学习完毕, 跳过该课程")
        return

    # 处理各个章节
    for count, box in enumerate(chapter_boxes, start=1):
        section_type = await box.get_attribute("data-sectiontype")
        box_text = await box.locator(".text-overflow").inner_text()
        logging.info(f"课程信息: \n{box_text}\n")

        # 预先检查是否已学习(针对可检测的类型)
        if section_type in ["1", "2", "3", "5", "6"]:
            progress_text = await box.locator(".section-item-wrapper").inner_text()
            if is_learned(progress_text):
                logging.info(f"课程{count}已学习, 跳过该节\n")
                continue

        # 点击章节, 如果存在课程五星评价窗口, 则点击评价按钮
        if await handle_rating_popup(page_detail):
            logging.info("五星评价完成")
        await box.locator(".section-item-wrapper").wait_for()
        await box.locator(".section-item-wrapper").click()

        # 根据章节类型处理
        if section_type in ["5", "6"]:
            # 处理视频类型课程
            logging.info("该课程为视频类型")
            await handle_video(box, page_detail)
        elif section_type in ["1", "2", "3"]:
            # 处理文档、网页类型课程
            logging.info("该课程为文档、网页类型")
            await handle_document(page_detail)
        elif section_type == "4":
            # 处理h5类型课程
            logging.info("该课程为h5类型")
            await handle_h5(page_detail, learn_item)
        elif section_type == "9":
            # 处理考试类型课程
            logging.info("该课程为考试类型")
            if await check_exam_passed(page_detail):
                logging.info("考试已通过, 跳过该节")
                continue
            else:
                if learn_item:
                    await handle_examination(page_detail, learn_item)
                else:
                    await handle_examination(page_detail)
        else:
            logging.info("未知课程学习类型, 存入文档单独审查")
            if learn_item:
                save_to_file("未知类型链接.txt", await get_course_url(learn_item))
            else:
                save_to_file("未知类型链接.txt", page_detail.url)
            continue
        logging.info(f"课程{count}学习完毕")


async def check_and_handle_rating_popup(page):
    """检查并处理视频内课程质量评价弹窗"""
    try:
        # 使用快速超时检查弹窗是否存在, 避免长时间等待
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
    """定期检查视频内评价弹窗, 持续指定时间"""

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

    # 等待计算的剩余时间, 同时定期检查评价弹窗
    timer_task = asyncio.create_task(timer(remaining))
    popup_check_task = asyncio.create_task(
        check_rating_popup_periodically(page, remaining)
    )
    await page.wait_for_timeout(remaining * 1000)
    await timer_task
    await popup_check_task

    # 确认课程进度是否已同步到服务器
    logging.info("课程学习完毕, 确认课程进度同步状态...")
    current_text = await box.locator(".section-item-wrapper").inner_text()
    if is_learned(current_text):
        logging.info(f"课程进度已同步到服务器")
        return

    # 额外等待最多5分钟, 以便同步课程进度
    extra_wait_time = 5 * 60  # 额外等待5分钟同步状态
    check_interval = 10  # 每10秒检查一次

    for i in range(0, extra_wait_time, check_interval):
        # 每次检查前先检查评价弹窗
        await check_and_handle_rating_popup(page)

        # 检查是否还有"需再学"字样
        current_text = await box.locator(".section-item-wrapper").inner_text()
        if is_learned(current_text):
            logging.info(f"课程进度已同步到服务器, 额外等待 {i} 秒")
            return

        logging.info(
            f"课程进度仍未同步完成, 已额外等待 {i + check_interval} 秒, 继续等待..."
        )
        await page.wait_for_timeout(check_interval * 1000)

    # 如果5分钟后仍未完成, 抛出异常
    current_text = await box.locator(".section-item-wrapper").inner_text()
    if not is_learned(current_text):
        logging.info(f"超时: 已额外等待5分钟, 课程进度仍未同步")
        raise Exception("课程进度未能在额外等待时间内同步完成")


async def handle_document(page):
    """处理文档、网页类型课程"""

    # await page.wait_for_timeout(3 * 1000)
    # await page.locator('.clearfix').first.wait_for()
    await page.locator(".image-text-water").first.wait_for()
    timer_task = asyncio.create_task(timer(10, 1))
    await page.wait_for_timeout(10 * 1000)
    await timer_task


async def handle_h5(page, learn_item):
    """处理h5类型课程"""

    logging.info("h5课程类型, 存入文档")
    save_to_file("h5课程类型链接.txt", await get_course_url(learn_item))


async def handle_examination(page, learn_item=None):
    """处理考试类型课程"""

    # await page_detail.wait_for_timeout(3 * 1000)
    if await check_exam_passed(page):
        logging.info("考试已通过, 跳过该节")
    else:
        if learn_item:
            logging.info("学习课程考试类型, 存入文档")
            save_to_file("学习课程考试链接.txt", await get_course_url(learn_item))
            logging.info(f"链接: {await get_course_url(learn_item)}\n")
        else:
            logging.info("学习课程考试类型, 存入文档")
            save_to_file("学习课程考试链接.txt", page.url)
            logging.info(f"链接: {page.url}\n")


async def is_subject_url_completed(page):
    """判断学习主题中的URL是否学习完毕"""

    await page.wait_for_load_state("load")
    await page.locator(".item.current-hover").last.wait_for()
    await page.locator(".item.current-hover").locator(".section-type").last.wait_for()

    content = (
        await page.locator(".item.current-hover", has_not_text="重新学习")
        .filter(has_text="URL")
        .all()
    )
    return not bool(content)


#######################################################################################################################
# 考试部分组件
async def detect_exam_mode(page):
    """检测考试模式：根据是否存在下一题按钮来判断"""
    try:
        # 检查是否存在"下一题"按钮，这是单题目模式的特征
        single_btns = page.locator(".single-btns")
        await single_btns.wait_for(state="visible", timeout=3000)
        logging.info("检测为单题目模式（有下一题按钮）")
        return "single"

    except Exception as e:
        logging.info(f"检测为多题目模式（无下一题按钮）\n{e}")
        return "multi"  # 无法检测到下一题按钮元素证明为多题目模式


async def extract_single_question_data(page):
    """提取单题目信息"""
    try:
        # 获取题目类型
        question_type_text = await page.locator(".o-score").last.inner_text()
        logging.debug(f"题目类型文本: {question_type_text}")

        if "单选题" in question_type_text:
            question_type = "single"
        elif "多选题" in question_type_text or "不定项选择" in question_type_text:
            question_type = "multiple"
        elif "判断题" in question_type_text:
            question_type = "judge"
        elif "填空题" in question_type_text:
            question_type = "fill_blank"
        elif "排序题" in question_type_text:
            question_type = "ordering"
        elif "阅读理解题" in question_type_text:
            question_type = "reading"
        else:
            # 通过结构检测填空题
            if await page.locator("form.vertical .sentence-input").count() > 0:
                question_type = "fill_blank"
            # 检测排序题
            elif await page.locator(".answer-input-shot").count() > 0:
                question_type = "ordering"
            else:
                question_type = "unknown"

        # 获取题目内容
        question_text = await page.locator(
            ".single-title .rich-text-style"
        ).inner_text()
        logging.debug(f"题目内容: {question_text}")

        # 获取选项
        options = []

        # 如果是填空题，不获取选项
        if question_type == "fill_blank":
            logging.info("检测到填空题，跳过选项提取")
        # 如果是排序题，获取排序选项
        elif question_type == "ordering":
            option_elements = page.locator(".preview-list dd")
            count = await option_elements.count()

            for i in range(count):
                option_element = option_elements.nth(i)
                option_label = await option_element.locator(".option-num").inner_text()
                option_text = await option_element.locator(
                    ".answer-options"
                ).inner_text()
                options.append(
                    {
                        "label": option_label.strip().replace(".", ""),
                        "text": option_text.strip(),
                    }
                )
        # 判断题的选项处理
        elif question_type == "judge":
            judge_options = page.locator(".preview-list dd span.pointer")
            count = await judge_options.count()

            for i in range(count):
                option_text = await judge_options.nth(i).inner_text()
                options.append(
                    {
                        "label": "T" if "正确" in option_text else "F",
                        "text": option_text.strip(),
                    }
                )
        else:
            # 单选题、多选题和阅读理解题的选项定位
            option_elements = page.locator(".preview-list dd")
            count = await option_elements.count()

            for i in range(count):
                option_element = option_elements.nth(i)
                option_label = await option_element.locator(".option-num").inner_text()
                option_text = await option_element.locator(
                    ".answer-options"
                ).inner_text()
                options.append(
                    {
                        "label": option_label.strip().replace(".", ""),
                        "text": option_text.strip(),
                    }
                )

        logging.debug(f"选项: {options}")

        return {"type": question_type, "text": question_text, "options": options}
    except Exception as e:
        logging.error(f"提取题目信息出错: {e}")
        logging.error(traceback.format_exc())
        return None


async def extract_multi_questions_data(page):
    """提取页面中所有题目的信息（多题目模式）"""
    try:
        # 获取所有题目项
        question_items = page.locator(".question-type-item")
        count = await question_items.count()
        logging.info(f"检测到 {count} 个题目")

        all_questions = []

        for i in range(count):
            question_item = question_items.nth(i)

            # 获取题目类型
            question_type_text = await question_item.locator(
                ".o-score"
            ).last.inner_text()
            logging.debug(f"题目 {i+1} 类型文本: {question_type_text}")

            if "单选题" in question_type_text:
                question_type = "single"
            elif "多选题" in question_type_text or "不定项选择" in question_type_text:
                question_type = "multiple"
            elif "判断题" in question_type_text:
                question_type = "judge"
            elif "填空题" in question_type_text:
                question_type = "fill_blank"
            elif "排序题" in question_type_text:
                question_type = "ordering"
            elif "阅读理解题" in question_type_text:
                question_type = "reading"
            else:
                # 通过DOM结构判断题型
                if (
                    await question_item.locator("form.vertical .sentence-input").count()
                    > 0
                ):
                    question_type = "fill_blank"
                elif await question_item.locator(".answer-input-shot").count() > 0:
                    question_type = "ordering"
                else:
                    question_type = "unknown"

            # 获取题目内容 - 多题目页面的结构
            try:
                # 尝试获取带有前缀编号的题目
                if await question_item.locator(".stem-content-main").count() > 0:
                    question_text = await question_item.locator(
                        ".stem-content-main"
                    ).inner_text()
                else:
                    # 尝试获取普通题目文本
                    question_text = await question_item.locator(
                        ".single-title .rich-text-style"
                    ).inner_text()
            except Exception:
                logging.error(f"无法获取题目 {i+1} 的内容")
                continue

            logging.debug(f"题目 {i+1} 内容: {question_text}")

            # 获取选项
            options = []

            # 如果是填空题，跳过选项获取
            if question_type == "fill_blank":
                logging.info(f"题目 {i+1} 是填空题，跳过选项提取")
            # 如果是排序题，获取排序选项
            elif question_type == "ordering":
                option_elements = question_item.locator(".preview-list dd")
                option_count = await option_elements.count()

                for j in range(option_count):
                    option_element = option_elements.nth(j)
                    option_label = await option_element.locator(
                        ".option-num"
                    ).inner_text()
                    option_text = await option_element.locator(
                        ".answer-options"
                    ).inner_text()
                    options.append(
                        {
                            "label": option_label.strip().replace(".", ""),
                            "text": option_text.strip(),
                        }
                    )
            # 判断题的选项处理
            elif question_type == "judge":
                judge_options = question_item.locator(".preview-list dd .pointer")
                option_count = await judge_options.count()

                for j in range(option_count):
                    option_text = await judge_options.nth(j).inner_text()
                    options.append(
                        {
                            "label": "T" if "正确" in option_text else "F",
                            "text": option_text.strip(),
                        }
                    )
            else:
                # 单选题和多选题的选项定位
                option_elements = question_item.locator(".preview-list dd")
                option_count = await option_elements.count()

                for j in range(option_count):
                    option_element = option_elements.nth(j)
                    option_label = await option_element.locator(
                        ".option-num"
                    ).inner_text()
                    option_text = await option_element.locator(
                        ".answer-options"
                    ).inner_text()
                    options.append(
                        {
                            "label": option_label.strip().replace(".", ""),
                            "text": option_text.strip(),
                        }
                    )

            logging.debug(f"题目 {i+1} 选项: {options}")

            # 存储题目数据和元素ID，便于后续定位
            item_id = (
                await question_item.get_attribute("data-dynamic-key") or f"item-{i}"
            )

            question_data = {
                "index": i,
                "type": question_type,
                "text": question_text,
                "options": options,
                "item_id": item_id,  # 存储元素ID，方便后续定位
            }

            all_questions.append(question_data)

        return all_questions
    except Exception as e:
        logging.error(f"提取所有题目信息出错: {e}")
        logging.error(traceback.format_exc())
        return []


async def get_ai_answers(client, model, question_data, is_thinking):
    """使用AI分析题目并获取答案 - 适配百炼API的流式输出和思考过程"""
    try:
        # 如果是填空题，直接返回空数组，跳过自动作答
        if question_data["type"] == "fill_blank":
            logging.info("检测到填空题，将跳过自动作答")
            return []

        # 构建提示
        question_type_str = ""
        if question_data["type"] == "single":
            question_type_str = "单选题"
        elif question_data["type"] == "multiple":
            question_type_str = "多选题/不定项选择题"
        elif question_data["type"] == "judge":
            question_type_str = "判断题（请回答'正确'或'错误'）"
        elif question_data["type"] == "ordering":
            question_type_str = "排序题（请按正确顺序给出选项字母，如'ACBDEF'）"
        elif question_data["type"] == "reading":
            question_type_str = "阅读理解题"

        options_str = ""
        for option in question_data["options"]:
            options_str += f"{option['label']}. {option['text']}\n"

        prompt = f"""
        请回答以下{question_type_str}：
        
        问题：{question_data['text']}
        
        选项：
        {options_str}
        """

        # 根据题型添加具体提示
        if question_data["type"] == "ordering":
            prompt += "请直接给出正确的排序顺序，只需按字母顺序列出，如'ACBDEF'。"
        elif question_data["type"] == "reading":
            prompt += "请直接回答选项代号（如A、B、C、D）。"
        elif question_data["type"] == "judge":
            prompt += "请直接回答'正确'或'错误'。"
        else:
            prompt += "请直接回答选项代号（如A、B、C、D等），不定项选择题、多选题可以选择多个选项。"

        # 使用OpenAI API，启用流式响应和思考过程
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的考试助手，请根据题目选择最合适的答案。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            stream=True,
            # 是否启用推理模式
            extra_body={"enable_thinking": is_thinking},
        )

        # 流式处理响应
        reasoning_content = ""  # 完整思考过程
        answer_content = ""  # 完整回复
        is_answering = False  # 是否进入回复阶段

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # 收集思考内容
            if (
                hasattr(delta, "reasoning_content")
                and delta.reasoning_content is not None
            ):
                reasoning_content += delta.reasoning_content

            # 收集回答内容
            if hasattr(delta, "content") and delta.content:
                is_answering = True
                answer_content += delta.content

        logging.info(f"AI推理过程: {reasoning_content[:200]}...")
        logging.info(f"AI最终答案: {answer_content}")

        # 使用answer_content作为最终答案
        final_answer = answer_content.strip()

        # 针对不同题型处理答案
        if question_data["type"] == "judge":
            # 处理判断题答案
            if "正确" in final_answer.lower():
                return ["正确"]
            elif "错误" in final_answer.lower():
                return ["错误"]
            # 如果回答中包含T/F
            elif "t" in final_answer.lower():
                return ["正确"]
            elif "f" in final_answer.lower():
                return ["错误"]
            else:
                logging.warning(f"无法识别的判断题答案: {final_answer}")
                return ["正确"]  # 默认选择正确
        elif question_data["type"] == "ordering":
            # 处理排序题答案 - 先尝试提取完整序列，再尝试单个字母提取
            pattern = r"[A-Z]+"
            sequences = re.findall(pattern, final_answer)

            if sequences:
                longest_sequence = max(sequences, key=len)
                answers = list(longest_sequence)
                logging.info(f"提取的排序顺序: {answers}")
                return answers
            else:
                pattern = r"[A-Z]"
                answers = re.findall(pattern, final_answer)
                logging.info(f"提取的排序顺序: {answers}")
                return answers
        else:
            # 处理选择题答案 - 提取所有的A-Z选项
            pattern = r"[A-Z]"
            answers = re.findall(pattern, final_answer)

            # 去重但保持顺序
            seen = set()
            answers = [x for x in answers if not (x in seen or seen.add(x))]

            logging.info(f"提取的答案选项: {answers}")
            return answers
    except Exception as e:
        logging.error(f"获取AI答案出错: {e}")
        logging.error(traceback.format_exc())
        return []


async def select_answers(page, question_data, answers, course_url):
    """根据AI答案选择选项（单题目模式）"""
    try:
        if not answers:
            logging.info(
                "没有获取到有效答案，推测存在填空类型题目，存入人工考试链接备查)"
            )
            # 没有获取到有效答案，推测存在填空类型题目，存入人工考试链接备查
            save_to_file("./人工考试链接.txt", course_url)
            return

        logging.info(f"选择答案: {answers}")

        # 如果是填空题，跳过自动作答
        if question_data["type"] == "fill_blank":
            logging.info("填空题，跳过自动作答")
            return

        # 如果是排序题，填入排序顺序
        elif question_data["type"] == "ordering":
            answer_sequence = "".join(answers)
            logging.info(f"输入排序顺序: {answer_sequence}")

            try:
                # 定位输入框并填入答案
                await page.fill(".answer-input-shot", answer_sequence)
                logging.info(f"已输入排序顺序: {answer_sequence}")
            except Exception as e:
                logging.warning(f"输入排序顺序失败: {e}")

        elif question_data["type"] == "judge":
            # 判断题选择逻辑
            answer_index = 0 if answers[0] == "正确" else 1
            # 尝试直接点击dd元素而非内部的label
            try:
                await page.locator(
                    f".preview-list dd:nth-child({answer_index + 1})"
                ).click()
                logging.info(f"已点击判断题选项: {answers[0]}")
            except Exception as e:
                logging.warning(f"直接点击dd元素失败: {e}")

        else:
            # 单选题和多选题的选择逻辑
            for answer in answers:
                option_index = ord(answer) - ord("A")
                if 0 <= option_index < len(question_data["options"]):
                    try:
                        # 直接点击dd元素而非内部的label
                        await page.locator(
                            f".preview-list dd:nth-child({option_index + 1})"
                        ).first.click()
                        logging.info(f"已点击选项: {answer}")
                        await page.wait_for_timeout(300)  # 稍微延迟，避免点击太快
                    except Exception as e:
                        logging.warning(f"点击选项 {answer} 失败: {e}")

    except Exception as e:
        logging.error(f"选择答案出错: {e}")
        logging.error(traceback.format_exc())


async def select_answer_for_multi_question(page, question_data, answers, course_url):
    """为多题目模式中的单个题目选择答案"""
    try:
        item_id = question_data["item_id"]

        if not answers:
            logging.info(
                "没有获取到有效答案，推测存在填空类型题目，存入人工考试链接备查)"
            )
            # 没有获取到有效答案，推测存在填空类型题目，存入人工考试链接备查
            save_to_file("./人工考试链接.txt", course_url)
            return

        logging.info(f"题目 {question_data['index']+1}: 选择答案: {answers}")

        # 如果是填空题，跳过自动作答
        if question_data["type"] == "fill_blank":
            logging.info(f"题目 {question_data['index']+1}: 填空题，跳过自动作答")
            return

        # 如果是排序题，填入排序顺序
        elif question_data["type"] == "ordering":
            answer_sequence = "".join(answers)
            logging.info(
                f"题目 {question_data['index']+1}: 输入排序顺序: {answer_sequence}"
            )

            try:
                selector = f"[data-dynamic-key='{item_id}'] .answer-input-shot"
                await page.fill(selector, answer_sequence)
                logging.info(
                    f"题目 {question_data['index']+1}: 已输入排序顺序: {answer_sequence}"
                )
            except Exception as e:
                logging.warning(
                    f"题目 {question_data['index']+1}: 输入排序顺序失败: {e}"
                )

        elif question_data["type"] == "judge":
            # 判断题选择逻辑
            answer_index = 0 if answers[0] == "正确" else 1
            try:
                selector = f"[data-dynamic-key='{item_id}'] .preview-list dd:nth-child({answer_index + 1})"
                await page.locator(selector).click(timeout=2000)
                logging.info(
                    f"题目 {question_data['index']+1}: 已点击判断题选项: {answers[0]}"
                )
            except Exception as e:
                logging.warning(
                    f"题目 {question_data['index']+1}: 点击判断题选项失败: {e}"
                )

        elif question_data["type"] == "single":
            # 单选题选择逻辑
            answer = answers[0]  # 单选题只取第一个答案
            option_index = ord(answer) - ord("A")

            if 0 <= option_index < len(question_data["options"]):
                try:
                    selector = f"[data-dynamic-key='{item_id}'] .preview-list dd:nth-child({option_index + 1})"
                    await page.locator(selector).first.click(timeout=2000)
                    logging.info(
                        f"题目 {question_data['index']+1}: 已点击单选题选项: {answer}"
                    )
                except Exception as e:
                    logging.warning(
                        f"题目 {question_data['index']+1}: 点击选项 {answer} 失败: {e}"
                    )

        else:  # 多选题
            # 多选题选择逻辑
            for answer in answers:
                option_index = ord(answer) - ord("A")
                if 0 <= option_index < len(question_data["options"]):
                    try:
                        selector = f"[data-dynamic-key='{item_id}'] .preview-list dd:nth-child({option_index + 1})"
                        await page.locator(selector).click(timeout=2000)
                        logging.info(
                            f"题目 {question_data['index']+1}: 已点击多选题选项: {answer}"
                        )
                        await page.wait_for_timeout(300)  # 稍微延迟，避免点击太快
                    except Exception as e:
                        logging.warning(
                            f"题目 {question_data['index']+1}: 点击选项 {answer} 失败: {e}"
                        )

    except Exception as e:
        logging.error(f"题目 {question_data['index']+1}: 选择答案出错: {e}")
        logging.error(traceback.format_exc())


async def ai_exam(client, model, page, is_thinking, course_url):
    """AI自动答题主函数"""
    logging.info("AI考试开始")

    # 检测考试模式
    exam_mode = await detect_exam_mode(page)

    if exam_mode == "single":
        # 单题目模式
        while True:
            # 等待页面加载
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)  # 额外等待时间确保页面完全加载

            # 提取题目信息
            question_data = await extract_single_question_data(page)
            if not question_data:
                logging.error("无法提取题目信息")
                break

            logging.info(f"当前题目: {question_data['text']}")
            logging.info(f"题目类型: {question_data['type']}")

            # 使用AI分析题目并获取答案
            answers = await get_ai_answers(client, model, question_data, is_thinking)

            # 根据题目类型和AI答案点击选项
            await select_answers(page, question_data, answers, course_url)

            # 检查是否有下一题按钮并且可以点击
            next_button = page.locator(".single-btn-next")
            next_button_classes = await next_button.get_attribute("class") or ""

            if "next-disabled" in next_button_classes:
                logging.info("已经是最后一题，准备交卷")
                # 点击交卷
                await page.locator("text=我要交卷").click()
                await page.wait_for_timeout(1000)
                await page.locator("button:has-text('确 定')").click()
                await page.wait_for_timeout(1000)
                await page.locator("text=确定").click()
                break
            else:
                logging.info("点击下一题")
                await next_button.click()
                await page.wait_for_timeout(1000)  # 等待下一题加载
    else:
        # 多题目模式
        # 等待页面加载
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)  # 额外等待时间确保页面完全加载

        # 提取所有题目信息
        all_questions = await extract_multi_questions_data(page)
        if not all_questions:
            logging.error("无法提取任何题目信息")
            return

        logging.info(f"本页共有 {len(all_questions)} 道题目")

        # 为每个题目获取AI答案并选择
        for question_data in all_questions:
            logging.info(
                f"处理题目 {question_data['index']+1}: {question_data['text']}"
            )

            # 使用AI分析题目并获取答案
            answers = await get_ai_answers(client, model, question_data, is_thinking)

            # 根据题目类型和AI答案点击选项
            await select_answer_for_multi_question(
                page, question_data, answers, course_url
            )

            # 短暂等待，确保选择已生效
            await page.wait_for_timeout(500)

        # 点击交卷
        try:
            await page.locator("text=我要交卷").click()
            await page.wait_for_timeout(1000)
            await page.locator("button:has-text('确 定')").click()
            await page.wait_for_timeout(1000)
            await page.locator("text=确定").click()
        except Exception as e:
            logging.error(f"点击交卷按钮失败: {e}")

    logging.info("考试完成")


async def wait_for_finish_test(client, model, page1, is_thinking=False):
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    await ai_exam(client, model, page2, is_thinking, page1.url)
    await page2.wait_for_event("close", timeout=0)
