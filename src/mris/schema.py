"""Shared data contract. Everyone imports these models; change them only through a pull request.

Flow of data between modules:
  scraper  -> SiteData (pages + fetch status)
  rules    -> RuleResult
  llm      -> LLMResult
  decision -> SiteResult  (what the API returns)
"""
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Decision(str, Enum):
    NO_HUMAN_REVIEW = "NO_HUMAN_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class FetchStatus(str, Enum):
    OK = "ok"
    LIMITED_CONTENT = "limited_content"   # little static HTML (e.g. JavaScript-only site)
    BLOCKED = "blocked"                   # 403 / 429 / bot protection
    TIMEOUT = "timeout"
    DNS_ERROR = "dns_error"
    SSL_ERROR = "ssl_error"
    NOT_FOUND = "not_found"
    INVALID_URL = "invalid_url"
    ERROR = "error"


class Flag(str, Enum):
    """The five risk flags from the project brief."""
    DELAYED_DELIVERY = "delayed_delivery"
    RESTRICTED_GOODS = "restricted_goods"
    NO_TERMS_OF_SERVICE = "no_terms_of_service"
    AMBIGUOUS_REFUND = "ambiguous_refund"
    MISSING_CONTACT = "missing_contact"


# ---------- API input ----------
class AssessRequest(BaseModel):
    urls: List[str] = Field(..., min_length=1, max_length=20000)


# ---------- scraper output ----------
class Page(BaseModel):
    page_type: str                  # home, terms, refund, shipping, contact, checkout, other
    url: str
    html: str = ""
    text: str = ""                  # cleaned visible text (filled by processing)


class SiteData(BaseModel):
    site_id: int
    url: str
    domain: str = ""
    status: FetchStatus = FetchStatus.OK
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    pages: List[Page] = []
    domain_age_days: Optional[int] = None   # None = unknown


# ---------- rule layer output ----------
class RuleResult(BaseModel):
    gateways_found: List[str] = []
    checkout_detected: bool = False
    has_terms: bool = False
    has_contact: bool = False
    domain_age_days: Optional[int] = None
    young_domain: Optional[bool] = None
    declared_location: Optional[str] = None
    restricted_keyword_hits: List[str] = []


# ---------- LLM layer output ----------
class FieldJudgement(BaseModel):
    value: Optional[bool] = None            # True = risk present
    confidence: float = 0.0                 # 0..1
    evidence: str = ""                      # short quote from the page


class LLMResult(BaseModel):
    industry: str = ""
    mcc: Optional[str] = None
    naics: Optional[str] = None
    industry_confidence: float = 0.0
    product_matches_industry: Optional[bool] = None
    product_match_confidence: float = 0.0
    refund_ambiguous: FieldJudgement = FieldJudgement()
    delivery_risk: FieldJudgement = FieldJudgement()
    restricted_goods: FieldJudgement = FieldJudgement()
    valid: bool = True                      # False if the model output could not be parsed
    error: Optional[str] = None


# ---------- final result returned by the API ----------
class SiteResult(BaseModel):
    site_id: int
    url: str
    decision: Decision
    mcc: Optional[str] = None
    naics: Optional[str] = None
    industry: str = ""
    flags: Dict[str, bool] = {}             # the five flags -> True/False
    confidences: Dict[str, float] = {}
    reasons: List[str] = []
    fetch_status: FetchStatus = FetchStatus.OK
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


class AssessResponse(BaseModel):
    count: int
    elapsed_seconds: float
    results: List[SiteResult]
