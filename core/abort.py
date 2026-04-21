class UserAbortRequested(Exception):
    """用户主动终止当前流程，调用方应按正常退出处理。"""

