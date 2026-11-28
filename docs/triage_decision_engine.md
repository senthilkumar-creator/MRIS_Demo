# Triage and Decision Engine

## 1. Purpose

The Triage and Decision Engine is responsible for determining whether a merchant website requires manual review. It combines rule-based findings, LLM-based assessments, confidence scores, domain age, and website fetch status to make a routing decision.

The engine produces one of two decisions:

- `HUMAN_REVIEW`: The website requires further assessment by a human reviewer.
- `NO_HUMAN_REVIEW`: No conditions requiring manual review were identified.

The main objective is to reduce unnecessary manual reviews while minimizing the risk of overlooking potentially risky merchants.

## 2. Input and Output

### 2.1 Input

The decision engine receives three data objects:

| Input | Description |
|---|---|
| SiteData | Website information, fetch status, and errors |
| RuleResult | Findings from the rule-based detection layer |
| LLMResult | LLM assessments, confidence scores, and validation status |

### 2.2 Output

The engine returns a SiteResult object containing:

- Website URL
- Routing decision
- Human review requirement
- Review reasons
- Checkout availability
- Detected payment gateways
- Industry classification
- Product-industry match
- Risk flags
- Business information
- LLM validation notes
- Website fetch status and errors

The existing output schema is preserved to maintain compatibility with the API, dashboard, and other project components.

## 3. Decision Matrix

The following matrix defines the conditions used to determine whether a merchant requires human review.

| Condition | Routing Decision |
|---|---|
| Website fetch status is not OK | HUMAN_REVIEW |
| Invalid or unusable LLM response | HUMAN_REVIEW |
| Missing Terms of Service | HUMAN_REVIEW |
| Missing contact information | HUMAN_REVIEW |
| Missing refund or return policy | HUMAN_REVIEW |
| Ambiguous refund policy detected | HUMAN_REVIEW |
| Delivery timeline risk detected | HUMAN_REVIEW |
| Missing delivery information for physical goods when delivery assessment is skipped | HUMAN_REVIEW |
| Restricted goods detected | HUMAN_REVIEW |
| Restricted or high-risk industry category | HUMAN_REVIEW |
| Product-industry mismatch | HUMAN_REVIEW |
| Unknown product-industry match | HUMAN_REVIEW |
| Inconclusive applicable LLM judgment | HUMAN_REVIEW |
| Evaluated LLM confidence below 0.70 | HUMAN_REVIEW |
| Young domain with young-domain review enabled | HUMAN_REVIEW |
| Young domain with young-domain review disabled and no other review triggers | NO_HUMAN_REVIEW |
| No risk flags or other review triggers | NO_HUMAN_REVIEW |

The engine uses OR-based decision logic. A single review trigger is sufficient to route a website to human review.

## 4. Risk Flag Evaluation

The engine evaluates five risk flags:

| Risk Flag | Detection Method |
|---|---|
| Missing Terms of Service | Rule-based |
| Missing contact information | Rule-based |
| Ambiguous refund policy | Rule-based and LLM-based |
| Delayed delivery | Rule-based and LLM-based |
| Restricted goods | Rule-based and LLM-based |

Rule-based detection identifies observable website information, such as missing policies and contact details.

LLM-based detection evaluates information that requires contextual understanding, such as ambiguous refund conditions, delivery risks, and restricted goods.

When the LLM response is invalid, restricted-goods keyword findings are used as an additional precaution.

## 5. Routing Logic and Justification

The decision engine follows a conservative routing approach. A website is sent for human review when a risk is detected or when the available information is insufficient to make a reliable decision.

The main routing conditions are:

- Website fetch failure or limited content
- Invalid LLM output
- One or more risk flags
- Low LLM confidence
- Inconclusive LLM judgments
- Product-industry mismatch or unknown match
- Young domain when the corresponding setting is enabled

This approach prioritizes reducing false negatives, where a potentially risky merchant is incorrectly routed without human review.

However, conservative routing may increase the number of websites requiring manual review. This trade-off should be evaluated during benchmark testing.

## 6. Confidence Threshold

The confidence threshold is defined in `config/config.yaml`.

Current configuration:

    decision:
      confidence_threshold: 0.7
      domain_age_days_threshold: 180
      review_on_young_domain: true

An evaluated confidence score below 0.70 triggers human review.

| Confidence Score | Confidence-Based Decision |
|---|---|
| 0.69 | HUMAN_REVIEW |
| 0.70 | Eligible for NO_HUMAN_REVIEW |
| 0.71 | Eligible for NO_HUMAN_REVIEW |

A confidence score equal to or above the threshold does not override other risk flags or review conditions.

The existing threshold of 0.70 was retained as the initial operating threshold. It provides a configurable starting point for balancing automated routing and manual review.

