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


class ExactClient:
    def __init__(self, base_url: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"

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
            url = data.get("next")  # type: ignore[assignment]
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
