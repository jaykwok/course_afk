import logging


def setup_logging(log_file="log.txt", mode="w"):
    """统一日志配置，所有脚本共用"""

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s) %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode=mode, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
