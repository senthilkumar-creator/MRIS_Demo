"""New scraper architecture, safety, concurrency and API contract tests."""
import asyncio
import csv
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from mris.api import app
from mris.batch import process_chunks
from mris.cli import read_urls, scrape_csv_rows
from mris.config import get_config
from mris.schema import FetchStatus
from mris.scraper.fetcher import fetch_site
from mris.scraper.parser import find_page_links, is_valid_url, normalize_url, visible_text
from mris.scraper.service import ScrapeRequest, scrape_urls

HTML = '''<html><head><title>My Store</title><script src="/app.js"></script>
<script>window.store = {theme: "blue"};</script></head><body>
<nav>Ignore this navigation</nav><h1>Merchant sells stationery</h1>
<a href="/terms">Terms of service</a><a href="/contact">Contact us</a>
<a href="https://other.test/checkout">Should be ignored</a>
''' + '<p>We sell notebooks, stationery and school supplies in Canada.</p>' * 20 + '</body></html>'


def test_url_hygiene_and_link_scope():
    assert normalize_url(' example.com/path#section ') == 'https://example.com/path'
    assert normalize_url('EXAMPLE.COM') == 'https://EXAMPLE.COM'
    assert not is_valid_url('file:///etc/passwd')
    assert not is_valid_url('https://user:password@example.com')
    assert not is_valid_url('https://example.com:99999')
    assert not is_valid_url('javascript:alert(1)')
    links = find_page_links(HTML, 'https://example.com/shop')
    assert links['terms'] == ['https://example.com/terms']
    assert links['contact'] == ['https://example.com/contact']
    assert 'checkout' not in links
    assert 'Ignore this navigation' not in visible_text(HTML)
    assert 'window.store' not in visible_text(HTML)


def test_scrape_returns_text_html_scripts_and_linked_pages(monkeypatch):
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '0')

    def handler(req):
        page = req.url.path
        html = {'/': HTML, '/terms': '<html><title>Legal</title><body>Terms of service</body></html>',
                '/contact': '<html><body>Contact customer support: email@example.com</body></html>',
                '/app.js': 'const merchantDemo = true;'}.get(page)
        return httpx.Response(200 if html else 404, text=html or 'Missing page')

    def local():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with patch('mris.scraper.service.make_client', local):
        response = asyncio.run(scrape_urls(ScrapeRequest(urls=['https://example.com', 'https://example.com'], include_html=True, fetch_external_scripts=True)))
    assert response.count == 1 and response.successful == 1 and response.total_pages == 3
    page = response.results[0].pages[0]
    assert page.title == 'My Store'
    assert 'Merchant sells stationery' in page.text
    assert 'window.store' not in page.text
    assert '<script>' in page.html
    assert page.script_count == 2
    assert page.scripts[0].src == 'https://example.com/app.js'
    assert page.scripts[0].fetched and 'merchantDemo' in page.scripts[0].content
    assert page.scripts[1].inline and 'window.store' in page.scripts[1].content
    assert {p.page_type for p in response.results[0].pages} == {'home','terms','contact'}


def test_robots_txt_disallow_is_recorded(monkeypatch):
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '1')

    def handler(req):
        if req.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nDisallow: /blocked\n')
        return httpx.Response(200, text=HTML)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site(client, 1, 'https://example.com/blocked')

    result = asyncio.run(go())
    assert result.status == FetchStatus.BLOCKED
    assert 'robots.txt' in result.error
    assert not result.pages


def test_private_ip_blocked_by_default(monkeypatch):
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '0')
    monkeypatch.setenv('MRIS_SKIP_DNS_CHECK', '1')
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '0')

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=HTML))) as client:
            return await fetch_site(client, 1, 'http://127.0.0.1/admin')

    result = asyncio.run(go())
    assert result.status == FetchStatus.INVALID_URL
    assert 'private' in result.error.lower() or 'reserved' in result.error.lower()


def test_redirect_to_private_is_not_fetched(monkeypatch):
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '0')
    monkeypatch.setenv('MRIS_SKIP_DNS_CHECK', '1')
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '0')
    hits = []

    def handler(req):
        hits.append(str(req.url))
        return httpx.Response(302, headers={'Location':'http://169.254.169.254/latest/meta-data/'})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site(client, 1, 'https://example.com/')

    result = asyncio.run(go())
    assert result.status == FetchStatus.INVALID_URL
    assert len(hits) == 1  # destination was never requested


def test_large_response_rejected(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '0')
    cfg = get_config()['fetch']
    monkeypatch.setitem(cfg, 'max_response_bytes', 1024)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=b'A' * 1025))) as client:
            return await fetch_site(client, 1, 'https://example.com/')

    result = asyncio.run(go())
    assert result.status == FetchStatus.ERROR
    assert 'limit' in result.error


def test_batch_concurrency_order_and_per_host_limit(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '0')
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    cfg = get_config()['fetch']
    monkeypatch.setitem(cfg, 'max_concurrent_sites', 3)
    monkeypatch.setitem(cfg, 'max_concurrent_per_host', 2)
    monkeypatch.setitem(cfg, 'min_host_interval_seconds', 0)
    active, peak = 0, 0

    async def handler(req):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.005)
        active -= 1
        return httpx.Response(200, text=HTML)

    def local():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    urls = [f'https://example.com/shop/{i}' for i in range(18)]
    with patch('mris.scraper.service.make_client', local):
        response = asyncio.run(scrape_urls(ScrapeRequest(urls=urls)))
    assert response.count == 18
    assert [r.url for r in response.results] == urls
    assert all(r.fetch_status == FetchStatus.OK for r in response.results)
    assert 1 <= peak <= 2  # all requests target one domain


