# Output and Integration

## 1. Overview

The Output and Integration layer converts the results from the
rule-based detection layer, LLM analysis, and Triage and Decision
Engine into a structured JSON response.

The output provides merchant assessment results, identified risks,
confidence scores, business information, and routing decisions in
a consistent format that can be used by downstream applications.

This implementation focuses on the following project tasks:

- Task 5.1: Build structured JSON output matching the proposal schema.
- Task 5.4: Validate output against the example JSON format.

## 2. Implementation Objectives

- Preserve the JSON structure defined in the project proposal.
- Provide consistent field names and data types.
- Include confidence scores for LLM-generated risk assessments.
- Handle missing information without inventing values.
- Return structured results for unsuccessful website assessments.
- Maintain compatibility with existing project functionality.
- Validate the output through automated testing.

## 3. Output Generation Process

The final output is generated through the following stages:

1. The scraper collects merchant website information.
2. The rule-based layer identifies deterministic risk indicators.
3. The LLM layer evaluates industry classification, product matching,
   refund ambiguity, delivery risks, and restricted goods.
4. The Decision Engine combines the available findings.
5. The SiteResult model structures the final merchant assessment.
6. The API returns the assessment results in JSON format.

The AssessResponse model supports multiple merchant assessments
within a single API response.

## 4. JSON Output Structure

The existing proposal fields have been preserved.

| Field | Data Type | Description |
|---|---|---|
| url | String | Merchant website URL |
| routing_decision | String | Final routing decision |
| requires_human_review | Boolean | Indicates whether manual review is required |
| review_reasons | Array | Reasons associated with the assessment |
| has_working_checkout | Boolean | Checkout detection result |
| detected_gateways | Array | Detected payment gateways |
| industry_classification | Object | Industry classification and confidence |
| product_industry_match | Object | Product and industry alignment |
| risk_flags | Object | Identified merchant risk indicators |
| business_info | Object | Domain age and declared business location |
| llm_validation_notes | String | Explanation of the assessment decision |

The implementation also includes the following additional fields:

| Field | Data Type | Description |
|---|---|---|
| risk_confidence | Object | Confidence scores for LLM risk assessments |
| fetch_status | String | Website retrieval status |
| error | String or null | Website retrieval error information |

The risk_confidence object is a proposed extension to the original
example JSON. The existing fetch_status and error fields have been
retained to support unsuccessful website assessments.

## 5. Confidence Score Handling

Previously, confidence scores for refund ambiguity, delayed delivery,
and restricted goods were not consistently available as structured
fields in the final JSON response.

The RiskConfidence model was introduced to preserve these scores.

The object contains:

- ambiguous_refund_policy
- delayed_delivery
- restricted_goods

Confidence scores are included regardless of whether the LLM
identifies a risk, provided the corresponding assessment was
requested and the LLM response was usable.

This allows downstream applications to inspect the confidence
associated with both positive and negative LLM judgments.

### 5.1 Confidence Range Validation

Confidence scores are restricted to values between 0.0 and 1.0.

Pydantic field constraints are applied to:

- Industry classification confidence
- Product-industry match confidence
- Refund ambiguity confidence
- Delayed delivery confidence
- Restricted goods confidence

The existing LLM parser also normalizes numerical confidence
values before they reach the Decision Engine.

### 5.2 Missing Confidence Scores

A null value is returned for a risk confidence score when:

- The corresponding LLM assessment was not requested.
- The LLM response was invalid or unusable.
- The website could not be assessed successfully.

This avoids assigning an artificial LLM confidence score to
a finding determined entirely by the rule-based layer.

An inconclusive LLM judgment may still have a confidence score.
The existing Decision Engine routes inconclusive assessments
to human review where applicable.

Confidence scores represent the model's reported confidence
and should not be interpreted as calibrated probabilities.

## 6. Example JSON Output

The following example illustrates the updated output structure
using synthetic merchant assessment data.

```json
{
  "url": "https://example-store.com",
  "routing_decision": "NO_HUMAN_REVIEW",
  "requires_human_review": false,
  "review_reasons": [],
  "has_working_checkout": true,
  "detected_gateways": [
    "Helcim",
    "Shopify"
  ],
  "industry_classification": {
    "mcc": "5691",
    "naics": "448140",
    "description": "Apparel and Accessories",
    "confidence_score": 0.95
  },
  "product_industry_match": {
    "is_match": true,
    "confidence_score": 0.92,
    "details": "Products and services appear to match 'Apparel and Accessories'."
  },
  "risk_flags": {
    "missing_terms_of_service": false,
    "ambiguous_refund_policy": false,
    "delayed_delivery": false,
    "restricted_goods": false,
    "missing_contact_info": false
  },
  "risk_confidence": {
    "ambiguous_refund_policy": 0.91,
    "delayed_delivery": 0.93,
    "restricted_goods": 0.94
  },
  "business_info": {
    "domain_age_days": 365,
    "location": "Calgary, AB, Canada"
  },
  "llm_validation_notes": "All LLM fields at or above the 0.7 confidence threshold; no risk flags raised.",
  "fetch_status": "ok",
  "error": null
}
```

