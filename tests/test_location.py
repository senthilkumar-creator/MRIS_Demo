
from mris.rules.location import detect_location
from mris.schema import Page, SiteData


def test_canadian_address():
    site = SiteData(
        site_id=1,
        url="https://example.com",
        pages=[
            Page(
                page_type="contact",
                url="https://example.com/contact",
                text="120 Main St, Calgary AB T2P 1A1",
                html="",
            )
        ],
    )

    assert detect_location(site) == (
        "120 Main St, Calgary, AB, T2P 1A1, Canada"
    )


def test_us_address():
    site = SiteData(
        site_id=2,
        url="https://example.com",
        pages=[
            Page(
                page_type="contact",
                url="https://example.com/contact",
                text="100 Main Street, Seattle, WA 98101",
                html="",
            )
        ],
    )

    assert detect_location(site) == (
        "100 Main Street, Seattle, WA, 98101, USA"
    )


def test_structured_address():
    html = """
    <script type="application/ld+json">
    {
        "@type": "LocalBusiness",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "120 Main St",
            "addressLocality": "Calgary",
            "addressRegion": "AB",
            "postalCode": "T2P 1A1",
            "addressCountry": "CA"
        }
    }
    </script>
    """

    site = SiteData(
        site_id=3,
        url="https://example.com",
        pages=[
            Page(
                page_type="home",
                url="https://example.com",
                html=html,
            )
        ],
    )

    assert detect_location(site) == (
        "120 Main St, Calgary, AB, T2P 1A1, Canada"
    )


def test_missing_address():
    site = SiteData(
        site_id=4,
        url="https://example.com",
        pages=[
            Page(
                page_type="home",
                url="https://example.com",
                html="<p>Welcome to our online store.</p>",
            )
        ],
    )

    assert detect_location(site) is None


def test_contact_page_priority():
    site = SiteData(
        site_id=5,
        url="https://example.com",
        pages=[
            Page(
                page_type="home",
                url="https://example.com",
                text="Toronto, ON",
                html="",
            ),
            Page(
                page_type="contact",
                url="https://example.com/contact",
                text="Calgary, AB",
                html="",
            ),
        ],
    )

    assert detect_location(site) == "Calgary, AB, Canada"


def test_malformed_json_ld():
    site = SiteData(
        site_id=6,
        url="https://example.com",
        pages=[
            Page(
                page_type="home",
                url="https://example.com",
                html="""
                <script type="application/ld+json">
                {invalid json}
                </script>
                <p>Calgary, AB</p>
                """,
            )
        ],
    )

    assert detect_location(site) == "Calgary, AB, Canada"
