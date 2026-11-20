# Troubleshooting: every website says BLOCKED / 0 pages

## Why this happened

In previous versions, the scraper treated *any* robots.txt retrieval failure
(timeout, TLS problem, robots HTTP 403/429/5xx, redirect loop) as if the
website explicitly prohibited crawling. It labeled every one of these cases
`blocked`, even though the policy was only *unknown*. That was a reporting bug.

The corrected crawler **does not bypass restrictions**. It still declines to
fetch when robots permission is unknown, but it now distinguishes:

| Status | Meaning | What you can do |
|---|---|---|
| `ok` | Public page fetched | Inspect results |
| `limited_content` | HTTP page fetched; little useful static text | Consider JS-rendered fallback only on permitted sites |
| `blocked` | Actual robots.txt Disallow or HTTP access denial (e.g. 403/429) | Respect access rules; use an authorized API or merchant data export |
| `robots_unavailable` | robots.txt could not be reliably retrieved | Check DNS/proxy/TLS/network connectivity, then retry |
| `dns_error` / `ssl_error` / `timeout` | Main website request failed | Check Internet, DNS and certificates |

For instance, some merchants redirect their homepage to a session or login
endpoint. If the new destination is prohibited by robots.txt, `blocked` with
zero pages is the **correct** outcome. It does not indicate merchant fraud.

## Step-by-step on Windows

1. Stop the running server using `Ctrl+C`.
2. Extract the updated ZIP to a new folder, for example `Downloads\\MRIS_RiskLens_Updated`.
   Do not copy your old `.venv` into the new folder.
3. Open that folder in VS Code and open a PowerShell terminal.
4. Start the app using `./run_dashboard.bat` (or `.\\run_dashboard.bat`). The
   launcher installs requirements automatically.
5. Open `http://127.0.0.1:8000/ui` and first try one page:

   `https://example.com`

6. If that is unsuccessful, in a **second VS Code terminal** run either `.\diagnose_access.bat` or the Python command:

   ```powershell
   .\.venv\Scripts\python.exe scripts\diagnose_access.py
   ```

   This uses three public sample sites by default. You can also specify URLs:

   ```powershell
   .\.venv\Scripts\python.exe scripts\diagnose_access.py https://example.com https://www.python.org
   ```

7. For each site, note the exact **Status** and **Reason** lines. Share the
   complete output if you need help interpreting it (remove private tokens or
   internal site URLs).

## Corporate / university network or proxy

Some networks require an `HTTPS_PROXY` environment variable or a trusted
organization certificate. The default scraper does *not* use proxy environment
variables; this is a deliberate safety default. The diagnostic script will
warn when proxy variables exist but the scraper is not using them.

On a **trusted machine/network where you control the proxy settings**, you can
opt in for the current PowerShell session:

```powershell
$env:MRIS_TRUST_ENV="1"
.\run_dashboard.bat
```

This uses proxy and certificate-related settings from your environment. Do not
use an untrusted proxy. **Do not set `MRIS_RESPECT_ROBOTS=0` on third-party sites**:
that would bypass the project's robots.txt compliance and is not a solution.

## Test one site before running large batches

If `https://example.com` works but specific merchants are blocked, the crawler
is functioning and those domains likely impose restrictions or redirects.
If all sample sites report `robots_unavailable`, diagnose your network and
robot policy fetch first. If all samples report `blocked`, inspect the explicit
Disallow/HTTP status details before assuming a systemic problem.

Note that the project targets large-scale processing, but this change has not
been benchmarked against real third-party merchant sites, nor does it guarantee
access to websites that prohibit automated crawling.
