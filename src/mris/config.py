"""Loads config/config.yaml once. Override the path with the MRIS_CONFIG environment variable."""
import os
from functools import lru_cache
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_config() -> dict:
    path = Path(os.environ.get("MRIS_CONFIG", ROOT / "config" / "config.yaml"))
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if os.environ.get("MRIS_LLM_MODE"):          # e.g. MRIS_LLM_MODE=mock
        cfg["llm"]["mode"] = os.environ["MRIS_LLM_MODE"]
    return cfg


@lru_cache(maxsize=1)
def get_signatures() -> dict:
    with open(ROOT / "config" / "gateway_signatures.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
