# RiskLens AI / MRIS — Tasks 1, 2 and 3: Implementation Guide

This guide describes code delivered for the **first three scraper and infrastructure tasks only**. It was built by extending the user's `MRIS_Demo-main` GitHub ZIP and comparing it with the Phase 2 proposal, system design, progress reports and architecture diagram.

The existing payment gateway/risk rule layer, LLM integration, domain-age lookup, evaluation scripts and shared assessment schema have been **preserved** for subsequent team tasks. This implementation adds a *separate scraper-preview output contract* rather than changing the team's `schema.py`.

## Task 1 — Design the scraper/crawler, URL/API/script interfaces and repository

### 1.1 Inputs and flow

```
       User browser / CLI / external API client
                         |
                    URL list
                         v
             FastAPI   /scrape  /assess
                         |
            validate + deduplicate URLs
                         |
              bounded chunk scheduler
                         |
    global site semaphore (default 30 concurrent)
                         |
           shared per-domain crawl policy
              |        |        |
          robots    pacing     SSRF
              |        |        |
                         v
           asynchronous HTTPX fetcher
                         |
         homepage + relevant internal links
               |                 |
           raw HTML             metadata
               |                 |
         BeautifulSoup parser    |
               |                 |
           text, script tags, page category
                         |
        scraper preview      existing ETL + rules
          /scrape             + LLM + decision
              |                   |
          JSON / CSV          JSON / CSV
```

### 1.2 Core file organization

```text
MRIS_RiskLens_Updated/
├── config/
│   ├── config.yaml                      # site workers, retries, host limits, size/robots controls
│   ├── gateway_signatures.yaml          # original gateway rules
│   └── industries.yaml                  # original MCC/NAICS mapping
├── data/                                # original sample URL list and labels template
├── docs/
│   └── TASKS_1_TO_3_IMPLEMENTATION.md  # this implementation guide
├── scripts/
│   ├── benchmark_scraper.py             # controlled offline concurrency experiment
│   └── ...                              # original evaluation/test utilities
├── src/mris/
│   ├── api.py                           # GET /ui, GET /health, POST /scrape, POST /assess
│   ├── cli.py                           # python -m mris.cli scrape/assess
│   ├── batch.py                         # ordered, bounded chunk scheduler
│   ├── pipeline.py                      # existing assessment; separate fetch/LLM semaphores
│   ├── scraper/
│   │   ├── parser.py                    # normalize, discover same-host links, visible text
│   │   ├── policy.py                    # robots, private-network URL checks, per-host rate limiting
│   │   ├── fetcher.py                   # async HTTP, retries, redirects, bounded HTML downloads
│   │   ├── service.py                   # scraper-only result contract and HTML/script summaries
│   │   └── dynamic_handler.py           # OPTIONAL Playwright; off by default
│   ├── processing/                     # original ETL
│   ├── rules/                          # original flags / gateway logic
│   ├── llm/                            # original hosted/local/mock model options
│   ├── decision/                       # original HUMAN_REVIEW routing
│   └── ui/
│       ├── dashboard/
│       │   ├── index.html               # browser dashboard
│       │   ├── style.css                # responsive dark styling
│       │   └── app.js                   # CSV upload, API calls, filtering, exports
│       └── streamlit_app.py             # original optional Streamlit UI
├── tests/
│   ├── test_scraper_architecture.py     # 11 new targeted tests
│   └── ...                              # original 35 passing tests
├── requirements-server.txt             # minimal dashboard dependencies
├── requirements.txt                    # original full project dependencies
├── run_dashboard.bat                    # Windows start
└── run_dashboard.sh                     # Linux/macOS start
```

### 1.3 HTTP interfaces

**GET `/`** redirects to `/ui`.

**GET `/ui`** serves the browser dashboard. All assets are local (no CSS/JS CDN).

**GET `/health`** returns `{"status":"ok"}`.

**POST `/scrape`** accepts this JSON:

```json
{
  "urls": ["https://example.com", "another-store.com"],
  "include_html": true,
  "include_inline_scripts": true,
  "fetch_external_scripts": false,
  "max_text_chars": 12000,
  "max_html_chars": 20000
}
```

Returns `count`, `successful`, `limited`, `failed`, `total_pages`, `elapsed_seconds`, and `results`. Each result contains its `url`, `domain`, `fetch_status`, `error`, `elapsed_seconds`, `pages_found`, and `pages`. Each page contains its `page_type`, `url`, `title`, `text`, optional `html`, `script_count`, and `scripts`.

