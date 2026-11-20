# RiskLens AI — Merchant Risk Intelligence System (MRIS)

**Updated codebase for the first three project tasks:** scraper/crawler design, core HTML/text/script extraction, and bounded batch/concurrent processing.

This repository **extends** the original `MRIS_Demo-main` starter. Existing `POST /assess` merchant decisions, rule modules, gateway checks, domain-age code, LLM clients, evaluation utilities and original tests remain in place. A new **`POST /scrape`** endpoint and a responsive browser dashboard provide a standalone scraper playground without requiring an LLM or Streamlit.

## Fastest way to run

On Windows, **extract this repository and double-click `run_dashboard.bat`**. On Linux/macOS, run `bash run_dashboard.sh`. Both launch the local web application at:

**http://127.0.0.1:8000/ui**

API documentation: **http://127.0.0.1:8000/docs**

The first run installs the minimal server packages automatically into a project `.venv` (internet connection needed once). Python 3.11+ is recommended.

> The supplied launchers set `MRIS_LLM_MODE=mock` so that the existing assessment can be demonstrated without a paid model service. **Mock results are illustrative, not real risk decisions.** The scraping feature accesses actual public websites independently of LLM mode.

**[Dashboard preview](docs/dashboard_preview.png)** (visual sample; no live merchant data shown).

## What works now

- Paste a URL list or upload CSV/TXT; one-click scraper or existing risk assessment
- Crawls merchant home, Terms, refund, shipping, contact and checkout links on the same host
- Extracts visible text, raw HTML previews and inline/external-script metadata
- Optionally fetches up to 3 same-origin JavaScript files per site without executing them
- URL validation, DNS/private network screening, robots.txt, retries, rate limits and capped downloads
- Bounded parallel HTTP requests, per-host limits and batch scheduling
- JSON/CSV downloads, site-status browsing, per-page tabs and responsive dashboard
- CLI, API docs, controlled offline benchmark and regression tests

## One-minute API example

```bash
curl -X POST http://127.0.0.1:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"urls":["https://example.com"],"include_html":true}'
```

For the **original MRIS assessment** contract:

```bash
curl -X POST http://127.0.0.1:8000/assess \
  -H "Content-Type: application/json" \
  -d '{"urls":["https://example.com"]}'
```

## CLI (from repository root)

```bash
# Linux/macOS
PYTHONPATH=src python -m mris.cli scrape --url https://example.com --include-html -o output/example.json
PYTHONPATH=src python -m mris.cli scrape --file data/urls_sample.csv -o output/sites.csv

# Windows PowerShell
$env:PYTHONPATH="src"
python -m mris.cli scrape --url https://example.com -o output/example.json
```

## Documentation

**Read [`docs/TASKS_1_TO_3_IMPLEMENTATION.md`](docs/TASKS_1_TO_3_IMPLEMENTATION.md)** for the three tasks broken down step by step: architecture, repository tree, exact file responsibilities, endpoints, CLI examples, security measures, concurrency design, limitations, setup and tests.

To test the entire project, use `pip install -r requirements.txt` followed by `python -m pytest -q`. The included offline benchmark is `python scripts/benchmark_scraper.py --sites 100 --workers 30`.

## Important constraints

- The 100-sites/60-seconds and 10,000-site requirements are **targets**, not yet validated against live merchants or the full LLM pipeline. The benchmark script uses mocked responses.
- Playwright/Chromium rendering is optional and **disabled by default**. See the detailed guide to enable it locally.
- This is a **local development prototype**. Before exposing it publicly, implement authentication, traffic quotas and network-level egress protection against DNS rebinding. Respect robots.txt and website policies.
- Existing `config/config.yaml` configures the risk LLM mode for other team tasks. The launchers deliberately override it with the demonstration/mock LLM.

### Crawling access troubleshooting (November 2026 maintenance update)

If every website displays `BLOCKED` and `0 pages`, see
[docs/ROBOTS_TROUBLESHOOTING.md](docs/ROBOTS_TROUBLESHOOTING.md). The crawler
now reports `robots_unavailable` separately from explicit access restrictions;
it does **not** bypass robots.txt. In PowerShell, run `.\diagnose_access.bat` or the included Python diagnostic:

```powershell
.\.venv\Scripts\python.exe scripts\diagnose_access.py
```

If a trusted corporate/university proxy is required, optional environment
proxy support can be enabled with `$env:MRIS_TRUST_ENV="1"` before launching.
The default remains off. This update preserves the API request format and
original assessment pipeline.
