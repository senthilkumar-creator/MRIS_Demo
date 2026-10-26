"""Runs the LLM on one site and validates the answer. Owner: Member 4 (validation, retries)."""
import json
import re
import httpx
from pydantic import ValidationError

from ..config import get_config
from ..processing.clean import text_for_llm
from ..schema import LLMResult, SiteData
from .client import chat_json
from .prompts import build_messages


def parse_llm_json(raw: str) -> LLMResult:
    """Parse model output into LLMResult. Raises ValueError / ValidationError if unusable."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()   # remove code fences
    data = json.loads(raw)
    return LLMResult.model_validate(data)


async def analyze_site(client: httpx.AsyncClient, site: SiteData) -> LLMResult:
    """One structured LLM call; retry once if the answer is not valid JSON."""
    cfg = get_config()["llm"]
    text = text_for_llm(site, cfg["max_chars_per_site"])
    if not text.strip():
        return LLMResult(valid=False, error="no text to analyse")
    messages = build_messages(text)
    last_error = ""
    for _ in range(2):
        try:
            return parse_llm_json(await chat_json(client, messages))
        except (ValueError, ValidationError) as e:
            last_error = f"invalid LLM output: {type(e).__name__}"
        except httpx.HTTPError as e:
            last_error = f"LLM request failed: {type(e).__name__}"
    return LLMResult(valid=False, error=last_error)
