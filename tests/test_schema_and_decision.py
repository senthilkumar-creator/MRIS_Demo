from mris.decision.engine import decide
from mris.schema import (Decision, FetchStatus, FieldJudgement, LLMResult, RuleResult, SiteData)


def good_llm(**kw):
    base = dict(industry="Retail", mcc="5399", naics="452", industry_confidence=0.9,
                refund_ambiguous=FieldJudgement(value=False, confidence=0.9),
                delivery_risk=FieldJudgement(value=False, confidence=0.9),
                restricted_goods=FieldJudgement(value=False, confidence=0.9))
    base.update(kw)
    return LLMResult(**base)


def site(status=FetchStatus.OK):
    return SiteData(site_id=1, url="https://shop.test", domain="shop.test", status=status)


def test_clean_site_goes_automatic():
    r = decide(site(), RuleResult(has_terms=True, has_contact=True), good_llm())
    assert r.decision == Decision.NO_HUMAN_REVIEW and not any(r.flags.values())


def test_missing_terms_triggers_review():
    r = decide(site(), RuleResult(has_terms=False, has_contact=True), good_llm())
    assert r.decision == Decision.HUMAN_REVIEW and r.flags["no_terms_of_service"]


def test_low_confidence_triggers_review():
    llm = good_llm(refund_ambiguous=FieldJudgement(value=False, confidence=0.3))
    r = decide(site(), RuleResult(has_terms=True, has_contact=True), llm)
    assert r.decision == Decision.HUMAN_REVIEW


def test_invalid_llm_triggers_review():
    r = decide(site(), RuleResult(has_terms=True, has_contact=True), LLMResult(valid=False, error="bad json"))
    assert r.decision == Decision.HUMAN_REVIEW


def test_failed_fetch_triggers_review():
    r = decide(site(FetchStatus.TIMEOUT), RuleResult(), LLMResult(valid=False))
    assert r.decision == Decision.HUMAN_REVIEW and r.fetch_status == FetchStatus.TIMEOUT
