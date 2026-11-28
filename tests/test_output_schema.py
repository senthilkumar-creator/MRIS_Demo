"""Tests for structured JSON output and proposal schema compatibility."""

import json

import pytest
from pydantic import ValidationError

from mris.decision.engine import decide
from mris.schema import (
    AssessResponse,
    Decision,
    FetchStatus,
    FieldJudgement,
    IndustryClassification,
    LLMResult,
    ProductIndustryMatch,
    RiskConfidence,
    RuleResult,
    SiteData,
    SiteResult,
)


def sample_site(**kwargs):
    data = {
        "site_id": 1,
        "url": "https://example-store.com",
        "domain": "example-store.com",
    }
    data.update(kwargs)
    return SiteData(**data)


def sample_rules(**kwargs):
    data = {
        "has_terms": True,
        "has_contact": True,
        "refund_text_found": True,
        "delivery_text_found": True,
        "checkout_detected": True,
        "gateways_found": ["Helcim", "Shopify"],
        "domain_age_days": 365,
        "declared_location": "Calgary, AB, Canada",
    }
    data.update(kwargs)
    return RuleResult(**data)


def sample_llm(**kwargs):
    data = {
        "industry": "Apparel and Accessories",
        "mcc": "5691",
        "naics": "448140",
        "physical_goods": True,
        "industry_confidence": 0.95,
        "product_matches_industry": True,
        "product_match_confidence": 0.92,
        "refund_ambiguous": FieldJudgement(
            value=False, confidence=0.91
        ),
        "delivery_risk": FieldJudgement(
            value=False, confidence=0.93
        ),
        "restricted_goods": FieldJudgement(
            value=False, confidence=0.94
        ),
        "asked": [
            "industry",
            "product_match",
            "refund",
            "delivery",
            "restricted",
        ],
    }
    data.update(kwargs)
    return LLMResult(**data)


# Check that all fields required by the proposal are present.
def test_proposal_json_structure():
    result = decide(
        sample_site(), sample_rules(), sample_llm()
    ).model_dump(mode="json")

    expected_keys = {
        "url",
        "routing_decision",
        "requires_human_review",
        "review_reasons",
        "has_working_checkout",
        "detected_gateways",
        "industry_classification",
        "product_industry_match",
        "risk_flags",
        "business_info",
        "llm_validation_notes",
    }

    additional_keys = {
        "risk_confidence",
        "fetch_status",
        "error",
    }

    assert set(result) == expected_keys | additional_keys

    assert set(result["industry_classification"]) == {
        "mcc", "naics", "description", "confidence_score"
    }

    assert set(result["product_industry_match"]) == {
        "is_match", "confidence_score", "details"
    }

    assert set(result["risk_flags"]) == {
        "missing_terms_of_service",
        "ambiguous_refund_policy",
        "delayed_delivery",
        "restricted_goods",
        "missing_contact_info",
    }

    assert set(result["business_info"]) == {
        "domain_age_days", "location"
    }

    assert set(result["risk_confidence"]) == {
        "ambiguous_refund_policy",
        "delayed_delivery",
        "restricted_goods",
    }


# Verify the data types returned in JSON.
def test_json_data_types():
    result = decide(
        sample_site(), sample_rules(), sample_llm()
    ).model_dump(mode="json")

    assert isinstance(result["url"], str)
    assert isinstance(result["routing_decision"], str)
    assert isinstance(result["requires_human_review"], bool)
    assert isinstance(result["review_reasons"], list)
    assert isinstance(result["has_working_checkout"], bool)
    assert isinstance(result["detected_gateways"], list)
    assert isinstance(result["llm_validation_notes"], str)

    assert all(
        isinstance(reason, str)
        for reason in result["review_reasons"]
    )

    assert all(
        isinstance(gateway, str)
        for gateway in result["detected_gateways"]
    )

    assert all(
        isinstance(flag, bool)
        for flag in result["risk_flags"].values()
    )

    industry = result["industry_classification"]
    assert isinstance(industry["mcc"], str)
    assert isinstance(industry["naics"], str)
    assert isinstance(industry["description"], str)
    assert isinstance(industry["confidence_score"], float)

    match = result["product_industry_match"]
    assert isinstance(match["is_match"], bool)
    assert isinstance(match["confidence_score"], float)
    assert isinstance(match["details"], str)

    business = result["business_info"]
    assert type(business["domain_age_days"]) is int
    assert isinstance(business["location"], str)


