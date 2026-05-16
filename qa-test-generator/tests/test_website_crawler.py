"""Unit tests for tools/website_crawler.py — pure functions and mocked fetch."""

import pytest
from unittest.mock import MagicMock, patch
from tools.website_crawler import (
    _attrs,
    _best_locator,
    _sanitize,
    _check_safe_url,
    _extract_title,
    _extract_forms,
    _extract_inputs,
    _extract_buttons,
    _extract_nav,
    _extract_api_urls,
    _build_context,
    WebsiteContext,
    WebsiteContextFetcher,
    _MAX_CONTEXT_CHARS,
)


# ── _attrs ────────────────────────────────────────────────────────────────────

def test_attrs_double_quotes():
    result = _attrs('type="email" id="user-email" name="email"')
    assert result["type"] == "email"
    assert result["id"] == "user-email"
    assert result["name"] == "email"


def test_attrs_single_quotes():
    result = _attrs("data-testid='login-btn' aria-label='Submit'")
    assert result["data-testid"] == "login-btn"
    assert result["aria-label"] == "Submit"


def test_attrs_empty_string():
    assert _attrs("") == {}


def test_attrs_mixed_quotes():
    result = _attrs('id="foo" name=\'bar\'')
    assert result["id"] == "foo"
    assert result["name"] == "bar"


# ── _best_locator ─────────────────────────────────────────────────────────────

def test_best_locator_prefers_data_testid():
    attrs = {"data-testid": "email-input", "id": "email", "name": "email"}
    assert _best_locator(attrs) == "[data-testid='email-input']"


def test_best_locator_falls_back_to_id():
    attrs = {"id": "password", "name": "password"}
    assert _best_locator(attrs) == "#password"


def test_best_locator_falls_back_to_name():
    attrs = {"name": "username", "placeholder": "Enter username"}
    assert _best_locator(attrs) == "[name='username']"


def test_best_locator_falls_back_to_aria_label():
    attrs = {"aria-label": "Search field"}
    assert _best_locator(attrs) == "[aria-label='Search field']"


def test_best_locator_returns_none_when_no_attrs():
    assert _best_locator({}) is None


def test_best_locator_data_cy():
    attrs = {"data-cy": "submit-btn", "id": "btn"}
    assert _best_locator(attrs) == "[data-cy='submit-btn']"


def test_best_locator_data_test():
    attrs = {"data-test": "search-input"}
    assert _best_locator(attrs) == "[data-test='search-input']"


def test_best_locator_falls_back_to_placeholder():
    attrs = {"placeholder": "Enter email"}
    assert _best_locator(attrs) == "[placeholder='Enter email']"


def test_best_locator_escapes_single_quote_in_value():
    attrs = {"aria-label": "Don't click"}
    locator = _best_locator(attrs)
    assert "Don\\'t" in locator or '"' in locator  # quote must be escaped


# ── _extract_title ────────────────────────────────────────────────────────────

def test_extract_title_basic():
    html = "<html><head><title>Login Page</title></head><body></body></html>"
    assert _extract_title(html) == "Login Page"


def test_extract_title_missing():
    assert _extract_title("<html><body></body></html>") == ""


def test_extract_title_case_insensitive():
    html = "<TITLE>Dashboard</TITLE>"
    assert _extract_title(html) == "Dashboard"


# ── _extract_forms ────────────────────────────────────────────────────────────

_LOGIN_FORM_HTML = """
<html><body>
<form action="/api/login" method="post">
  <input type="email" data-testid="email-input" name="email" />
  <input type="password" id="password" name="password" />
  <input type="hidden" name="_csrf" value="tok" />
  <input type="submit" value="Login" />
</form>
</body></html>
"""


def test_extract_forms_finds_one_form():
    forms = _extract_forms(_LOGIN_FORM_HTML)
    assert len(forms) == 1


def test_extract_forms_action_and_method():
    form = _extract_forms(_LOGIN_FORM_HTML)[0]
    assert form["action"] == "/api/login"
    assert form["method"] == "POST"


def test_extract_forms_skips_hidden_and_submit():
    form = _extract_forms(_LOGIN_FORM_HTML)[0]
    field_types = [f["type"] for f in form["fields"]]
    assert "hidden" not in field_types
    assert "submit" not in field_types


