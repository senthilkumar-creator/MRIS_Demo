import os, sys, time, httpx

base = sys.argv[1] if len(sys.argv) > 1 else "https://api.groq.com/openai/v1"
model = sys.argv[2] if len(sys.argv) > 2 else "openai/gpt-oss-20b"
effort = sys.argv[3] if len(sys.argv) > 3 else None   # e.g. low, minimal, none

body = {"model": model, "max_tokens": 300,
        "messages": [{"role": "user", "content": 'Reply with this JSON only: {"ok": true}'}]}
if effort:
    body["reasoning_effort"] = effort

t = time.time()
try:
    r = httpx.post(base.rstrip("/") + "/chat/completions",
                   headers={"Authorization": "Bearer " + os.environ["MRIS_LLM_API_KEY"]},
                   json=body, timeout=90)
    print(r.status_code, round(time.time() - t, 1), "s")
    print(r.text[:700])
except Exception as e:
    print("FAILED after", round(time.time() - t, 1), "s:", repr(e))