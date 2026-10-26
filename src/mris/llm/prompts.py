"""Prompt for the LLM layer. Owners: Member 3 (industry / MCC-NAICS part), Member 4 (risk part).

One combined call per site keeps latency low. Keep the JSON shape in sync with schema.LLMResult.
TODO: compare zero-shot vs few-shot examples on the development set (see eval/).
"""

SYSTEM_PROMPT = """You are a merchant-risk analyst for a payment processor. You read text taken from a merchant website
and answer ONLY with one JSON object. Never add explanations outside the JSON.
Base every answer on the text provided. If the text does not contain the information, set the value to null
and give a low confidence. Confidence is a number from 0 to 1."""

USER_TEMPLATE = """Website text (may be truncated):
\"\"\"
{text}
\"\"\"

Return JSON with exactly these keys:
{{
  "industry": "short industry name",
  "mcc": "4-digit MCC code or null",
  "naics": "2 to 6 digit NAICS code or null",
  "industry_confidence": 0.0,
  "product_matches_industry": true or false or null,
  "product_match_confidence": 0.0,
  "refund_ambiguous":  {{"value": true or false or null, "confidence": 0.0, "evidence": "short quote"}},
  "delivery_risk":     {{"value": true or false or null, "confidence": 0.0, "evidence": "short quote"}},
  "restricted_goods":  {{"value": true or false or null, "confidence": 0.0, "evidence": "short quote"}}
}}

Definitions:
- refund_ambiguous: true if the refund / return policy is missing, vague, or contradictory (no time limit, no process).
- delivery_risk: true if delivery times are missing, very long, unclear, or the site promises pre-orders without dates.
- restricted_goods: true if the site sells restricted or prohibited goods (weapons, drugs, counterfeit items, etc.).
- product_matches_industry: true if the products shown match the industry you chose."""


def build_messages(text: str) -> list:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(text=text)},
    ]
