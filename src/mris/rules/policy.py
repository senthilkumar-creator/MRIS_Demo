"""Terms of Service and contact-information detection. Owner: Member 4.

What counts as PRESENT
  Terms of Service: a link or fetched page whose text or URL says terms of service / terms of use / terms and
    conditions / terms of sale / conditions of use / user agreement (or a bare "Terms" / "T&C" link), or a page
    that contains one of those phrases. A page the scraper typed "terms" is NOT trusted by itself.
  Contact information: any one of
    - a mailto: link or an email address in the page text (image / file names such as logo@2x.png are ignored),
      [free-text emails, phones and addresses only count in a Contact page, header, footer or contact block; text
       elsewhere, such as ads written by users on a marketplace, is ignored],
    - a tel: link, a North-American style or +international phone number, or a phone number next to a label
      such as "Phone:" / "Call",
    - a contact form (a <form> with a message box and an email or name field),
    - a link to a Contact page ("Contact", "Contact us", "Get in touch", /contact...),
    - a street address ("123 Main Street") .
  "About us" and "Support" links do NOT count as contact information.

Both checks only look at what the scraper fetched. If the page had little static HTML (JavaScript site), "absent"
is uncertain; the decision layer already sends such sites to human review.
"""
import re
from functools import lru_cache
from typing import List, NamedTuple, Optional, Tuple
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from ..schema import Page, SiteData

# ---------------------------------------------------------------- page parsing (footer and nav are KEPT here)


class _View(NamedTuple):
    links: Tuple[Tuple[str, str], ...]     # (link text, href)
    text: str                              # all visible text, including footer
    has_contact_form: bool
    edge_text: str = ""                    # text of header / footer / address / "contact" blocks only


_EDGE_ATTR_RE = re.compile(r"(?:^|[\s_-])(?:footer|header|contact|topbar|address)(?:$|[\s_-])", re.I)
_EDGE_MAX_CHARS = 3000


@lru_cache(maxsize=16)
def _parse(html: str) -> _View:
    soup = BeautifulSoup(html, "lxml")
    links = tuple((a.get_text(" ", strip=True), a["href"].strip()) for a in soup.find_all("a", href=True))
    has_form = False
    for form in soup.find_all("form"):
        has_message = form.find("textarea") is not None
        has_sender = form.find("input", attrs={"type": re.compile("^email$", re.I)}) is not None or any(
            re.search(r"e-?mail|name", (i.get("name") or "") + " " + (i.get("id") or "") + " " + (i.get("placeholder") or ""), re.I)
            for i in form.find_all("input"))
        if has_message and has_sender:
            has_form = True
            break
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    edge = []
    for tag in soup.find_all(True):
        if tag.name in ("html", "body", "main"):
            continue
        attrs = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
        if tag.name in ("header", "footer", "address") or _EDGE_ATTR_RE.search(attrs):
            t = " ".join(tag.get_text(" ", strip=True).split())
            if t and len(t) <= _EDGE_MAX_CHARS:            # a huge block is page content, not a footer
                edge.append(t)
    return _View(links, " ".join(soup.get_text(" ", strip=True).split()), has_form, " ".join(dict.fromkeys(edge)))


def _view(page: Page) -> _View:
    if page.html:
        return _parse(page.html)
    return _View((), page.text or "", False, page.text or "")      # only cleaned text available


def _path_segments(href: str) -> List[str]:
    path = urlsplit(href).path.lower()
    return [re.sub(r"\.(html?|php|aspx?)$", "", seg) for seg in path.split("/") if seg]


# ---------------------------------------------------------------- Terms of Service

TERMS_PHRASE_RE = re.compile(
    r"\b(terms\s+of\s+(?:service|services|use|sale|sales)|terms\s*(?:&|&amp;|and)\s*conditions?"
    r"|conditions\s+of\s+(?:use|sale)|user\s+agreement|terms\s*&\s*policies)\b", re.I)
TERMS_LINK_TEXT_RE = re.compile(
    r"^(?:our\s+)?(?:terms|tos|t\s*&\s*cs?|terms\s*(?:&|and)\s*policies)$", re.I)
TERMS_SEGMENT_RE = re.compile(
    r"^(?:terms|tos|tandc|t-c|terms[-_](?:of[-_])?(?:service|services|use|sale|sales)"
    r"|terms[-_](?:and[-_])?conditions?|conditions[-_]of[-_](?:use|sale)|user[-_]agreement)$")


def _is_terms_link(text: str, href: str) -> bool:
    if TERMS_PHRASE_RE.search(text) or TERMS_LINK_TEXT_RE.match(text.strip()):
        return True
    return any(TERMS_SEGMENT_RE.match(seg) for seg in _path_segments(href))


def terms_evidence(site: SiteData) -> Optional[str]:
    """Why we think Terms of Service exist (a short description), or None if nothing was found."""
    for page in site.pages:
        v = _view(page)
        for t, h in v.links:
            if _is_terms_link(t, h):
                return f"terms link: '{t[:40]}' -> {h[:80]}"
        m = TERMS_PHRASE_RE.search(v.text)
        if m:
            return f"terms wording in text: '{m.group()}'"
        if any(TERMS_SEGMENT_RE.match(seg) for seg in _path_segments(page.url)):    # the fetched page itself
            return f"fetched page URL: {page.url[:80]}"
    return None


def has_terms(site: SiteData) -> bool:
    return terms_evidence(site) is not None


# ---------------------------------------------------------------- Contact information

