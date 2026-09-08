from __future__ import annotations

import logging
import json
from core.abort import UserCancelRequested
from core.exam.contracts import valid_answers
from core.runtime import close_safely

from core.exam.actions import close_exam_notice_if_present, select_answers, submit_exam
from core.exam.answers import get_ai_answers
from core.exam.parsing import (
    detect_exam_mode,
    extract_multi_questions_data,
    extract_single_question_data,
)

MANUAL_SUBMIT_RESULT_CLOSE_SELECTOR = (
    "[data-region='modal:modal'] .btn.white.border:has-text('确定')"
)
QUESTION_EXTRACTION_ATTEMPTS = 3
QUESTION_EXTRACTION_RETRY_MS = 750
EXAM_NETWORK_IDLE_TIMEOUT_MS = 3000


class ExamQuestionExtractionError(RuntimeError):
    """答题页已打开，但题目 DOM 在重试后仍无法解析。"""

    def __init__(self, message: str, *, page=None):
        super().__init__(message)
        self.page = page


def _log_question_snapshot(question_data, *, index: int | None = None) -> None:
    logging.info("处理题目 %s，题型 %s，选项数 %s", question_data.get("item_id", index or "single"), question_data.get("type"), len(question_data.get("options") or []))


def _should_disable_auto_submit(question_data, answers) -> bool:
    return not valid_answers(question_data, answers)


def _ensure_manual_submit(auto_submit: bool, question_data, answers) -> bool:
    if auto_submit and _should_disable_auto_submit(question_data, answers):
        logging.info("检测到需要人工处理的题目，已自动切换为手动交卷")
        return False
    return auto_submit


