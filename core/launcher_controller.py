from __future__ import annotations

import asyncio

def choose_learning_zone_mode(learning_zone_urls, prompt_choice_func) -> str:
    if not learning_zone_urls:
        return "manual"

    choice = prompt_choice_func(
        "检测到学习专区链接，请选择处理方式",
        [
            "全部学习：自动解析并写入学习链接",
            "手动选择学习模块：打开页面后自己点击课程",
        ],
    )
    return "auto" if choice == 1 else "manual"


def handle_recommended_flow(ui) -> None:
    from core.workflows import run_recommended_flow

    result = asyncio.run(run_recommended_flow(status_callback=ui.show_info))
    ui.show_summary("推荐流程结果", [("流程状态", result)])
    ui.pause()


def handle_refresh_credential(state, ui) -> None:
    from core.workflows import refresh_credential

    if state.has_credential and not state.credential_expired:
        ui.show_warning("当前登录凭证仍有效，继续将覆盖现有登录状态")
    profile = refresh_credential(status_callback=ui.show_info)
    ui.show_success(f"登录凭证已更新，当前账号：{profile.label}")
    ui.pause()


def handle_show_learning_links(learning_urls_file, ui) -> None:
    from core.state import read_non_empty_lines

    links = read_non_empty_lines(learning_urls_file)
    if not links:
        ui.show_warning("学习链接.txt 当前为空")
    else:
        ui.show_summary(
            "学习链接状态",
            [("学习链接总数", str(len(links))), ("首条学习链接", links[0])],
        )
    ui.pause()


def handle_manual_selection(prompts, ui) -> None:
    from core.links import split_manual_selection_urls
    from core.workflows import parse_manual_selection_input, run_manual_course_selection

    input_text = ui.prompt_multiline_input(prompts)
    _, learning_zone_urls, _ = split_manual_selection_urls(
        parse_manual_selection_input(input_text)
    )
    learning_zone_mode = choose_learning_zone_mode(
        learning_zone_urls,
        prompt_choice_func=ui.prompt_choice,
    )
    result = asyncio.run(
        run_manual_course_selection(
            input_text,
            learning_zone_mode=learning_zone_mode,
            status_callback=ui.show_info,
        )
    )
    ui.show_summary(
        "手动选择学习课程结果",
        [
            ("识别到的输入链接", str(result["input_url_count"])),
            ("直接写入的学习链接", str(result["direct_learning_count"])),
            ("学习专区链接数量", str(result["learning_zone_url_count"])),
            ("学习专区自动解析数量", str(result["learning_zone_parsed_count"])),
            ("需要手动打开的入口链接", str(result["entry_url_count"])),
            ("手动点击记录的学习链接", str(result["manual_record_count"])),
            ("当前学习链接总数", str(result["learning_total"])),
        ],
    )
    ui.pause()


def handle_afk(ui) -> None:
    from core.workflows import run_afk_workflow

    has_exam = asyncio.run(run_afk_workflow(status_callback=ui.show_info))
    if has_exam:
        ui.show_success("挂课完成，并检测到考试链接")
    else:
        ui.show_warning("挂课完成，未检测到考试链接")
    ui.pause()


def handle_ai_exam(ui) -> None:
    from core.workflows import run_ai_exam_workflow

    manual_count = asyncio.run(run_ai_exam_workflow(status_callback=ui.show_info))
    if manual_count:
        ui.show_warning(f"AI 自动考试结束，剩余人工考试 {manual_count} 条")
    else:
        ui.show_success("AI 自动考试流程结束")
    ui.pause()


def handle_manual_exam(ui) -> None:
    from core.state import collect_project_state
    from core.workflows import run_manual_exam_workflow

    count = asyncio.run(run_manual_exam_workflow(status_callback=ui.show_info))
    state = collect_project_state()
    if count and state.manual_exam_count == 0:
        ui.show_success(f"人工考试流程结束，共处理 {count} 条")
    elif count:
        ui.show_warning(
            f"人工考试已处理 {count} 条，仍有 {state.manual_exam_count} 条待继续处理"
        )
    else:
        ui.show_warning("本次没有完成新的人工考试链接")
    ui.pause()


def handle_show_output_state(exam_urls_file, learning_urls_file, manual_exam_file, ui) -> None:
    from core.state import read_non_empty_lines

    ui.show_summary(
        "当前输出文件状态",
        [
            ("学习链接", str(len(read_non_empty_lines(learning_urls_file)))),
            ("考试链接", str(len(read_non_empty_lines(exam_urls_file)))),
            ("人工考试链接", str(len(read_non_empty_lines(manual_exam_file)))),
        ],
    )
    ui.pause()
