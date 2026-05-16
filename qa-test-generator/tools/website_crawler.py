"""
Website Context Fetcher.

Crawls a hosted website to extract Playwright locators (data-testid, id, name,
aria-label) and API endpoint URLs from inline JavaScript — then returns a
WebsiteContext object with both structured data (for the generator) and a
formatted markdown string (for the planner).
"""

import ipaddress
import re
import requests  # module-level import so missing dep is caught at import time (DESIGN-2)
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse
from rich.console import Console

console = Console()

_MAX_CONTEXT_CHARS = 4_000
_MAX_HTML_BYTES = 2 * 1024 * 1024  # 2 MB cap to prevent OOM on huge pages (M-4)
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 QATestBot/1.0"
)

# API URL extraction patterns — href removed to avoid JS navigation assignment noise (M-3)
_API_PATTERNS = [
    re.compile(r"""fetch\(\s*['"`]([^'"`\s]+)['"`]"""),
    re.compile(r"""axios\.\w+\(\s*['"`]([^'"`\s]+)['"`]"""),
    re.compile(r"""url\s*:\s*['"`]([^'"`\s]+)['"`]"""),
    re.compile(r"""\.open\(\s*['"`]\w+['"`]\s*,\s*['"`]([^'"`\s]+)['"`]"""),
]

# Static asset extensions excluded from API URL extraction (BUG-3)
_STATIC_EXTENSIONS = (
    ".js", ".css", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav",
    ".pdf", ".zip", ".tar", ".gz",
    ".map",
)

_LOCATOR_PRIORITY = ["data-testid", "data-test", "data-cy", "id", "name", "aria-label", "placeholder"]


def _sanitize(s: str) -> str:
    """Strip newlines and control characters from an HTML-extracted string (C-2: prompt injection guard)."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", s).strip()


def _check_safe_url(url: str) -> None:
    """Raise ValueError if url targets a private/loopback address (C-1: SSRF guard)."""
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError(f"website_url has no hostname: '{url}'")
    if host in ("localhost", "localhost.localdomain"):
        raise ValueError(f"website_url must point to a public host, not '{host}'")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            raise ValueError(
                f"website_url points to a non-public IP address '{host}' — "
                "provide a publicly accessible URL"
            )
    except ValueError as exc:
        if any(kw in str(exc) for kw in ("non-public", "public host", "no hostname")):
            raise
        # host is a domain name, not an IP literal — DNS check not performed here


# ------------------------------------------------------------------ #
# Structured result (DESIGN-1 — eliminates markdown round-trip)       #
# ------------------------------------------------------------------ #

@dataclass
class WebsiteContext:
    """
    Structured data extracted from a website crawl.

    Holds both the raw structured data (for direct use by the generator when
    building task-specific prompts) and a pre-formatted markdown string (for
    the planner's tool_context).
    """
    url: str = ""
    title: str = ""
    locators: list[str] = field(default_factory=list)       # CSS/attribute selectors
    api_urls: list[str] = field(default_factory=list)        # API endpoint paths
    form_actions: list[str] = field(default_factory=list)    # form POST/PUT targets
    formatted: str = ""                                       # markdown for planner

    def is_empty(self) -> bool:
        return not (self.locators or self.api_urls or self.form_actions or self.title)


# ------------------------------------------------------------------ #
# Pure helper functions (testable without network)                    #
# ------------------------------------------------------------------ #

def _attrs(tag_snippet: str) -> dict[str, str]:
    """Parse attribute key=value pairs from an HTML tag snippet string."""
    result: dict[str, str] = {}
    for m in re.finditer(r"""(\w[\w-]*)\s*=\s*(?:'([^']*)'|"([^"]*)"|(\S+))""", tag_snippet):
        key = m.group(1).lower()
        val = _sanitize(m.group(2) or m.group(3) or m.group(4) or "")
        result[key] = val
    return result


