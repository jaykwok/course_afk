import asyncio
import json
import logging
import os
import re
import time
import func_module as fm

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

# 配置DashScope API
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")

# 加载默认模型
model = os.getenv("MODEL_NAME")

# 初始化OpenAI客户端 (使用DashScope兼容模式)
client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


async def extract_question_data(page):
    """提取单题目信息"""
    try:
        # 获取题目类型
        question_type_text = await page.locator(".o-score").inner_text()
        logging.debug(f"题目类型文本: {question_type_text}")

        if "单选题" in question_type_text:
            question_type = "single"
        elif "多选题" in question_type_text:
            question_type = "multiple"
        elif "判断题" in question_type_text:
            question_type = "judge"
        else:
            question_type = "unknown"

        # 获取题目内容
        question_text = await page.locator(
            ".single-title .rich-text-style"
        ).inner_text()
        logging.debug(f"题目内容: {question_text}")

        # 获取选项
        options = []

        # 判断题和选择题的选项定位方式不同
        if question_type == "judge":
            # 判断题选项是直接的 "正确"/"错误" 文本
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
            # 单选题和多选题的选项定位
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
        import traceback

        logging.error(traceback.format_exc())
        return None


async def extract_all_questions_data(page):
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
            question_type_text = await question_item.locator(".o-score").inner_text()
            logging.debug(f"题目 {i+1} 类型文本: {question_type_text}")

            if "单选题" in question_type_text:
                question_type = "single"
            elif "多选题" in question_type_text:
                question_type = "multiple"
            elif "判断题" in question_type_text:
                question_type = "judge"
            else:
                question_type = "unknown"

            # 获取题目内容 - 多题目页面的结构
            try:
                question_text = await question_item.locator(
                    ".stem-content-main"
                ).inner_text()
            except Exception:
                logging.error(f"无法获取题目 {i+1} 的内容")
                continue

            logging.debug(f"题目 {i+1} 内容: {question_text}")

            # 获取选项
            options = []

            # 判断题和选择题的选项定位方式不同
            if question_type == "judge":
                # 判断题选项是直接的 "正确"/"错误" 文本
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
        import traceback

        logging.error(traceback.format_exc())
        return []


async def select_answers(page, question_data, answers):
    """根据AI答案选择选项（单题目模式）"""
    try:
        if not answers:
            logging.warning("没有获取到有效答案，随机选择第一个选项")
            # 如果没有获取到答案，选择第一个选项
            if question_data["type"] == "judge":
                await page.locator(".preview-list dd:first-child span.pointer").click(
                    strict=False
                )
            else:
                await page.locator(".preview-list dd:first-child").click()
            return

        logging.info(f"选择答案: {answers}")

        if question_data["type"] == "judge":
            # 判断题选择逻辑
            answer_index = 0 if answers[0] == "正确" else 1
            # 尝试直接点击dd元素而非内部的label
            try:
                await page.locator(
                    f".preview-list dd:nth-child({answer_index + 1})"
                ).click()
                logging.info(f"已点击判断题选项: {answers[0]}")
            except Exception as e:
                logging.warning(f"直接点击dd元素失败，尝试使用JavaScript点击: {e}")
                # 使用JavaScript点击
                await page.evaluate(
                    f"""
                    document.querySelectorAll(".preview-list dd")[{answer_index}].click();
                """
                )
                logging.info(f"已点击判断题选项(使用JavaScript): {answers[0]}")
        else:
            # 单选题和多选题的选择逻辑
            for answer in answers:
                option_index = ord(answer) - ord("A")
                if 0 <= option_index < len(question_data["options"]):
                    try:
                        # 直接点击dd元素而非内部的label
                        await page.locator(
                            f".preview-list dd:nth-child({option_index + 1})"
                        ).click()
                        logging.info(f"已点击选项: {answer}")
                        await page.wait_for_timeout(300)  # 稍微延迟，避免点击太快
                    except Exception as e:
                        logging.warning(
                            f"点击选项 {answer} 失败，尝试使用JavaScript点击: {e}"
                        )
                        # 备选方案：使用JavaScript点击
                        await page.evaluate(
                            f"""
                            document.querySelectorAll(".preview-list dd")[{option_index}].click();
                        """
                        )
                        logging.info(f"已点击选项(使用JavaScript): {answer}")
                        await page.wait_for_timeout(300)
    except Exception as e:
        logging.error(f"选择答案出错: {e}")
        import traceback

        logging.error(traceback.format_exc())


