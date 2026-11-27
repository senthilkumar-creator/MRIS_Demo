from mris.llm.prompts import build_messages


def refund_prompt():
    messages = build_messages(
        "Sample merchant refund policy.",
        asked=["refund"]
    )
    return messages[-1]["content"]


def test_refund_output_fields():
    prompt = refund_prompt()
    assert "refund_ambiguous" in prompt
    assert "refund_conf" in prompt


def test_vague_refund_conditions():
    prompt = refund_prompt()
    assert "vague eligibility conditions" in prompt


def test_contradictory_refund_policy():
    prompt = refund_prompt()
    assert "contradictory statements" in prompt


def test_missing_refund_deadline():
    prompt = refund_prompt()
    assert "missing applicable refund deadlines" in prompt


def test_unclear_refund_procedure():
    prompt = refund_prompt()
    assert "unclear refund procedures" in prompt


def test_non_refundable_policy():
    prompt = refund_prompt()
    assert "not ambiguous solely" in prompt


def test_insufficient_refund_information():
    prompt = refund_prompt()
    assert "Return null with low confidence" in prompt


def test_truncated_website_text():
    prompt = refund_prompt()
    assert "website text may be truncated" in prompt


def test_only_refund_question_requested():
    prompt = refund_prompt()
    assert "refund_ambiguous" in prompt
    assert '"delivery_risk"' not in prompt
    assert '"restricted_goods"' not in prompt
    assert '"product_match"' not in prompt