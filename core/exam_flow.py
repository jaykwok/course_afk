from __future__ import annotations

import logging

from core.exam_actions import close_exam_notice_if_present, select_answers, submit_exam
from core.exam_answers import get_ai_answers
from core.exam_parsing import (
    detect_exam_mode,
    extract_multi_questions_data,
    extract_single_question_data,
)


def _format_question_options(question_data) -> str:
    options = question_data.get("options") or []
    formatted_options = []
    for option in options:
        label = str(option.get("label", "")).strip()
        text = str(option.get("text", "")).strip()
        if label and text:
            formatted_options.append(f"{label}. {text}")
        elif text:
            formatted_options.append(text)
        elif label:
            formatted_options.append(label)
    return "\n".join(formatted_options) if formatted_options else "无"


def _log_question_snapshot(question_data, *, index: int | None = None) -> None:
    option_prefix = "题目选项" if index is None else f"题目 {index} 选项"
    logging.info(f"{option_prefix}:\n{_format_question_options(question_data)}")


async def ai_exam(client, model, page, course_url, auto_submit=True):
    """AI自动答题主函数"""
    logging.info("AI考试开始")

    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)
    await close_exam_notice_if_present(page)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(1000)

    exam_mode = await detect_exam_mode(page)

    if exam_mode == "single":
        while True:
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)

            question_data = await extract_single_question_data(page)
            if not question_data:
                logging.error("无法提取题目信息")
                break

            logging.info(f"当前题目: {question_data['text']}")
            logging.info(f"题目类型: {question_data['type']}")
            _log_question_snapshot(question_data)

            answers = await get_ai_answers(client, model, question_data)
            await select_answers(page, question_data, answers, course_url)

            next_button = page.locator(".single-btn-next")
            next_button_classes = await next_button.get_attribute("class") or ""

            if "next-disabled" in next_button_classes:
                if auto_submit:
                    logging.info("已经是最后一题, 准备交卷")
                    await submit_exam(page)
                else:
                    logging.info("自动交卷已取消, 请手动交卷")
                    logging.info("页面将保持打开状态, 等待手动操作...")
                    await page.wait_for_event("close", timeout=0)
                break

            logging.info("点击下一题")
            await next_button.click()
            await page.wait_for_timeout(1000)
    else:
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        all_questions = await extract_multi_questions_data(page)
        if not all_questions:
            logging.error("无法提取任何题目信息")
            return

        logging.info(f"本页共有 {len(all_questions)} 道题目")
        for question_data in all_questions:
            question_number = question_data["index"] + 1
            logging.info(f"处理题目 {question_number}: {question_data['text']}")
            logging.info(f"题目 {question_number} 类型: {question_data['type']}")
            _log_question_snapshot(question_data, index=question_number)
            answers = await get_ai_answers(client, model, question_data)
            item_id = question_data["item_id"]
            await select_answers(
                page,
                question_data,
                answers,
                course_url,
                selector_prefix=f"[data-dynamic-key='{item_id}'] ",
            )
            await page.wait_for_timeout(500)

        if auto_submit:
            try:
                await submit_exam(page)
            except Exception as exc:
                logging.error(f"点击交卷按钮失败: {exc}")
        else:
            logging.info("自动交卷已取消, 请手动交卷")
            logging.info("页面将保持打开状态, 等待手动操作...")
            await page.wait_for_event("close", timeout=0)

    logging.info("考试完成")


async def wait_for_finish_test(client, model, page1):
    """打开考试弹窗并执行AI考试"""
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    await ai_exam(client, model, page2, page1.url)
    await page2.wait_for_event("close", timeout=0)
