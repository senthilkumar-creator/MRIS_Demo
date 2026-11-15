"""Fixed industry list (config/industries.yaml): the LLM picks a number, the code supplies the codes."""
from functools import lru_cache
from typing import Dict, Optional
import yaml
from .config import ROOT


@lru_cache(maxsize=1)
def categories() -> Dict[int, dict]:
    with open(ROOT / "config" / "industries.yaml", encoding="utf-8") as f:
        return {c["id"]: c for c in yaml.safe_load(f)["categories"]}


def get_category(cat_id) -> Optional[dict]:
    try:
        return categories().get(int(cat_id))
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def prompt_list() -> str:
    """Numbered list shown to the model, one short line per category."""
    return "\n".join(f"{c['id']} {c['name']}" for c in categories().values())


def other_id() -> int:
    return max(categories())