**POST `/assess`** is preserved. Example request: `{"urls":["https://example.com"]}`. It continues to return the existing MCC/NAICS, risk flags, confidence and HUMAN_REVIEW routing structure. Use `POST /assess?format=csv` for the original assessment CSV format. The `/scrape` endpoint does **not** perform classification or LLM inference.

**GET `/docs`** provides FastAPI's interactive OpenAPI interface. Try requests directly in the browser.

### 1.4 Command-line interface

Execute with `PYTHONPATH=src` on Linux/macOS or PowerShell `$env:PYTHONPATH="src"` on Windows (unless the package has been installed):

```bash
python -m mris.cli scrape --url https://example.com --include-html -o output/example.json
python -m mris.cli scrape --file data/urls_sample.csv -o output/scrape.csv
python -m mris.cli scrape --url https://example.com --fetch-external-scripts -o output/scripts.json
python -m mris.cli assess --url https://example.com -o output/assessment.json
```

When using the CLI from the repository root, `-o` outputs JSON or CSV. TXT import supports one URL per line; CSV requires an `url`, `website`, `website_url`, `merchant_url`, or `domain` column. Duplicate URLs are skipped.

## Task 2 — Build the core web scraper/crawler

### Step 1: Normalize and validate the URL (`scraper/parser.py`)

Add HTTPS if no scheme was supplied, remove fragments, reject non-HTTP(S), invalid ports, and embedded credentials. Actual network requests further check targets against private/reserved IP ranges and internal hostnames (`scraper/policy.py`). The same check is applied to every redirect.

### Step 2: Respect robots.txt (`scraper/policy.py`)

For each site origin, retrieve and parse `robots.txt` once per batch. Cache that decision, so repeated pages from one host do not refetch the file. A disallowed URL is reported as `fetch_status="blocked"`, with an explanatory error. The crawler conservatively refuses a site when robots policy cannot be determined.

### Step 3: Download the homepage (`scraper/fetcher.py`)

Use one reusable async `httpx.AsyncClient`, request timeout (8 s default), bounded redirects (up to 5), and capped response size (1 MB/page). Retry transient network failures and 408/425/429/5xx responses using exponential backoff. Never silently treat a blocked or unreachable homepage as risk-free.

### Step 4: Discover relevant links (`scraper/parser.py`)

Scan homepage `<a href>` links for merchant-specific categories: `terms`, `refund`, `shipping`, `contact`, `checkout`. Only follow links on the same **hostname** as the fetched homepage. Deduplicate these links and limit the total pages per merchant to 6 (homepage plus 5). This is a *focused crawler*, not an unlimited whole-site spider.

### Step 5: Extract page text and scripts (`scraper/service.py`)

Use BeautifulSoup/lxml. Remove scripts, styles, templates, navigation and hidden sections when producing **visible text**. Return each page's HTML title, visible text and original HTML (when requested). Identify `<script>` tags: inline code, external `src` URLs, script type, counts and truncation markers.

Optional `fetch_external_scripts: true` fetches at most 3 **same-origin** external JS files per merchant, includes up to 10,000 characters/file and does not execute them. Third-party JS references are listed as URLs only.

### Step 6: Handle failure and limited content

Return a status such as `ok`, `limited_content`, `blocked`, `timeout`, `dns_error`, `ssl_error`, `not_found`, `invalid_url`, or `error` instead of crashing the batch. Thin JavaScript-only pages may be marked `limited_content`. Playwright exists in the repository but is **disabled by default**, since it requires installing Chromium, adds major latency and should be isolated for security. To opt in locally, set `MRIS_ENABLE_DYNAMIC_FALLBACK=1` and install the browser via `python -m playwright install chromium`.

### Step 7: Release temporary HTML

The `/scrape` response only contains bounded previews. The existing `/assess` pipeline cleans and analyzes site HTML, then runs `free_raw_html(site)` before sending the site to the LLM. This reduces raw-data retention. There is no database, and no page data is stored by default except exports requested by the user.

## Task 3 — Design and implement efficient batch/concurrent processing

### 3.1 Concurrency model

- **Async I/O:** `httpx.AsyncClient` shares keep-alive connections across the run.
- **Bounded site slots:** `fetch.max_concurrent_sites: 30`; test alternatives of 10/30/50.
- **Per-host limits:** `fetch.max_concurrent_per_host: 2` limits simultaneous requests to one host.
- **Minimum host interval:** `fetch.min_host_interval_seconds: 0.2` spaces out request *starts* on a host. Can be increased to reduce site load.
- **Chunked task creation:** `batch.chunk_size: 200` avoids queuing all 10,000 coroutines in a single `gather` call. Results remain in input order.
- **Separate RDAP slots:** `fetch.max_concurrent_domain_age: 8` protects the external domain registry service.
- **Separate LLM slots:** `llm.max_concurrent_calls: 6` prevents slow inference from occupying web-fetch semaphore slots; existing risk/LLM code is otherwise preserved.
- **Response bounds:** maximum 6 merchant pages × 1 MB fetched HTML each (per-site worst-case input), with limited JSON previews. Large sites should be processed in smaller chunks.
- **Timeouts, limited redirects, retry and errors:** a broken website does not stop other jobs.