async def select_answer_for_question_multi(page, question_data, answers):
    """为多题目模式中的单个题目选择答案"""
    try:
        item_id = question_data["item_id"]

        if not answers:
            logging.warning(
                f"题目 {question_data['index']+1}: 没有获取到有效答案，随机选择第一个选项"
            )
            # 如果没有获取到答案，选择第一个选项
            try:
                # 定位到当前题目区域内的第一个选项
                selector = (
                    f"[data-dynamic-key='{item_id}'] .preview-list dd:first-child"
                )
                await page.locator(selector).click(timeout=2000)
                logging.info(f"题目 {question_data['index']+1}: 已点击第一个选项")
            except Exception as e:
                logging.error(
                    f"题目 {question_data['index']+1}: 点击第一个选项失败: {e}"
                )
                # 尝试使用JavaScript点击
                try:
                    await page.evaluate(
                        f"""
                        (function() {{
                            const questionItem = document.querySelector("[data-dynamic-key='{item_id}']");
                            if (!questionItem) return false;
                            const firstOption = questionItem.querySelector(".preview-list dd");
                            if (!firstOption) return false;
                            firstOption.click();
                            return true;
                        }})()
                    """
                    )
                    logging.info(
                        f"题目 {question_data['index']+1}: 已使用JavaScript点击第一个选项"
                    )
                except Exception as js_e:
                    logging.error(
                        f"题目 {question_data['index']+1}: JavaScript点击第一个选项失败: {js_e}"
                    )
            return

        logging.info(f"题目 {question_data['index']+1}: 选择答案: {answers}")

        if question_data["type"] == "judge":
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
                # 尝试使用JavaScript点击
                try:
                    await page.evaluate(
                        f"""
                        (function() {{
                            const questionItem = document.querySelector("[data-dynamic-key='{item_id}']");
                            if (!questionItem) return false;
                            const options = questionItem.querySelectorAll(".preview-list dd");
                            if (!options || options.length <= {answer_index}) return false;
                            options[{answer_index}].click();
                            return true;
                        }})()
                    """
                    )
                    logging.info(
                        f"题目 {question_data['index']+1}: 已使用JavaScript点击判断题选项: {answers[0]}"
                    )
                except Exception as js_e:
                    logging.error(
                        f"题目 {question_data['index']+1}: JavaScript点击判断题选项失败: {js_e}"
                    )

        elif question_data["type"] == "single":
            # 单选题选择逻辑
            answer = answers[0]  # 单选题只取第一个答案
            option_index = ord(answer) - ord("A")

            if 0 <= option_index < len(question_data["options"]):
                try:
                    selector = f"[data-dynamic-key='{item_id}'] .preview-list dd:nth-child({option_index + 1})"
                    await page.locator(selector).click(timeout=2000)
                    logging.info(
                        f"题目 {question_data['index']+1}: 已点击单选题选项: {answer}"
                    )
                except Exception as e:
                    logging.warning(
                        f"题目 {question_data['index']+1}: 点击选项 {answer} 失败: {e}"
                    )
                    # 尝试使用JavaScript点击
                    try:
                        await page.evaluate(
                            f"""
                            (function() {{
                                const questionItem = document.querySelector("[data-dynamic-key='{item_id}']");
                                if (!questionItem) return false;
                                const options = questionItem.querySelectorAll(".preview-list dd");
                                if (!options || options.length <= {option_index}) return false;
                                options[{option_index}].click();
                                return true;
                            }})()
                        """
                        )
                        logging.info(
                            f"题目 {question_data['index']+1}: 已使用JavaScript点击单选题选项: {answer}"
                        )
                    except Exception as js_e:
                        logging.error(
                            f"题目 {question_data['index']+1}: JavaScript点击单选题选项失败: {js_e}"
                        )

                        # 尝试通过ID直接点击
                        try:
                            # 获取选项的ID
                            dd_id = await page.evaluate(
                                f"""
                                (function() {{
                                    const questionItem = document.querySelector("[data-dynamic-key='{item_id}']");
                                    if (!questionItem) return null;
                                    const options = questionItem.querySelectorAll(".preview-list dd");
                                    if (!options || options.length <= {option_index}) return null;
                                    return options[{option_index}].id;
                                }})()
                            """
                            )

                            if dd_id:
                                await page.locator(f"#{dd_id}").click(timeout=2000)
                                logging.info(
                                    f"题目 {question_data['index']+1}: 已通过ID点击单选题选项: {answer}"
                                )
                        except Exception as id_e:
                            logging.error(
                                f"题目 {question_data['index']+1}: 通过ID点击单选题选项失败: {id_e}"
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
                        # 尝试使用JavaScript点击
                        try:
                            await page.evaluate(
                                f"""
                                (function() {{
                                    const questionItem = document.querySelector("[data-dynamic-key='{item_id}']");
                                    if (!questionItem) return false;
                                    const options = questionItem.querySelectorAll(".preview-list dd");
                                    if (!options || options.length <= {option_index}) return false;
                                    options[{option_index}].click();
                                    return true;
                                }})()
                            """
                            )
                            logging.info(
                                f"题目 {question_data['index']+1}: 已使用JavaScript点击多选题选项: {answer}"
                            )
                            await page.wait_for_timeout(300)
                        except Exception as js_e:
                            logging.error(
                                f"题目 {question_data['index']+1}: JavaScript点击多选题选项失败: {js_e}"
                            )

                            # 尝试通过元素ID直接点击
                            try:
                                # 获取选项的ID
                                dd_id = await page.evaluate(
                                    f"""
                                    (function() {{
                                        const questionItem = document.querySelector("[data-dynamic-key='{item_id}']");
                                        if (!questionItem) return null;
                                        const options = questionItem.querySelectorAll(".preview-list dd");
                                        if (!options || options.length <= {option_index}) return null;
                                        return options[{option_index}].id;
                                    }})()
                                """
                                )

                                if dd_id:
                                    await page.locator(f"#{dd_id}").click(timeout=2000)
                                    logging.info(
                                        f"题目 {question_data['index']+1}: 已通过ID点击多选题选项: {answer}"
                                    )
                            except Exception as id_e:
                                logging.error(
                                    f"题目 {question_data['index']+1}: 通过ID点击多选题选项失败: {id_e}"
                                )
    except Exception as e:
        logging.error(f"题目 {question_data['index']+1}: 选择答案出错: {e}")
        import traceback

        logging.error(traceback.format_exc())


async def get_ai_answers(question_data, is_thinking):
    """使用AI分析题目并获取答案 - 适配百炼API的流式输出和思考过程"""
    try:
        # 构建提示
        question_type_str = ""
        if question_data["type"] == "single":
            question_type_str = "单选题"
        elif question_data["type"] == "multiple":
            question_type_str = "多选题"
        elif question_data["type"] == "judge":
            question_type_str = "判断题（请回答'正确'或'错误'）"

        options_str = ""
        for option in question_data["options"]:
            options_str += f"{option['label']}. {option['text']}\n"

        prompt = f"""
        请回答以下{question_type_str}：
        
        问题：{question_data['text']}
        
        选项：
        {options_str}
        
        {"请直接回答选项代号（如A、B、C、D），多选题可以选择多个选项" if question_data["type"] != "judge" else "请直接回答'正确'或'错误'"}。
        """

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
        else:
            # 处理选择题答案 - 提取所有的A、B、C、D
            pattern = r"[ABCD]"
            answers = re.findall(pattern, final_answer)

            # 去重但保持顺序
            seen = set()
            answers = [x for x in answers if not (x in seen or seen.add(x))]

            logging.info(f"提取的答案选项: {answers}")
            return answers
    except Exception as e:
        logging.error(f"获取AI答案出错: {e}")
        import traceback

        logging.error(traceback.format_exc())
        return []


async def detect_exam_mode(page):
    """检测考试模式：根据是否存在下一题按钮来判断"""
    try:
        # 检查是否存在"下一题"按钮，这是单题目模式的特征
        single_btns = page.locator(".single-btns")
        await single_btns.wait_for(state="visible", timeout=3000)

        if await single_btns.count() > 0:
            logging.info("检测为单题目模式（有下一题按钮）")
            return "single"
        else:
            logging.info("检测为多题目模式（无下一题按钮）")
            return "multi"
    except Exception as e:
        logging.error(f"检测考试模式出错: {e}")
        return "single"  # 默认单题目模式


async def ai_exam(page, is_thinking):
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
            question_data = await extract_question_data(page)
            if not question_data:
                logging.error("无法提取题目信息")
                break

            logging.info(f"当前题目: {question_data['text']}")
            logging.info(f"题目类型: {question_data['type']}")

            # 使用AI分析题目并获取答案
            answers = await get_ai_answers(question_data, is_thinking)

            # 根据题目类型和AI答案点击选项
            await select_answers(page, question_data, answers)

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
        all_questions = await extract_all_questions_data(page)
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
            answers = await get_ai_answers(question_data, is_thinking)

            # 根据题目类型和AI答案点击选项
            await select_answer_for_question_multi(page, question_data, answers)

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
            try:
                # 尝试使用JavaScript点击
                await page.evaluate(
                    """
                    (function() {
                        const submitBtn = Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes('我要交卷'));
                        if (submitBtn) {
                            submitBtn.click();
                            return true;
                        }
                        return false;
                    })()
                """
                )
                await page.wait_for_timeout(1000)
                await page.evaluate(
                    """
                    (function() {
                        const confirmBtn = Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes('确 定'));
                        if (confirmBtn) {
                            confirmBtn.click();
                            return true;
                        }
                        return false;
                    })()
                """
                )
                await page.wait_for_timeout(1000)
                await page.evaluate(
                    """
                    (function() {
                        const finalBtn = Array.from(document.querySelectorAll('button')).find(el => el.textContent.includes('确定'));
                        if (finalBtn) {
                            finalBtn.click();
                            return true;
                        }
                        return false;
                    })()
                """
                )
            except Exception as js_e:
                logging.error(f"JavaScript点击交卷按钮失败: {js_e}")

    logging.info("考试完成")


# 其余函数保持不变
async def wait_for_finish_test(page1, is_thinking=False):
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    await ai_exam(page2, is_thinking)
    await page2.wait_for_event("close", timeout=0)


async def main():
    with open("./学习课程考试链接.txt", encoding="utf-8") as f:
        urls = f.readlines()

    # Load the cookies
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

            while True:
                await page1.locator(".top").first.wait_for(timeout=3000)
                await page1.locator(".top").first.click()
                await page1.locator('dl.chapter-list-box[data-sectiontype="9"]').click()
                await page1.locator(".tab-container").wait_for()
                await page1.wait_for_timeout(1000)

                # 如果为限定次数的考试，则纳入人工考试
                exam_button_locator = page1.locator(".btn.new-radius")
                # 如果存在考试按钮, 判定是否为限定次数的考试
                if await exam_button_locator.count() > 0:
                    button_text = await exam_button_locator.inner_text()
                    if "剩余" in button_text:
                        logging.info("当前为限定次数的考试")
                        fm.save_to_file("./人工考试链接.txt", url.strip())
                        await page1.close()
                        break

                # AI考试
                # 如果存在考试记录
                if await page1.locator(".neer-status").count() > 0:
                    if await fm.check_exam_passed(page1):
                        await page1.close()
                        is_thinking = False
                        break
                    # AI考试未通过，尝试试用推理模式
                    else:
                        if is_thinking:
                            logging.info("AI考试未通过，使用人工模式重新考试")
                            fm.save_to_file("./人工考试链接.txt", url.strip())
                            is_thinking = False
                            await page1.close()
                            break
                        else:
                            is_thinking = True
                            logging.info("使用推理模式重新考试")
                            await wait_for_finish_test(page1, is_thinking)
                            await page1.reload(wait_until="load")
                            await page1.wait_for_timeout(1500)
                            # 如果存在评价窗口, 则点击评价按钮
                            if await fm.handle_rating_popup(page1):
                                logging.info("五星评价完成")
                            continue
                else:
                    logging.info("开始考试")
                    await wait_for_finish_test(page1, is_thinking)
                    await page1.reload(wait_until="load")
                    await page1.wait_for_timeout(1500)
                    # 如果存在评价窗口, 则点击评价按钮
                    if await fm.handle_rating_popup(page1):
                        logging.info("五星评价完成")
                    continue

        await context.close()
        await browser.close()
        logging.info(f"\n考试完成, 当前时间为{time.ctime()}\n")
        os.remove("./学习课程考试链接.txt")


if __name__ == "__main__":
    asyncio.run(main())
