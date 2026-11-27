"""Prompt for the LLM layer. Owners: Member 3 (industry / product match), Member 4 (risk questions).

Design for speed (CPU-only machines are slow at WRITING text):
- the model answers with NUMBERS and true/false only: an industry number from config/industries.yaml,
  never MCC / NAICS codes (the code looks those up), and no explanations or quotes
- only the questions that rules cannot settle are asked (no refund text on the site = rules already know)
- the fixed instructions come FIRST and the website text LAST so the model server can reuse its work on the
  unchanged start of the prompt between calls
Keep the JSON keys in sync with analyze.parse_llm_json.
"""

from typing import Iterable, Optional
from ..industries import prompt_list

SYSTEM_PROMPT = (
    "You are a merchant-risk analyst for a payment processor. Answer ONLY with one short JSON object, "
    "no explanations. Base answers on the website text. If the text does not say, use null and a low confidence. "
    "Confidence is a number from 0 to 1."
)

# Each question contains a JSON template and its definition.
FIELDS = {
    "industry": (
        '"industry_id": 0, "industry_conf": 0.0',
        "industry_id: the number of the best matching industry in the list above (use the last number if unsure)."
    ),

    "product_match": (
        '"product_match": true/false/null, "product_conf": 0.0',
        "product_match: true if the products or services sold match the industry you chose."
    ),

    "refund": (
        '"refund_ambiguous": true/false/null, "refund_conf": 0.0',
        "refund_ambiguous: evaluate the clarity of the merchant's refund or return policy. "
        "Return true if the policy contains vague eligibility conditions, contradictory statements, "
        "unclear refund procedures, missing applicable refund deadlines, or undefined exceptions. "
        "Statements such as 'refunds may be considered' or 'refunds are at our discretion' "
        "without clear criteria indicate ambiguity. "
        "Return false if the policy clearly explains the applicable refund conditions, "
        "time limits, and request procedure. "
        "A clearly stated non-refundable or final-sale policy is not ambiguous solely "
        "because refunds are unavailable. "
        "Return null with low confidence if the available website text is insufficient "
        "to evaluate the policy. "
        "Do not assume missing information when the website text may be truncated. "
        "Set refund_conf according to the strength and completeness of the available evidence."
    ),

    "delivery": (
        '"delivery_risk": true/false/null, "delivery_conf": 0.0',
        "delivery_risk: true if delivery times are unclear, very long, or pre-orders have no dates."
    ),

    "restricted": (
        '"restricted_goods": true/false/null, "restricted_conf": 0.0',
        "restricted_goods: true if the site sells restricted or prohibited goods (weapons, drugs, counterfeit items)."
    ),
}

ALL_FIELDS = tuple(FIELDS)


def build_messages(text: str, asked: Optional[Iterable[str]] = None) -> list:
    asked = [f for f in ALL_FIELDS if asked is None or f in set(asked)]

    template = ", ".join(FIELDS[f][0] for f in asked)
    definitions = "\n".join("- " + FIELDS[f][1] for f in asked)

    user = (
        "Industries (choose one number):\n" + prompt_list() + "\n\n"
        "Return JSON with exactly these keys: {" + template + "}\n" + definitions +
        "\n\nWebsite text (may be cut off):\n" + text
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user}
    ]