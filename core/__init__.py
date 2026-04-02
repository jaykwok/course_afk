# core 包 - 统一导出所有公共函数

from core.browser import create_browser_context
from core.exam_engine import ai_exam, wait_for_finish_test
from core.file_ops import del_file, is_compliant_url_regex, normalize_url, save_to_file
from core.learning import (
    check_exam_passed,
    check_permission,
    course_learning,
    handle_rating_popup,
    is_subject_url_completed,
    subject_learning,
)
from core.logging_config import setup_logging
