import logging
import sys
from datetime import datetime


def setup_logging(log_file="log.txt"):
    """统一日志配置, 所有脚本共用, 追加模式保留历史日志"""

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    # 启动分隔线: 记录启动时间和脚本文件名
    script_name = sys.argv[0] if sys.argv[0] else "unknown"
    separator = f"\n{'='*60}\n[启动] {script_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}"
    logging.info(separator)
