from __future__ import annotations

from rich.align import Align
from rich.box import HEAVY_HEAD, ROUNDED, SIMPLE_HEAVY
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from core.credential import load_credential_metadata
from core.state import ProjectState, recommend_next_step


console = Console()


def show_title(title: str, subtitle: str | None = None) -> None:
    text = Text(title, style="bold cyan")
    if subtitle:
        text.append(f"\n{subtitle}", style="dim")
    console.print(
        Align.center(
            Panel(
                text,
                expand=False,
                border_style="bright_blue",
                padding=(0, 3),
            )
        )
    )


def show_info(message: str) -> None:
    console.print(f"[cyan]{message}[/cyan]")


def show_success(message: str) -> None:
    console.print(f"[green]{message}[/green]")


def show_warning(message: str) -> None:
    console.print(f"[yellow]{message}[/yellow]")


def show_error(message: str) -> None:
    console.print(f"[bold red]{message}[/bold red]")


def render_dashboard(state: ProjectState) -> None:
    metadata = load_credential_metadata()
    account_label = metadata.account_label if metadata else "未登录"
    credential_status = "已过期" if state.credential_expired else "有效"
    if not state.has_credential:
        credential_status = "不存在"

    table = Table(
        title="当前状态",
        show_header=True,
        header_style="bold magenta",
        box=ROUNDED,
    )
    table.add_column("项目")
    table.add_column("值", overflow="fold", min_width=36)
    table.add_row("当前账号", account_label)
    table.add_row("登录凭证", credential_status)
    table.add_row("学习链接数量", str(state.learning_count))
    table.add_row("考试链接数量", str(state.exam_count))
    table.add_row("人工考试数量", str(state.manual_exam_count))
    table.add_row(
        "推荐下一步",
        recommend_next_step(
            has_credential=state.has_credential and not state.credential_expired,
            learning_count=state.learning_count,
            exam_count=state.exam_count,
            manual_exam_count=state.manual_exam_count,
        ),
    )
    console.print(Align.center(table))


def show_menu(options: list[str]) -> int:
    table = Table(
        title="主菜单",
        show_header=True,
        header_style="bold green",
        box=HEAVY_HEAD,
    )
    table.add_column("序号", justify="right", style="bold cyan")
    table.add_column("功能", min_width=32)
    for index, option in enumerate(options, start=1):
        table.add_row(str(index), option)
    console.print(Align.center(table))
    return IntPrompt.ask("请选择功能", choices=[str(i) for i in range(1, len(options) + 1)])


def prompt_choice(title: str, options: list[str], prompt: str = "请选择") -> int:
    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        box=ROUNDED,
    )
    table.add_column("序号", justify="right", style="bold cyan")
    table.add_column("选项", min_width=32)
    for index, option in enumerate(options, start=1):
        table.add_row(str(index), option)
    console.print(Align.center(table))
    return IntPrompt.ask(prompt, choices=[str(i) for i in range(1, len(options) + 1)])


def prompt_multiline_input(messages: list[str]) -> str:
    instruction = Text()
    for index, message in enumerate(messages, start=1):
        instruction.append(f"{index}. {message}\n", style="cyan")
    instruction.append("输入完成后请直接输入单独一行 END（不区分大小写）", style="bold yellow")
    console.print(
        Align.center(
            Panel(
                instruction,
                title="手动选择学习课程",
                border_style="cyan",
                box=ROUNDED,
                width=76,
            )
        )
    )
    lines: list[str] = []
    while True:
        line = Prompt.ask("")
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def pause(message: str = "按回车返回主菜单") -> None:
    Prompt.ask(message, default="")


def show_summary(title: str, rows: list[tuple[str, str]]) -> None:
    table = Table(
        title=title,
        show_header=True,
        header_style="bold blue",
        box=SIMPLE_HEAVY,
    )
    table.add_column("项目")
    table.add_column("结果", overflow="fold", min_width=36)
    for left, right in rows:
        table.add_row(left, right)
    console.print(Align.center(table))


async def wait_with_progress(
    duration: int,
    description: str = "处理中",
    step: int = 1,
) -> None:
    import asyncio

    duration = int(duration)
    if duration <= 0:
        return
    step = max(1, int(step))
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} 秒"),
        TimeRemainingColumn(),
        console=console,
        auto_refresh=False,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=duration)
        progress.refresh()
        completed = 0
        while completed < duration:
            advance = min(step, duration - completed)
            await asyncio.sleep(advance)
            completed += advance
            progress.update(task, advance=advance)
            progress.refresh()
