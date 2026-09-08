from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
import sysconfig
from pathlib import Path
from core.runtime import run_child
from core.storage import write_text_atomic


OCR_STATUS_PREFIX = "COURSE_AFK_OCR_STATUS:"
OCR_RESULT_PREFIX = "COURSE_AFK_OCR_RESULT:"
OCR_FILE_PREFIX = "COURSE_AFK_OCR_FILE:"
OCR_MODEL_NAME = "PP-OCRv6_medium"
OCR_FORMAT_MARKER = "<!-- course-afk-ocr-format: 2 -->"
OCR_COMMIT_FILE = "complete.json"


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def is_complete_ocr_artifact(output_dir: Path, pdf_path: Path) -> bool:
    """Reuse only a committed artifact whose source, markdown and images match."""
    markdown = expected_ocr_markdown_path(output_dir, pdf_path)
    root = markdown.parent.resolve()
    try:
        manifest = json.loads((root / OCR_COMMIT_FILE).read_text(encoding="utf-8"))
        if manifest.get("version") != 1 or manifest.get("source_sha256") != file_digest(pdf_path):
            return False
        files = manifest.get("files")
        if not isinstance(files, dict) or markdown.name not in files:
            return False
        for name, digest in files.items():
            target = (root / name).resolve()
            if root not in target.parents or not target.is_file() or target.stat().st_size == 0:
                return False
            if file_digest(target) != digest:
                return False
        return True
    except (OSError, ValueError, TypeError, AttributeError):
        return False


class PdfOcrUnavailable(RuntimeError):
    """Raised when the optional PaddleOCR runtime is not installed."""


class PdfOcrRuntimeError(RuntimeError):
    """Raised when the PaddleOCR worker cannot finish conversion."""


def find_pdf_files(output_dir: Path) -> list[Path]:
    docs_dir = Path(output_dir) / "docs"
    if not docs_dir.is_dir():
        return []
    return sorted(
        path for path in docs_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"
    )


