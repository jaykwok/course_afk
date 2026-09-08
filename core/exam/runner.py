from __future__ import annotations

import asyncio
import logging
import hashlib
from typing import Callable

from openai import AsyncOpenAI
from playwright.async_api import Locator
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from core.abort import UserAbortRequested, UserCancelRequested
from core.browser.session import (
    create_browser_context,
    get_page_context,
    is_target_closed_exception,
)
from core.config import (
    COURSE_EXAM_ATTEMPT_THRESHOLD,
    EXAM_URLS_FILE,
    MANUAL_EXAM_FILE,
    PAPER_EXAM_ATTEMPT_THRESHOLD,
    ZHIXUEYUN_COURSE_PREFIX,
    ZHIXUEYUN_EXAM_PREFIX,
    ZHIXUEYUN_SUBJECT_PREFIX,
)
from core.exam.flow import ExamQuestionExtractionError, ai_exam, wait_for_finish_test
from core.exam.answers import ExamAiConfigurationError
from core.exam.settings import AiSettings
from core.runtime import close_safely
from core.exam.rules import (
    extract_attempt_limit_message as _extract_attempt_limit_message,
    parse_remaining_attempts,
    explicitly_unlimited,
)
from core.exam.routing import queue_exam_url_by_attempt_text
from core.file_ops import normalize_url
from core.queues.exam import (
    has_ai_failed_model_config,
    read_exam_urls,
    record_ai_failed_model_config,
    remove_exam_url,
)
from core.learning.exam_bridge import get_course_exam_outcome
from core.learning.exam_api import read_exam_state
from core.queues.history import record_submission_intent, pending_submission, finish_submission
from core.auth.credential import load_credential_metadata
from core.exam.flow import _wait_for_manual_submit_completion
from core.learning.popups import handle_rating_popup
from core.queues.manual_exam import (
    append_manual_exam_entry,
    read_manual_exam_queue,
    write_manual_exam_queue,
)
StatusCallback = Callable[[str], None]

COURSE_EXAM_BUTTON = ".btn.new-radius"
PAPER_EXAM_BUTTONS = [
    ".banner-handler-btn.themeColor-border-color.themeColor-background-color",
    "button:has-text('开始考试')",
    "button:has-text('继续考试')",
    "button:has-text('去考试')",
    "a:has-text('开始考试')",
    "a:has-text('继续考试')",
    "a:has-text('去考试')",
    ".btn.new-radius",
]

LOGIN_REDIRECT_TIMEOUT_MS = 120000
LOGIN_REDIRECT_POLL_MS = 500


def classify_exam_entry_url(url: str) -> str:
    """按标准 hash 路由区分考试入口，避免普通查询参数误命中。"""
    normalized = normalize_url(url)
    if normalized.startswith(ZHIXUEYUN_EXAM_PREFIX):
        return "exam"
    if normalized.startswith(ZHIXUEYUN_COURSE_PREFIX):
        return "course"
    if normalized.startswith(ZHIXUEYUN_SUBJECT_PREFIX):
        return "subject"
    return "unknown"


async def _locate_exam_button(page) -> Locator | None:
    """按入口语义定位开考按钮，兼容不同试卷页布局。"""
    for selector in PAPER_EXAM_BUTTONS:
        try:
            button = page.locator(selector)
            count = await button.count()
            if count > 0:
                for i in range(min(count, 5)):
                    candidate = button.nth(i)
                    if await candidate.is_visible():
                        return candidate
        except Exception:
            continue
    return None


async def _has_authorization_cookie(page) -> bool:
    context = get_page_context(page)
    if context is None:
        return False
    try:
        cookies = await context.cookies()
    except Exception:
        return False
    return any(
        str(cookie.get("name", "")).strip().lower() == "authorization"
        for cookie in cookies
    )


async def _has_ready_answer_question(page) -> bool:
    """确认至少一道题的题型和题干均已挂载，排除空壳/登录页。"""
    try:
        items = page.locator(".question-type-item")
        count = await items.count()
        for index in range(min(count, 3)):
            item = items.nth(index)
            score = item.locator(".o-score")
            if await score.count() <= 0 or not (await score.last.inner_text()).strip():
                continue
            for selector in (".stem-content-main", ".single-title .rich-text-style"):
                question = item.locator(selector)
                if await question.count() > 0 and (await question.first.inner_text()).strip():
                    return True

        # 单题模式部分版本没有 question-type-item 外壳，使用解析器同款全局选择器。
        score = page.locator(".o-score")
        question = page.locator(".single-title .rich-text-style")
        if (
            await score.count() > 0
            and (await score.last.inner_text()).strip()
            and await question.count() > 0
            and (await question.first.inner_text()).strip()
        ):
            return True
    except Exception:
        return False
    return False


