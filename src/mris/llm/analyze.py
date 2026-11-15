"""Runs the LLM on one site and validates the answer. Owner: Member 4 (validation, retries)."""
import json
import re
from typing import Iterable, List, Optional

import httpx
from pydantic import ValidationError

from ..config import get_config
from ..industries import get_category, other_id
from ..processing.clean import text_for_llm
from ..schema import FieldJudgement, LLMResult, RuleResult, SiteData
from .client import chat_json
from .prompts import ALL_FIELDS, build_messages


def fields_to_ask(rules: Optional[RuleResult]) -> List[str]:
    """Ask the model only what the rules cannot settle."""
    fields = ["industry", "product_match", "restricted"]
    if rules is None or rules.refund_text_found:      # no refund text at all = rules already know (flag raised)
        fields.append("refund")
    if rules is None or rules.delivery_text_found:
        fields.append("delivery")
    return [f for f in ALL_FIELDS if f in fields]


def _num(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _bool(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, str):
        return {"true": True, "false": False}.get(v.strip().lower())
    return None


def parse_llm_json(raw: str, asked: Optional[Iterable[str]] = None) -> LLMResult:
    """Parse the model's short answer into LLMResult. Raises ValueError if it is not a JSON object."""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise ValueError("LLM answer is not a JSON object")
    asked = list(asked) if asked is not None else list(ALL_FIELDS)
    cat = get_category(d.get("industry_id"))
    if cat is None:                                    # missing or invalid number -> "Other or unclear", no confidence
        cat, ind_conf = get_category(other_id()), 0.0
    else:
        ind_conf = _num(d.get("industry_conf"))
    return LLMResult(
        industry_id=cat["id"], industry=cat["name"], mcc=cat["mcc"] or None, naics=cat["naics"] or None,
        physical_goods=bool(cat["physical"]), high_risk_category=bool(cat["high_risk"]),
        industry_confidence=ind_conf,
        product_matches_industry=_bool(d.get("product_match")), product_match_confidence=_num(d.get("product_conf")),
        refund_ambiguous=FieldJudgement(value=_bool(d.get("refund_ambiguous")), confidence=_num(d.get("refund_conf"))),
        delivery_risk=FieldJudgement(value=_bool(d.get("delivery_risk")), confidence=_num(d.get("delivery_conf"))),
        restricted_goods=FieldJudgement(value=_bool(d.get("restricted_goods")), confidence=_num(d.get("restricted_conf"))),
        asked=asked,
    )


async def analyze_site(client: httpx.AsyncClient, site: SiteData, rules: Optional[RuleResult] = None) -> LLMResult:
    """One structured LLM call; retry once if the answer is not valid JSON."""
    cfg = get_config()["llm"]
    text = text_for_llm(site, cfg["max_chars_per_site"])
    if not text.strip():
        return LLMResult(valid=False, error="no text to analyse")
    asked = fields_to_ask(rules)
    messages = build_messages(text, asked)
    last_error = ""
    for _ in range(2):
        try:
            return parse_llm_json(await chat_json(client, messages), asked)
        except (ValueError, ValidationError) as e:
            last_error = f"invalid LLM output: {type(e).__name__}"
        except httpx.HTTPError as e:
            last_error = f"LLM request failed: {type(e).__name__}"
    return LLMResult(valid=False, error=last_error)
