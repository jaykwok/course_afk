"""Validated AI configuration, loaded once for each exam batch."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import dotenv_values


class ExamAiConfigurationError(ValueError):
    """Configuration errors block AI operations, never application startup."""


def read_ai_environment() -> dict[str, str]:
    values = dotenv_values(Path(__file__).resolve().parents[2] / ".env", encoding="utf-8-sig")
    return {**{key: value for key, value in values.items() if value is not None}, **os.environ}


def validate_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    try:
        parsed = urlparse(value)
        parsed.port
    except ValueError as exc:
        raise ExamAiConfigurationError("AI 接口地址格式不正确") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ExamAiConfigurationError("AI 接口地址须为不含用户名、密码、查询参数或片段的 HTTP/HTTPS 地址")
    return value


def ai_is_configured(values: dict[str, str] | None = None) -> bool:
    values = read_ai_environment() if values is None else values
    required = [str(values.get(name, "")).strip() for name in ("OPENAI_COMPLETION_BASE_URL", "OPENAI_COMPLETION_API_KEY", "MODEL_NAME")]
    return all(required) and required[1].lower() not in {"your_api_key_here", "your-api-key", "sk-xxx", "changeme"}


@dataclass(frozen=True)
class AiSettings:
    base_url: str
    api_key: str
    model: str
    request_type: str = "responses"
    provider: str = "openai"
    output_mode: str = "prompt_json"
    web_search: bool = False
    thinking: bool = False
    reasoning_effort: str | None = None
    temperature: float | None = None
    request_timeout: float = 60
    total_timeout: float = 180
    max_retries: int = 2

    @classmethod
    def load(cls, values: dict[str, str] | None = None) -> "AiSettings":
        values = read_ai_environment() if values is None else values
        if not ai_is_configured(values):
            raise ExamAiConfigurationError("请在 .env 填写真实的 AI 接口地址、API Key 和 MODEL_NAME 后重试")

        def text(name, default=""):
            return str(values.get(name, default) or "").strip()

        def number(name, default, minimum, maximum, *, integer=False):
            try:
                value = float(text(name, str(default)))
            except ValueError as exc:
                raise ExamAiConfigurationError(f"{name} 必须是数值") from exc
            if not math.isfinite(value) or not minimum <= value <= maximum or (integer and not value.is_integer()):
                raise ExamAiConfigurationError(f"{name} 必须在 {minimum}–{maximum} 之间" + ("且为整数" if integer else ""))
            return int(value) if integer else value

        def flag(name):
            value = text(name, "0").lower()
            if value not in {"0", "1", "true", "false", "yes", "no", "on", "off"}:
                raise ExamAiConfigurationError(f"{name} 必须为 0/1 或 true/false")
            return value in {"1", "true", "yes", "on"}

        protocol = text("AI_REQUEST_TYPE", "responses").lower()
        provider = text("AI_PROVIDER", "openai").lower()
        output_mode = text("AI_OUTPUT_MODE", "prompt_json").lower()
        effort = text("AI_REASONING_EFFORT").lower() or None
        if protocol not in {"responses", "chat"}:
            raise ExamAiConfigurationError("AI_REQUEST_TYPE 仅支持 responses / chat")
        if provider not in {"openai", "compatible"}:
            raise ExamAiConfigurationError("AI_PROVIDER 仅支持 openai / compatible")
        if output_mode not in {"prompt_json", "json_schema"}:
            raise ExamAiConfigurationError("AI_OUTPUT_MODE 仅支持 prompt_json / json_schema")
        if effort not in {None, "none", "minimal", "low", "medium", "high", "xhigh"}:
            raise ExamAiConfigurationError("AI_REASONING_EFFORT 值不受支持")
        thinking, web_search = flag("AI_ENABLE_THINKING"), flag("AI_ENABLE_WEB_SEARCH")
        if provider == "openai" and thinking and effort is None:
            raise ExamAiConfigurationError("标准 OpenAI 协议请设置 AI_REASONING_EFFORT；enable_thinking 仅用于显式 compatible 配置")
        if provider == "openai" and protocol == "chat" and web_search:
            raise ExamAiConfigurationError("标准 OpenAI 的联网搜索请使用 responses；chat 的 enable_search 仅用于兼容服务")
        return cls(
            base_url=validate_base_url(text("OPENAI_COMPLETION_BASE_URL")), api_key=text("OPENAI_COMPLETION_API_KEY"), model=text("MODEL_NAME"),
            request_type=protocol, provider=provider, output_mode=output_mode, web_search=web_search, thinking=thinking, reasoning_effort=effort,
            temperature=number("AI_TEMPERATURE", 0, 0, 2) if text("AI_TEMPERATURE") else None,
            request_timeout=number("AI_REQUEST_TIMEOUT", 60, 1, 3600), total_timeout=number("AI_TOTAL_TIMEOUT", 180, 1, 3600), max_retries=number("AI_MAX_RETRIES", 2, 0, 5, integer=True),
        )

    def fingerprint(self) -> dict[str, object]:
        from core.exam.contracts import PROMPT_VERSION
        return {"model": self.model, "base_url": self.base_url, "provider": self.provider, "request_type": self.request_type, "output_mode": self.output_mode, "web_search": self.web_search, "thinking": self.thinking if self.provider == "compatible" and not self.reasoning_effort else False, "reasoning_effort": self.reasoning_effort, "temperature": self.temperature, "prompt_version": PROMPT_VERSION}
