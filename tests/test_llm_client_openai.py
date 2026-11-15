"""The 'openai' client mode works against any OpenAI-compatible server (hosted provider or local)."""
import asyncio
import http.server
import json
import threading

import httpx
from mris.config import get_config
from mris.llm import client as llm_client


class FakeAPI(http.server.BaseHTTPRequestHandler):
    seen = {}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeAPI.seen = {"path": self.path, "auth": self.headers.get("Authorization"), "body": body}
        out = json.dumps({"choices": [{"message": {"content": '{"industry_id": 2, "industry_conf": 0.9}'}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_openai_compatible_mode(monkeypatch):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = get_config()["llm"]
    old = dict(cfg)
    cfg.update(mode="openai", base_url=f"http://127.0.0.1:{srv.server_port}/v1", model="test-model")
    monkeypatch.setenv("MRIS_LLM_API_KEY", "secret-key")
    try:
        async def go():
            async with httpx.AsyncClient() as c:
                return await llm_client.chat_json(c, [{"role": "user", "content": "hi"}])
        raw = asyncio.run(go())
    finally:
        cfg.clear(); cfg.update(old); srv.shutdown()
    assert json.loads(raw)["industry_id"] == 2
    assert FakeAPI.seen["path"] == "/v1/chat/completions" and FakeAPI.seen["auth"] == "Bearer secret-key"
    assert FakeAPI.seen["body"]["model"] == "test-model" and FakeAPI.seen["body"]["max_tokens"] == old.get("max_output_tokens", 120)