def _best_locator(attrs: dict[str, str]) -> Optional[str]:
    """Return the best Playwright locator string given an element's attributes."""
    for attr in _LOCATOR_PRIORITY:
        if attrs.get(attr):
            val = attrs[attr]
            # Escape double-quotes so the locator string is always safely single-quoted (EDGE-1)
            val_escaped = val.replace("'", "\\'")
            if attr == "id":
                # CSS ID selector — no quotes needed, but keep special chars safe
                return f"#{val}" if re.match(r"^[a-zA-Z0-9_-]+$", val) else f"[id='{val_escaped}']"
            if attr in ("data-testid", "data-test", "data-cy"):
                return f"[{attr}='{val_escaped}']"
            if attr == "name":
                return f"[name='{val_escaped}']"
            if attr == "aria-label":
                return f"[aria-label='{val_escaped}']"
            if attr == "placeholder":
                return f"[placeholder='{val_escaped}']"
    return None


def _extract_title(html: str) -> str:
    """Extract page <title> text."""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return _sanitize(m.group(1)) if m else ""


def _extract_forms(html: str) -> list[dict]:
    """Extract forms and their fields from HTML."""
    forms = []
    for form_match in re.finditer(
        r"<form([^>]*)>(.*?)</form>", html, re.IGNORECASE | re.DOTALL
    ):
        form_attrs = _attrs(form_match.group(1))
        action = form_attrs.get("action", "")
        method = form_attrs.get("method", "GET").upper()
        # Strip script blocks so embedded JS with </form> strings doesn't end the match early (M-6)
        form_html = re.sub(r"<script[^>]*>.*?</script>", "", form_match.group(2), flags=re.IGNORECASE | re.DOTALL)

        fields = []
        # Use re.DOTALL so multi-line attribute lists are matched (EDGE-2)
        for inp_match in re.finditer(r"<input([^>]*?)/?>\s*", form_html, re.IGNORECASE | re.DOTALL):
            a = _attrs(inp_match.group(1))
            if a.get("type", "").lower() in ("hidden", "submit"):
                continue
            locator = _best_locator(a)
            if locator or a.get("type"):
                fields.append({
                    "locator": locator,
                    "type": a.get("type", "text"),
                    "name": a.get("name", ""),
                })

        for sel_match in re.finditer(r"<select([^>]*?)>", form_html, re.IGNORECASE | re.DOTALL):
            a = _attrs(sel_match.group(1))
            locator = _best_locator(a)
            if locator:
                fields.append({"locator": locator, "type": "select", "name": a.get("name", "")})

        for ta_match in re.finditer(r"<textarea([^>]*?)>", form_html, re.IGNORECASE | re.DOTALL):
            a = _attrs(ta_match.group(1))
            locator = _best_locator(a)
            if locator:
                fields.append({"locator": locator, "type": "textarea", "name": a.get("name", "")})

        forms.append({"action": action, "method": method, "fields": fields})
    return forms


def _extract_inputs(html: str) -> list[dict]:
    """Extract standalone input elements not inside any <form> tag."""
    # Remove complete form blocks
    cleaned = re.sub(r"<form[^>]*>.*?</form>", "", html, flags=re.IGNORECASE | re.DOTALL)
    # Also strip everything after an unclosed <form> tag to end-of-string (BUG-2)
    cleaned = re.sub(r"<form[^>]*>.*", "", cleaned, flags=re.IGNORECASE | re.DOTALL)

    inputs = []
    for m in re.finditer(r"<input([^>]*?)/?>\s*", cleaned, re.IGNORECASE | re.DOTALL):
        a = _attrs(m.group(1))
        if a.get("type", "").lower() in ("hidden", "submit", "button"):
            continue
        locator = _best_locator(a)
        if locator:
            inputs.append({"locator": locator, "type": a.get("type", "text")})
    return inputs


def _extract_buttons(html: str) -> list[dict]:
    """Extract button elements and their labels."""
    buttons = []
    for m in re.finditer(r"<button([^>]*)>(.*?)</button>", html, re.IGNORECASE | re.DOTALL):
        a = _attrs(m.group(1))
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        locator = _best_locator(a)
        if locator or text:
            buttons.append({"locator": locator, "text": text[:80]})

    for m in re.finditer(r"<input([^>]*)>", html, re.IGNORECASE):
        a = _attrs(m.group(1))
        if a.get("type", "").lower() in ("submit", "button"):
            locator = _best_locator(a)
            label = a.get("value", a.get("aria-label", ""))
            if locator or label:
                buttons.append({"locator": locator, "text": label[:80]})

    return buttons


