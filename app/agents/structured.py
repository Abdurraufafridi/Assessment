"""Shared parsing for structured LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredOutputError(ValueError):
    """Raised when an LLM response cannot be parsed into the requested model."""


def parse_model_output(raw_output: str, model: type[ModelT], *, agent_name: str) -> ModelT:
    """Parse a JSON object from an LLM response and validate it as ``model``."""

    text = raw_output.strip()
    if not text:
        raise StructuredOutputError(f"{agent_name} model returned an empty response")

    candidate = _unwrap_code_fence(text)
    payload = _load_json_object(candidate, agent_name=agent_name)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(f"{agent_name} output failed schema validation: {exc}") from exc


def _unwrap_code_fence(text: str) -> str:
    match = _CODE_FENCE_RE.match(text)
    return match.group(1).strip() if match else text


def _load_json_object(text: str, *, agent_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise StructuredOutputError(f"{agent_name} model did not return a JSON object") from exc
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(f"{agent_name} model returned malformed JSON") from exc

    if not isinstance(payload, dict):
        raise StructuredOutputError(f"{agent_name} model must return a JSON object")
    return payload


__all__ = ["StructuredOutputError", "parse_model_output"]
