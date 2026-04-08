"""
统一配置文件 - 所有可调参数集中管理。

修改参数时只需编辑本文件，无需改动业务代码。
"""

import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# 加载 .env 文件（API密钥等敏感信息仍由 .env 管理）
load_dotenv()

# ============================================================
# 日志配置
# ============================================================
LOG_FILE = "log.txt"
LOG_LEVEL = logging.DEBUG
LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s"
)


def setup_logging():
    """统一日志配置，所有脚本共用，追加模式保留历史日志"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    script_name = sys.argv[0] if sys.argv[0] else "unknown"
    separator = (
        f"\n{'='*60}\n"
        f"[启动] {script_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'='*60}"
    )
    logging.info(separator)


# ============================================================
# DashScope / AI 模型配置（从 .env 读取）
# ============================================================
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")

# AI 考试参数
AI_TEMPERATURE = 0
AI_SYSTEM_PROMPT = "你是一个专业的考试助手, 请根据题目选择最合适的答案。"

# ============================================================
# 浏览器配置
# ============================================================
BROWSER_CHANNEL = "msedge"
BROWSER_ARGS = ["--mute-audio", "--start-maximized"]

# ============================================================
# 平台 URL
# ============================================================
MYLEARNING_HOME = "https://www.mylearning.cn/p5/index.html"
MYLEARNING_SSO_PATTERN = "**/sso/login**"
ZHIXUEYUN_HOME = "https://kc.zhixueyun.com/"
ZHIXUEYUN_HOME_PATTERN = r"https://kc\.zhixueyun\.com/#/home-v\?id=\d+"
ZHIXUEYUN_COURSE_PREFIX = "https://kc.zhixueyun.com/#/study/course/detail/"
ZHIXUEYUN_SUBJECT_PREFIX = "https://kc.zhixueyun.com/#/study/subject/detail/"
ZHIXUEYUN_EXAM_PREFIX = "https://kc.zhixueyun.com/#/exam/exam/answer-paper/"

# ============================================================
# 文件路径
# ============================================================
COOKIES_FILE = "cookies.json"
LEARNING_URLS_FILE = "./学习链接.txt"
RETRY_URLS_FILE = "./剩余未看课程链接.txt"
EXAM_URLS_FILE = "./学习课程考试链接.txt"
MANUAL_EXAM_FILE = "./人工考试链接.txt"
NO_PERMISSION_FILE = "无权限资源链接.txt"
NON_COMPLIANT_FILE = "不合规链接.txt"
URL_TYPE_FILE = "URL类型链接.txt"
H5_TYPE_FILE = "h5课程类型链接.txt"
SURVEY_TYPE_FILE = "调研类型链接.txt"
SUBJECT_EXAM_FILE = "学习主题考试链接.txt"
UNKNOWN_TYPE_FILE = "未知类型链接.txt"
OTHER_TYPE_FILE = "非课程及考试类学习类型链接.txt"
CLICK_URLS_FILE = "学习链接_点击按钮.txt"

# 每次全新运行 3afk.py 时需要清理的中间文件
CLEANUP_FILES = [
    SUBJECT_EXAM_FILE,
    SURVEY_TYPE_FILE,
    URL_TYPE_FILE,
    H5_TYPE_FILE,
    OTHER_TYPE_FILE,
    UNKNOWN_TYPE_FILE,
]

# ============================================================
# 超时 / 等待时间（秒）
# ============================================================
# 视频课程进度同步额外等待时间
VIDEO_SYNC_EXTRA_WAIT = 5 * 60  # 5分钟
VIDEO_SYNC_CHECK_INTERVAL = 10  # 每10秒检查一次

# 文档课程初始等待时间
DOCUMENT_INITIAL_WAIT = 5  # 秒
# 文档课程进度同步额外等待时间
DOCUMENT_SYNC_EXTRA_WAIT = 30  # 秒

# URL 学习类型等待时间
URL_TYPE_WAIT = 10  # 秒

# timer 默认间隔
TIMER_DEFAULT_INTERVAL = 30  # 秒

# 3afk.py 的 slow_mo 参数
AFK_SLOW_MO = 3000  # 毫秒

# ============================================================
# 考试配置
# ============================================================
# 课程内考试: 剩余次数 <= 此值时转为人工考试
COURSE_EXAM_ATTEMPT_THRESHOLD = 3
# 试卷链接考试: 剩余次数 <= 此值时转为人工考试
PAPER_EXAM_ATTEMPT_THRESHOLD = 1

# ============================================================
# 自动登录配置
# ============================================================
# 自动登录天数选项的 data-time 值 ("3" 对应30天)
AUTO_LOGIN_DATA_TIME = "3"