def test_shared_batch_chunking_is_ordered():
    async def worker(i, value):
        await asyncio.sleep((3 - i % 3) * .001)
        return i, value
    items = [str(i) for i in range(10)]
    assert asyncio.run(process_chunks(items, worker, 4)) == list(enumerate(items))


def test_browser_ui_and_api_routes():
    c = TestClient(app)
    assert c.get('/', follow_redirects=False).status_code in (302, 307)
    index = c.get('/ui')
    assert index.status_code == 200
    assert 'RiskLens AI' in index.text and 'Start a web scraping run' in index.text
    assert 'text/css' in c.get('/assets/style.css').headers['content-type']
    assert 'Run web scraper' in c.get('/assets/app.js').text
    assert c.get('/openapi.json').json()['paths']['/scrape']['post']


def test_invalid_request_payload_rejected():
    c = TestClient(app)
    assert c.post('/scrape', json={'urls': []}).status_code == 422
    assert c.post('/scrape', json={'urls': ['example.com'], 'max_html_chars': 10000000}).status_code == 422


def test_cli_csv_file_roundtrip(tmp_path):
    f = tmp_path / 'input.csv'
    f.write_text('url,name\nexample.com,"Example, Inc."\nother.com,Other\n', encoding='utf8')
    assert read_urls(f) == ['example.com','other.com']
    with open(tmp_path/'out.csv', 'w', newline='') as out:
        writer = csv.writer(out); writer.writerow(read_urls(f))
    assert (tmp_path/'out.csv').read_text().strip()


def test_scrape_http_endpoint_full_response(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '0')
    def local():
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=HTML)))
    with patch('mris.scraper.service.make_client', local):
        response = TestClient(app).post('/scrape', json={'urls':['https://example.com'], 'include_html': True})
    assert response.status_code == 200
    payload = response.json()
    assert payload['count'] == 1 and payload['results'][0]['fetch_status'] == 'ok'
    assert payload['results'][0]['pages'][0]['scripts'][0]['src'] == 'https://example.com/app.js'


def test_transient_http_failure_is_retried(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '0')
    cfg = get_config()['fetch']
    monkeypatch.setitem(cfg, 'retries', 1)
    home_hits = 0
    def handler(req):
        nonlocal home_hits
        if req.url.path == '/':
            home_hits += 1
            return httpx.Response(503 if home_hits == 1 else 200, text='busy' if home_hits == 1 else HTML)
        return httpx.Response(200, text=HTML)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site(client, 1, 'https://example.com/')
    site = asyncio.run(go())
    assert home_hits == 2 and site.status == FetchStatus.OK


def test_robots_unavailable_timeout_is_not_mislabeled_blocked(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '1')
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    home_hits = 0
    def handler(req):
        nonlocal home_hits
        if req.url.path == '/robots.txt':
            raise httpx.ReadTimeout('timed out while checking robots.txt')
        home_hits += 1
        return httpx.Response(200, text=HTML)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site(client, 1, 'https://example.com/')
    site = asyncio.run(go())
    assert site.status == FetchStatus.ROBOTS_UNAVAILABLE
    assert 'ReadTimeout' in site.error
    assert home_hits == 0


def test_robots_403_unknown_policy_fails_closed_but_has_correct_status(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '1')
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    paths = []
    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(403, text='Forbidden')
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site(client, 1, 'https://example.com/')
    site = asyncio.run(go())
    assert site.status == FetchStatus.ROBOTS_UNAVAILABLE
    assert 'HTTP 403' in site.error
    assert paths == ['/robots.txt']


def test_missing_robots_txt_allows_fetch(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '1')
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    def handler(req):
        if req.url.path == '/robots.txt':
            return httpx.Response(404)
        return httpx.Response(200, text=HTML)
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site(client, 1, 'https://example.com/')
    site = asyncio.run(go())
    assert site.status == FetchStatus.OK and len(site.pages) > 0


def test_robots_auth_redirect_excludes_query_tokens_from_error(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '1')
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    url = 'https://merchant.test/'
    def handler(req):
        if req.url.host == 'merchant.test' and req.url.path == '/robots.txt':
            return httpx.Response(404)
        if req.url.host == 'merchant.test':
            return httpx.Response(302, headers={'Location': 'https://auth.test/session/generate_auth_code?token=secret-token'})
        if req.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nDisallow: /session/\n')
        raise AssertionError('Should not download redirected auth endpoint')
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site(client, 1, url)
    site = asyncio.run(go())
    assert site.status == FetchStatus.BLOCKED
    assert 'https://auth.test/session/generate_auth_code' in site.error
    assert 'secret-token' not in site.error


def test_robots_html_response_is_unknown_not_permission(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '1')
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    paths = []
    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(200, text='<html><body>Sign in to continue</body></html>')
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_site(client, 1, 'https://example.com/')
    site = asyncio.run(go())
    assert site.status == FetchStatus.ROBOTS_UNAVAILABLE
    assert paths == ['/robots.txt']


def test_scrape_api_exposes_unavailable_robots_reason_without_fetching_home(monkeypatch):
    monkeypatch.setenv('MRIS_RESPECT_ROBOTS', '1')
    monkeypatch.setenv('MRIS_ALLOW_PRIVATE_NETWORKS', '1')
    accessed = []
    def handler(req):
        accessed.append(req.url.path)
        return httpx.Response(503, text='Try again')
    def local():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch('mris.scraper.service.make_client', local):
        response = TestClient(app).post('/scrape', json={'urls':['https://example.com/']})
    assert response.status_code == 200
    data = response.json()['results'][0]
    assert data['fetch_status'] == 'robots_unavailable'
    assert 'HTTP 503' in data['error']
    assert data['pages_found'] == 0
    assert accessed == ['/robots.txt']
    assert 'resultsAlert' in TestClient(app).get('/ui').text
