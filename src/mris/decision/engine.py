"""Triage / decision engine. Owner: Member 4.

Routing rule (from the project design):
    any risk flag  OR  low LLM confidence / invalid LLM output  OR  fetch problem   ->  HUMAN_REVIEW
    otherwise                                                                        ->  NO_HUMAN_REVIEW
Thresholds come from config/config.yaml and are tuned on the development set.
"""
from ..config import get_config
from ..schema import Decision, FetchStatus, Flag, LLMResult, RuleResult, SiteData, SiteResult


def decide(site: SiteData, rules: RuleResult, llm: LLMResult) -> SiteResult:
    cfg = get_config()["decision"]
    thr = cfg["confidence_threshold"]
    reasons: list = []
    flags = {f.value: False for f in Flag}
    conf = {}

    fetch_problem = site.status != FetchStatus.OK
    if fetch_problem:
        reasons.append(f"Could not assess site properly: fetch status '{site.status.value}'"
                       + (f" ({site.error})" if site.error else ""))

    if not fetch_problem:
        # --- flags from rules ---
        flags[Flag.NO_TERMS_OF_SERVICE.value] = not rules.has_terms
        flags[Flag.MISSING_CONTACT.value] = not rules.has_contact
        # --- flags from the LLM (True only when the model says so) ---
        if llm.valid:
            flags[Flag.AMBIGUOUS_REFUND.value] = llm.refund_ambiguous.value is True
            flags[Flag.DELAYED_DELIVERY.value] = llm.delivery_risk.value is True
            flags[Flag.RESTRICTED_GOODS.value] = llm.restricted_goods.value is True
            conf = {
                "industry": llm.industry_confidence,
                "refund_ambiguous": llm.refund_ambiguous.confidence,
                "delivery_risk": llm.delivery_risk.confidence,
                "restricted_goods": llm.restricted_goods.confidence,
            }
        else:
            reasons.append(f"LLM answer unusable: {llm.error}")
            if rules.restricted_keyword_hits:       # be cautious when the LLM could not confirm
                flags[Flag.RESTRICTED_GOODS.value] = True

        if flags[Flag.NO_TERMS_OF_SERVICE.value]: reasons.append("No Terms of Service found")
        if flags[Flag.MISSING_CONTACT.value]: reasons.append("No contact information found")
        if flags[Flag.AMBIGUOUS_REFUND.value]: reasons.append("Refund policy missing or ambiguous: " + llm.refund_ambiguous.evidence)
        if flags[Flag.DELAYED_DELIVERY.value]: reasons.append("Delivery timeline risk: " + llm.delivery_risk.evidence)
        if flags[Flag.RESTRICTED_GOODS.value]:
            reasons.append("Possible restricted goods: " + (llm.restricted_goods.evidence or ", ".join(rules.restricted_keyword_hits)))
        if rules.young_domain:
            reasons.append(f"Young domain ({rules.domain_age_days} days old)")
        low = [k for k, v in conf.items() if v < thr]
        if low:
            reasons.append("Low LLM confidence: " + ", ".join(low))

    uncertain = fetch_problem or not llm.valid or any(v < thr for v in conf.values())
    review = fetch_problem or uncertain or any(flags.values())
    return SiteResult(
        site_id=site.site_id, url=site.url,
        decision=Decision.HUMAN_REVIEW if review else Decision.NO_HUMAN_REVIEW,
        mcc=llm.mcc, naics=llm.naics, industry=llm.industry,
        flags=flags, confidences=conf, reasons=reasons,
        fetch_status=site.status, error=site.error, elapsed_seconds=round(site.elapsed_seconds, 3),
    )