def _page_is_closed(page) -> bool:
    checker = getattr(page, "is_closed", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except Exception:
        return False


async def _wait_for_manual_submit_completion(page) -> None:
    while True:
        if _page_is_closed(page):
            raise UserCancelRequested("考试页面已关闭，未确认交卷，已保留待办")

        try:
            close_button = page.locator(MANUAL_SUBMIT_RESULT_CLOSE_SELECTOR)
            if await close_button.count() > 0 and await close_button.last.is_visible():
                logging.info("检测到交卷结果弹窗, 准备关闭")
                await close_button.last.click()
                await page.wait_for_timeout(500)
                return
        except Exception as exc:
            if _page_is_closed(page):
                raise UserCancelRequested("考试页面已关闭，未确认交卷，已保留待办") from None
            logging.debug(f"等待手动交卷完成时检查结果弹窗失败: {exc}")

        await page.wait_for_timeout(500)


async def _wait_for_exam_page_stable(page) -> None:
    """尽量等待请求稳定；考试心跳/自动保存可能使 networkidle 永不满足。"""
    try:
        await page.wait_for_load_state(
            "networkidle", timeout=EXAM_NETWORK_IDLE_TIMEOUT_MS
        )
    except Exception as exc:
        logging.debug(f"考试页在 3 秒内未达到 networkidle，按已就绪 DOM 继续: {exc}")


async def _extract_with_retry(page, extractor, *, empty_message: str):
    for attempt in range(1, QUESTION_EXTRACTION_ATTEMPTS + 1):
        result = await extractor(page)
        if result:
            return result
        if attempt < QUESTION_EXTRACTION_ATTEMPTS:
            logging.warning(
                f"{empty_message}，等待页面更新后重试 "
                f"({attempt}/{QUESTION_EXTRACTION_ATTEMPTS})"
            )
            await page.wait_for_timeout(QUESTION_EXTRACTION_RETRY_MS)
    raise ExamQuestionExtractionError(empty_message, page=page)


async def ai_exam(client, model, page, course_url, auto_submit=True, ai_model_config=None):
    """AI自动答题主函数"""
    logging.info("AI考试开始")

    await _wait_for_exam_page_stable(page)
    await page.wait_for_timeout(1000)
    await close_exam_notice_if_present(page)
    await _wait_for_exam_page_stable(page)
    await page.wait_for_timeout(1000)

    exam_mode = await detect_exam_mode(page)

    if exam_mode == "single":
        # Without an authoritative question manifest, opening mid-paper cannot
        # prove that earlier questions were handled. Keep final submission manual.
        if auto_submit:
            logging.info("单题导航模式无法核实整卷题目清单，改为人工确认交卷")
            auto_submit = False
        seen_questions = set()
        while True:
            await _wait_for_exam_page_stable(page)
            await page.wait_for_timeout(1000)

            question_data = await _extract_with_retry(
                page,
                extract_single_question_data,
                empty_message="无法提取当前题目信息",
            )

            logging.info(f"题目类型: {question_data['type']}")
            _log_question_snapshot(question_data)

            identity = json.dumps([question_data.get("item_id"), question_data["text"], question_data.get("options")], ensure_ascii=False, sort_keys=True)
            if identity in seen_questions or len(seen_questions) >= 500:
                raise ExamQuestionExtractionError("题目导航未推进或超出题数上限，停止自动答题", page=page)
            seen_questions.add(identity)
            answers = await get_ai_answers(client, model, question_data)
            await select_answers(
                page,
                question_data,
                answers,
                course_url,
                ai_model_config=ai_model_config,
            )
            next_button = page.locator(".single-btn-next")
            next_button_classes = await next_button.get_attribute("class") or ""

            if "next-disabled" in next_button_classes:
                logging.info("自动交卷已取消, 请手动交卷")
                logging.info("页面将保持打开状态, 等待手动交卷完成...")
                await _wait_for_manual_submit_completion(page)
                break

            logging.info("点击下一题")
            await next_button.click()
            # 每题的间隔天然随机：get_ai_answers 的模型思考耗时本身就在抖动，
            # 不必再叠加固定区间的停顿。
            await page.wait_for_timeout(1000)
    else:
        await _wait_for_exam_page_stable(page)
        await page.wait_for_timeout(1000)

        all_questions = await _extract_with_retry(
            page,
            extract_multi_questions_data,
            empty_message="无法提取任何题目信息",
        )

        logging.info(f"本页共有 {len(all_questions)} 道题目")
        for question_data in all_questions:
            question_number = question_data["index"] + 1
            logging.info(f"题目 {question_number} 类型: {question_data['type']}")
            _log_question_snapshot(question_data, index=question_number)
            answers = await get_ai_answers(client, model, question_data)
            auto_submit = _ensure_manual_submit(auto_submit, question_data, answers)
            item_id = question_data["item_id"]
            selected_successfully = await select_answers(
                page,
                question_data,
                answers,
                course_url,
                selector_prefix=f"[data-dynamic-key={json.dumps(item_id)}] ",
                ai_model_config=ai_model_config,
            )
            auto_submit = _ensure_manual_submit(
                auto_submit,
                question_data,
                answers if selected_successfully else [],
            )
            await page.wait_for_timeout(500)

        if auto_submit:
            await submit_exam(page)
        else:
            logging.info("自动交卷已取消, 请手动交卷")
            logging.info("页面将保持打开状态, 等待手动交卷完成...")
            await _wait_for_manual_submit_completion(page)

    logging.info("已检测到交卷结果，等待服务端状态核对")


async def wait_for_finish_test(client, model, page1, auto_submit=True, ai_model_config=None):
    """打开考试弹窗并执行AI考试"""
    async with page1.expect_popup() as page2_info:
        await page1.locator(".btn.new-radius").click()
    page2 = await page2_info.value
    logging.info("等待作答完毕并关闭页面")
    try:
        await ai_exam(
            client,
            model,
            page2,
            page1.url,
            auto_submit=auto_submit,
            ai_model_config=ai_model_config,
        )
    finally:
        if not _page_is_closed(page2):
            await close_safely(page2.close(), label="answer page")
