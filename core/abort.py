class UserAbortRequested(Exception):
    """用户主动终止当前流程，调用方应按正常退出处理。"""

    def __init__(self, message: str = "", *, save_pending_urls: bool = True):
        super().__init__(message)
        self.save_pending_urls = save_pending_urls
