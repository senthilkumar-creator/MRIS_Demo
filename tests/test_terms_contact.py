"""Terms of Service and contact-information detection. Owner: Member 4. Each case is a tiny HTML page."""
import pytest

from mris.rules.policy import has_contact, has_terms
from mris.schema import Page, SiteData

FILLER = "<p>Welcome to our shop. We sell many things.</p>" * 5


def site(html, url="https://shop.test/", extra_pages=()):
    pages = [Page(page_type="home", url=url, html=f"<html><body>{html}{FILLER}</body></html>")]
    pages += [Page(page_type=t, url=u, html=f"<html><body>{h}</body></html>") for t, u, h in extra_pages]
    return SiteData(site_id=0, url=url, domain="shop.test", pages=pages)


# ---------------- Terms of Service: present ----------------
@pytest.mark.parametrize("html", [
    '<footer><a href="/pages/legal">Terms &amp; Conditions</a></footer>',
    '<footer><a href="/x">Terms of Use</a></footer>',
    '<footer><a href="/policies/terms-of-service">Legal</a></footer>',          # Shopify style, wording only in URL
    '<footer><a href="/terms">Terms</a></footer>',
    '<footer><a href="/tos.html">Read this</a></footer>',
    '<footer><a href="/info">T&amp;Cs</a></footer>',
    '<footer><a href="/a">Conditions of Sale</a></footer>',
    '<footer>Please read our Terms of Service before ordering.</footer>',      # phrase in the text only
    '<footer>USER AGREEMENT applies to all orders</footer>',                    # upper case
])
def test_terms_present(html):
    assert has_terms(site(html))


def test_terms_page_fetched_with_terms_url():
    s = site("<p>hi</p>", extra_pages=[("terms", "https://shop.test/terms-and-conditions", "<p>text</p>")])
    assert has_terms(s)


# ---------------- Terms of Service: absent ----------------
@pytest.mark.parametrize("html", [
    "<p>nothing legal here</p>",
    '<a href="/photos">Our photos</a><a href="/autos">Autos</a>',               # "tos" inside other words
    '<a href="/about">About us</a><a href="/privacy">Privacy policy</a>',
    "<p>Payment terms are net 30. In terms of price we are the best.</p>",        # the word "terms" alone is not a ToS
])
def test_terms_absent(html):
    assert not has_terms(site(html))


def test_page_typed_terms_by_scraper_but_not_really_terms():
    # the scraper's keyword "tos" typed /photos as "terms"; we must not trust the type alone
    s = site("<p>hi</p>", extra_pages=[("terms", "https://shop.test/photos", "<p>pictures</p>")])
    assert not has_terms(s)


# ---------------- Contact: present ----------------
@pytest.mark.parametrize("html", [
    '<footer><a href="mailto:help@shop.test">Email us</a></footer>',
    '<footer>Write to help@shop.test</footer>',
    '<footer>help [at] shop [dot] test</footer>',                               # simple obfuscation
    '<footer><a href="tel:+14035551234">Call</a></footer>',
    '<footer>Phone: 403-555-1234</footer>',
    '<footer>(403) 555 1234</footer>',
    '<footer>+44 20 7946 0958</footer>',
    '<footer>Call us on 4035551234</footer>',                                   # label + unformatted number
    '<footer><a href="/contact-us">Contact us</a></footer>',
    '<footer><a href="/pages/x">Get in touch</a></footer>',
    '<footer>Visit us at 123 Main Street, Calgary</footer>',
    '<form><input name="name"><input type="email" name="e"><textarea name="message"></textarea></form>',
])
def test_contact_present(html):
    assert has_contact(site(html))


def test_contact_page_fetched():
    s = site("<p>hi</p>", extra_pages=[("contact", "https://shop.test/contact", "<p>Reach us</p>")])
    assert has_contact(s)


# ---------------- Contact: absent ----------------
@pytest.mark.parametrize("html", [
    "<p>no way to reach us</p>",
    '<img src="/img/logo@2x.png"><img src="a@3x.jpg">',                          # looks like an email, is a file
    "<p>Order 20241114 12345 shipped on 2024-11-14. Price 1,234.56</p>",         # looks like a phone, is not
    '<a href="/about">About us</a><a href="/support">Support</a>',               # not contact information
    '<form><input type="email" name="newsletter"><button>Subscribe</button></form>',   # newsletter, no message box
    '<p>Contact: example@example.com</p>',                                       # placeholder address
    '<a href="mailto:">Email</a>',
])
def test_contact_absent(html):
    assert not has_contact(site(html))


def test_text_only_pages_without_html():
    s = SiteData(site_id=0, url="u", domain="d", pages=[Page(page_type="home", url="u", text="Email help@shop.test, see our Terms of Service")])
    assert has_terms(s) and has_contact(s)


def test_no_pages():
    s = SiteData(site_id=0, url="u", domain="d", pages=[])
    assert not has_terms(s) and not has_contact(s)


# ---------------- own details vs. user-written page content (marketplaces) ----------------
def test_phone_in_listing_text_is_not_the_sites_contact_info():
    html = '<main><div class="ad"><p>Sneakers size 42 price 70 EUR tel 0477438495 like new</p></div></main>'
    assert not has_contact(site(html))


@pytest.mark.parametrize("html", [
    '<header>Call us: 403-555-1234</header>',
    '<div class="site-footer">Email help@shop.test</div>',
    '<div id="contact-info">Phone: 403-555-1234</div>',
    '<address>123 Main Street, Calgary</address>',
])
def test_contact_details_in_header_footer_or_contact_block(html):
    assert has_contact(site("<main><p>products</p></main>" + html))


def test_free_text_in_main_content_only_counts_on_a_contact_page():
    s = site("<main><p>Email help@shop.test</p></main>")
    assert not has_contact(s)
    s2 = site("<p>hi</p>", extra_pages=[("contact", "https://shop.test/x", "<main><p>Email help@shop.test</p></main>")])
    assert has_contact(s2)
