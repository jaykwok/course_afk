import logging

# 题型关键词映射
QUESTION_TYPE_MAP = {
    "单选题": "single",
    "多选题": "multiple",
    "不定项选择": "multiple",
    "判断题": "judge",
    "填空题": "fill_blank",
    "排序题": "ordering",
    "阅读理解题": "reading",
}


def parse_question_type(type_text: str) -> str:
    """根据题型文本解析题目类型"""
    for keyword, qtype in QUESTION_TYPE_MAP.items():
        if keyword in type_text:
            return qtype
    return "unknown"


async def detect_question_type_by_dom(locator) -> str:
    """通过 DOM 结构检测题型(文本解析失败时的后备方案)"""
    if await locator.locator("form.vertical .sentence-input").count() > 0:
        return "fill_blank"
    if await locator.locator(".answer-input-shot").count() > 0:
        return "ordering"
    return "unknown"


async def extract_options(locator, question_type: str) -> list[dict]:
    """
    从题目容器中提取选项列表。

    Args:
        locator: 题目容器的 Playwright Locator(单题模式为 page, 多题模式为 question_item)
        question_type: 题目类型字符串
    """
    options = []

    if question_type == "fill_blank":
        logging.info("检测到填空题, 跳过选项提取")
        return options

    if question_type == "ordering":
        option_elements = locator.locator(".preview-list dd")
        count = await option_elements.count()
        for i in range(count):
            option_element = option_elements.nth(i)
            option_label = await option_element.locator(".option-num").inner_text()
            option_text = await option_element.locator(".answer-options").inner_text()
            options.append(
                {
                    "label": option_label.strip().replace(".", ""),
                    "text": option_text.strip(),
                }
            )
        return options

    if question_type == "judge":
        judge_options = locator.locator(".preview-list dd span.pointer")
        # 多题模式下选择器稍有不同
        if await judge_options.count() == 0:
            judge_options = locator.locator(".preview-list dd .pointer")
        count = await judge_options.count()
        for i in range(count):
            option_text = await judge_options.nth(i).inner_text()
            options.append(
                {
                    "label": "T" if "正确" in option_text else "F",
                    "text": option_text.strip(),
                }
            )
        return options

    # 单选题、多选题、阅读理解题
    option_elements = locator.locator(".preview-list dd")
    count = await option_elements.count()
    for i in range(count):
        option_element = option_elements.nth(i)
        option_label = await option_element.locator(".option-num").inner_text()
        option_text = await option_element.locator(".answer-options").inner_text()
        options.append(
            {
                "label": option_label.strip().replace(".", ""),
                "text": option_text.strip(),
            }
        )

    return options
