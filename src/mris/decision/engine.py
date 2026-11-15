"""Triage / decision engine. Owner: Member 4.

Routing rule (from the project design and the proposal):
    any risk flag  OR  low LLM confidence / invalid LLM output  OR  product-industry mismatch
    OR  young domain (configurable)  OR  fetch problem                          ->  HUMAN_REVIEW
    otherwise                                                                    ->  NO_HUMAN_REVIEW
Who decides what:
    rules: missing Terms of Service, missing contact, no refund text at all, domain age, checkout / gateways
    LLM:   industry (-> MCC / NAICS by lookup), product match, vague refund policy, delivery risk, restricted goods
Thresholds come from config/config.yaml and are tuned on the development set.
"""
from typing import List

from ..config import get_config
from ..schema import (BusinessInfo, Decision, FetchStatus, IndustryClassification, LLMResult, ProductIndustryMatch,
                      RiskFlags, RuleResult, SiteData, SiteResult)

FIELD_NAMES = {"industry": "industry classification", "product_match": "product / industry match",
               "refund": "refund policy", "delivery": "delivery timeline", "restricted": "restricted goods"}


def _pct(x: float) -> str:
    return f"{x:.2f}"


def decide(site: SiteData, rules: RuleResult, llm: LLMResult) -> SiteResult:
    cfg = get_config()["decision"]
    thr = cfg["confidence_threshold"]
    reasons: List[str] = []
    causes: List[str] = []           # short phrases for llm_validation_notes
    flags = RiskFlags()
    industry, match = IndustryClassification(), ProductIndustryMatch()
    low_conf: List[str] = []

    fetch_problem = site.status != FetchStatus.OK
    if fetch_problem:
        reasons.append(f"Could not assess site properly: fetch status '{site.status.value}'"
                       + (f" ({site.error})" if site.error else ""))
        causes.append(f"fetch problem ({site.status.value})")
    else:
        # ---------- rule-based flags (certain) ----------
        flags.missing_terms_of_service = not rules.has_terms
        flags.missing_contact_info = not rules.has_contact
        if flags.missing_terms_of_service:
            reasons.append("No Terms of Service found"); causes.append("missing Terms of Service")
        if flags.missing_contact_info:
            reasons.append("No contact information found"); causes.append("missing contact information")
        if not rules.refund_text_found:
            flags.ambiguous_refund_policy = True
            reasons.append("No refund or return policy found on the site"); causes.append("missing refund policy")

        if llm.valid:
            # ---------- industry + product match ----------
            industry = IndustryClassification(mcc=llm.mcc, naics=llm.naics, description=llm.industry,
                                              confidence_score=llm.industry_confidence)
            if llm.industry_confidence < thr:
                low_conf.append("industry")
            match = ProductIndustryMatch(
                is_match=llm.product_matches_industry, confidence_score=llm.product_match_confidence,
                details=("Products and services appear to match '%s'." % llm.industry if llm.product_matches_industry is True
                         else "Site content does not clearly match '%s'." % llm.industry if llm.product_matches_industry is False
                         else "Could not determine whether the products match the industry."))
            if llm.product_match_confidence < thr:
                low_conf.append("product_match")
            if llm.product_matches_industry is False:
                reasons.append("Product catalog does not fully align with selected NAICS code"
                               f" (Confidence: {_pct(llm.product_match_confidence)})")
                causes.append("product / industry mismatch")

            # ---------- LLM judgements ----------
            if "refund" in llm.asked:
                if llm.refund_ambiguous.value is True:
                    flags.ambiguous_refund_policy = True
                    reasons.append(f"Ambiguous refund policy detected (Confidence: {_pct(llm.refund_ambiguous.confidence)})")
                    causes.append("ambiguous refund policy")
                if llm.refund_ambiguous.confidence < thr:
                    low_conf.append("refund")
            if "delivery" in llm.asked:
                if llm.delivery_risk.value is True:
                    flags.delayed_delivery = True
                    reasons.append(f"Delivery timeline risk detected (Confidence: {_pct(llm.delivery_risk.confidence)})")
                    causes.append("delivery timeline risk")
                if llm.delivery_risk.confidence < thr:
                    low_conf.append("delivery")
            elif llm.physical_goods and not rules.delivery_text_found:
                flags.delayed_delivery = True
                reasons.append("No delivery information found for a site selling physical goods")
                causes.append("missing delivery information")
            if llm.restricted_goods.value is True:
                flags.restricted_goods = True
                reasons.append(f"Possible restricted goods (Confidence: {_pct(llm.restricted_goods.confidence)})")
                causes.append("possible restricted goods")
            elif llm.high_risk_category:
                flags.restricted_goods = True
                reasons.append(f"Industry category is restricted or high risk: {llm.industry}")
                causes.append("high-risk industry category")
            if llm.restricted_goods.confidence < thr:
                low_conf.append("restricted")
        else:
            reasons.append(f"LLM answer unusable: {llm.error}")
            causes.append("invalid LLM output")
            if rules.restricted_keyword_hits:       # be cautious when the LLM could not confirm
                flags.restricted_goods = True
                reasons.append("Restricted-goods keywords found: " + ", ".join(rules.restricted_keyword_hits))

        if low_conf:
            reasons.append("Low LLM confidence: " + ", ".join(FIELD_NAMES[f] for f in low_conf))
            causes.append("low confidence in " + ", ".join(FIELD_NAMES[f] for f in low_conf))

    young = bool(rules.young_domain) and not fetch_problem
    if young:
        reasons.append(f"Young domain ({rules.domain_age_days} days old)")
        if cfg.get("review_on_young_domain", True):
            causes.append("young domain age")
    young_trigger = young and cfg.get("review_on_young_domain", True)

    review = (fetch_problem or not llm.valid or any(flags.model_dump().values()) or bool(low_conf)
              or llm.product_matches_industry is False or young_trigger)
    if review:
        notes = "Pushed to human review due to " + "; ".join(causes) + "."
    else:
        notes = f"All LLM fields at or above the {thr} confidence threshold; no risk flags raised."
    if fetch_problem:
        notes += " The LLM was not run because the site could not be fetched properly."

    return SiteResult(
        url=site.url,
        routing_decision=Decision.HUMAN_REVIEW if review else Decision.NO_HUMAN_REVIEW,
        requires_human_review=review,
        review_reasons=reasons,
        has_working_checkout=rules.checkout_detected,
        detected_gateways=rules.gateways_found,
        industry_classification=industry,
        product_industry_match=match,
        risk_flags=flags,
        business_info=BusinessInfo(domain_age_days=rules.domain_age_days, location=rules.declared_location),
        llm_validation_notes=notes,
        fetch_status=site.status, error=site.error,
    )