_FILE_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js", "woff", "woff2", "ico", "avif"}
_PLACEHOLDER_DOMAINS = {"example.com", "example.org", "domain.com", "yourdomain.com", "email.com", "sentry.io",
                        "wixpress.com", "sentry.wixpress.com", "mysite.com", "test.com"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_AT_RE = re.compile(r"\s*[\[(]\s*at\s*[\])]\s*", re.I)
_DOT_RE = re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.I)
PHONE_NA_RE = re.compile(r"(?<![\d.])(?:\+?1[\s.\-]?)?\(?[2-9]\d{2}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)")
PHONE_INTL_RE = re.compile(r"(?<![\w])\+\d{1,3}[\s.\-]?\(?\d{1,4}\)?(?:[\s.\-]?\d{2,4}){2,4}(?!\d)")
PHONE_LABEL_RE = re.compile(r"(?:phone|tel|telephone|call|mobile|whatsapp)\b[^0-9+]{0,15}(\+?\d[\d\s().\-]{7,16}\d)", re.I)
CONTACT_TEXT_RE = re.compile(r"^(?:contact(?:\s+us)?|get\s+in\s+touch|reach\s+us|contact\s+(?:page|form|info(?:rmation)?))$", re.I)
CONTACT_SEGMENT_RE = re.compile(r"^(?:contact|contact[-_]?us|contactus|get[-_]in[-_]touch|reach[-_]us|contact[-_]info(?:rmation)?)$")
ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z0-9][A-Za-z0-9.'\-]*\s+){1,4}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Highway|Hwy|Trail|Tr)\b\.?")


def _real_email(addr: str) -> bool:
    addr = addr.strip().strip(".,;:)>]").lower()
    m = EMAIL_RE.fullmatch(addr)
    if not m:
        return False
    domain = addr.rsplit("@", 1)[1]
    return domain.rsplit(".", 1)[1] not in _FILE_TLDS and domain not in _PLACEHOLDER_DOMAINS


def _digits(s: str) -> int:
    return sum(c.isdigit() for c in s)


def _text_has_email(text: str) -> bool:
    text = _DOT_RE.sub(".", _AT_RE.sub("@", text))
    return any(_real_email(m.group()) for m in EMAIL_RE.finditer(text))


def _text_has_phone(text: str) -> bool:
    if PHONE_NA_RE.search(text) or PHONE_INTL_RE.search(text):
        return True
    return any(_digits(m.group(1)) >= 9 for m in PHONE_LABEL_RE.finditer(text))


def _is_contact_link(text: str, href: str) -> bool:
    low = href.lower()
    if low.startswith("mailto:"):
        return _real_email(low[7:].split("?")[0])
    if low.startswith("tel:"):
        return _digits(low) >= 7
    if CONTACT_TEXT_RE.match(text.strip()):
        return True
    return any(CONTACT_SEGMENT_RE.match(seg) for seg in _path_segments(href))


def _ctx(text: str, m) -> str:
    """The match with ~40 characters of text on each side, so a person can see where it came from."""
    return "..." + text[max(0, m.start() - 40): m.end() + 40].replace("\n", " ") + "..."


def contact_evidence(site: SiteData) -> Optional[str]:
    """Why we think contact information exists (a short description), or None if nothing was found."""
    for page in site.pages:
        v = _view(page)
        if v.has_contact_form:
            return "contact form"
        for t, h in v.links:
            if _is_contact_link(t, h):
                return f"contact link: '{t[:40]}' -> {h[:80]}"
        # Free-text emails / phones / addresses only count where a business puts its own details (see module docstring):
        # a Contact page, or the header / footer / address / contact blocks. Page content (for example the ads on a
        # marketplace) is ignored.
        own = v.text if page.page_type == "contact" else v.edge_text
        text = _DOT_RE.sub(".", _AT_RE.sub("@", own))
        for m in EMAIL_RE.finditer(text):
            if _real_email(m.group()):
                return f"email in text: {m.group()}  | context: {_ctx(text, m)}"
        m = PHONE_NA_RE.search(own) or PHONE_INTL_RE.search(own)
        if m:
            return f"phone in text: {m.group().strip()}  | context: {_ctx(own, m)}"
        for m in PHONE_LABEL_RE.finditer(own):
            if _digits(m.group(1)) >= 9:
                return f"labelled phone in text: {m.group(0)[:40]}  | context: {_ctx(own, m)}"
        m = ADDRESS_RE.search(own)
        if m:
            return f"address in text: {m.group()[:60]}  | context: {_ctx(own, m)}"
        if any(CONTACT_SEGMENT_RE.match(seg) for seg in _path_segments(page.url)):    # the fetched page itself
            return f"fetched page URL: {page.url[:80]}"
    return None


def has_contact(site: SiteData) -> bool:
    return contact_evidence(site) is not None


REFUND_RE = re.compile(r"\b(refund\w*|returns|return policy|returned items?|money[- ]back|exchange policy)\b", re.I)
DELIVERY_RE = re.compile(r"\b(ship|ships|shipping|shipped|deliver|delivers|delivery|delivered|arrive|arrives)\b", re.I)


def _all_text(site: SiteData) -> str:
    return " ".join((p.text or p.html).lower() for p in site.pages)


def refund_text_found(site: SiteData) -> bool:
    """True if the site mentions refunds / returns anywhere. False means the policy is missing (a certain
    answer, so no LLM is needed for this flag)."""
    return any(p.page_type == "refund" for p in site.pages) or bool(REFUND_RE.search(_all_text(site)))


def delivery_text_found(site: SiteData) -> bool:
    return any(p.page_type == "shipping" for p in site.pages) or bool(DELIVERY_RE.search(_all_text(site)))
