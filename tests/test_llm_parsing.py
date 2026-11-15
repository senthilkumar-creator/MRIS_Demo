import pytest
from mris.industries import categories, get_category
from mris.llm.analyze import fields_to_ask, parse_llm_json
from mris.llm.prompts import build_messages
from mris.schema import RuleResult

ANS = ('{"industry_id": 1, "industry_conf": 0.8, "product_match": true, "product_conf": 0.7, '
       '"refund_ambiguous": true, "refund_conf": 0.7, "delivery_risk": false, "delivery_conf": 0.9, '
       '"restricted_goods": "false", "restricted_conf": 0.95}')


def test_industry_number_is_looked_up_not_invented():
    r = parse_llm_json(ANS)
    assert r.industry == "Clothing and accessories" and r.mcc == "5691" and r.naics == "458110"
    assert r.restricted_goods.value is False and r.refund_ambiguous.value is True


def test_fenced_json_is_accepted():
    assert parse_llm_json("```json\n" + ANS + "\n```").industry_id == 1


def test_invalid_industry_number_becomes_other_with_zero_confidence():
    r = parse_llm_json('{"industry_id": 9999, "industry_conf": 0.99}')
    assert r.industry == "Other or unclear" and r.mcc is None and r.industry_confidence == 0.0


def test_garbage_and_bad_values():
    with pytest.raises(ValueError):
        parse_llm_json("not json at all")
    r = parse_llm_json('{"industry_id": 3, "industry_conf": "high", "refund_ambiguous": "maybe"}')
    assert r.industry_confidence == 0.0 and r.refund_ambiguous.value is None


def test_industry_table_is_consistent():
    cats = categories()
    assert len(cats) >= 50 and list(cats) == list(range(1, len(cats) + 1))
    assert get_category(len(cats))["name"] == "Other or unclear"
    assert any(c["high_risk"] for c in cats.values()) and any(c["physical"] for c in cats.values())


def test_only_unsettled_questions_are_asked():
    assert "refund" not in fields_to_ask(RuleResult(refund_text_found=False, delivery_text_found=True))
    assert "delivery" not in fields_to_ask(RuleResult(refund_text_found=True, delivery_text_found=False))
    assert fields_to_ask(None) == ["industry", "product_match", "refund", "delivery", "restricted"]


def test_prompt_structure():
    msg = build_messages("SITE TEXT HERE", ["industry"])[-1]["content"]
    assert msg.endswith("SITE TEXT HERE") and "refund_ambiguous" not in msg and "industry_id" in msg
    assert msg.index("Industries") < msg.index("SITE TEXT HERE")