async def _is_paper_entry_ready(page) -> bool:
    if await _has_ready_answer_question(page):
        return True
    if await _locate_exam_button(page) is not None:
        return True
    return await _get_paper_attempt_limit_message(page) is not None


async def _wait_for_target_route_after_auth(
    page,
    target_url: str,
    *,
    timeout_ms: int = LOGIN_REDIRECT_TIMEOUT_MS,
    interval_ms: int = LOGIN_REDIRECT_POLL_MS,
) -> bool:
    """等待 OAuth 完成且原考试路由的可用 DOM 已稳定挂载。

    自动认证有绝对期限；人工答题等待另行处理，不能让登录无限挂起。
    """
    expected_url = normalize_url(target_url)
    elapsed = 0
    observed_external_route = False
    timeout_ms = max(1, timeout_ms)
    interval_ms = max(1, interval_ms)
    logging.info("等待登录授权完成并加载考试页面（最多 %g 秒）", timeout_ms / 1000)
    async def wait_ready():
        nonlocal elapsed, observed_external_route
        while elapsed < timeout_ms:
            if await check_ready():
                return True
            wait_ms = min(interval_ms, timeout_ms - elapsed)
            await page.wait_for_timeout(wait_ms)
            elapsed += wait_ms
        return False

    async def check_ready():
        nonlocal observed_external_route
        current_url = normalize_url(str(getattr(page, "url", "") or ""))
        if current_url != expected_url:
            observed_external_route = True
            return False
        auth_completed = observed_external_route or await _has_authorization_cookie(page)
        if not auth_completed or not await _is_paper_entry_ready(page):
            return False
        logging.info("登录授权已完成，考试页面内容已就绪")
        return True

    try:
        async with asyncio.timeout(timeout_ms / 1000):
            return await wait_ready()
    except TimeoutError:
        return False


async def _raise_if_login_required(page, target_url: str) -> None:
    if not await _wait_for_target_route_after_auth(page, target_url):
        raise UserCancelRequested(
            "考试链接进入登录页后未完成授权并加载考试内容；"
            "已保留当前及剩余考试链接，请先更新登录凭证后重试"
        )


async def _open_paper_answer_page(page, exam_button, *, popup_timeout_ms: int = 5000):
    """点击开考按钮，兼容新窗口和当前页两种答题页打开方式。"""
    try:
        async with page.expect_popup(timeout=popup_timeout_ms) as popup_info:
            await exam_button.click()
        return await popup_info.value
    except PlaywrightTimeoutError:
        if await _is_direct_answer_paper_page(page):
            logging.info("开考后在当前页面进入答题页")
            return page
        raise


def _build_exam_client() -> tuple[AsyncOpenAI, str]:
    settings = AiSettings.load()
    client = AsyncOpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.request_timeout, max_retries=0)
    client._course_afk_settings = settings
    return client, settings.model


def _current_account() -> str:
    metadata = load_credential_metadata()
    identity = (metadata.account_name or metadata.account_label) if metadata else "unbound"
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def _build_ai_exam_model_config(model: str, client=None) -> dict[str, object]:
    settings = getattr(client, "_course_afk_settings", None) or AiSettings.load()
    return {**settings.fingerprint(), "model": model, "account": _current_account()}


async def _is_direct_answer_paper_page(page) -> bool:
    elapsed = 0
    while elapsed < 5000:
        if await _has_ready_answer_question(page):
            return True
        await page.wait_for_timeout(250)
        elapsed += 250
    return False


async def _get_paper_attempt_limit_message(page) -> str | None:
    for selector in ("[data-region='modal:modal']", "body"):
        try:
            locator = page.locator(selector)
            if await locator.count() <= 0:
                continue
            text = (await locator.first.inner_text()).strip()
        except Exception:
            continue
        message = _extract_attempt_limit_message(text)
        if message:
            return message
    return None


async def _handle_attempt_limit_if_present(page, url: str) -> bool:
    attempt_limit_message = await _get_paper_attempt_limit_message(page)
    if not attempt_limit_message:
        return False

    queue_exam_url_by_attempt_text(
        url,
        attempt_limit_message,
        threshold=PAPER_EXAM_ATTEMPT_THRESHOLD,
        exam_file=EXAM_URLS_FILE,
        manual_exam_file=MANUAL_EXAM_FILE,
    )
    return True