The threshold has been verified through boundary testing but has not yet been optimized using a labeled benchmark dataset.

## 7. Handling Inconclusive LLM Judgments

The LLM may return one of three values for a risk assessment:

| Value | Interpretation |
|---|---|
| True | Risk detected |
| False | Risk not detected |
| None | Unable to determine the result |

Previously, an inconclusive judgment could result in NO_HUMAN_REVIEW when its confidence score was above the configured threshold.

The updated decision engine routes inconclusive applicable judgments to HUMAN_REVIEW regardless of their confidence score.

This improvement applies to:

- Product-industry match
- Refund policy ambiguity
- Delivery timeline risk
- Restricted goods detection

Inconclusive judgments are recorded in the review reasons and validation notes without automatically treating uncertainty as a confirmed risk flag.

Refund and delivery judgments are checked for uncertainty when the corresponding fields were requested from the LLM.

## 8. Young-Domain Handling

The configured domain-age threshold is 180 days.

When the rule-based layer identifies a young domain and `review_on_young_domain` is enabled, the website is routed to HUMAN_REVIEW.

When the setting is disabled, a young domain alone does not trigger human review. The domain-age information is still included in the result, and the young-domain observation remains available in the review reasons.

Domain age is treated as a precautionary indicator rather than proof of merchant risk.

## 9. Review Reasons and Explainability

The decision engine generates descriptive review reasons to explain why a merchant requires further assessment.

Examples include:

- No Terms of Service found
- No contact information found
- Ambiguous refund policy detected
- Delivery timeline risk detected
- Possible restricted goods
- Low LLM confidence
- Inconclusive LLM judgment
- Could not determine product / industry match

Multiple reasons can be recorded for a single website.

The LLM validation notes also provide a summary of the conditions that triggered human review. This supports transparency and helps reviewers understand the routing decision.

## 10. Automated Testing

The decision engine was tested using:

    python -m pytest tests/test_schema_and_decision.py -v

The original implementation contained 12 automated tests. An additional 14 tests were added to improve coverage.

### 10.1 Testing Progress

| Testing Stage | Passed | Failed | Total |
|---|---:|---:|---:|
| Original baseline | 12 | 0 | 12 |
| After adding initial tests | 21 | 4 | 25 |
| After product-match improvement | 22 | 3 | 25 |
| After inconclusive judgment improvements | 25 | 0 | 25 |
| After young-domain configuration test | 26 | 0 | 26 |

### 10.2 Additional Test Coverage

The additional tests cover:

- Confidence below the threshold
- Confidence equal to the threshold
- Confidence above the threshold
- Missing contact information
- Unknown product-industry match
- Inconclusive refund judgment
- Inconclusive delivery judgment
- Inconclusive restricted-goods judgment
- Delayed delivery detection
- Restricted goods detection
- Multiple simultaneous risk flags
- Restricted keywords with invalid LLM output
- Clean website without review reasons
- Disabled young-domain review

### 10.3 Final Unit Test Results

- Total tests: 26
- Passed: 26
- Failed: 0
- Unit test pass rate: 100%

All original tests continued to pass after the decision engine improvements.

These results validate the tested routing scenarios using predefined inputs. They do not represent real-world merchant classification accuracy.

### 10.4 Integration Testing

The pipeline and API integration test was executed using:

    python -m pytest tests/test_pipeline_api.py -v

- Passed: 1
- Failed: 0
- Warnings: 1

### 10.5 Regression Testing

Regression testing was performed to verify that the decision
engine improvements did not break existing project components.

    python -m pytest tests -v --ignore=tests/test_fetch_site_live.py

- Total tests: 136
- Passed: 136
- Failed: 0
- Warnings: 1
- Pass rate: 100%

All executed tests passed successfully. The dependency
deprecation warning did not affect the test results.

The personal live website test was excluded from this run.
Real-world benchmark validation remains pending.

## 11. Limitations and Future Improvements

Although all current decision engine unit tests pass, further validation is required.

Future improvements include:

- Evaluating the confidence threshold using a labeled benchmark dataset.
- Measuring false-positive and false-negative rates.
- Performing end-to-end testing with real merchant websites.
- Evaluating confidence score range validation.
- Assessing the impact of conservative routing on manual review workload.
- Revalidating the decision engine after changes to the LLM detection layer.

## 12. Conclusion

The Triage and Decision Engine combines rule-based findings and LLM assessments to determine whether a merchant website requires human review.

The updated implementation improves uncertainty handling while preserving the existing risk flags, configuration settings, and output schema.

All 26 decision engine unit tests passed successfully. Further benchmark and integration testing will help evaluate the effectiveness of the routing strategy in real-world scenarios.