### 3.2 Simplified concurrency pseudocode

```python
policy = CrawlPolicy()                       # shared robots/host queues
site_slots = asyncio.Semaphore(30)          # across domains
llm_slots = asyncio.Semaphore(6)            # inference requests

async def one(url):
    async with site_slots:
        site = await fetch_site(client, site_id, url, policy)
    # /scrape: extract summaries and return
    # /assess: clean, run rules and lookups, drop HTML
    async with llm_slots:
        llm_output = await analyze_site(llm_client, site, rules)
    return decide(site, rules, llm_output)

for chunk in chunks(urls, size=200):
    results.extend(await asyncio.gather(*(one(url) for url in chunk)))
```

### 3.3 Performance test and what it proves

To run an offline, deterministic performance check without touching real websites:

```bash
python scripts/benchmark_scraper.py --sites 100 --workers 10
python scripts/benchmark_scraper.py --sites 100 --workers 30
python scripts/benchmark_scraper.py --sites 100 --workers 50
```

The offline run uses a mocked 20-ms network response on 100 independent mock hosts, so it verifies concurrency caps/overhead **only**. It is **not** evidence that 100 real merchants finish within 60 seconds, nor that the entire MRIS pipeline is fast enough. The true sponsor acceptance test must use 100 permitted, reachable real merchants, include domain age/rule/LLM processing as required, and be repeated for at least three trials on team hardware. Run the 10,000-site evaluation with documented results and error rates; do not claim it as complete yet.

### 3.4 Important security boundaries

This is a student prototype, not a hardened public crawling service. Public URLs are screened for internal/private hosts and resolved private addresses. Because DNS may change between the check and the actual socket connection (**DNS rebinding**), production operation needs a **network egress firewall or proxy** to block private, metadata and internal destinations. Do not open this API to arbitrary Internet clients without authentication, request budgets and egress isolation. Browser fallback must also run inside isolation.

The optional test/development environment flag `MRIS_ALLOW_PRIVATE_NETWORKS=1` is only for local mock sites. Do not use it on an Internet-exposed server. Respect each website's robots policy, terms and applicable law.

## Setup and run (beginner-friendly)

### Windows (easiest)

1. Extract the ZIP (do not run inside the ZIP viewer).
2. Open the extracted `MRIS_RiskLens_Updated` folder.
3. Double-click **`run_dashboard.bat`**. On first run it creates `.venv` and installs the minimal dashboard dependencies.
4. Open **http://127.0.0.1:8000/ui** in Chrome/Edge.
5. Paste one or more public merchant URLs, choose *Scrape content*, press **Run web scraper**. Open a site and select **Visible text**, **HTML source** or **Scripts**. Download JSON or CSV.
6. Choose *Assess risk* for the existing team pipeline. The launcher uses `MRIS_LLM_MODE=mock`, which is a **demonstration model only**, not real merchant risk analysis.

For manual setup on Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-server.txt
$env:MRIS_LLM_MODE="mock"
.\.venv\Scripts\python.exe -m uvicorn mris.api:app --app-dir src --host 127.0.0.1 --port 8000
```

### Mac/Linux

```bash
bash run_dashboard.sh
```

Visit **http://127.0.0.1:8000/ui** or **http://127.0.0.1:8000/docs**.

### Tests

Install the full dependencies and run from the repository root:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

The bundled test suite sets the mock LLM and grants local-only network fixture access inside tests; those are not the normal production settings.

## Results and hand-off

- Original automated tests: **35 passed** before development.
- Revised suite: **48 passed** at delivery (35 existing + 13 new tests).
- Offline mock concurrency run: example 100 sites/30 workers completed in approximately 0.64 seconds in the execution environment used to build the ZIP; real throughput will differ.
- Existing code was extended, not replaced. The original `POST /assess` shape and shared risk schema remain intact.
- Changes to future scraping logic should be reviewed with teammates, especially if a later task modifies the shared `schema.py`.
- **Not included / later tasks:** production deployment, new payment gateway signatures, label creation, baseline model training, verified 100-real-site speed target, or 10,000-live-site evaluation.
