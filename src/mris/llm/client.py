"""LLM client. Owner: Member 3 (setup + latency test).

mode "ollama": calls a local Ollama server (https://ollama.com). Setup:
    ollama pull llama3.1:8b          # then keep `ollama serve` running
mode "mock":   returns a fixed, valid answer so the rest of the pipeline can be built and tested
               without a model. Switch with config.yaml or MRIS_LLM_MODE=mock.
"""
import json
import httpx
from ..config import get_config


async def chat_json(client: httpx.AsyncClient, messages: list) -> str:
    """Return the raw JSON text produced by the model."""
    cfg = get_config()["llm"]
    if cfg["mode"] == "mock":
        return _mock_answer(messages[-1]["content"])
    r = await client.post(
        cfg["base_url"].rstrip("/") + "/api/chat",
        json={
            "model": cfg["model"],
            "messages": messages,
            "stream": False,
            "format": "json",                         # ask Ollama for valid JSON
            "options": {"temperature": cfg["temperature"]},
        },
        timeout=cfg["timeout_seconds"],
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _mock_answer(prompt: str) -> str:
    # look only at the website text, not at the instructions (which mention these words as examples)
    parts = prompt.split('"""')
    low = (parts[1] if len(parts) > 2 else prompt).lower()
    restricted = any(w in low for w in ("firearm", "ammunition", "counterfeit"))
    refund_unclear = "refund" not in low and "return" not in low
    return json.dumps({
        "industry": "General retail", "mcc": "5399", "naics": "452",
        "industry_confidence": 0.9, "product_matches_industry": True, "product_match_confidence": 0.9,
        "refund_ambiguous": {"value": refund_unclear, "confidence": 0.85, "evidence": ""},
        "delivery_risk": {"value": False, "confidence": 0.85, "evidence": ""},
        "restricted_goods": {"value": restricted, "confidence": 0.9, "evidence": ""},
    })
