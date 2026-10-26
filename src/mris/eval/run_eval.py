"""Run MRIS on a labeled CSV and print the metrics.   Owner: Member 5.

Usage (from the project root):
    python -m mris.eval.run_eval data/labels_dev.csv
Set MRIS_LLM_MODE=mock to test the script without a model.
"""
import asyncio
import json
import sys
import pandas as pd

from ..pipeline import assess_urls, results_to_dataframe
from .metrics import evaluate


def main(path: str) -> None:
    labels = pd.read_csv(path)
    resp = asyncio.run(assess_urls(labels["url"].tolist()))
    metrics = evaluate(labels, results_to_dataframe(resp.results))
    metrics["seconds_total"] = resp.elapsed_seconds
    metrics["seconds_per_site"] = round(resp.elapsed_seconds / max(len(labels), 1), 3)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
