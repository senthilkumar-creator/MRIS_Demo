"""Evaluation metrics. Owner: Member 5.

Compares MRIS output with hand labels (data/labels_*.csv, see labels_template.csv).
Priority metric: false-negative rate = risky sites that MRIS would send to NO_HUMAN_REVIEW.
"""
from typing import Dict, List
import pandas as pd

FLAGS = ["delayed_delivery", "restricted_goods", "no_terms_of_service", "ambiguous_refund", "missing_contact"]


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "y")


def prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def evaluate(labels: pd.DataFrame, preds: pd.DataFrame) -> Dict:
    """labels columns: url, decision, + one column per flag. preds: output of results_to_dataframe()."""
    df = labels.merge(preds, on="url", suffixes=("_true", "_pred"))
    out: Dict = {"n_sites": len(df)}
    if df.empty:
        return out
    true_review = df["decision_true"].str.upper().eq("HUMAN_REVIEW")
    pred_review = df["decision_pred"].str.upper().eq("HUMAN_REVIEW")
    out["routing_agreement"] = round(float((true_review == pred_review).mean()), 3)
    out["false_negative_rate"] = round(float((true_review & ~pred_review).sum() / max(true_review.sum(), 1)), 3)
    out["human_review_share_pred"] = round(float(pred_review.mean()), 3)
    per_flag = {}
    for f in FLAGS:
        t = df[f].map(_truthy) if f in df else None
        pcol = f"flag_{f}"
        if t is None or pcol not in df:
            continue
        pr = df[pcol].map(_truthy)
        per_flag[f] = prf(int((t & pr).sum()), int((~t & pr).sum()), int((t & ~pr).sum()))
    out["per_flag"] = per_flag
    return out
