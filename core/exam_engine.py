import logging
import re
import traceback

from core.file_ops import save_to_file
from core.question_parser import (
    detect_question_type_by_dom,
    extract_options,
    parse_question_type,
)


async def detect_exam_mode(page):
    """检测考试模式：根据是否存在下一题按钮来判断"""
    try:
        single_btns = page.locator(".single-btns")
        await single_btns.wait_for(state="visible", timeout=3000)
        logging.info("检测为单题目模式(有下一题按钮)")
        return "single"
    except Exception as e:
        logging.info(f"检测为多题目模式(无下一题按钮)\n{e}")
        return "multi"


async def extract_single_question_data(page):
    """提取单题目信息"""
    try:
        # 获取题目类型
        question_type_text = await page.locator(".o-score").last.inner_text()
        logging.debug(f"题目类型文本: {question_type_text}")

        question_type = parse_question_type(question_type_text)
        if question_type == "unknown":
            question_type = await detect_question_type_by_dom(page)

        # 获取题目内容
        question_text = await page.locator(
            ".single-title .rich-text-style"
        ).inner_text()
        logging.debug(f"题目内容: {question_text}")

        # 获取选项
        options = await extract_options(page, question_type)
        logging.debug(f"选项: {options}")

        return {"type": question_type, "text": question_text, "options": options}
    except Exception as e:
        logging.error(f"提取题目信息出错: {e}")
        logging.error(traceback.format_exc())
        return None


async def extract_multi_questions_data(page):
    """提取页面中所有题目的信息(多题目模式)"""
    try:
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

            question_type = parse_question_type(question_type_text)
            if question_type == "unknown":
                question_type = await detect_question_type_by_dom(question_item)

            # 获取题目内容
            try:
                if await question_item.locator(".stem-content-main").count() > 0:
                    question_text = await question_item.locator(
                        ".stem-content-main"
                    ).inner_text()
                else:
                    question_text = await question_item.locator(
                        ".single-title .rich-text-style"
                    ).inner_text()
            except Exception:
                logging.error(f"无法获取题目 {i+1} 的内容")
                continue

            logging.debug(f"题目 {i+1} 内容: {question_text}")

            # 获取选项(使用统一的提取函数)
            options = await extract_options(question_item, question_type)
            logging.debug(f"题目 {i+1} 选项: {options}")

            item_id = (
                await question_item.get_attribute("data-dynamic-key") or f"item-{i}"
            )

            all_questions.append(
                {
                    "index": i,
                    "type": question_type,
                    "text": question_text,
                    "options": options,
                    "item_id": item_id,
                }
            )

        return all_questions
    except Exception as e:
        logging.error(f"提取所有题目信息出错: {e}")
        logging.error(traceback.format_exc())
        return []