async def _can_continue_ai_exam(
    button_locator,
    *,
    threshold: int,
    url: str,
) -> bool:
    button_text = await button_locator.inner_text()
    if explicitly_unlimited(button_text):
        logging.info("不限制考试次数, 继续 AI 自动考试")
        return True

    remaining = parse_remaining_attempts(button_text)
    if remaining is None:
        queue_exam_url_by_attempt_text(
            url,
            button_text,
            threshold=threshold,
            exam_file=EXAM_URLS_FILE,
            manual_exam_file=MANUAL_EXAM_FILE,
        )
        return False

    if remaining <= threshold:
        queue_exam_url_by_attempt_text(
            url,
            button_text,
            threshold=threshold,
            exam_file=EXAM_URLS_FILE,
            manual_exam_file=MANUAL_EXAM_FILE,
        )
        return False

    logging.info(f"当前考试剩余次数为 {remaining}, 大于 {threshold} 次, 继续 AI 自动考试")
    return True


async def _open_course_exam_tab(page) -> None:
    await page.locator(".top").first.wait_for(timeout=5000)
    await page.locator(".top").first.click()
    await page.locator('dl.chapter-list-box[data-sectiontype="9"]').click()
    await page.locator(".tab-container").wait_for()
    await page.wait_for_timeout(1000)


async def _handle_exam_result(page) -> None:
    # 考试结果页勿跑通用顶层关闭：交卷确认/结果弹窗可能被误关
    await page.reload(wait_until="load")
    await page.wait_for_timeout(1500)
    if await handle_rating_popup(page):
        logging.info("五星评价完成")


async def _close_page_safely(page) -> None:
    if page is None:
        return
    await close_safely(page.close(), label="exam page")


def _to_manual(url: str, reason: str, message: str, model_config=None) -> bool:
    """目标先落盘；调用方随后删除 AI 待办，崩溃窗口只允许重复，不允许丢失。"""
    if reason == "ai_failed" and model_config:
        record_ai_failed_model_config(url, model_config, file_path=EXAM_URLS_FILE)
    append_manual_exam_entry(url, reason=reason, reason_text=message,
        ai_failed_model_config=model_config if reason == "ai_failed" else None,
        file_path=MANUAL_EXAM_FILE)
    return True


async def _paper_state(page, url):
    exam_id = url.split(ZHIXUEYUN_EXAM_PREFIX, 1)[-1].split("?")[0].split("/")[0]
    try:
        return await read_exam_state(page, exam_id)
    except Exception as exc:
        if is_target_closed_exception(exc):
            raise
        logging.warning("试卷结果无法核对（%s）", type(exc).__name__)
        return None


def _finish_ai_outcome(url, outcome, model_config) -> bool:
    if outcome == "passed":
        finish_submission(url, "verified", EXAM_URLS_FILE, account=model_config["account"])
        return True
    if outcome == "pending_grading":
        _to_manual(url, "pending_grading", "已提交，等待服务端评卷后复查")
        finish_submission(url, "pending_grading", EXAM_URLS_FILE, account=model_config["account"])
        return True
    if outcome == "failed":
        _to_manual(url, "ai_failed", "本次已交卷但未通过，转人工处理", model_config)
        finish_submission(url, "failed", EXAM_URLS_FILE, account=model_config["account"])
        return True
    return _to_manual(url, "submission_unverified", "交卷结果尚未确认，请核对考试记录；禁止自动重考")


async def _run_course_ai_exam(page, url: str, client: AsyncOpenAI, model: str, *, auto_submit: bool = True) -> bool:
    model_config = _build_ai_exam_model_config(model, client)
    await _open_course_exam_tab(page)
    outcome = await get_course_exam_outcome(page)
    if outcome in {"passed", "pending_grading"}:
        return _finish_ai_outcome(url, outcome, model_config)
    if pending_submission(url, EXAM_URLS_FILE, account=model_config["account"]):
        # 没有可靠的新旧记录 ID 时，不用旧失败分数证明这次已经交卷。
        return _to_manual(url, "submission_unverified", "发现上次未确认的提交，请先人工核对考试记录")
    button = page.locator(COURSE_EXAM_BUTTON)
    if await button.count() == 0:
        return _to_manual(url, "attempt_unknown", "未找到可用的开考入口")
    if not await _can_continue_ai_exam(button, threshold=COURSE_EXAM_ATTEMPT_THRESHOLD, url=url):
        return True
    # 在开始任何答题操作前提交意图，覆盖手动提前交卷和强制退出的窗口。
    record_submission_intent(url, model_config, EXAM_URLS_FILE)
    await wait_for_finish_test(client, model, page, auto_submit=auto_submit, ai_model_config=model_config)
    await _handle_exam_result(page)
    await _open_course_exam_tab(page)
    outcome = await get_course_exam_outcome(page)
    # DOM 无记录身份，失败结果也可能仍是上次记录；保守转人工核对。
    if outcome == "failed":
        outcome = "unknown"
    return _finish_ai_outcome(url, outcome, model_config)