def _extract_nav(html: str) -> list[str]:
    """
    Extract navigation link hrefs from <nav>, <header>, or elements whose
    class contains 'nav', 'navbar', 'navigation', or 'menu'. (DESIGN-3)
    """
    seen: set[str] = set()
    nav_links: list[str] = []

    # Patterns that likely contain navigation
    nav_block_patterns = [
        r"<nav[^>]*>(.*?)</nav>",
        r"<header[^>]*>(.*?)</header>",
        r'<div[^>]*class=["\'][^"\']*\b(?:nav|navbar|navigation|menu)\b[^"\']*["\'][^>]*>(.*?)</div>',
    ]

    for pat in nav_block_patterns:
        for block_m in re.finditer(pat, html, re.IGNORECASE | re.DOTALL):
            for a_m in re.finditer(r"""href\s*=\s*['"]([^'"]+)['"]""", block_m.group(1), re.IGNORECASE):
                href = _sanitize(a_m.group(1))
                if href and not href.startswith(("javascript:", "mailto:", "#")) and href not in seen:
                    seen.add(href)
                    nav_links.append(href)

    return nav_links[:20]


def _extract_api_urls(html: str, page_url: str = "") -> list[str]:
    """
    Extract likely API endpoint URLs from inline <script> blocks.

    Filters out static assets (BUG-3) and third-party absolute URLs (EDGE-3).
    Only same-origin absolute URLs are kept (converted to path-only).
    """
    page_host = urlparse(page_url).netloc if page_url else ""
    urls: list[str] = []
    seen: set[str] = set()

    script_content = " ".join(
        m.group(1)
        for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.IGNORECASE | re.DOTALL)
    )

    for pattern in _API_PATTERNS:
        for m in pattern.finditer(script_content):
            url = _sanitize(m.group(1))
            if not url:
                continue

            # Filter out static assets
            lower = url.lower().split("?")[0]
            if any(lower.endswith(ext) for ext in _STATIC_EXTENSIONS):
                continue

            # Handle absolute URLs — filter third-party, convert same-origin to path
            if url.startswith(("http://", "https://")):
                parsed = urlparse(url)
                if page_host and parsed.netloc != page_host:
                    continue  # third-party — skip (EDGE-3)
                url = parsed.path or url  # keep path only

            if url and url not in seen:
                seen.add(url)
                urls.append(url)

    return urls[:30]


def _build_context(
    url: str,
    title: str,
    forms: list[dict],
    standalone_inputs: list[dict],
    buttons: list[dict],
    nav_links: list[str],
    api_urls: list[str],
) -> str:
    """Assemble the structured context string for the planner."""
    lines = [
        "## WEBSITE CONTEXT",
        f"**URL:** {url}",
    ]
    if title:
        lines.append(f"**Page Title:** {title}")
    lines.append("")

    if forms:
        lines.append("### Forms & Input Fields")
        for i, form in enumerate(forms, 1):
            action = form["action"] or "(no action)"
            lines.append(f"\n**Form {i}** — `{form['method']} {action}`")
            for f in form["fields"]:
                locator = f["locator"] or "(no locator)"
                lines.append(f"  - `{locator}` type={f['type']}" +
                              (f" name={f['name']}" if f["name"] else ""))
        lines.append("")

    if standalone_inputs:
        lines.append("### Standalone Inputs")
        for inp in standalone_inputs:
            lines.append(f"  - `{inp['locator']}` type={inp['type']}")
        lines.append("")

    if buttons:
        lines.append("### Buttons & Actions")
        for btn in buttons:
            loc = btn["locator"] or ""
            text = btn["text"] or ""
            if loc and text:
                lines.append(f"  - `{loc}` → \"{text}\"")
            elif loc:
                lines.append(f"  - `{loc}`")
            elif text:
                lines.append(f"  - button: \"{text}\"")
        lines.append("")

    if nav_links:
        lines.append("### Navigation Links")
        for link in nav_links:
            lines.append(f"  - `{link}`")
        lines.append("")

    if api_urls:
        lines.append("### API Endpoints (from page scripts)")
        for endpoint in api_urls:
            lines.append(f"  - `{endpoint}`")
        lines.append("")

    result = "\n".join(lines)

    # Truncate at the last newline boundary to avoid cutting a locator mid-string (EDGE-4)
    if len(result) > _MAX_CONTEXT_CHARS:
        truncate_at = result.rfind("\n", 0, _MAX_CONTEXT_CHARS)
        if truncate_at == -1:
            truncate_at = _MAX_CONTEXT_CHARS
        result = result[:truncate_at] + "\n... (truncated)"

    return result