async def get_ai_answers(client, model, question_data, is_thinking):
    """使用AI分析题目并获取答案"""
    try:
        if question_data["type"] == "fill_blank":
            logging.info("检测到填空题, 将跳过自动作答")
            return []

        # 构建提示
        type_labels = {
            "single": "单选题",
            "multiple": "多选题/不定项选择题",
            "judge": "判断题(请回答'正确'或'错误')",
            "ordering": "排序题(请按正确顺序给出选项字母, 如'ACBDEF')",
            "reading": "阅读理解题",
        }
        question_type_str = type_labels.get(question_data["type"], "")

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
        type_hints = {
            "ordering": "请直接给出正确的排序顺序, 只需按字母顺序列出, 如'ACBDEF'。",
            "reading": "请直接回答选项代号(如A、B、C、D)。",
            "judge": "请直接回答'正确'或'错误'。",
        }
        prompt += type_hints.get(
            question_data["type"],
            "请直接回答选项代号(如A、B、C、D等), 不定项选择题、多选题可以选择多个选项。",
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的考试助手, 请根据题目选择最合适的答案。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            stream=True,
            extra_body={"enable_thinking": is_thinking},
        )

        reasoning_content = ""
        answer_content = ""

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if (
                hasattr(delta, "reasoning_content")
                and delta.reasoning_content is not None
            ):
                reasoning_content += delta.reasoning_content

            if hasattr(delta, "content") and delta.content:
                answer_content += delta.content

        logging.info(f"AI推理过程: {reasoning_content[:200]}...")
        logging.info(f"AI最终答案: {answer_content}")

        final_answer = answer_content.strip()

        # 针对不同题型处理答案
        if question_data["type"] == "judge":
            if "正确" in final_answer.lower():
                return ["正确"]
            elif "错误" in final_answer.lower():
                return ["错误"]
            elif "t" in final_answer.lower():
                return ["正确"]
            elif "f" in final_answer.lower():
                return ["错误"]
            else:
                logging.warning(f"无法识别的判断题答案: {final_answer}")
                return ["正确"]
        elif question_data["type"] == "ordering":
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
            pattern = r"[A-Z]"
            answers = re.findall(pattern, final_answer)
            seen = set()
            answers = [x for x in answers if not (x in seen or seen.add(x))]
            logging.info(f"提取的答案选项: {answers}")
            return answers
    except Exception as e:
        logging.error(f"获取AI答案出错: {e}")
        logging.error(traceback.format_exc())
        return []


async def select_answers(page, question_data, answers, course_url, selector_prefix=""):
    """
    根据AI答案选择选项(统一处理单题目和多题目模式)。

    Args:
        selector_prefix: CSS选择器前缀, 多题目模式传入 "[data-dynamic-key='xxx'] "
    """
    try:
        question_index = question_data.get("index", 0)
        log_prefix = f"题目 {question_index + 1}: " if selector_prefix else ""

        if not answers:
            logging.info(
                f"{log_prefix}没有获取到有效答案, 推测存在填空类型题目, 存入人工考试链接备查"
            )
            save_to_file("./人工考试链接.txt", course_url)
            return

        logging.info(f"{log_prefix}选择答案: {answers}")

        if question_data["type"] == "fill_blank":
            logging.info(f"{log_prefix}填空题, 跳过自动作答")
            return

        if question_data["type"] == "ordering":
            answer_sequence = "".join(answers)
            logging.info(f"{log_prefix}输入排序顺序: {answer_sequence}")
            try:
                selector = f"{selector_prefix}.answer-input-shot"
                await page.fill(selector, answer_sequence)
                logging.info(f"{log_prefix}已输入排序顺序: {answer_sequence}")
            except Exception as e:
                logging.warning(f"{log_prefix}输入排序顺序失败: {e}")

        elif question_data["type"] == "judge":
            answer_index = 0 if answers[0] == "正确" else 1
            try:
                selector = (
                    f"{selector_prefix}.preview-list dd:nth-child({answer_index + 1})"
                )
                await page.locator(selector).click(timeout=2000)
                logging.info(f"{log_prefix}已点击判断题选项: {answers[0]}")
            except Exception as e:
                logging.warning(f"{log_prefix}点击判断题选项失败: {e}")

        elif question_data["type"] == "single" and selector_prefix:
            # 多题目模式下的单选题：只取第一个答案
            answer = answers[0]
            option_index = ord(answer) - ord("A")
            if 0 <= option_index < len(question_data["options"]):
                try:
                    selector = f"{selector_prefix}.preview-list dd:nth-child({option_index + 1})"
                    await page.locator(selector).first.click(timeout=2000)
                    logging.info(f"{log_prefix}已点击单选题选项: {answer}")
                except Exception as e:
                    logging.warning(f"{log_prefix}点击选项 {answer} 失败: {e}")

        else:
            # 单选题(单题模式)和多选题
            for answer in answers:
                option_index = ord(answer) - ord("A")
                if 0 <= option_index < len(question_data["options"]):
                    try:
                        selector = f"{selector_prefix}.preview-list dd:nth-child({option_index + 1})"
                        await page.locator(selector).first.click(timeout=2000)
                        logging.info(f"{log_prefix}已点击选项: {answer}")
                        await page.wait_for_timeout(300)
                    except Exception as e:
                        logging.warning(f"{log_prefix}点击选项 {answer} 失败: {e}")

    except Exception as e:
        logging.error(f"选择答案出错: {e}")
        logging.error(traceback.format_exc())


