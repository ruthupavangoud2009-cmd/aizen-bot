"""Automated regression tests for Cloudflare Pages _redirects, route resolution, and redirect loop prevention."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_redirects_no_circular_200_html_rewrites():
    """Verify that _redirects does not contain conflicting /page /page.html 200 rules.
    
    Cloudflare Pages natively handles extensionless URLs (Pretty URLs).
    Adding rules like '/dashboard /dashboard.html 200' creates an infinite 308 redirect
    loop (ERR_TOO_MANY_REDIRECTS) between Cloudflare's extension-stripping engine and the rewrite rule.
    """
    for redirects_file in [REPO_ROOT / "_redirects", REPO_ROOT / "website" / "_redirects"]:
        assert redirects_file.exists(), f"Missing {redirects_file}"
        content = redirects_file.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]

        for line in lines:
            parts = line.split()
            # If it's a rewrite (status 200)
            if len(parts) >= 3 and parts[2] == "200":
                src, dst = parts[0], parts[1]
                assert not (dst == f"{src}.html"), (
                    f"Forbidden circular 200 rewrite found in {redirects_file.name}: '{line}'. "
                    f"This causes Cloudflare Pages ERR_TOO_MANY_REDIRECTS loop."
                )


def test_redirects_has_safe_utility_aliases():
    """Verify that _redirects contains helpful non-looping 302 aliases for /login and /logout."""
    content = (REPO_ROOT / "_redirects").read_text(encoding="utf-8")
    assert "/login /api/auth/login 302" in content
    assert "/logout /api/auth/logout 302" in content


def test_html_navbars_use_clean_canonical_routes():
    """Verify that navbar links in major pages do not link to /dashboard.html (which triggers 308 redirects)."""
    major_pages = ["index.html", "dashboard.html", "tickets.html", "staff.html", "owner.html"]
    for page_name in major_pages:
        html_file = REPO_ROOT / "website" / page_name
        assert html_file.exists()
        content = html_file.read_text(encoding="utf-8")
        
        # Check navbar links specifically
        nav_match = re.search(r'<ul[^>]*class="[^"]*nav-links[^"]*"[^>]*>(.*?)</ul>', content, re.DOTALL)
        if nav_match:
            nav_content = nav_match.group(1)
            assert 'href="/dashboard.html"' not in nav_content, (
                f"Found href='/dashboard.html' in navbar of {page_name}. Should use clean path href='/dashboard'."
            )
            assert 'href="/tickets.html"' not in nav_content, (
                f"Found href='/tickets.html' in navbar of {page_name}. Should use clean path href='/tickets'."
            )


def test_callback_js_redirects_to_clean_dashboard():
    """Verify that edge OAuth callback functions redirect to /dashboard to prevent 308 hops."""
    for cb_file in [
        REPO_ROOT / "functions" / "api" / "auth" / "callback.js",
        REPO_ROOT / "website" / "functions" / "api" / "auth" / "callback.js"
    ]:
        assert cb_file.exists()
        content = cb_file.read_text(encoding="utf-8")
        assert "${destinationOrigin}/dashboard#" in content
        assert "${destinationOrigin}/dashboard?" in content
        assert "${destinationOrigin}/dashboard.html#" not in content


def test_api_js_login_calls_server_endpoint():
    """Verify that loginWithDiscord navigates to /api/auth/login to ensure CSRF cookie generation."""
    api_js = REPO_ROOT / "website" / "js" / "api.js"
    content = api_js.read_text(encoding="utf-8")
    assert "window.location.href = '/api/auth/login';" in content
