"""EXACT annotation server client.

EXACT: github.com/DeepMicroscopy/Exact
EXACT-Sync: github.com/DeepMicroscopy/EXACT-Sync

Authentication:
  - Personal Access Token (PAT): set via set_token().
    Sent as ``Authorization: Bearer <token>``.
  - Username / password: passed to authenticate(), which uses HTTP Basic Auth
    directly (no token exchange endpoint is needed).

Image upload:
  POST /api/v1/images/images/ with multipart form data.
  File field name: ``file_path``
  Metadata field:  ``image_set`` (integer id)
  Response: ``{"count": N, "results": [...]}`` — the created image is in results[0].

Image sets:
  GET /api/v1/images/image_sets/  (paginated)
"""

from __future__ import annotations
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter


class _StaleConnectionAdapter(HTTPAdapter):
    """Retry once on 'Remote end closed connection without response'.

    Both the Django dev server and nginx close idle keep-alive connections
    after a short timeout.  When requests tries to reuse such a dead socket
    the OS lets the send succeed, but reading the response raises
    RemoteDisconnected (wrapped as ConnectionError by requests).
    One transparent retry is enough: urllib3 always opens a fresh socket on
    retry, so the second attempt succeeds.
    """

    def send(self, request, **kwargs):
        try:
            return super().send(request, **kwargs)
        except requests.exceptions.ConnectionError:
            return super().send(request, **kwargs)


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers["Accept"] = "application/json"
    # Disable persistent connections — avoids stale-socket errors with nginx
    # and Django's dev server without any timing dependency.
    session.headers["Connection"] = "close"
    adapter = _StaleConnectionAdapter()
    session.mount("http://",  adapter)
    session.mount("https://", adapter)
    return session


class ExactClient:
    def __init__(self, base_url: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self._session = _make_session()

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_base_url(self, url: str) -> None:
        self.base_url = url.rstrip("/")

    def set_token(self, token: str) -> None:
        """Configure a Personal Access Token (PAT). Sent as 'Bearer <token>'."""
        self.token = token.strip()
        if self.token:
            self._session.headers["Authorization"] = f"Bearer {self.token}"
        else:
            self._session.headers.pop("Authorization", None)

    # ── Authentication ────────────────────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> None:
        """Configure HTTP Basic Auth (username / password).

        EXACT does not issue session tokens via the API; Basic Auth credentials
        are sent on every request.  Raises on the first failed request.
        """
        self._session.auth = (username, password)
        self._session.headers.pop("Authorization", None)
        self.token = None

    def verify_connection(self) -> dict:
        """Make a lightweight authenticated request to confirm credentials work.

        Returns the first user record visible to the authenticated user.
        Raises requests.HTTPError on auth failure.
        """
        url = f"{self.base_url}/api/v1/users/users/"
        resp = self._session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        return results[0] if results else {}

    # ── Image sets ────────────────────────────────────────────────────────────

    def _fix_url_scheme(self, url: str) -> str:
        """Ensure paginated 'next' URLs use the same scheme as base_url.

        The EXACT server sometimes returns http:// in pagination links even
        when running behind an HTTPS reverse proxy.  nginx drops plain-HTTP
        connections silently, causing RemoteDisconnected on the second page.
        """
        from urllib.parse import urlparse, urlunparse
        base_scheme = urlparse(self.base_url).scheme   # "https"
        parts = urlparse(url)
        if parts.scheme != base_scheme:
            url = urlunparse(parts._replace(scheme=base_scheme))
        return url

    def get_image_sets(self) -> list[dict]:
        """Return all image sets the authenticated user can access."""
        url: str | None = f"{self.base_url}/api/v1/images/image_sets/"
        results: list[dict] = []
        while url:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
                break
            results.extend(data.get("results", []))
            next_url = data.get("next")
            url = self._fix_url_scheme(next_url) if next_url else None
        return results

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload_image(
        self,
        image_set_id: int,
        file_path: str | Path,
        name: str | None = None,
    ) -> dict:
        """Upload *file_path* into *image_set_id*.

        The server converts uploaded files to its internal format (e.g. TIFF).
        Returns the created image record dict (the first entry in results).
        Raises requests.HTTPError on failure.
        """
        fp   = Path(file_path)
        name = name or fp.stem  # name shown in EXACT UI (without extension)
        url  = f"{self.base_url}/api/v1/images/images/"

        with open(fp, "rb") as fh:
            resp = self._session.post(
                url,
                files={"file_path": (fp.name, fh, "application/octet-stream")},
                data={"image_set": image_set_id},
                timeout=300,
            )
        resp.raise_for_status()

        body = resp.json()
        # Response is {"count": N, "results": [...]} — return the created record
        if isinstance(body, dict) and "results" in body:
            results = body["results"]
            return results[0] if results else body
        return body