def test_extract_forms_email_field_locator():
    form = _extract_forms(_LOGIN_FORM_HTML)[0]
    locators = [f["locator"] for f in form["fields"]]
    assert "[data-testid='email-input']" in locators


def test_extract_forms_password_field_locator():
    form = _extract_forms(_LOGIN_FORM_HTML)[0]
    locators = [f["locator"] for f in form["fields"]]
    assert "#password" in locators


def test_extract_forms_empty_html():
    assert _extract_forms("<html><body></body></html>") == []


# ── _extract_inputs ───────────────────────────────────────────────────────────

_SEARCH_HTML = """
<html><body>
<input type="search" data-testid="search-box" name="q" />
<input type="text" id="filter" />
</body></html>
"""


def test_extract_inputs_finds_standalone():
    inputs = _extract_inputs(_SEARCH_HTML)
    assert len(inputs) >= 1


def test_extract_inputs_correct_locators():
    inputs = _extract_inputs(_SEARCH_HTML)
    locators = [i["locator"] for i in inputs]
    assert "[data-testid='search-box']" in locators


def test_extract_inputs_skips_form_inputs():
    # Inputs inside <form> should NOT appear in standalone list
    inputs = _extract_inputs(_LOGIN_FORM_HTML)
    assert len(inputs) == 0


# ── _extract_buttons ──────────────────────────────────────────────────────────

_BUTTON_HTML = """
<html><body>
<button data-testid="submit-btn">Sign In</button>
<button id="cancel">Cancel</button>
<input type="submit" value="Save" aria-label="Save record" />
</body></html>
"""


def test_extract_buttons_finds_buttons():
    buttons = _extract_buttons(_BUTTON_HTML)
    assert len(buttons) >= 2


def test_extract_buttons_data_testid():
    buttons = _extract_buttons(_BUTTON_HTML)
    locators = [b["locator"] for b in buttons]
    assert "[data-testid='submit-btn']" in locators


def test_extract_buttons_text_content():
    buttons = _extract_buttons(_BUTTON_HTML)
    texts = [b["text"] for b in buttons]
    assert "Sign In" in texts


def test_extract_buttons_input_submit():
    buttons = _extract_buttons(_BUTTON_HTML)
    texts = [b["text"] for b in buttons]
    assert any("Save" in (t or "") for t in texts)


# ── _extract_nav ──────────────────────────────────────────────────────────────

_NAV_HTML = """
<html><body>
<nav>
  <a href="/home">Home</a>
  <a href="/dashboard">Dashboard</a>
  <a href="/settings">Settings</a>
  <a href="javascript:void(0)">Ignored</a>
  <a href="mailto:a@b.com">Ignored</a>
</nav>
</body></html>
"""


def test_extract_nav_finds_links():
    links = _extract_nav(_NAV_HTML)
    assert "/home" in links
    assert "/dashboard" in links
    assert "/settings" in links


def test_extract_nav_excludes_javascript():
    links = _extract_nav(_NAV_HTML)
    assert not any("javascript" in l for l in links)


def test_extract_nav_excludes_mailto():
    links = _extract_nav(_NAV_HTML)
    assert not any("mailto" in l for l in links)


# ── _extract_api_urls ─────────────────────────────────────────────────────────

_SCRIPT_HTML = """
<html><body>
<script>
  fetch('/api/users', { method: 'GET' });
  axios.post('/api/login', { email, password });
  const options = { url: '/api/products' };
  xhr.open('GET', '/api/orders');
</script>
</body></html>
"""


def test_extract_api_urls_fetch():
    urls = _extract_api_urls(_SCRIPT_HTML)
    assert "/api/users" in urls


def test_extract_api_urls_axios():
    urls = _extract_api_urls(_SCRIPT_HTML)
    assert "/api/login" in urls


def test_extract_api_urls_url_variable():
    urls = _extract_api_urls(_SCRIPT_HTML)
    assert "/api/products" in urls


def test_extract_api_urls_xhr_open():
    urls = _extract_api_urls(_SCRIPT_HTML)
    assert "/api/orders" in urls


def test_extract_api_urls_no_scripts():
    assert _extract_api_urls("<html><body></body></html>") == []


