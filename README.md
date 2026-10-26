# MRIS – Merchant Risk Intelligence System (RiskLens AI)

Takes a list of merchant website URLs and returns, for each site, **HUMAN_REVIEW / NO_HUMAN_REVIEW**,
an MCC / NAICS classification, the five risk flags and the reasons.
Stack: FastAPI · BeautifulSoup · open-source LLM (Ollama) · in-memory data · optional Streamlit UI.

This skeleton already runs end to end with a **mock LLM** (no model needed), so every member can start
on their own module straight away. All tests pass: `python -m pytest`.

## 1. Setup (each member, once)

```bash
git clone https://github.com/senthilkumar-creator/MRIS_Demo.git && cd mris
python -m venv .venv
# Windows:  .venv\Scripts\activate        Mac/Linux:  source .venv/bin/activate
pip install -r requirements.txt
python -m pytest            # should show all tests passing
```

## 2. Run it

```bash
# API (mock LLM, no model needed)
# Windows PowerShell:  $env:MRIS_LLM_MODE="mock"      Mac/Linux:  export MRIS_LLM_MODE=mock
uvicorn mris.api:app --reload --app-dir src
# open http://localhost:8000/docs  ->  POST /assess  ->  {"urls": ["https://example.com"]}
# add ?format=csv to get a CSV instead of JSON
```

Real LLM (Member 3 sets this up first, see section 4):
```bash
ollama pull llama3.1:8b        # install Ollama first: https://ollama.com
# then remove MRIS_LLM_MODE (config/config.yaml already says mode: ollama)
```

Optional UI (build last):  `streamlit run src/mris/ui/streamlit_app.py`

## 3. How the code maps to the architecture diagram

```
config/                      config.yaml (all thresholds), gateway_signatures.yaml
src/mris/schema.py           SHARED DATA CONTRACT - change only through a pull request
src/mris/api.py              FastAPI: POST /assess, GET /health            (stage 1)
src/mris/scraper/            fetcher.py, parser.py (BeautifulSoup)          (stage 2)
src/mris/processing/         clean.py - cleaning, text for the LLM          (stage 3)
src/mris/rules/              gateway.py, policy.py, domain_age.py, engine.py (stage 4a)
src/mris/llm/                client.py (Ollama), prompts.py, analyze.py     (stage 4b)
src/mris/decision/engine.py  routing rule                                   (stage 5)
src/mris/pipeline.py         glues the stages, concurrency, chunks
src/mris/eval/               metrics.py, run_eval.py
src/mris/ui/                 streamlit_app.py (optional)
tests/                       pytest tests (add one per feature)
data/                        urls_sample.csv, labels_template.csv
```

## 4. Who starts where (suggested – adjust as a team)

| Member | Module | First tasks |
|---|---|---|
| 1 | `scraper/fetcher.py`, `pipeline.py`, `api.py` | Test fetching on 20 real sites; measure time per stage; try concurrency 10/30/50 |
| 2 | error statuses, `api.py` output, `ui/` | Test blocked / timeout / JavaScript-only sites; location cues (`declared_location`); Streamlit last |
| 3 | `rules/gateway.py`, `llm/client.py`, MCC/NAICS part of `prompts.py` | **Install Ollama and run the latency test first**; signature catalogue; MCC/NAICS table |
| 4 | `rules/policy.py`, `llm/analyze.py`, risk part of `prompts.py`, `decision/engine.py` | ToS and contact edge cases; prompts for refund / delivery / restricted goods; threshold tuning |
| 5 | `rules/domain_age.py`, `processing/clean.py`, `eval/` | RDAP incl. `.ca` domains; label the benchmark; run `eval/run_eval.py` |

Everyone: label 10 sites each into `data/labels_template.csv` (copy it to `data/labels_test.csv`).

## 5. Team rules (keep five people from colliding)

1. Work on a branch (`git checkout -b member3-gateway`), open a pull request, get one review, then merge.
2. Do not change `schema.py` without telling everyone.
3. Every new rule or bug fix gets a test in `tests/`.
4. Do not commit real API keys or large data files (`.gitignore` covers `output/`).
5. Put thresholds in `config/config.yaml`, not in code.

## 6. Known limits (write these in the report)

- BeautifulSoup reads static HTML only: JavaScript-built sites get status `limited_content` -> HUMAN_REVIEW.
- Data lives in memory for one run; large runs are processed in chunks (`batch.chunk_size`).
- The skeleton's rules are first versions (substring matching). Expect to improve them on real sites.
- Be polite when scraping: keep timeouts, a clear User-Agent, and do not hammer one site.
