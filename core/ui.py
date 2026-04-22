from __future__ import annotations

from datetime import datetime

from rich.align import Align
from rich.box import DOUBLE_EDGE, HEAVY_HEAD, ROUNDED, SIMPLE_HEAVY
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
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from core.credential import load_credential_metadata
from core.state import ProjectState, recommend_next_step


console = Console()


def show_title(title: str, subtitle: str | None = None) -> None:
    console.print()
    title_text = Text(justify="center")
    title_text.append(title, style="bold bright_cyan")
    if subtitle:
        title_text.append(f"\n{subtitle}", style="dim white")
    console.print(
        Align.center(
            Panel(
                title_text,
                expand=False,
                border_style="bright_cyan",
                padding=(1, 6),
                box=DOUBLE_EDGE,
            )
        )
    )
    console.print()


def show_info(message: str) -> None:
    console.print(f"  [cyan]·[/cyan]  {message}")


def show_success(message: str) -> None:
    console.print(f"  [bold green]√[/bold green]  [green]{message}[/green]")


def show_warning(message: str) -> None:
    console.print(f"  [bold yellow]![/bold yellow]  [yellow]{message}[/yellow]")


def show_error(message: str) -> None:
    console.print(f"  [bold red]×[/bold red]  [bold red]{message}[/bold red]")


def _credential_display(state: ProjectState, metadata) -> Text:
    if not state.has_credential:
        return Text("×  不存在", style="bold red")
    if state.credential_expired:
        return Text("!  已过期", style="bold yellow")
    if metadata and metadata.expires_at:
        try:
            expires_dt = datetime.fromisoformat(metadata.expires_at)
            days_left = (expires_dt - datetime.now()).days
            t = Text("√  有效", style="bold green")
            t.append(f"  （还有 {days_left} 天）", style="dim")
            return t
        except ValueError:
            pass
    return Text("√  有效", style="bold green")


def _count_display(count: int) -> Text:
    if count == 0:
        return Text("0", style="dim")
    return Text(str(count), style="bold bright_white")


def render_dashboard(state: ProjectState) -> None:
    metadata = load_credential_metadata()
    account_label = metadata.account_label if metadata else "未登录"

    recommended = recommend_next_step(
        has_credential=state.has_credential and not state.credential_expired,
        learning_count=state.learning_count,
        exam_count=state.exam_count,
        manual_exam_count=state.manual_exam_count,
    )

    table = Table(
        show_header=False,
        box=ROUNDED,
        border_style="bright_black",
        title="[bold white]当前状态[/bold white]",
        title_style="bold white",
        min_width=54,
        padding=(0, 1),
    )
    table.add_column("项目", style="dim white", min_width=10, justify="right")
    table.add_column("值", overflow="fold", min_width=40)

    table.add_row("账号", Text(account_label, style="bold white"))
    table.add_row("凭证", _credential_display(state, metadata))
    table.add_row("课程链接", _count_display(state.learning_count))
    table.add_row("考试链接", _count_display(state.exam_count))
    table.add_row("人工考试", _count_display(state.manual_exam_count))
    table.add_row(
        "建议操作",
        Text(f"->  {recommended}", style="bold bright_yellow"),
    )
    console.print(Align.center(table))
    console.print()


def show_menu(options: list[str]) -> int:
    table = Table(
        show_header=False,
        box=HEAVY_HEAD,
        border_style="bright_black",
        title="[bold white]主菜单[/bold white]",
        title_style="bold white",
        min_width=54,
        padding=(0, 1),
    )
    table.add_column("序号", justify="right", style="bold cyan", width=4)
    table.add_column("功能", min_width=44)
    for index, option in enumerate(options, start=1):
        if index == len(options):
            table.add_row(str(index), Text(option, style="dim"))
        else:
            table.add_row(str(index), option)
    console.print(Align.center(table))
    return IntPrompt.ask(
        "\n  [bold cyan]请选择功能[/bold cyan]",
        choices=[str(i) for i in range(1, len(options) + 1)],
    )


def prompt_choice(title: str, options: list[str], prompt: str = "请选择") -> int:
    table = Table(
        show_header=False,
        box=ROUNDED,
        border_style="bright_black",
        title=f"[bold white]{title}[/bold white]",
        title_style="bold white",
        min_width=54,
        padding=(0, 1),
    )
    table.add_column("序号", justify="right", style="bold cyan", width=4)
    table.add_column("选项", min_width=44)
    for index, option in enumerate(options, start=1):
        table.add_row(str(index), option)
    console.print(Align.center(table))
    return IntPrompt.ask(
        f"\n  [bold cyan]{prompt}[/bold cyan]",
        choices=[str(i) for i in range(1, len(options) + 1)],
    )


def prompt_yes_no(message: str, default: str = "N") -> bool:
    choice = Prompt.ask(
        f"\n  [bold cyan]{message}[/bold cyan]",
        choices=["Y", "N", "y", "n"],
        default=default,
    )
    return choice.strip().upper() == "Y"


def prompt_multiline_input(messages: list[str]) -> str:
    instruction = Text()
    for index, message in enumerate(messages, start=1):
        instruction.append(f"  {index}. ", style="bold cyan")
        instruction.append(f"{message}\n", style="white")
    instruction.append("\n  输入完成后请直接输入单独一行 END（不区分大小写）", style="bold yellow")
    console.print(
        Align.center(
            Panel(
                instruction,
                title="[bold white]手动选择学习课程[/bold white]",
                border_style="cyan",
                box=ROUNDED,
                width=76,
                padding=(1, 2),
            )
        )
    )
    lines: list[str] = []
    while True:
        line = Prompt.ask("  ")
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def pause(message: str = "按回车返回主菜单") -> None:
    console.print()
    console.print(Rule(style="bright_black"))
    Prompt.ask(f"  [dim]{message}[/dim]", default="")
    console.print()


def show_summary(title: str, rows: list[tuple[str, str]]) -> None:
    table = Table(
        show_header=False,
        box=SIMPLE_HEAVY,
        border_style="bright_black",
        title=f"[bold white]{title}[/bold white]",
        title_style="bold white",
        min_width=54,
        padding=(0, 1),
    )
    table.add_column("项目", style="dim white", min_width=16, justify="right")
    table.add_column("结果", overflow="fold", min_width=34)
    for left, right in rows:
        table.add_row(left, Text(right, style="bold white"))
    console.print(Align.center(table))


async def wait_with_progress(
    duration: int,
    description: str = "处理中",
) -> None:
    import asyncio

    duration = int(duration)
    if duration <= 0:
        return
    with Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=28),
        TextColumn("[cyan]{task.completed}[/cyan][dim]/{task.total}s[/dim]"),
        TextColumn("[dim]([/dim][bold]{task.percentage:>3.0f}%[/bold][dim])[/dim]"),
        TimeRemainingColumn(),
        console=console,
        auto_refresh=True,
        refresh_per_second=10,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=duration)
        for _ in range(duration):
            await asyncio.sleep(1)
            progress.update(task, advance=1)
