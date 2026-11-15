"""LLM client. Owner: Member 3 (setup + latency test).

Modes (config/config.yaml  llm.mode, or the MRIS_LLM_MODE environment variable):
  "ollama": a local Ollama server (https://ollama.com).   ollama pull llama3.1:8b
  "openai": any server that speaks the OpenAI chat API: hosted providers (for example Google Gemini or Groq
            through their OpenAI-compatible endpoints) or a local server such as vLLM / LM Studio.
            Set llm.base_url, llm.model and the API key in the environment variable MRIS_LLM_API_KEY.
  "mock":   a fixed, valid answer so the rest of the pipeline can be built and tested without any model.
"""
import json
import os
import re
import httpx
from ..config import get_config
from ..industries import categories


async def chat_json(client: httpx.AsyncClient, messages: list) -> str:
    """Return the raw JSON text produced by the model."""
    cfg = get_config()["llm"]
    mode = cfg["mode"]
    if mode == "mock":
        return _mock_answer(messages[-1]["content"])
    if mode == "openai":
        headers = {"Authorization": "Bearer " + os.environ.get("MRIS_LLM_API_KEY", "")}
        body = {"model": cfg["model"], "messages": messages, "temperature": cfg["temperature"],
                "max_tokens": cfg.get("max_output_tokens", 120), "response_format": {"type": "json_object"}}
        if cfg.get("reasoning_effort"):          # "thinking" models: keep reasoning small so the answer is not cut off
            body["reasoning_effort"] = cfg["reasoning_effort"]
        r = await client.post(cfg["base_url"].rstrip("/") + "/chat/completions", headers=headers,
                              timeout=cfg["timeout_seconds"], json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]
    r = await client.post(
        cfg["base_url"].rstrip("/") + "/api/chat",
        json={
            "model": cfg["model"],
            "messages": messages,
            "stream": False,
            "format": "json",                         # ask Ollama for valid JSON
            "options": {"temperature": cfg["temperature"], "num_predict": cfg.get("max_output_tokens", 120)},
        },
        timeout=cfg["timeout_seconds"],
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _mock_answer(prompt: str) -> str:
    """Fake model for tests: looks only at the website text, not at the instructions."""
    low = prompt.split("Website text (may be cut off):", 1)[-1].lower()
    cats = categories()
    general = next((i for i, c in cats.items() if c["name"].startswith("Online marketplace")), max(cats))
    cat = general
    if any(w in low for w in ("firearm", "ammunition")):
        cat = next(i for i, c in cats.items() if c["name"].startswith("Firearms"))
    ans = {"industry_id": cat, "industry_conf": 0.9, "product_match": True, "product_conf": 0.9,
           "refund_ambiguous": False, "refund_conf": 0.85, "delivery_risk": False, "delivery_conf": 0.85,
           "restricted_goods": any(w in low for w in ("firearm", "ammunition", "counterfeit")), "restricted_conf": 0.9}
    return json.dumps(ans)
