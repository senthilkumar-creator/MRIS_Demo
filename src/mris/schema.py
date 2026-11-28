"""Shared data contract. Everyone imports these models; change them only through a pull request.

Flow of data between modules:
  scraper  -> SiteData (pages + fetch status)
  rules    -> RuleResult
  llm      -> LLMResult
  decision -> SiteResult  (what the API returns; follows the example JSON in the project proposal)
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Decision(str, Enum):
    NO_HUMAN_REVIEW = "NO_HUMAN_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class FetchStatus(str, Enum):
    OK = "ok"
    LIMITED_CONTENT = "limited_content"   # little static HTML (e.g. JavaScript-only site)
    BLOCKED = "blocked"                   # explicit robots Disallow or HTTP access denial
    ROBOTS_UNAVAILABLE = "robots_unavailable"  # robots policy unknown; fail closed
    TIMEOUT = "timeout"
    DNS_ERROR = "dns_error"
    SSL_ERROR = "ssl_error"
    NOT_FOUND = "not_found"
    INVALID_URL = "invalid_url"
    ERROR = "error"


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
    refund_text_found: bool = False         # any refund / return wording on the site
    delivery_text_found: bool = False       # any shipping / delivery wording on the site
    domain_age_days: Optional[int] = None
    young_domain: Optional[bool] = None
    declared_location: Optional[str] = None
    restricted_keyword_hits: List[str] = []


# ---------- LLM layer output ----------
class FieldJudgement(BaseModel):
    value: Optional[bool] = None            # True = risk present
    confidence: float = 0.0                 # 0..1
    evidence: str = ""


class LLMResult(BaseModel):
    industry_id: Optional[int] = None       # number from config/industries.yaml
    industry: str = ""                      # description from the lookup table
    mcc: Optional[str] = None               # from the lookup table, never invented by the model
    naics: Optional[str] = None
    physical_goods: Optional[bool] = None   # from the lookup table
    high_risk_category: bool = False        # from the lookup table
    industry_confidence: float = 0.0
    product_matches_industry: Optional[bool] = None
    product_match_confidence: float = 0.0
    refund_ambiguous: FieldJudgement = FieldJudgement()
    delivery_risk: FieldJudgement = FieldJudgement()
    restricted_goods: FieldJudgement = FieldJudgement()
    asked: List[str] = []                   # fields the model was asked about (others are decided by rules)
    valid: bool = True                      # False if the model output could not be parsed
    error: Optional[str] = None


# ---------- final result: same structure as the example JSON in the proposal ----------
class IndustryClassification(BaseModel):
    mcc: Optional[str] = None
    naics: Optional[str] = None
    description: str = ""
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ProductIndustryMatch(BaseModel):
    is_match: Optional[bool] = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    details: str = ""


class RiskFlags(BaseModel):
    missing_terms_of_service: bool = False
    ambiguous_refund_policy: bool = False
    delayed_delivery: bool = False
    restricted_goods: bool = False
    missing_contact_info: bool = False


class RiskConfidence(BaseModel):
    ambiguous_refund_policy: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    delayed_delivery: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    restricted_goods: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )


class BusinessInfo(BaseModel):
    domain_age_days: Optional[int] = None
    location: Optional[str] = None


class SiteResult(BaseModel):
    url: str
    routing_decision: Decision
    requires_human_review: bool
    review_reasons: List[str] = []
    has_working_checkout: bool = False
    detected_gateways: List[str] = []
    industry_classification: IndustryClassification = IndustryClassification()
    product_industry_match: ProductIndustryMatch = ProductIndustryMatch()
    risk_flags: RiskFlags = RiskFlags()
    risk_confidence: RiskConfidence = Field(default_factory=RiskConfidence)
    business_info: BusinessInfo = BusinessInfo()
    llm_validation_notes: str = ""
    # extra fields (not in the proposal example) so failures are visible
    fetch_status: FetchStatus = FetchStatus.OK
    error: Optional[str] = None


class AssessResponse(BaseModel):
    count: int
    elapsed_seconds: float
    results: List[SiteResult]
