"""End-to-end test: a tiny local web server stands in for merchant sites; the mock LLM stands in for the model."""
import http.server
import threading
from fastapi.testclient import TestClient

from mris.api import app

GOOD = b"""<html><body><h1>Good Shop</h1><a href="/terms">Terms of Service</a> <a href="/contact">Contact</a>
<a href="/refund">Refund policy</a><button>Add to cart</button><p>We refund within 30 days. Ships in 3 days.</p>
%s</body></html>""" % (b"<p>filler text</p>" * 60)
TERMS = b"<html><body>Terms of service text</body></html>"
CONTACT = b"<html><body>Email us at help@goodshop.test</body></html>"
REFUND = b"<html><body>Refund within 30 days of purchase.</body></html>"
BARE = b"<html><body><h1>Bare shop</h1>" + b"<p>nothing here</p>" * 60 + b"</body></html>"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        pages = {"/good": GOOD, "/terms": TERMS, "/contact": CONTACT, "/refund": REFUND, "/bare": BARE}
        body = pages.get(self.path)
        self.send_response(200 if body else 404)
        self.end_headers()
        self.wfile.write(body or b"not found")

    def log_message(self, *a):
        pass


def test_assess_endpoint_end_to_end():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}

    r = client.post("/assess", json={"urls": [base + "/good", base + "/bare", "not a url", base + "/good"]})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3                       # duplicate removed
    by_url = {x["url"]: x for x in data["results"]}
    assert by_url[base + "/good"]["decision"] == "NO_HUMAN_REVIEW"
    assert by_url[base + "/bare"]["decision"] == "HUMAN_REVIEW"
    assert by_url[base + "/bare"]["flags"]["no_terms_of_service"] is True
    assert by_url["not a url"]["fetch_status"] == "invalid_url"

    csv = client.post("/assess?format=csv", json={"urls": [base + "/good"]})
    assert csv.headers["content-type"].startswith("text/csv") and "NO_HUMAN_REVIEW" in csv.text
    srv.shutdown()