async def _run_paper_ai_exam(page, url: str, client: AsyncOpenAI, model: str, *, auto_submit: bool = True) -> bool:
    model_config = _build_ai_exam_model_config(model, client)
    await _raise_if_login_required(page, url)
    before = await _paper_state(page, url)
    if before and before.outcome in {"passed", "pending_grading"}:
        return _finish_ai_outcome(url, before.outcome, model_config)
    if pending_submission(url, EXAM_URLS_FILE, account=model_config["account"]):
        return _to_manual(url, "submission_unverified", "发现上次未确认的提交，请先人工核对考试记录")
    if await _handle_attempt_limit_if_present(page, url):
        return True
    if before is None:
        return _to_manual(url, "state_unknown", "考试状态读取失败，转人工核对")
    if before.allowed_attempts != 0 and (before.remaining_attempts is None or before.remaining_attempts <= PAPER_EXAM_ATTEMPT_THRESHOLD):
        text = f"剩余 {before.remaining_attempts} 次" if before.remaining_attempts is not None else "次数未知"
        queue_exam_url_by_attempt_text(url, text, threshold=PAPER_EXAM_ATTEMPT_THRESHOLD,
            exam_file=EXAM_URLS_FILE, manual_exam_file=MANUAL_EXAM_FILE)
        return True

    record_submission_intent(url, model_config, EXAM_URLS_FILE)
    answer_page = page
    try:
        if not await _has_ready_answer_question(page):
            button = await _locate_exam_button(page)
            if button is None:
                return _to_manual(url, "state_unknown", "无法定位开考按钮，转人工核对")
            answer_page = await _open_paper_answer_page(page, button)
        await ai_exam(client, model, answer_page, url, auto_submit=auto_submit, ai_model_config=model_config)
        after = await _paper_state(page, url)
        outcome = after.outcome if after else "unknown"
        if outcome == "failed" and not (
            after.record_id and after.record_id != before.record_id
            or after.used_attempts is not None and before.used_attempts is not None and after.used_attempts > before.used_attempts
        ):
            outcome = "unknown"
        return _finish_ai_outcome(url, outcome, model_config)
    finally:
        if answer_page is not page:
            await _close_page_safely(answer_page)


async def run_ai_exam_batch(status_callback: StatusCallback | None = None, *, auto_submit: bool = False) -> int:
    urls = read_exam_urls(EXAM_URLS_FILE)
    if not urls:
        return 0
    client, model = _build_exam_client()
    try:
        model_config = _build_ai_exam_model_config(model, client)
        async with create_browser_context() as (_, context):
            for index, url in enumerate(urls, start=1):
                if has_ai_failed_model_config(url, model_config, file_path=EXAM_URLS_FILE):
                    _to_manual(url, "ai_failed", "该账号已使用相同模型配置考试失败，请更换配置或人工处理", model_config)
                    remove_exam_url(url, file_path=EXAM_URLS_FILE)
                    continue
                entry_type = classify_exam_entry_url(url)
                if entry_type not in {"course", "exam"}:
                    _to_manual(url, "unknown_url_type", "此入口需要人工展开或核对")
                    remove_exam_url(url, file_path=EXAM_URLS_FILE)
                    continue
                page = None
                try:
                    page = await context.new_page()
                    if status_callback:
                        status_callback(f"AI 考试 {index}/{len(urls)}: {url}")
                    await page.goto(url, timeout=30000)
                    runner = _run_course_ai_exam if entry_type == "course" else _run_paper_ai_exam
                    completed = await runner(page, url, client, model, auto_submit=auto_submit)
                    if completed is True:
                        remove_exam_url(url, file_path=EXAM_URLS_FILE)
                except (UserAbortRequested, UserCancelRequested, ExamAiConfigurationError):
                    raise
                except ExamQuestionExtractionError as exc:
                    raise UserCancelRequested(f"{exc}；题目提取不完整，已保留考试待办") from exc
                except Exception as exc:
                    if is_target_closed_exception(exc):
                        raise UserCancelRequested("考试页面已关闭，未确认完成的待办已保留") from None
                    logging.exception("AI 考试流程失败，转人工核对")
                    _to_manual(url, "ai_exam_error", f"流程失败（{type(exc).__name__}），请核对提交记录")
                    remove_exam_url(url, file_path=EXAM_URLS_FILE)
                finally:
                    await _close_page_safely(page)
    except asyncio.CancelledError:
        raise UserCancelRequested("已中断 AI 考试，未确认完成的待办已保留") from None
    finally:
        await close_safely(client.close(), label="AI client")
    return len(read_manual_exam_queue(MANUAL_EXAM_FILE))