This example is for demonstrating the output structure only.
It does not represent an actual merchant assessment or verified
industry code assignment.

## 7. Batch Response Structure

The AssessResponse model contains three main fields:

- count: Number of merchant assessment results.
- elapsed_seconds: Total assessment processing time.
- results: List of individual SiteResult objects.

The API supports multiple website URLs in a single request.
Duplicate URL removal is also covered by the existing API
integration test.

Each merchant result maintains the same JSON structure,
including unsuccessful assessments.

## 8. Error Handling

Unsuccessful website assessments continue to return structured
JSON responses instead of omitting the affected merchant.

Examples of unsuccessful assessment conditions include:

- Invalid URLs
- Connection timeouts
- DNS errors
- SSL errors
- Blocked websites
- Limited website content
- Invalid LLM responses

Website retrieval failures are identified through fetch_status
and error information where available.

Invalid LLM responses are identified through review reasons
and validation notes.

Unsuccessful assessments are routed to HUMAN_REVIEW.

Risk flags that remain false after a failed assessment should
not be interpreted as confirmation that the merchant is safe.
The routing decision and fetch status must also be considered.

## 9. Implementation Changes

### 9.1 Schema

File: src/mris/schema.py

- Added the RiskConfidence model.
- Added risk_confidence to the SiteResult model.
- Added confidence score range validation.
- Preserved existing proposal fields and risk flag data types.

### 9.2 Decision Engine

File: src/mris/decision/engine.py

- Initialized the risk confidence object.
- Preserved confidence scores from requested LLM assessments.
- Returned null for skipped or unusable risk assessments.
- Included risk confidence information in the final SiteResult.
- Preserved the existing routing logic.

### 9.3 JSON Validation Tests

File: tests/test_output_schema.py

A dedicated test file was created to validate the JSON output
structure, data types, field values, confidence scores, error
handling, serialization, and batch responses.

### 9.4 API Integration Tests

File: tests/test_pipeline_api.py

The existing API integration test was expanded to validate:

- Batch response structure
- Required JSON fields
- Risk confidence fields
- Confidence score ranges
- Routing decision consistency
- Successful merchant assessments
- Invalid URL assessments

The existing CSV validation assertions were retained.

## 10. Testing and Validation

### 10.1 Dedicated JSON Validation

A total of 26 new automated test cases were added.

| Test Category | Test Cases |
|---|---:|
| JSON structure, types, and values | 3 |
| Risk confidence handling | 4 |
| Missing business information | 1 |
| Invalid LLM and failed fetch handling | 2 |
| Invalid confidence ranges | 10 |
| Valid confidence boundaries | 2 |
| JSON serialization | 1 |
| Batch response structure | 1 |
| Routing decision consistency | 2 |
| Total | 26 |

All 26 test cases passed.

### 10.2 API Integration Testing

The expanded API integration test passed successfully.

The test uses a local web server and a mock LLM to validate
the assessment pipeline without depending on external merchant
websites or live LLM API responses.

### 10.3 Regression Testing

The following command was used to run the regression suite:

```powershell
python -m pytest tests -v --ignore=tests/test_fetch_site_live.py
```

| Test Suite | Result |
|---|---|
| Decision Engine tests | 26 passed |
| Dedicated JSON validation tests | 26 passed |
| Expanded API integration test | 1 passed |
| Full selected regression suite | 162 passed |

The full regression suite completed in 28.07 seconds with
zero test failures and one dependency deprecation warning.

The individual test suites are included in the regression
total and should not be counted separately.

The personal live website test was excluded from this run.

## 11. Compatibility and Limitations

The existing proposal fields, nested objects, Boolean risk
flags, and routing decisions have been preserved.

The additional risk_confidence object provides structured
access to LLM confidence scores without changing the existing
risk flag representation.

However, the additional field requires team review before
the shared output contract is finalized.

The existing CSV integration test continues to pass. Full
compatibility with all external consumers has not yet been
independently verified.

The following limitations remain:

- Live merchant website validation is pending.
- Confidence calibration has not been evaluated.
- False positive and false negative rates have not been measured.
- Benchmark dataset evaluation remains pending.
- Non-finite confidence inputs, such as NaN, require further
  review in the upstream LLM parser.
- The existing Starlette/httpx deprecation warning remains.

These items should be considered during subsequent validation
and integration activities.

## 12. Conclusion

The updated Output and Integration layer provides a consistent
JSON representation of merchant assessments while preserving
the existing project output structure.

Structured risk confidence scores improve the availability
of LLM assessment information for downstream applications
and human reviewers.

The implementation was validated through 26 dedicated JSON
test cases, expanded API integration testing, and a regression
suite containing 162 passing tests.

The results demonstrate that the updated output works correctly
within the tested scenarios. Further live merchant validation
and team review are required before finalizing the shared
output contract.