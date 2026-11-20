"""Command-line entry point for batch scraping and the existing MRIS assessment.

Examples:
  python -m mris.cli scrape --url example.com --include-html -o output/scrape.json
  python -m mris.cli scrape --file data/urls_sample.csv -o output/scrape.csv
  python -m mris.cli assess --url example.com -o output/assessment.json
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

from .pipeline import assess_urls, results_to_dataframe
from .scraper.service import ScrapeRequest, ScrapeResponse, scrape_urls


def read_urls(file_path: Path) -> list[str]:
    if file_path.suffix.lower() == ".csv":
        with file_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fields = {name.lower().strip(): name for name in reader.fieldnames or []}
            key = next((fields[k] for k in ("url", "website", "website_url", "domain", "merchant_url") if k in fields), None)
            if not key:
                raise ValueError("CSV must have a 'url', 'website', or 'domain' column")
            return [str(row.get(key) or "").strip() for row in reader if str(row.get(key) or "").strip()]
    if file_path.suffix.lower() == ".txt":
        return [line.strip() for line in file_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    raise ValueError("The input file must be .csv or .txt")


def unique_urls(urls: list[str]) -> list[str]:
    from .scraper.parser import normalize_url
    keys: set[str] = set()
    out: list[str] = []
    for url in urls:
        key = normalize_url(url)
        if key and key not in keys:
            keys.add(key)
            out.append(url)
    return out


def scrape_csv_rows(response: ScrapeResponse) -> list[dict]:
    rows = []
    for site in response.results:
        if not site.pages:
            rows.append({"url": site.url, "page_url": "", "page_type": "", "title": "", "fetch_status": site.fetch_status.value,
                         "text": "", "script_count": 0, "script_sources": "", "elapsed_seconds": site.elapsed_seconds, "error": site.error or ""})
        for page in site.pages:
            rows.append({"url": site.url, "page_url": page.url, "page_type": page.page_type,
                         "title": page.title, "fetch_status": site.fetch_status.value, "text": page.text,
                         "script_count": page.script_count,
                         "script_sources": "; ".join(s.src for s in page.scripts if s.src),
                         "elapsed_seconds": site.elapsed_seconds, "error": site.error or ""})
    return rows


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mris", description="RiskLens AI merchant crawler and assessment")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("scrape", "assess"):
        p = commands.add_parser(name)
        p.add_argument("--url", action="append", default=[], help="Single URL (repeatable)")
        p.add_argument("--file", type=Path, help="File containing URL list (.csv with url column, or .txt)")
        p.add_argument("-o", "--output", type=Path, help="Write to a .json or .csv output file (default stdout JSON)")
        if name == "scrape":
            p.add_argument("--include-html", action="store_true", help="Include an HTML snippet per page (bounded)")
            p.add_argument("--fetch-external-scripts", action="store_true", help="Retrieve at most 3 same-origin JavaScript files per site")
            p.add_argument("--max-text-chars", type=int, default=12000)
            p.add_argument("--max-html-chars", type=int, default=20000)
    args = parser.parse_args(argv)
    try:
        urls = unique_urls(args.url + (read_urls(args.file) if args.file else []))
        if not urls:
            parser.error("Provide at least one --url or a --file with URLs")
        if args.command == "scrape":
            # Keep output memory bounded by processing a configurable group.
            chunk_limit = 250
            results = []
            elapsed = 0.0
            for i in range(0, len(urls), chunk_limit):
                part = asyncio.run(scrape_urls(ScrapeRequest(urls=urls[i:i + chunk_limit], include_html=args.include_html,
                                                           max_text_chars=args.max_text_chars, max_html_chars=args.max_html_chars,
                                                           fetch_external_scripts=args.fetch_external_scripts)))
                results.extend(part.results)
                elapsed += part.elapsed_seconds
            response = ScrapeResponse(count=len(results), successful=sum(x.fetch_status.value == "ok" for x in results),
                                      limited=sum(x.fetch_status.value == "limited_content" for x in results),
                                      failed=sum(x.fetch_status.value not in ("ok", "limited_content") for x in results),
                                      total_pages=sum(x.pages_found for x in results), elapsed_seconds=round(elapsed, 3), results=results)
            json_output = response.model_dump_json(indent=2)
            rows = scrape_csv_rows(response)
        else:
            response = asyncio.run(assess_urls(urls))
            json_output = response.model_dump_json(indent=2)
            rows = results_to_dataframe(response.results).to_dict(orient="records")
        if args.output:
            if args.output.suffix.lower() not in {".json", ".csv"}:
                raise ValueError("Output path must end in .json or .csv")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.output.suffix.lower() == ".json":
                args.output.write_text(json_output + "\n", encoding="utf-8")
            else:
                with args.output.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["url"])
                    writer.writeheader()
                    writer.writerows(rows)
            print(f"Completed {response.count} sites in {response.elapsed_seconds}s -> {args.output}", file=sys.stderr)
        else:
            print(json_output)
        return 0
    except (OSError, ValueError) as exc:
        print(f"MRIS error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
