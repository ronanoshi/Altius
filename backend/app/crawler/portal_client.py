"""
Low-level HTTP client for the Altius portal REST API.
All portal knowledge lives here; the crawler is kept agnostic of URL shapes.
"""
from __future__ import annotations

import httpx
from pathlib import Path


class PortalAuthError(Exception):
    pass


class PortalClient:
    def __init__(self, api_base_url: str, timeout: float = 30.0):
        self._api_base = api_base_url.rstrip("/")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, username: str, password: str) -> str:
        """Return a Bearer JWT token."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._api_base}/v0.0.2/login",
                json={"email": username, "password": password},
            )
            r.raise_for_status()
            data = r.json()

        token = (
            data.get("success", {}).get("token")
            or data.get("token")
            or data.get("access_token")
        )
        if not token:
            raise PortalAuthError(f"No token in login response: {data}")
        return token

    # ------------------------------------------------------------------
    # Deals
    # ------------------------------------------------------------------

    async def list_deals(self, token: str) -> list[dict]:
        """Return the list of deals the authenticated user can access."""
        async with httpx.AsyncClient(
            headers=self._auth_headers(token), timeout=self._timeout
        ) as client:
            r = await client.post(
                f"{self._api_base}/v0.0.2/deals-list", json={}
            )
            r.raise_for_status()
        return r.json().get("data", [])

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    async def list_files(self, token: str, deal_id: int) -> list[dict]:
        """Return all files for a deal (across all folders)."""
        async with httpx.AsyncClient(
            headers=self._auth_headers(token), timeout=self._timeout
        ) as client:
            r = await client.get(
                f"{self._api_base}/v0.0.3/deals/{deal_id}/files"
            )
            r.raise_for_status()
        raw = r.json().get("data", {})
        # The API returns a dict keyed by file_id; normalise to a list.
        if isinstance(raw, dict):
            return list(raw.values())
        return raw

    async def download_file(self, url: str, dest: Path) -> None:
        """Stream a pre-signed S3 URL to *dest*."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                with open(dest, "wb") as fh:
                    async for chunk in r.aiter_bytes(chunk_size=65536):
                        fh.write(chunk)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}