# Verify that rule and LLM values reach the final output.
def test_output_field_values():
    result = decide(
        sample_site(), sample_rules(), sample_llm()
    )

    assert result.url == "https://example-store.com"
    assert result.has_working_checkout is True
    assert result.detected_gateways == ["Helcim", "Shopify"]

    assert result.industry_classification.mcc == "5691"
    assert result.industry_classification.naics == "448140"
    assert result.industry_classification.description == (
        "Apparel and Accessories"
    )
    assert result.industry_classification.confidence_score == 0.95

    assert result.product_industry_match.is_match is True
    assert result.product_industry_match.confidence_score == 0.92

    assert result.business_info.domain_age_days == 365
    assert result.business_info.location == "Calgary, AB, Canada"


# Confidence scores should remain available for safe assessments.
def test_confidence_scores_without_risk():
    result = decide(
        sample_site(), sample_rules(), sample_llm()
    )

    assert not any(result.risk_flags.model_dump().values())

    assert result.risk_confidence.model_dump() == {
        "ambiguous_refund_policy": 0.91,
        "delayed_delivery": 0.93,
        "restricted_goods": 0.94,
    }


# Confidence scores should also be available for detected risks.
def test_confidence_scores_with_risk():
    llm = sample_llm(
        refund_ambiguous=FieldJudgement(
            value=True, confidence=0.65
        ),
        delivery_risk=FieldJudgement(
            value=True, confidence=0.85
        ),
        restricted_goods=FieldJudgement(
            value=True, confidence=0.88
        ),
    )

    result = decide(sample_site(), sample_rules(), llm)

    assert result.risk_flags.ambiguous_refund_policy is True
    assert result.risk_flags.delayed_delivery is True
    assert result.risk_flags.restricted_goods is True

    assert result.risk_confidence.model_dump() == {
        "ambiguous_refund_policy": 0.65,
        "delayed_delivery": 0.85,
        "restricted_goods": 0.88,
    }

    assert result.requires_human_review is True


# Rule-based assessments should not have invented LLM confidence.
def test_skipped_llm_assessments_have_null_confidence():
    rules = sample_rules(
        refund_text_found=False,
        delivery_text_found=False,
    )

    llm = sample_llm(
        asked=["industry", "product_match", "restricted"]
    )

    result = decide(
        sample_site(), rules, llm
    ).model_dump(mode="json")

    assert result["risk_confidence"]["ambiguous_refund_policy"] is None
    assert result["risk_confidence"]["delayed_delivery"] is None
    assert result["risk_confidence"]["restricted_goods"] == 0.94

    assert result["risk_flags"]["ambiguous_refund_policy"] is True
    assert result["risk_flags"]["delayed_delivery"] is True


# Preserve confidence even when an LLM judgement is inconclusive.
def test_inconclusive_assessment_confidence():
    llm = sample_llm(
        refund_ambiguous=FieldJudgement(
            value=None, confidence=0.4
        )
    )

    result = decide(sample_site(), sample_rules(), llm)

    assert result.risk_confidence.ambiguous_refund_policy == 0.4
    assert result.requires_human_review is True


# Missing business information should be represented as null.
def test_missing_business_information():
    rules = sample_rules(
        domain_age_days=None,
        declared_location=None,
    )

    result = decide(
        sample_site(), rules, sample_llm()
    ).model_dump(mode="json")

    assert result["business_info"]["domain_age_days"] is None
    assert result["business_info"]["location"] is None


