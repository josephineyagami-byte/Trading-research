"""Read-only research requests using the website's existing auth cookie.

Credentials are supplied explicitly via environment, never read from a browser,
included in URLs, printed, or followed across redirects.
"""

import os
from urllib.parse import urlsplit

import requests


class ResearchAPIError(RuntimeError):
    """Access/configuration failures must not masquerade as missing market data."""


def fetch_api(base_url: str, path: str, params: dict | None = None, timeout: float = 60):
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ResearchAPIError("Use a plain HTTP(S) API base URL without credentials, query or fragment")
    if not path.startswith("/") or path.startswith("//") or urlsplit(path).netloc:
        raise ResearchAPIError("Research API paths must be relative to the configured server")
    token = os.environ.get("US_STOCK_AUTH_COOKIE", "").strip()
    if token and (any(c.isspace() or c in ";," for c in token) or len(token) > 8192):
        raise ResearchAPIError("US_STOCK_AUTH_COOKIE must contain only the session cookie value")
    if token and parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ResearchAPIError("Do not send session credentials over public HTTP; use HTTPS or a local tunnel")
    try:
        response = requests.get(
            base_url.rstrip("/") + path,
            params=params,
            cookies={"auth": token} if token else None,
            timeout=timeout,
            allow_redirects=False,
        )
        code = response.status_code
        if code in {401, 403}:
            raise ResearchAPIError(
                f"Research API HTTP {code}: authentication or data access denied. "
                "Provide an authorized US_STOCK_AUTH_COOKIE locally; this is not a zero-flow observation."
            )
        if code == 429:
            raise ResearchAPIError("Research API HTTP 429: rate limited; retry later, not as zero flow")
        if 300 <= code < 400:
            raise ResearchAPIError("Research API redirect refused; configure the final trusted API URL")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, (dict, list)):
            raise ValueError("Unexpected API payload type")
        return payload
    except (requests.RequestException, ValueError):
        # Do not echo exception URLs, response bodies or cookie values.
        print("[WARN] Research API request failed; source data is unavailable")
        return None
