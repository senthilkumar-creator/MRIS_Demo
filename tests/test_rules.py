from mris.rules.engine import run_rules
from mris.schema import Page, SiteData

HOME = """<html><body><h1>Cool Shop</h1>
<a href="/terms">Terms of Service</a> <a href="/contact">Contact us</a>
<button>Add to cart</button><script src="https://js.stripe.com/v3/"></script>
%s</body></html>""" % ("<p>filler</p>" * 50)


def test_gateway_and_checkout_detected():
    s = SiteData(site_id=1, url="https://x.test", domain="x.test", pages=[Page(page_type="home", url="https://x.test", html=HOME)])
    r = run_rules(s)
    assert "stripe" in r.gateways_found and r.checkout_detected


def test_terms_and_contact_pages():
    pages = [Page(page_type="home", url="u", html="<p>hi</p>"), Page(page_type="terms", url="u/terms", html="<p>t</p>"),
             Page(page_type="contact", url="u/contact", html="<p>c</p>")]
    r = run_rules(SiteData(site_id=1, url="u", pages=pages))
    assert r.has_terms and r.has_contact


def test_missing_terms_and_contact():
    r = run_rules(SiteData(site_id=1, url="u", pages=[Page(page_type="home", url="u", html="<p>just a page</p>")]))
    assert not r.has_terms and not r.has_contact
