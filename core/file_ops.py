import logging
import os
import re

from core.config import ZHIXUEYUN_COURSE_PREFIX, ZHIXUEYUN_SUBJECT_PREFIX


def del_file(filename):
    """删除文件(如果存在)"""
    if os.path.exists(filename):
        os.remove(filename)


def save_to_file(filename, url):
    """将链接保存到指定文件"""

    with open(filename, "a+", encoding="utf-8") as wp:
        logging.info(f"写入{filename}完毕\n")
        wp.write(f"{url}\n")


_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_BUSINESS_TYPE_MAP = {"1": "course", "2": "subject"}

# 根据配置的 URL 前缀生成合规正则
_COURSE_PREFIX_ESCAPED = re.escape(ZHIXUEYUN_COURSE_PREFIX)
_SUBJECT_PREFIX_ESCAPED = re.escape(ZHIXUEYUN_SUBJECT_PREFIX)
_COMPLIANT_URL_PATTERN = re.compile(
    rf"^({_COURSE_PREFIX_ESCAPED}|{_SUBJECT_PREFIX_ESCAPED}){_UUID}$"
)


def normalize_url(url):
    """
    将非标准学习链接转换为标准格式。

    支持的非标准格式:
    1. qrScan格式: .../qrScan?businessType=1&businessId=UUID...  →  .../course/detail/UUID
                    .../qrScan?businessType=2&businessId=UUID...  →  .../subject/detail/UUID
    2. detail带前缀格式: .../detail/11&UUID...  →  .../detail/UUID

    已是标准格式的链接原样返回。
    """
    # qrScan格式: 从查询参数中提取 businessType 和 businessId
    qr_match = re.search(
        rf"qrScan\?.*?businessType=(\d+).*?businessId=({_UUID})", url
    )
    if qr_match:
        btype = _BUSINESS_TYPE_MAP.get(qr_match.group(1))
        if btype:
            prefix = ZHIXUEYUN_COURSE_PREFIX if btype == "course" else ZHIXUEYUN_SUBJECT_PREFIX
            return f"{prefix}{qr_match.group(2)}"

    # detail带前缀格式: /detail/数字&UUID → /detail/UUID
    detail_match = re.search(
        rf"/detail/\d+&({_UUID})", url
    )
    if detail_match:
        prefix = url[: url.index("/detail/")]
        return f"{prefix}/detail/{detail_match.group(1)}"

    return url


def is_compliant_url_regex(url):
    """
    使用正则表达式判断URL是否符合指定的合规格式。

    合规格式: https://kc.zhixueyun.com/#/study/(course|subject)/detail/UUID
    """

    return bool(_COMPLIANT_URL_PATTERN.match(url))