# ── _build_context ────────────────────────────────────────────────────────────

def test_build_context_contains_url():
    ctx = _build_context(
        url="https://example.com/login",
        title="Login",
        forms=[],
        standalone_inputs=[],
        buttons=[],
        nav_links=[],
        api_urls=[],
    )
    assert "https://example.com/login" in ctx


def test_build_context_contains_title():
    ctx = _build_context(
        url="https://example.com",
        title="My App",
        forms=[],
        standalone_inputs=[],
        buttons=[],
        nav_links=[],
        api_urls=[],
    )
    assert "My App" in ctx


def test_build_context_lists_api_urls():
    ctx = _build_context(
        url="https://example.com",
        title="",
        forms=[],
        standalone_inputs=[],
        buttons=[],
        nav_links=[],
        api_urls=["/api/login", "/api/users"],
    )
    assert "/api/login" in ctx
    assert "/api/users" in ctx


def test_build_context_truncates_at_max():
    long_api_urls = [f"/api/endpoint-{i}" for i in range(500)]
    ctx = _build_context(
        url="https://example.com",
        title="Big Page",
        forms=[],
        standalone_inputs=[],
        buttons=[],
        nav_links=[],
        api_urls=long_api_urls,
    )
    assert len(ctx) <= _MAX_CONTEXT_CHARS + len("\n... (truncated)")


def test_build_context_includes_form_action():
    forms = [{"action": "/api/auth", "method": "POST", "fields": []}]
    ctx = _build_context(
        url="https://example.com",
        title="",
        forms=forms,
        standalone_inputs=[],
        buttons=[],
        nav_links=[],
        api_urls=[],
    )
    assert "/api/auth" in ctx


def test_build_context_includes_button_locator():
    buttons = [{"locator": "[data-testid='login-btn']", "text": "Login"}]
    ctx = _build_context(
        url="https://example.com",
        title="",
        forms=[],
        standalone_inputs=[],
        buttons=buttons,
        nav_links=[],
        api_urls=[],
    )
    assert "login-btn" in ctx


def test_build_context_truncates_at_last_newline():
    """Truncation must not cut mid-line (EDGE-4)."""
    long_api_urls = [f"/api/endpoint-{i:04d}" for i in range(500)]
    ctx = _build_context(
        url="https://example.com", title="", forms=[], standalone_inputs=[],
        buttons=[], nav_links=[], api_urls=long_api_urls,
    )
    # Truncation marker must appear, and it must follow a newline (m-3 fix)
    assert ctx.endswith("\n... (truncated)")


# ── _extract_inputs — unclosed form (BUG-2) ───────────────────────────────────

def test_extract_inputs_ignores_inputs_in_unclosed_form():
    """Inputs inside an unclosed <form> tag must not appear as standalone inputs."""
    html = """
    <html><body>
    <input type="email" data-testid="standalone" />
    <form action="/login">
      <input type="email" data-testid="form-email" />
    </body></html>
    """
    inputs = _extract_inputs(html)
    locators = [i["locator"] for i in inputs]
    assert "[data-testid='standalone']" in locators
    assert "[data-testid='form-email']" not in locators


# ── _extract_api_urls — static extension filtering (BUG-3) ───────────────────

def test_extract_api_urls_excludes_static_assets():
    html = """<script>
    fetch('/assets/logo.svg');
    fetch('/styles/main.css');
    fetch('/bundle.js');
    fetch('/api/data');
    </script>"""
    urls = _extract_api_urls(html)
    assert "/api/data" in urls
    assert not any(u.endswith((".svg", ".css", ".js")) for u in urls)


def test_extract_api_urls_excludes_third_party():
    """Third-party absolute URLs should be filtered out when page_url is provided (EDGE-3)."""
    html = """<script>
    fetch('https://api.segment.io/v1/track');
    fetch('/api/internal');
    </script>"""
    urls = _extract_api_urls(html, page_url="https://myapp.com/login")
    assert "/api/internal" in urls
    assert not any("segment.io" in u for u in urls)


def test_extract_api_urls_keeps_same_origin_absolute():
    """Same-origin absolute URLs should be kept but converted to path-only."""
    html = """<script>
    fetch('https://myapp.com/api/users');
    </script>"""
    urls = _extract_api_urls(html, page_url="https://myapp.com/")
    assert "/api/users" in urls