# Invalid LLM responses should not expose usable risk confidence.
def test_invalid_llm_output():
    llm = LLMResult(
        valid=False,
        error="Invalid LLM response",
    )

    result = decide(
        sample_site(), sample_rules(), llm
    ).model_dump(mode="json")

    assert result["routing_decision"] == "HUMAN_REVIEW"
    assert result["requires_human_review"] is True

    assert all(
        score is None
        for score in result["risk_confidence"].values()
    )

    assert result["industry_classification"]["mcc"] is None
    assert result["product_industry_match"]["is_match"] is None


# Failed website assessments must still return structured JSON.
def test_failed_fetch_output():
    site = sample_site(
        status=FetchStatus.TIMEOUT,
        error="Connection timed out",
    )

    result = decide(
        site,
        RuleResult(),
        LLMResult(valid=False),
    ).model_dump(mode="json")

    assert result["routing_decision"] == "HUMAN_REVIEW"
    assert result["requires_human_review"] is True
    assert result["fetch_status"] == "timeout"
    assert result["error"] == "Connection timed out"
    assert result["review_reasons"]

    assert all(
        score is None
        for score in result["risk_confidence"].values()
    )


# Confidence values outside the accepted range must be rejected.
@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_invalid_industry_confidence(score):
    with pytest.raises(ValidationError):
        IndustryClassification(confidence_score=score)


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_invalid_product_match_confidence(score):
    with pytest.raises(ValidationError):
        ProductIndustryMatch(confidence_score=score)


@pytest.mark.parametrize(
    "field",
    [
        "ambiguous_refund_policy",
        "delayed_delivery",
        "restricted_goods",
    ],
)
@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_invalid_risk_confidence(field, score):
    with pytest.raises(ValidationError):
        RiskConfidence(**{field: score})


# Both ends of the confidence range should be accepted.
@pytest.mark.parametrize("score", [0.0, 1.0])
def test_valid_confidence_boundaries(score):
    industry = IndustryClassification(confidence_score=score)
    match = ProductIndustryMatch(confidence_score=score)

    risk = RiskConfidence(
        ambiguous_refund_policy=score,
        delayed_delivery=score,
        restricted_goods=score,
    )

    assert industry.confidence_score == score
    assert match.confidence_score == score

    assert all(
        value == score
        for value in risk.model_dump().values()
    )


# Verify that the output can be converted to JSON and restored.
def test_json_serialization_round_trip():
    result = decide(
        sample_site(), sample_rules(), sample_llm()
    )

    json_output = result.model_dump_json()
    parsed = json.loads(json_output)

    assert parsed == result.model_dump(mode="json")

    restored = SiteResult.model_validate_json(json_output)
    assert restored == result


# Verify the structure of a response containing multiple websites.
def test_batch_response_structure():
    first = decide(
        sample_site(), sample_rules(), sample_llm()
    )

    second = decide(
        sample_site(
            site_id=2,
            url="https://another-store.com",
            domain="another-store.com",
        ),
        sample_rules(has_terms=False),
        sample_llm(),
    )

    response = AssessResponse(
        count=2,
        elapsed_seconds=0.5,
        results=[first, second],
    )

    data = response.model_dump(mode="json")

    assert set(data) == {
        "count", "elapsed_seconds", "results"
    }

    assert data["count"] == len(data["results"])
    assert data["elapsed_seconds"] >= 0

    assert data["results"][0]["routing_decision"] == (
        "NO_HUMAN_REVIEW"
    )
    assert data["results"][1]["routing_decision"] == (
        "HUMAN_REVIEW"
    )


# Routing labels and Boolean review requirements must agree.
@pytest.mark.parametrize("has_terms", [True, False])
def test_routing_decision_consistency(has_terms):
    result = decide(
        sample_site(),
        sample_rules(has_terms=has_terms),
        sample_llm(),
    )

    assert result.requires_human_review == (
        result.routing_decision == Decision.HUMAN_REVIEW
    )