#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements-server.txt
fi
export MRIS_LLM_MODE=mock
printf '\nRiskLens dashboard: http://127.0.0.1:8000/ui\nAPI docs: http://127.0.0.1:8000/docs\n'
printf 'Mock LLM is for demos only; scraping uses public websites.\n\n'
exec .venv/bin/python -m uvicorn mris.api:app --app-dir src --host 127.0.0.1 --port 8000