# ── _extract_nav — header/navbar class (DESIGN-3) ────────────────────────────

def test_extract_nav_finds_links_in_header():
    html = """
    <html><body>
    <header>
      <a href="/home">Home</a>
      <a href="/about">About</a>
    </header>
    </body></html>
    """
    links = _extract_nav(html)
    assert "/home" in links
    assert "/about" in links


def test_extract_nav_finds_links_in_navbar_div():
    html = """
    <html><body>
    <div class="navbar">
      <a href="/products">Products</a>
    </div>
    </body></html>
    """
    links = _extract_nav(html)
    assert "/products" in links


def test_extract_nav_ignores_links_outside_nav_blocks():
    """Links in plain <div> without nav class should not be returned."""
    html = """
    <html><body>
    <div class="content">
      <a href="/privacy">Privacy</a>
    </div>
    </body></html>
    """
    links = _extract_nav(html)
    assert "/privacy" not in links


# ── WebsiteContextFetcher.fetch() — mocked (MISSING-6) ───────────────────────

_SIMPLE_LOGIN_HTML = """
<!DOCTYPE html>
<html><head><title>Login</title></head>
<body>
<form action="/api/login" method="post">
  <input type="email" data-testid="email" name="email" />
  <input type="password" id="pwd" name="password" />
  <button data-testid="submit-btn">Sign In</button>
</form>
<script>fetch('/api/session');</script>
</body></html>
"""


def _mock_response(
    html: str,
    url: str = "https://example.com/login",
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
):
    resp = MagicMock()
    resp.url = url
    resp.status_code = status
    resp.encoding = "utf-8"
    resp.headers = {"Content-Type": content_type}
    html_bytes = html.encode("utf-8")
    resp.iter_content.return_value = iter([html_bytes])
    resp.raise_for_status = MagicMock()
    if status >= 400:
        import requests
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


def test_fetcher_returns_website_context():
    fetcher = WebsiteContextFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_response(_SIMPLE_LOGIN_HTML)):
        result = fetcher.fetch("https://example.com/login")
    assert isinstance(result, WebsiteContext)


def test_fetcher_extracts_page_url():
    fetcher = WebsiteContextFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_response(_SIMPLE_LOGIN_HTML)):
        result = fetcher.fetch("https://example.com/login")
    assert result.url == "https://example.com/login"


def test_fetcher_extracts_locators():
    fetcher = WebsiteContextFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_response(_SIMPLE_LOGIN_HTML)):
        result = fetcher.fetch("https://example.com/login")
    assert "[data-testid='email']" in result.locators
    assert "#pwd" in result.locators
    assert "[data-testid='submit-btn']" in result.locators


def test_fetcher_extracts_form_actions():
    fetcher = WebsiteContextFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_response(_SIMPLE_LOGIN_HTML)):
        result = fetcher.fetch("https://example.com/login")
    assert "/api/login" in result.form_actions


def test_fetcher_extracts_api_urls():
    fetcher = WebsiteContextFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_response(_SIMPLE_LOGIN_HTML)):
        result = fetcher.fetch("https://example.com/login")
    assert "/api/session" in result.api_urls


def test_fetcher_formatted_is_non_empty():
    fetcher = WebsiteContextFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_response(_SIMPLE_LOGIN_HTML)):
        result = fetcher.fetch("https://example.com/login")
    assert len(result.formatted) > 0
    assert "WEBSITE CONTEXT" in result.formatted


def test_fetcher_raises_value_error_for_invalid_url():
    fetcher = WebsiteContextFetcher()
    with pytest.raises(ValueError, match="http"):
        fetcher.fetch("ftp://example.com")


def test_fetcher_raises_http_error_on_404():
    import requests as req_lib
    fetcher = WebsiteContextFetcher()
    with patch.object(fetcher._session, "get", return_value=_mock_response("", status=404)):
        with pytest.raises(req_lib.HTTPError):
            fetcher.fetch("https://example.com/missing")