def ocr_document_dir_name(pdf_path: Path) -> str:
    digest = hashlib.sha1(pdf_path.name.encode("utf-8")).hexdigest()[:10]
    stem = re.sub(r'[\\/:*?"<>|\r\n]+', "_", pdf_path.stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .") or "document"
    return f"{stem[:72]}__{digest}"


def expected_ocr_markdown_path(output_dir: Path, pdf_path: Path) -> Path:
    return Path(output_dir) / "ocr" / ocr_document_dir_name(pdf_path) / "内容.md"


def missing_ocr_dependencies() -> list[str]:
    return [
        package
        for package in ("paddle", "paddleocr")
        if importlib.util.find_spec(package) is None
    ]


def ensure_ocr_dependencies() -> None:
    missing = missing_ocr_dependencies()
    if missing:
        raise PdfOcrUnavailable(
            "缺少 PDF OCR 可选依赖："
            f"{', '.join(missing)}。请先按 README 的“PDF 转 Markdown”章节安装 "
            "requirements-ocr.txt 和适合本机的 PaddlePaddle CPU/GPU 后端。"
        )


def nvidia_dll_directories(site_packages: Path | None = None) -> list[str]:
    if os.name != "nt" and site_packages is None:
        return []
    if site_packages is None:
        site_packages = Path(sysconfig.get_paths()["purelib"])
    nvidia_root = Path(site_packages) / "nvidia"
    if not nvidia_root.is_dir():
        return []

    directories = {dll_path.parent for dll_path in nvidia_root.rglob("*.dll")}
    return [
        str(path)
        for path in sorted(
            directories,
            key=lambda path: (
                0 if any(part.lower().startswith("cu13") for part in path.parts) else 1,
                str(path).lower(),
            ),
        )
    ]


def _configure_worker_dll_path(worker_env: dict[str, str]) -> None:
    dll_directories = nvidia_dll_directories()
    if not dll_directories:
        return
    existing_path = worker_env.get("PATH", "")
    worker_env["PATH"] = os.pathsep.join(
        [*dll_directories, *([existing_path] if existing_path else [])]
    )


def _insert_ocr_links(course_text: str, output_dir: Path, pdf_files: list[Path]) -> str:
    updated = course_text
    for pdf_path in pdf_files:
        markdown_path = expected_ocr_markdown_path(output_dir, pdf_path)
        if not markdown_path.is_file():
            continue
        document_line = f"- 文档：[打开 {pdf_path.name}](<../docs/{pdf_path.name}>)"
        ocr_relative = markdown_path.relative_to(output_dir).as_posix()
        markdown_name = f"{pdf_path.stem}.md"
        markdown_line = f"- 文档：[打开 {markdown_name}](<../{ocr_relative}>)"
        if document_line in updated:
            document_position = updated.index(document_line)
            section_position = updated.rfind("\n### ", 0, document_position)
            if section_position < 0:
                section_position = 0
            section_prefix = updated[section_position:document_position]
            updated_section_prefix = section_prefix.replace(
                "- 文件类型：pdf", "- 文件类型：md", 1
            )
            if updated_section_prefix != section_prefix:
                updated = (
                    updated[:section_position]
                    + updated_section_prefix
                    + updated[document_position:]
                )
            pattern = re.escape(document_line) + r"(?:\n- 文件大小：\d+ 字节)?"
            updated = re.sub(pattern, markdown_line, updated, count=1)
    return updated


def update_course_markdown_ocr_links(
    output_dir: Path,
    pdf_files: list[Path] | None = None,
) -> int:
    output_dir = Path(output_dir)
    if pdf_files is None:
        pdf_files = find_pdf_files(output_dir)
    linked_count = 0
    courses_dir = output_dir / "courses"
    if not courses_dir.is_dir():
        return linked_count
    for course_path in sorted(courses_dir.glob("*.md")):
        original = course_path.read_text(encoding="utf-8")
        updated = _insert_ocr_links(original, output_dir, pdf_files)
        if updated == original:
            continue
        write_text_atomic(course_path, updated)
        linked_count += sum(
            1
            for pdf_path in pdf_files
            if f"- 文档：[打开 {pdf_path.stem}.md]" in updated
            and f"- 文档：[打开 {pdf_path.stem}.md]" not in original
        )
    return linked_count


def update_document_index_ocr_links(output_dir: Path, pdf_files: list[Path]) -> int:
    index_path = Path(output_dir) / "文档索引.md"
    if not index_path.is_file():
        return 0
    original = index_path.read_text(encoding="utf-8")
    lines = original.splitlines()
    updated_count = 0
    for index, line in enumerate(lines):
        for pdf_path in pdf_files:
            markdown_path = expected_ocr_markdown_path(output_dir, pdf_path)
            prefix = f"- [{pdf_path.name}](<docs/{pdf_path.name}>)"
            if not markdown_path.is_file() or not line.startswith(prefix):
                continue
            relative = markdown_path.relative_to(output_dir).as_posix()
            lines[index] = f"- [{pdf_path.stem}.md](<{relative}>) (OCR Markdown)"
            updated_count += 1
            break
    if updated_count:
        write_text_atomic(index_path, "\n".join(lines) + "\n")
    return updated_count


def delete_converted_pdf_files(output_dir: Path, pdf_files: list[Path]) -> int:
    deleted_count = 0
    for pdf_path in pdf_files:
        if not is_complete_ocr_artifact(output_dir, pdf_path):
            continue
        pdf_path.unlink()
        deleted_count += 1
    return deleted_count


def _parse_worker_result(line: str) -> tuple[int, int, int] | None:
    if not line.startswith(OCR_RESULT_PREFIX):
        return None
    try:
        converted, failed, reused = line.removeprefix(OCR_RESULT_PREFIX).split("|")
        return int(converted), int(failed), int(reused)
    except (TypeError, ValueError):
        return None


def _parse_worker_file(line: str) -> str | None:
    if not line.startswith(OCR_FILE_PREFIX):
        return None
    encoded = line.removeprefix(OCR_FILE_PREFIX)
    try:
        padding = "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


async def convert_downloaded_pdfs_to_markdown(
    output_dir: Path | str,
    *,
    status_callback=None,
) -> dict:
    # The worker imports artifact helpers from this module. Keep application
    # configuration (including .env credentials) out of that import path.
    from core.config import _env_raw

    output_dir = Path(output_dir).resolve()
    pdf_files = find_pdf_files(output_dir)
    if not pdf_files:
        return {
            "ocr_output_dir": str(output_dir / "ocr"),
            "pdf_count": 0,
            "ocr_converted_count": 0,
            "ocr_failed_count": 0,
            "ocr_reused_count": 0,
            "ocr_linked_count": 0,
            "pdf_deleted_count": 0,
        }

    ensure_ocr_dependencies()
    if status_callback:
        status_callback(
            f"检测到 {len(pdf_files)} 个 PDF，准备使用 PP-StructureV3 + "
            f"{OCR_MODEL_NAME} 转换为 Markdown"
        )

    project_root = Path(__file__).resolve().parents[2]
    command = [
        sys.executable,
        "-u",
        "-m",
        "core.discovery.pdf_ocr_worker",
        "--input-dir",
        str(output_dir / "docs"),
        "--output-dir",
        str(output_dir / "ocr"),
        "--device",
        (_env_raw("COURSE_AFK_OCR_DEVICE") or "auto"),
    ]
    worker_env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("OPENAI_", "AI_", "ANTHROPIC_", "AZURE_OPENAI_"))}
    worker_env["PYTHONUTF8"] = "1"
    worker_env["PYTHONIOENCODING"] = "utf-8"
    _configure_worker_dll_path(worker_env)
    output_tail: list[str] = []
    worker_result: tuple[int, int, int] | None = None
    successful_pdf_names: set[str] = set()
    def consume_line(line: str) -> None:
        nonlocal worker_result
        line = line.strip()
        if not line:
            return
        parsed = _parse_worker_result(line)
        if parsed is not None:
            worker_result = parsed
            return
        successful_file = _parse_worker_file(line)
        if successful_file is not None:
            successful_pdf_names.add(successful_file)
            return
        if line.startswith(OCR_STATUS_PREFIX):
            if status_callback:
                status_callback(line.removeprefix(OCR_STATUS_PREFIX))
            return
        output_tail.append(line)
        del output_tail[:-20]

    try:
        timeout = float((_env_raw("COURSE_AFK_OCR_TIMEOUT") or "7200"))
        idle_timeout = float((_env_raw("COURSE_AFK_OCR_IDLE_TIMEOUT") or "600"))
    except (ValueError, TypeError) as exc:
        raise PdfOcrRuntimeError("OCR 超时配置必须是数值，修改 .env 后重启再试") from exc
    if not 1 <= timeout <= 86400 or not 1 <= idle_timeout <= timeout:
        raise PdfOcrRuntimeError("OCR 超时必须为 1–86400 秒，idle 不得超过总期限")
    try:
        return_code = await run_child(command, cwd=str(project_root), env=worker_env, on_line=consume_line, timeout=timeout, idle_timeout=idle_timeout)
    except TimeoutError as exc:
        raise PdfOcrRuntimeError("PDF OCR 已超过期限，工作进程已回收；源 PDF 已保留") from exc
    if return_code != 0:
        detail = "\n".join(output_tail[-8:]) or f"子进程退出码 {return_code}"
        raise PdfOcrRuntimeError(f"PDF OCR 转换失败：{detail}")

    if worker_result is None:
        raise PdfOcrRuntimeError("OCR 工作进程未返回完整结果；源 PDF 已保留")
    converted, failed, reused = worker_result
    successful_pdf_files = [
        path for path in pdf_files if path.name in successful_pdf_names and is_complete_ocr_artifact(output_dir, path)
    ]
    if min(converted, failed, reused) < 0 or converted + failed + reused != len(pdf_files) or len(successful_pdf_files) != converted + reused:
        raise PdfOcrRuntimeError("OCR 结果与已提交文件不一致；源 PDF 已保留")
    linked = update_course_markdown_ocr_links(output_dir, successful_pdf_files)
    update_document_index_ocr_links(output_dir, successful_pdf_files)
    delete_source = (_env_raw("COURSE_AFK_OCR_DELETE_SOURCE") or "false").strip().lower() in {"true", "1", "yes"}
    deleted = delete_converted_pdf_files(output_dir, successful_pdf_files) if delete_source else 0
    return {
        "ocr_output_dir": str(output_dir / "ocr"),
        "pdf_count": len(pdf_files),
        "ocr_converted_count": converted,
        "ocr_failed_count": failed,
        "ocr_reused_count": reused,
        "ocr_linked_count": linked,
        "pdf_deleted_count": deleted,
    }