async def _wait_for_manual_course_test(page) -> None:
    async with page.expect_popup() as popup_info:
        await page.locator(COURSE_EXAM_BUTTON).click()
    popup = await popup_info.value
    try:
        await _wait_for_manual_submit_completion(popup)
    finally:
        await _close_page_safely(popup)


async def _wait_for_manual_paper_test(page, exam_button=None) -> None:
    exam_button = exam_button or await _locate_exam_button(page)
    if exam_button is None:
        raise UserCancelRequested("未找到考试入口，已保留待办")
    answer_page = await _open_paper_answer_page(page, exam_button)
    try:
        await _wait_for_manual_submit_completion(answer_page)
    finally:
        if answer_page is not page:
            await _close_page_safely(answer_page)


async def _run_manual_course_exam(page, url: str, *, manual_exam_file=MANUAL_EXAM_FILE) -> bool:
    account = _current_account()
    await _open_course_exam_tab(page)
    outcome = await get_course_exam_outcome(page)
    if outcome == "passed":
        finish_submission(url, "verified", manual_exam_file, account=account)
        return True
    if outcome == "pending_grading":
        logging.info("考试待评卷，保留人工复查待办")
        return False
    record_submission_intent(url, {"account": account}, manual_exam_file)
    await _wait_for_manual_course_test(page)
    await _handle_exam_result(page)
    await _open_course_exam_tab(page)
    outcome = await get_course_exam_outcome(page)
    if outcome != "unknown":
        finish_submission(url, outcome, manual_exam_file, account=account)
    return outcome == "passed"


async def _run_manual_paper_exam(page, url: str, *, manual_exam_file=MANUAL_EXAM_FILE) -> bool:
    account = _current_account()
    await _raise_if_login_required(page, url)
    before = await _paper_state(page, url)
    if before and before.passed:
        finish_submission(url, "verified", manual_exam_file, account=account)
        return True
    if before and before.pending_grading:
        logging.info("考试待评卷，保留人工复查待办")
        return False
    record_submission_intent(url, {"account": account}, manual_exam_file)
    if await _has_ready_answer_question(page):
        await _wait_for_manual_submit_completion(page)
    else:
        await _wait_for_manual_paper_test(page)
    after = await _paper_state(page, url)
    if after and after.outcome != "unknown":
        finish_submission(url, after.outcome, manual_exam_file, account=account)
    return bool(after and after.passed)


async def run_manual_exam_batch(status_callback: StatusCallback | None = None, manual_exam_file=MANUAL_EXAM_FILE) -> int:
    entries = read_manual_exam_queue(manual_exam_file)
    if not entries:
        return 0
    processed = 0
    try:
        async with create_browser_context() as (_, context):
            for index, entry in enumerate(entries, start=1):
                page = None
                entry_type = classify_exam_entry_url(entry.url)
                if entry_type not in {"course", "exam"}:
                    continue
                try:
                    page = await context.new_page()
                    if status_callback:
                        status_callback(f"人工考试 {index}/{len(entries)}: {entry.url}")
                    await page.goto(entry.url, timeout=30000)
                    runner = _run_manual_course_exam if entry_type == "course" else _run_manual_paper_exam
                    if await runner(page, entry.url, manual_exam_file=manual_exam_file) is True:
                        current = read_manual_exam_queue(manual_exam_file)
                        write_manual_exam_queue([item for item in current if item.url != entry.url], file_path=manual_exam_file, keep_file=True)
                        processed += 1
                except (UserAbortRequested, UserCancelRequested):
                    raise
                except Exception as exc:
                    if is_target_closed_exception(exc):
                        raise UserCancelRequested("考试页面已关闭，未确认完成的人工待办已保留") from None
                    logging.exception("人工考试结果未确认，保留待办")
                finally:
                    await _close_page_safely(page)
    except asyncio.CancelledError:
        raise UserCancelRequested("已中断人工考试，未确认完成的待办已保留") from None
    return processed
