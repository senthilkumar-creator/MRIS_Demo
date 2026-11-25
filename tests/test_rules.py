from mris.rules.engine import run_rules
from mris.schema import Page, SiteData
import pytest

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


def test_refund_delivery_and_location_rules():
    from mris.rules.engine import run_rules
    s = SiteData(site_id=1, url="u", pages=[Page(page_type="home", url="u", text="We ship fast. Refund within 30 days. Visit us: 120 Main St, Calgary AB T2P 1A1", html="")])
    r = run_rules(s)
    assert r.refund_text_found and r.delivery_text_found and r.declared_location == "Calgary, AB, Canada"
    none = run_rules(SiteData(site_id=2, url="u", pages=[Page(page_type="home", url="u", text="Welcome to our shop", html="")]))
    assert not none.refund_text_found and not none.delivery_text_found and none.declared_location is None


@pytest.mark.parametrize(
    ("provider", "html"),
    [
        ("helcim", '<div id="helcim-pay"></div>'),
        ("stripe", '<script src="https://js.stripe.com/v3/"></script>'),
        ("shopify", '<button class="shop_pay">Shop Pay</button>'),
        ("adyen", '<div class="adyen-checkout"></div>'),
        (
            "woocommerce",
            '<script src="/wp-content/plugins/woocommerce/cart.js"></script>',
        ),
        ("stripe", '<iframe src="https://js.stripe.com/v3/"></iframe>'),
        ("helcim", '<form action="https://pay.helcim.app/checkout"></form>'),
    ],
)
def test_gateway_signatures_in_html_elements(provider, html):
    url = "https://merchant.example"
    site = SiteData(
        site_id=1,
        url=url,
        pages=[Page(page_type="home", url=url, html=html)],
    )

    assert provider in run_rules(site).gateways_found


@pytest.mark.parametrize(
    ("provider", "html"),
    [
        ("stripe", "<p>Stripe scripts are hosted at js.stripe.com.</p>"),
        (
            "shopify",
            '<script src="https://cdn.shopify.com/assets/storefront.js"></script>',
        ),
    ],
)
def test_unrelated_gateway_mentions_are_ignored(provider, html):
    url = "https://merchant.example"
    site = SiteData(
        site_id=1,
        url=url,
        pages=[Page(page_type="home", url=url, html=html)],
    )

    assert provider not in run_rules(site).gateways_found



def test_checkout_mention_in_article_is_ignored():
    url = "https://merchant.example/article"
    site = SiteData(
        site_id=1,
        url=url,
        pages=[
            Page(
                page_type="home",
                url=url,
                html="<article><p>This guide explains how checkout works.</p></article>",
            )
        ],
    )

    assert run_rules(site).checkout_detected is False