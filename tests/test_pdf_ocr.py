import asyncio
import base64
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.discovery.pdf_ocr import (
    expected_ocr_markdown_path,
    delete_converted_pdf_files,
    nvidia_dll_directories,
    ocr_document_dir_name,
    update_document_index_ocr_links,
    update_course_markdown_ocr_links,
    is_complete_ocr_artifact,
    convert_downloaded_pdfs_to_markdown,
    file_digest,
    PdfOcrRuntimeError,
    OCR_FILE_PREFIX,
    OCR_RESULT_PREFIX,
)
from core.discovery.pdf_ocr_worker import (
    _append_ocr_text_layer,
    _convert_pdf,
    _extract_ocr_lines,
    _markdown_text,
)


class PdfOcrTests(unittest.TestCase):
    def test_nvidia_cuda_13_dll_directory_has_priority(self):
        with TemporaryDirectory() as tmp:
            site_packages = Path(tmp)
            cuda_13_dir = site_packages / "nvidia" / "cu13" / "bin" / "x86_64"
            common_dir = site_packages / "nvidia" / "cudnn" / "bin"
            cuda_13_dir.mkdir(parents=True)
            common_dir.mkdir(parents=True)
            (cuda_13_dir / "cublas64_13.dll").write_bytes(b"dll")
            (common_dir / "cudnn64_9.dll").write_bytes(b"dll")

            directories = nvidia_dll_directories(site_packages)

            self.assertEqual(directories[0], str(cuda_13_dir))
            self.assertIn(str(common_dir), directories)

    def test_ocr_document_dir_name_is_stable_and_bounded(self):
        pdf_path = Path(("很长的课程名称" * 30) + ".pdf")

        first = ocr_document_dir_name(pdf_path)
        second = ocr_document_dir_name(pdf_path)

        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 84)
        self.assertRegex(first, r"__[0-9a-f]{10}$")

    def test_update_course_markdown_adds_link_for_converted_pdf_only(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            docs_dir = output_dir / "docs"
            courses_dir = output_dir / "courses"
            docs_dir.mkdir()
            courses_dir.mkdir()
            pdf_path = docs_dir / "课件.pdf"
            docx_path = docs_dir / "讲义.docx"
            pdf_path.write_bytes(b"%PDF-test")
            docx_path.write_bytes(b"docx")
            markdown_path = expected_ocr_markdown_path(output_dir, pdf_path)
            markdown_path.parent.mkdir(parents=True)
            markdown_path.write_text("# OCR", encoding="utf-8")
            course_path = courses_dir / "课程.md"
            course_path.write_text(
                "### 01 课件\n\n- 文件类型：pdf\n"
                "- 文档：[打开 课件.pdf](<../docs/课件.pdf>)\n"
                "- 文件大小：123 字节\n"
                "### 02 讲义\n\n- 文件类型：docx\n"
                "- 文档：[打开 讲义.docx](<../docs/讲义.docx>)\n",
                encoding="utf-8",
            )
            index_path = output_dir / "文档索引.md"
            index_path.write_text(
                "# 文档索引\n\n"
                "- [课件.pdf](<docs/课件.pdf>) (0.1 MB)\n"
                "- [讲义.docx](<docs/讲义.docx>) (0.1 MB)\n",
                encoding="utf-8",
            )

            linked = update_course_markdown_ocr_links(output_dir)
            content = course_path.read_text(encoding="utf-8")

            self.assertEqual(linked, 1)
            self.assertIn("- 文档：[打开 课件.md](<../ocr/", content)
            self.assertNotIn("打开 课件.pdf", content)
            self.assertIn("- 文件类型：md", content)
            self.assertNotIn("- 文件大小：123 字节", content)
            self.assertIn("打开 讲义.docx", content)

            index_updates = update_document_index_ocr_links(output_dir, [pdf_path])
            index_content = index_path.read_text(encoding="utf-8")
            self.assertEqual(index_updates, 1)
            self.assertIn("[课件.md](<ocr/", index_content)
            self.assertNotIn("[课件.pdf]", index_content)
            self.assertIn("[讲义.docx]", index_content)

            deleted = delete_converted_pdf_files(output_dir, [pdf_path])
            self.assertEqual(deleted, 0)
            self.assertTrue(pdf_path.exists(), "a Markdown file without a commit manifest cannot authorize deletion")

    def test_convert_pdf_writes_single_llm_markdown(self):
        class FakeResult:
            markdown = {
                "markdown_texts": "页面内容",
                "markdown_images": {},
            }
            json = {"overall_ocr_res": {"rec_texts": ["标题", "正文内容"]}}

        class FakePipeline:
            def predict(self, **_kwargs):
                return [FakeResult()]

            def concatenate_markdown_pages(self, pages):
                self.pages = pages
                return "## 第一页\n\n页面内容"

        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            docs_dir = output_dir / "docs"
            ocr_dir = output_dir / "ocr"
            docs_dir.mkdir()
            pdf_path = docs_dir / "课件.pdf"
            pdf_path.write_bytes(b"%PDF-test")

            markdown_path = _convert_pdf(FakePipeline(), pdf_path, ocr_dir)
            content = markdown_path.read_text(encoding="utf-8")

            self.assertIn("# 课件", content)
            self.assertIn("PP-StructureV3 + PP-OCRv6_medium", content)
            self.assertIn("## 第一页", content)
            self.assertNotIn("{", content)
            self.assertTrue(is_complete_ocr_artifact(output_dir, pdf_path))
            markdown_path.write_text("corrupted", encoding="utf-8")
            self.assertFalse(is_complete_ocr_artifact(output_dir, pdf_path))
            self.assertEqual(delete_converted_pdf_files(output_dir, [pdf_path]), 0)

    def test_sparse_structured_markdown_gets_ocr_text_layer(self):
        payload = {
            "overall_ocr_res": {
                "rec_texts": ["互联网政务应用安全管理规定", "第一章 总则"]
            }
        }
        lines = _extract_ocr_lines(payload)
        body = _append_ocr_text_layer(
            '<img src="imgs/page.jpg" alt="Image" />',
            [lines],
        )

        self.assertEqual(lines[0], "互联网政务应用安全管理规定")
        self.assertIn("## OCR 文字层", body)
        self.assertIn("### 第 1 页", body)
        self.assertIn("第一章 总则", body)

    def test_markdown_text_accepts_current_and_tuple_return_shapes(self):
        self.assertEqual(_markdown_text("正文"), "正文")
        self.assertEqual(_markdown_text(("正文", [])), "正文")
        self.assertEqual(_markdown_text({"markdown_texts": "正文"}), "正文")

    def test_image_failure_and_missing_page_never_publish_partial_artifact(self):
        class BadImage:
            def save(self, _path):
                raise OSError("image failed")
        with TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "docs").mkdir()
            pdf = output / "docs" / "source.pdf"
            pdf.write_bytes(b"%PDF-test")
            for pages in (
                [{"markdown_texts": "![image](imgs/a.png)", "markdown_images": {"imgs/a.png": BadImage()}}],
                [{"markdown_texts": "![image](imgs/missing.png)", "markdown_images": {}}],
                [{"markdown_texts": "first page"}, None],
            ):
                pipeline = SimpleNamespace(
                    predict=lambda **_kwargs: [SimpleNamespace(markdown=page) for page in pages],
                    concatenate_markdown_pages=lambda results: results[0]["markdown_texts"],
                )
                with self.assertRaises((OSError, RuntimeError)):
                    _convert_pdf(pipeline, pdf, output / "ocr")
                self.assertFalse(is_complete_ocr_artifact(output, pdf))
                self.assertEqual(delete_converted_pdf_files(output, [pdf]), 0)
                self.assertTrue(pdf.exists())

    def test_worker_import_does_not_load_application_configuration(self):
        result = subprocess.run(
            [sys.executable, "-c", "import sys; import core.discovery.pdf_ocr_worker; assert 'core.config' not in sys.modules"],
            capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


class PdfOcrParentTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_verified_artifacts_are_linked_and_source_is_retained_by_default(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "docs").mkdir()
            pdf = output / "docs" / "source.pdf"
            pdf.write_bytes(b"%PDF-test")
            markdown = expected_ocr_markdown_path(output, pdf)
            markdown.parent.mkdir(parents=True)
            markdown.write_text("complete text", encoding="utf-8")
            (markdown.parent / "complete.json").write_text(json.dumps({
                "version": 1, "source_sha256": file_digest(pdf), "files": {markdown.name: file_digest(markdown)},
            }), encoding="utf-8")
            async def worker(_command, **kwargs):
                self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
                self.assertNotIn("AI_BASE_URL", kwargs["env"])
                kwargs["on_line"](OCR_FILE_PREFIX + base64.urlsafe_b64encode(pdf.name.encode()).decode())
                kwargs["on_line"](OCR_RESULT_PREFIX + "1|0|0")
                return 0
            with (
                patch("core.discovery.pdf_ocr.ensure_ocr_dependencies"),
                patch("core.discovery.pdf_ocr.run_child", new=worker),
                patch("core.config._env_raw", return_value=None),
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy", "AI_BASE_URL": "dummy"}),
            ):
                result = await convert_downloaded_pdfs_to_markdown(output)
            self.assertEqual(result["ocr_converted_count"], 1)
            self.assertEqual(result["pdf_deleted_count"], 0)
            self.assertTrue(pdf.exists())
            with (
                patch("core.discovery.pdf_ocr.ensure_ocr_dependencies"),
                patch("core.discovery.pdf_ocr.run_child", new=worker),
                patch("core.config._env_raw", side_effect=lambda key: "true" if key == "COURSE_AFK_OCR_DELETE_SOURCE" else None),
            ):
                result = await convert_downloaded_pdfs_to_markdown(output)
            self.assertEqual(result["pdf_deleted_count"], 1)
            self.assertFalse(pdf.exists())

    async def test_cancel_failure_and_inconsistent_success_all_preserve_source(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "docs").mkdir()
            pdf = output / "docs" / "source.pdf"
            pdf.write_bytes(b"%PDF-test")
            async def inconsistent(_command, **kwargs):
                kwargs["on_line"](OCR_RESULT_PREFIX + "1|0|0")
                return 0
            for worker in (AsyncMock(side_effect=asyncio.CancelledError()), AsyncMock(side_effect=TimeoutError()), inconsistent):
                with self.subTest(worker=type(worker).__name__), patch("core.discovery.pdf_ocr.ensure_ocr_dependencies"), patch("core.discovery.pdf_ocr.run_child", new=worker), patch("core.config._env_raw", return_value=None):
                    with self.assertRaises((asyncio.CancelledError, PdfOcrRuntimeError)):
                        await convert_downloaded_pdfs_to_markdown(output)
                self.assertTrue(pdf.exists())


if __name__ == "__main__":
    unittest.main()
