import pytest
from mris.llm.analyze import parse_llm_json


def test_parses_fenced_json():
    raw = '```json\n{"industry": "Retail", "mcc": "5399", "industry_confidence": 0.8}\n```'
    assert parse_llm_json(raw).industry == "Retail"


def test_rejects_garbage():
    with pytest.raises(ValueError):
        parse_llm_json("not json at all")
