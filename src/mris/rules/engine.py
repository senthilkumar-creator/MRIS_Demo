"""Runs every rule check for one site and returns a RuleResult."""
from ..config import get_config
from ..schema import RuleResult, SiteData
from .gateway import detect_checkout, detect_gateways, restricted_keyword_hits
from .policy import has_contact, has_terms


def run_rules(site: SiteData) -> RuleResult:
    threshold = get_config()["decision"]["domain_age_days_threshold"]
    age = site.domain_age_days
    return RuleResult(
        gateways_found=detect_gateways(site),
        checkout_detected=detect_checkout(site),
        has_terms=has_terms(site),
        has_contact=has_contact(site),
        domain_age_days=age,
        young_domain=None if age is None else age < threshold,
        declared_location=None,    # TODO (Member 2): address / country / currency cues
        restricted_keyword_hits=restricted_keyword_hits(site),
    )