def test_fetcher_rejects_non_html_content_type():
    fetcher = WebsiteContextFetcher()
    resp = _mock_response('{"key":"value"}', content_type="application/json")
    with patch.object(fetcher._session, "get", return_value=resp):
        with pytest.raises(ValueError, match="text/html"):
            fetcher.fetch("https://example.com/api/data")


# ── _check_safe_url — SSRF guard (C-1) ────────────────────────────────────────

def test_check_safe_url_allows_public_domain():
    _check_safe_url("https://example.com/login")  # must not raise


def test_check_safe_url_rejects_localhost():
    with pytest.raises(ValueError, match="public host"):
        _check_safe_url("http://localhost/admin")


def test_check_safe_url_rejects_loopback_ip():
    with pytest.raises(ValueError, match="non-public"):
        _check_safe_url("http://127.0.0.1/secret")


def test_check_safe_url_rejects_private_class_a():
    with pytest.raises(ValueError, match="non-public"):
        _check_safe_url("http://10.0.0.1/internal")


def test_check_safe_url_rejects_private_class_c():
    with pytest.raises(ValueError, match="non-public"):
        _check_safe_url("http://192.168.1.1/router")


def test_check_safe_url_rejects_aws_metadata():
    with pytest.raises(ValueError, match="non-public"):
        _check_safe_url("http://169.254.169.254/latest/meta-data/")


def test_fetcher_rejects_localhost_ssrf():
    fetcher = WebsiteContextFetcher()
    with pytest.raises(ValueError, match="public host"):
        fetcher.fetch("http://localhost/admin")


def test_fetcher_rejects_private_ip_ssrf():
    fetcher = WebsiteContextFetcher()
    with pytest.raises(ValueError, match="non-public"):
        fetcher.fetch("http://192.168.1.1/config")


# ── _sanitize — prompt injection guard (C-2) ──────────────────────────────────

def test_sanitize_strips_newlines():
    assert "\n" not in _sanitize("foo\nbar")


def test_sanitize_strips_carriage_return():
    assert "\r" not in _sanitize("foo\rbar")


def test_sanitize_strips_null_byte():
    assert "\x00" not in _sanitize("foo\x00bar")


def test_sanitize_preserves_normal_text():
    assert _sanitize("email-input") == "email-input"


def test_attrs_strips_newlines_from_values():
    # Attribute value containing a newline — must be sanitized
    result = _attrs('data-testid="foo\nbar"')
    assert "\n" not in result.get("data-testid", "")


# ── href pattern removed from _API_PATTERNS (M-3) ────────────────────────────

def test_extract_api_urls_does_not_capture_js_href_assignments():
    """JS `element.href = '/profile'` must NOT be treated as an API endpoint."""
    html = """<script>
    element.href = '/profile';
    location.href = '/logout';
    </script>"""
    urls = _extract_api_urls(html)
    assert "/profile" not in urls
    assert "/logout" not in urls


# ── WebsiteContext.is_empty() (m-4) ──────────────────────────────────────────

def test_is_empty_returns_true_when_all_fields_empty():
    ctx = WebsiteContext()
    assert ctx.is_empty() is True


def test_is_empty_returns_false_when_locators_present():
    ctx = WebsiteContext(locators=["#email"])
    assert ctx.is_empty() is False


def test_is_empty_returns_false_when_api_urls_present():
    ctx = WebsiteContext(api_urls=["/api/login"])
    assert ctx.is_empty() is False


def test_is_empty_returns_false_when_title_present():
    ctx = WebsiteContext(title="Login")
    assert ctx.is_empty() is False


# ── _extract_inputs — standalone input after unclosed form (M-8) ─────────────

def test_extract_inputs_standalone_after_unclosed_form_is_excluded():
    """
    An input AFTER an unclosed <form> is conservatively excluded because we can't
    determine where the form ends. This is intentional behavior, not a bug.
    """
    html = """
    <html><body>
    <form action="/login">
      <input type="email" data-testid="form-email" />
    <!-- form tag never closed -->
    <input type="text" data-testid="standalone-after" />
    </body></html>
    """
    inputs = _extract_inputs(html)
    locators = [i["locator"] for i in inputs]
    # Both inputs are inside (or after) the unclosed form — neither should appear
    assert "[data-testid='standalone-after']" not in locators
    assert "[data-testid='form-email']" not in locators