async def ai_exam(client, model, page, is_thinking, course_url, auto_submit=True):
    """AI自动答题主函数"""
    logging.info("AI考试开始")

    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    # 检测并关闭考试提示弹窗
    try:
        popup = page.locator(".dialog.animated")
        if await popup.count() > 0:
            logging.info("检测到考试提示弹窗, 准备关闭")
            await popup.locator(".dialog-footer .btn").first.click()
            await page.wait_for_timeout(1000)
            logging.info("弹窗已关闭")
        else:
            logging.info("未检测到考试提示弹窗")
    except Exception as e:
        logging.error(f"处理考试提示弹窗时出错: {e}")
        await page.wait_for_timeout(2000)

    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    exam_mode = await detect_exam_mode(page)

    if exam_mode == "single":
        # 单题目模式
        while True:
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)

            question_data = await extract_single_question_data(page)
            if not question_data:
                logging.error("无法提取题目信息")
                break

            logging.info(f"当前题目: {question_data['text']}")
            logging.info(f"题目类型: {question_data['type']}")

            answers = await get_ai_answers(client, model, question_data, is_thinking)
            await select_answers(page, question_data, answers, course_url)

            next_button = page.locator(".single-btn-next")
            next_button_classes = await next_button.get_attribute("class") or ""

            if "next-disabled" in next_button_classes:
                if auto_submit:
                    logging.info("已经是最后一题, 准备交卷")
                    await page.locator("text=我要交卷").click()
                    await page.wait_for_timeout(1000)
                    await page.locator("button:has-text('确 定')").click()
                    await page.wait_for_timeout(1000)
                    await page.locator("text=确定").click()
                    break
                else:
                    logging.info("自动交卷已取消, 请手动交卷")
                    logging.info("页面将保持打开状态, 等待手动操作...")
                    await page.wait_for_event("close", timeout=0)
                    break
            else:
                logging.info("点击下一题")
                await next_button.click()
                await page.wait_for_timeout(1000)
    else:
        # 多题目模式
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        all_questions = await extract_multi_questions_data(page)
        if not all_questions:
            logging.error("无法提取任何题目信息")
            return

        logging.info(f"本页共有 {len(all_questions)} 道题目")

        for question_data in all_questions:
            logging.info(
                f"处理题目 {question_data['index']+1}: {question_data['text']}"
            )

            answers = await get_ai_answers(client, model, question_data, is_thinking)

            # 使用统一的 select_answers, 通过 selector_prefix 区分
            item_id = question_data["item_id"]
            await select_answers(
                page,
                question_data,
                answers,
                course_url,
                selector_prefix=f"[data-dynamic-key='{item_id}'] ",
            )

            await page.wait_for_timeout(500)

        # 点击交卷
        if auto_submit:
            try:
                await page.locator("text=我要交卷").click()
                await page.wait_for_timeout(1000)
                await page.locator("button:has-text('确 定')").click()
                await page.wait_for_timeout(1000)
                await page.locator("text=确定").click()
            except Exception as e:
                logging.error(f"点击交卷按钮失败: {e}")
        else:
            logging.info("自动交卷已取消, 请手动交卷")
            logging.info("页面将保持打开状态, 等待手动操作...")
            await page.wait_for_event("close", timeout=0)

    logging.info("考试完成")


async def wait_for_finish_test(client, model, page1, is_thinking=False):
    """打开考试弹窗并执行AI考试"""
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    await ai_exam(client, model, page2, is_thinking, page1.url)
    await page2.wait_for_event("close", timeout=0)
