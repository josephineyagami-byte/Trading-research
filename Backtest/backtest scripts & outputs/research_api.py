"""Read-only research requests using the website's existing auth cookie.

Credentials are supplied explicitly via environment or a private account file,
never read from a browser, included in URLs, printed, or followed across redirects.
"""

import json
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit

import requests


class ResearchAPIError(RuntimeError):
    """Access/configuration failures must not masquerade as missing market data."""


def _endpoint(base_url: str, path: str, credentialed: bool = False) -> str:
    parsed = urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ResearchAPIError("Use a plain HTTP(S) API base URL without credentials, query or fragment")
    if not path.startswith("/") or path.startswith("//") or urlsplit(path).netloc:
        raise ResearchAPIError("Research API paths must be relative to the configured server")
    if credentialed and parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ResearchAPIError("Do not send session credentials over public HTTP; use HTTPS or a local tunnel")
    return base_url.rstrip("/") + path


def login_from_private_file(base_url: str, credentials_file, username: str | None = None,
                            timeout: float = 20) -> str:
    """Perform normal account login; return the session only in memory.

    Supports one account object or an existing account list with an explicit
    username selector. Never iterate over accounts or retry failed passwords.
    """
    url = _endpoint(base_url, "/api/auth/login", credentialed=True)
    path = Path(credentials_file).expanduser()
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise ResearchAPIError("Credentials must be in a private regular file (chmod 600)")
        with path.open(encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, ValueError):
        raise ResearchAPIError("Cannot read a valid private credentials JSON file") from None
    accounts = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
    selected = [account for account in accounts if isinstance(account, dict)
                and (username is None or account.get("username") == username)]
    if len(selected) != 1:
        raise ResearchAPIError("Choose exactly one existing account with --api-username")
    account = {key: selected[0].get(key) for key in ("username", "password")}
    if any(not isinstance(value, str) or not value for value in account.values()):
        raise ResearchAPIError("Selected account must have nonempty username and password fields")
    try:
        response = requests.post(url, json=account, timeout=timeout, allow_redirects=False)
        if response.status_code != 200:
            raise ResearchAPIError(f"Account login HTTP {response.status_code}; check access locally")
        token = response.cookies.get("auth")
        if not token or response.json().get("username") != account["username"]:
            raise ResearchAPIError("Login did not return the expected account and auth session cookie")
        return token
    except (requests.RequestException, ValueError, AttributeError):
        raise ResearchAPIError("Account login failed; check the secure connection locally") from None


def fetch_api(base_url: str, path: str, params: dict | None = None, timeout: float = 60):
    token = os.environ.get("US_STOCK_AUTH_COOKIE", "").strip()
    if token and (any(c.isspace() or c in ";," for c in token) or len(token) > 8192):
        raise ResearchAPIError("US_STOCK_AUTH_COOKIE must contain only the session cookie value")
    url = _endpoint(base_url, path, credentialed=bool(token))
    try:
        response = requests.get(
            url,
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
