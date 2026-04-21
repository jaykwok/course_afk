from __future__ import annotations

import logging
import re
import traceback

from core.config import AI_RESPONSE_TOOLS, AI_SYSTEM_PROMPT, AI_TEMPERATURE


TYPE_LABELS = {
    "single": "单选题",
    "multiple": "多选题/不定项选择题",
    "judge": "判断题(请回答'正确'或'错误')",
    "ordering": "排序题(请按正确顺序给出选项字母, 如'ACBDEF')",
    "reading": "阅读理解题",
}

TYPE_HINTS = {
    "ordering": "请直接给出正确的排序顺序, 只需按字母顺序列出, 如'ACBDEF'。",
    "reading": "请直接回答选项代号(如A、B、C、D)。",
    "judge": "请直接回答'正确'或'错误'。",
}


def build_question_prompt(question_data) -> str:
    question_type_str = TYPE_LABELS.get(question_data["type"], "")
    options_str = "".join(
        f"{option['label']}. {option['text']}\n"
        for option in question_data["options"]
    )
    prompt = f"""
        请回答以下{question_type_str}：

        问题：{question_data['text']}

        选项：
        {options_str}
        """
    prompt += TYPE_HINTS.get(
        question_data["type"],
        "请直接回答选项代号(如A、B、C、D等), 不定项选择题、多选题可以选择多个选项。",
    )
    return prompt


def normalize_ai_answer_text(question_type: str, answer_text: str) -> list[str]:
    final_answer = (answer_text or "").strip()

    if question_type == "judge":
        lowered = final_answer.lower()
        if "正确" in lowered or "t" in lowered:
            return ["正确"]
        if "错误" in lowered or "f" in lowered:
            return ["错误"]
        logging.warning(f"无法识别的判断题答案: {final_answer}")
        return ["正确"]

    if question_type == "ordering":
        sequences = re.findall(r"[A-Z]+", final_answer)
        if sequences:
            return list(max(sequences, key=len))
        return re.findall(r"[A-Z]", final_answer)

    answers = re.findall(r"[A-Z]", final_answer)
    seen = set()
    return [x for x in answers if not (x in seen or seen.add(x))]


async def get_ai_answers(client, model, question_data):
    """使用AI分析题目并获取答案"""
    try:
        if question_data["type"] == "fill_blank":
            logging.info("检测到填空题, 将跳过自动作答")
            return []

        request_kwargs = {
            "model": model,
            "instructions": AI_SYSTEM_PROMPT,
            "input": build_question_prompt(question_data),
            "temperature": AI_TEMPERATURE,
        }
        if AI_RESPONSE_TOOLS:
            request_kwargs["tools"] = [tool.copy() for tool in AI_RESPONSE_TOOLS]

        response = client.responses.create(
            **request_kwargs,
        )
        answer_content = response.output_text
        logging.info(f"AI最终答案: {answer_content}")
        return normalize_ai_answer_text(question_data["type"], answer_content)
    except Exception as exc:
        logging.error(f"获取AI答案出错: {exc}")
        logging.error(traceback.format_exc())
        return []
