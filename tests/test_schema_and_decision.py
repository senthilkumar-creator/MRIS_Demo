from mris.decision.engine import decide
from mris.schema import Decision, FetchStatus, FieldJudgement, LLMResult, RuleResult, SiteData

ALL = ["industry", "product_match", "refund", "delivery", "restricted"]


def good_llm(**kw):
    base = dict(industry_id=10, industry="Online marketplace or mixed general goods", mcc="5399", naics="455219",
                physical_goods=True, industry_confidence=0.9, product_matches_industry=True, product_match_confidence=0.9,
                refund_ambiguous=FieldJudgement(value=False, confidence=0.9),
                delivery_risk=FieldJudgement(value=False, confidence=0.9),
                restricted_goods=FieldJudgement(value=False, confidence=0.9), asked=ALL)
    base.update(kw)
    return LLMResult(**base)


def good_rules(**kw):
    base = dict(has_terms=True, has_contact=True, refund_text_found=True, delivery_text_found=True)
    base.update(kw)
    return RuleResult(**base)


def site(status=FetchStatus.OK):
    return SiteData(site_id=1, url="https://shop.test", domain="shop.test", status=status)


def test_clean_site_goes_automatic():
    r = decide(site(), good_rules(), good_llm())
    assert r.routing_decision == Decision.NO_HUMAN_REVIEW and not r.requires_human_review
    assert not any(r.risk_flags.model_dump().values())
    assert r.industry_classification.mcc == "5399" and "confidence threshold" in r.llm_validation_notes


def test_missing_terms_triggers_review():
    r = decide(site(), good_rules(has_terms=False), good_llm())
    assert r.requires_human_review and r.risk_flags.missing_terms_of_service


def test_no_refund_text_is_flagged_by_rules_without_llm_answer():
    llm = good_llm(asked=["industry", "product_match", "delivery", "restricted"])   # refund not asked
    r = decide(site(), good_rules(refund_text_found=False), llm)
    assert r.risk_flags.ambiguous_refund_policy and r.requires_human_review
    assert not any("Low LLM confidence" in x for x in r.review_reasons)           # not asked -> no confidence penalty


def test_llm_says_refund_ambiguous():
    llm = good_llm(refund_ambiguous=FieldJudgement(value=True, confidence=0.65))
    r = decide(site(), good_rules(), llm)
    assert r.risk_flags.ambiguous_refund_policy
    assert any("Ambiguous refund policy detected (Confidence: 0.65)" in x for x in r.review_reasons)
    assert "low confidence" in r.llm_validation_notes


def test_no_delivery_info_for_physical_goods():
    llm = good_llm(asked=["industry", "product_match", "refund", "restricted"])
    r = decide(site(), good_rules(delivery_text_found=False), llm)
    assert r.risk_flags.delayed_delivery


def test_high_risk_category_sets_restricted_flag():
    r = decide(site(), good_rules(), good_llm(high_risk_category=True, industry="Firearms, ammunition and weapons"))
    assert r.risk_flags.restricted_goods and r.requires_human_review


def test_product_mismatch_triggers_review():
    r = decide(site(), good_rules(), good_llm(product_matches_industry=False))
    assert r.requires_human_review and any("does not fully align" in x for x in r.review_reasons)


def test_young_domain_triggers_review_by_default():
    r = decide(site(), good_rules(domain_age_days=12, young_domain=True), good_llm())
    assert r.requires_human_review and "young domain" in r.llm_validation_notes
    assert r.business_info.domain_age_days == 12


def test_low_confidence_triggers_review():
    r = decide(site(), good_rules(), good_llm(product_match_confidence=0.3))
    assert r.requires_human_review


def test_invalid_llm_triggers_review():
    r = decide(site(), good_rules(), LLMResult(valid=False, error="bad json"))
    assert r.requires_human_review and "invalid LLM output" in r.llm_validation_notes


def test_failed_fetch_triggers_review():
    r = decide(site(FetchStatus.TIMEOUT), RuleResult(), LLMResult(valid=False))
    assert r.requires_human_review and r.fetch_status == FetchStatus.TIMEOUT


def test_output_matches_proposal_example_keys():
    d = decide(site(), good_rules(), good_llm()).model_dump(mode="json")
    for key in ["url", "routing_decision", "requires_human_review", "review_reasons", "has_working_checkout",
                "detected_gateways", "industry_classification", "product_industry_match", "risk_flags",
                "business_info", "llm_validation_notes"]:
        assert key in d
    assert set(d["risk_flags"]) == {"missing_terms_of_service", "ambiguous_refund_policy", "delayed_delivery",
                                    "restricted_goods", "missing_contact_info"}
    assert set(d["industry_classification"]) == {"mcc", "naics", "description", "confidence_score"}
    assert set(d["product_industry_match"]) == {"is_match", "confidence_score", "details"}
    assert set(d["business_info"]) == {"domain_age_days", "location"}