# ------------------------------------------------------------------ #
# Public interface                                                     #
# ------------------------------------------------------------------ #

class WebsiteContextFetcher:
    """Fetch and summarise a hosted website for test-generation context."""

    def __init__(self, timeout: int = 15):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})
        self._timeout = timeout

    def fetch(self, url: str) -> WebsiteContext:
        """
        Crawl the given URL and return a WebsiteContext with both structured data
        (for the generator) and a formatted markdown string (for the planner).

        Args:
            url: Fully-qualified URL of the hosted website/app (http:// or https://)

        Returns:
            WebsiteContext with locators, api_urls, form_actions, and formatted string.

        Raises:
            ValueError: If the URL does not start with http:// or https://
            requests.RequestException: If the page cannot be fetched.
        """
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError(
                f"Invalid website URL: '{url}'. Must start with http:// or https://"
            )
        _check_safe_url(url)  # C-1: SSRF guard — blocks loopback/private IPs

        console.print(f"\n[bold cyan]  → Crawling website: {url}[/bold cyan]")

        resp = self._session.get(url, timeout=self._timeout, allow_redirects=True, stream=True)
        resp.raise_for_status()

        # M-5: reject non-HTML responses (JSON, PDF, binary) before reading the body
        content_type = resp.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            resp.close()
            raise ValueError(
                f"Expected text/html response from {url}, got '{content_type}'"
            )

        # M-4: cap at _MAX_HTML_BYTES to prevent OOM on huge pages
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            chunks.append(chunk)
            total += len(chunk)
            if total >= _MAX_HTML_BYTES:
                break
        resp.close()
        html = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
        final_url = resp.url

        title = _extract_title(html)
        forms = _extract_forms(html)
        standalone_inputs = _extract_inputs(html)
        buttons = _extract_buttons(html)
        nav_links = _extract_nav(html)
        api_urls = _extract_api_urls(html, page_url=final_url)

        # Build structured locator list (in priority order: form fields, standalone, buttons)
        seen_locators: set[str] = set()
        locators: list[str] = []
        for form in forms:
            for fld in form["fields"]:
                if fld["locator"] and fld["locator"] not in seen_locators:
                    seen_locators.add(fld["locator"])
                    locators.append(fld["locator"])
        for inp in standalone_inputs:
            if inp["locator"] and inp["locator"] not in seen_locators:
                seen_locators.add(inp["locator"])
                locators.append(inp["locator"])
        for btn in buttons:
            if btn["locator"] and btn["locator"] not in seen_locators:
                seen_locators.add(btn["locator"])
                locators.append(btn["locator"])

        form_actions = [
            form["action"]
            for form in forms
            if form["action"] and form["action"] not in ("(no action)", "")
        ]

        formatted = _build_context(
            url=final_url,
            title=title,
            forms=forms,
            standalone_inputs=standalone_inputs,
            buttons=buttons,
            nav_links=nav_links,
            api_urls=api_urls,
        )

        ctx = WebsiteContext(
            url=final_url,
            title=title,
            locators=locators,
            api_urls=api_urls,
            form_actions=form_actions,
            formatted=formatted,
        )

        console.print(
            f"  [green]✓ Website context ready "
            f"({len(forms)} form(s), {len(buttons)} button(s), "
            f"{len(api_urls)} API URL(s), {len(formatted)} chars)[/green]"
        )
        return ctx
