from __future__ import annotations

import logging
import traceback

from core.config import MANUAL_EXAM_FILE
from core.file_ops import save_to_file


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
            save_to_file(MANUAL_EXAM_FILE, course_url)
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
            except Exception as exc:
                logging.warning(f"{log_prefix}输入排序顺序失败: {exc}")
            return

        if question_data["type"] == "judge":
            answer_index = 0 if answers[0] == "正确" else 1
            try:
                selector = (
                    f"{selector_prefix}.preview-list dd:nth-child({answer_index + 1})"
                )
                await page.locator(selector).click(timeout=2000)
                logging.info(f"{log_prefix}已点击判断题选项: {answers[0]}")
            except Exception as exc:
                logging.warning(f"{log_prefix}点击判断题选项失败: {exc}")
            return

        if question_data["type"] == "single" and selector_prefix:
            answer = answers[0]
            option_index = ord(answer) - ord("A")
            if 0 <= option_index < len(question_data["options"]):
                try:
                    selector = f"{selector_prefix}.preview-list dd:nth-child({option_index + 1})"
                    await page.locator(selector).first.click(timeout=2000)
                    logging.info(f"{log_prefix}已点击单选题选项: {answer}")
                except Exception as exc:
                    logging.warning(f"{log_prefix}点击选项 {answer} 失败: {exc}")
            return

        for answer in answers:
            option_index = ord(answer) - ord("A")
            if 0 <= option_index < len(question_data["options"]):
                try:
                    selector = f"{selector_prefix}.preview-list dd:nth-child({option_index + 1})"
                    await page.locator(selector).first.click(timeout=2000)
                    logging.info(f"{log_prefix}已点击选项: {answer}")
                    await page.wait_for_timeout(300)
                except Exception as exc:
                    logging.warning(f"{log_prefix}点击选项 {answer} 失败: {exc}")
    except Exception as exc:
        logging.error(f"选择答案出错: {exc}")
        logging.error(traceback.format_exc())


async def close_exam_notice_if_present(page):
    try:
        popup = page.locator(".dialog.animated")
        if await popup.count() > 0:
            logging.info("检测到考试提示弹窗, 准备关闭")
            await popup.locator(".dialog-footer .btn").first.click()
            await page.wait_for_timeout(1000)
            logging.info("弹窗已关闭")
        else:
            logging.info("未检测到考试提示弹窗")
    except Exception as exc:
        logging.error(f"处理考试提示弹窗时出错: {exc}")
        await page.wait_for_timeout(2000)


async def submit_exam(page):
    await page.locator("text=我要交卷").click()
    await page.wait_for_timeout(1000)
    await page.locator("button:has-text('确 定')").click()
    await page.wait_for_timeout(1000)
    await page.locator("text=确定").click()
